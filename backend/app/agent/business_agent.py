from __future__ import annotations

import json
import logging
from email.utils import parseaddr
from typing import Any

from app.agent.bedrock import BedrockService
from app.knowledge.service import knowledge_base_service
from app.services.business_lookup_service import (
    business_lookup_service,
)

logger = logging.getLogger(__name__)


class BusinessAgent:
    """
    Dynamic business/customer-support agent.

    Responsibilities:
    - Extract business identifiers using Nova Pro.
    - Understand what information the customer wants.
    - Resolve company dynamically using verified DB relationships.
    - Resolve orders/customers/tracking records dynamically.
    - Never treat the sender's email domain as the company domain.
    - Use the Knowledge Base for business knowledge/policy context.
    - Use the database as the source of truth for customer/order data.
    """

    def __init__(
        self,
        bedrock: BedrockService,
    ) -> None:
        self.bedrock = bedrock

    # ========================================================
    # PROCESS EMAIL
    # ========================================================

    def process_email(
        self,
        email: dict[str, Any],
    ) -> dict[str, Any]:

        subject = (
            email.get("subject")
            or ""
        )

        body = (
            email.get("body")
            or ""
        )

        sender = (
            email.get("from")
            or email.get("sender")
            or ""
        )

        email_text = f"""
Subject:
{subject}

From:
{sender}

Email:
{body}
""".strip()

        # ----------------------------------------------------
        # STEP 1
        # Extract business identifiers using Nova Pro.
        # ----------------------------------------------------

        extracted = self._extract_identifiers(
            email_text=email_text,
        )

        # The sender's email domain must NOT automatically
        # become the company domain.

        extracted = self._remove_sender_domain_as_company(
            extracted=extracted,
            sender=sender,
        )

        logger.info(
            "Extracted business information: %s",
            extracted,
        )

        # ----------------------------------------------------
        # STEP 2
        # Retrieve Knowledge Base information.
        #
        # KB is useful for policies/terminology.
        # It is NOT authoritative for company ownership.
        # ----------------------------------------------------

        try:
            kb_result = knowledge_base_service.retrieve(
                query=email_text,
            )
        except Exception:
            logger.warning(
                "Knowledge Base retrieval failed.",
                exc_info=True,
            )
            kb_result = {}

        # ----------------------------------------------------
        # STEP 3
        # Determine what business information is required.
        # ----------------------------------------------------

        business_plan = self._determine_business_plan(
            email_text=email_text,
            extracted=extracted,
            kb_result=kb_result,
        )

        logger.info(
            "Business plan: %s",
            business_plan,
        )

        identifier_type = self._normalize_identifier_type(
            business_plan.get("identifier_type"),
        )

        requested_information = (
            business_plan.get("requested_information")
            or []
        )

        # ----------------------------------------------------
        # STEP 4
        # If Nova Pro did not determine the identifier type,
        # infer it only when exactly one business identifier
        # was explicitly extracted.
        # ----------------------------------------------------

        if not identifier_type:
            identifier_type = (
                self._infer_identifier_from_extracted(
                    extracted,
                )
            )

        logger.info(
            "Business identifier type: %s",
            identifier_type,
        )

        # ----------------------------------------------------
        # STEP 5
        # Get identifier value.
        # ----------------------------------------------------

        identifier_value = self._get_identifier_value(
            extracted=extracted,
            identifier_type=identifier_type,
        )

        logger.info(
            "Business identifier value present: %s",
            bool(identifier_value),
        )

        # ----------------------------------------------------
        # STEP 6
        # Resolve company + record dynamically.
        #
        # Priority:
        #
        # 1. Explicit company code/domain
        # 2. Order ID -> order -> company
        # 3. Tracking number -> order -> company
        # 4. Customer ID -> customer -> company
        # 5. Sender email -> customer -> company
        #
        # We never use the sender's domain as company identity.
        # ----------------------------------------------------

        company, record = self._resolve_company_and_record(
            sender=sender,
            extracted=extracted,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
        )

        logger.info(
            "Dynamic company resolution completed. "
            "Company=%s Record=%s",
            self._company_identifier(company),
            bool(record),
        )

        # ----------------------------------------------------
        # STEP 7
        # Company could not be identified.
        # ----------------------------------------------------

        if company is None:

            if self._has_ambiguous_business_reference(
                identifier_type=identifier_type,
                identifier_value=identifier_value,
            ):
                reply = (
                    self._generate_ambiguous_reference_reply(
                        email_text=email_text,
                        identifier_type=identifier_type,
                        identifier_value=identifier_value,
                        requested_information=requested_information,
                        kb_result=kb_result,
                    )
                )

                return {
                    "success": True,
                    "action": "clarification",
                    "reason": "ambiguous_business_reference",
                    "reply": reply,
                    "database_match": False,
                    "identifier_type": identifier_type,
                    "identifier_value": identifier_value,
                    "requested_information": requested_information,
                    "identifiers": extracted,
                    "knowledge_base": kb_result,
                }

            reply = self._generate_company_clarification(
                email_text=email_text,
                kb_result=kb_result,
            )

            return {
                "success": True,
                "action": "clarification",
                "reason": "company_not_identified",
                "reply": reply,
                "database_match": False,
                "identifier_type": identifier_type,
                "identifier_value": identifier_value,
                "requested_information": requested_information,
                "identifiers": extracted,
                "knowledge_base": kb_result,
            }

        # ----------------------------------------------------
        # STEP 8
        # Company is known but identifier is missing.
        #
        # Exception:
        # If customer/account information can be resolved
        # directly from sender email, use that customer.
        # ----------------------------------------------------

        if not identifier_value:

            if identifier_type == "customer_id":

                sender_customer = (
                    self._find_customer_from_sender(
                        sender,
                    )
                )

                if sender_customer:

                    record = sender_customer

            if record is None:

                reply = self._generate_missing_identifier_reply(
                    email_text=email_text,
                    identifier_type=identifier_type,
                    requested_information=requested_information,
                    kb_result=kb_result,
                )

                return {
                    "success": True,
                    "action": "clarification",
                    "reason": "missing_business_identifier",
                    "reply": reply,
                    "database_match": False,
                    "company": self._company_identifier(company),
                    "identifier_type": identifier_type,
                    "requested_information": requested_information,
                    "identifiers": extracted,
                    "knowledge_base": kb_result,
                }

        # ----------------------------------------------------
        # STEP 9
        # If company is known but record was not found during
        # cross-company resolution, perform company-scoped
        # lookup.
        # ----------------------------------------------------

        if record is None and identifier_value:

            record = self._lookup_business_record(
                company_id=self._company_id(company),
                identifier_type=identifier_type,
                identifier_value=identifier_value,
                extracted=extracted,
            )

        logger.info(
            "Business database lookup completed. Match=%s",
            bool(record),
        )

        # ----------------------------------------------------
        # STEP 10
        # No matching business record.
        # ----------------------------------------------------

        if record is None:

            reply = self._generate_no_match_reply(
                email_text=email_text,
                identifier_type=identifier_type,
                identifier_value=identifier_value or "",
                requested_information=requested_information,
                kb_result=kb_result,
            )

            return {
                "success": True,
                "action": "clarification",
                "reason": "database_record_not_found",
                "reply": reply,
                "database_match": False,
                "company": self._company_identifier(company),
                "identifier_type": identifier_type,
                "identifier_value": identifier_value,
                "requested_information": requested_information,
                "knowledge_base": kb_result,
            }

        # ----------------------------------------------------
        # STEP 11
        # Verified database record found.
        # ----------------------------------------------------

        reply = self._generate_answer_from_record(
            email_text=email_text,
            record=record,
            requested_information=requested_information,
            kb_result=kb_result,
        )

        return {
            "success": True,
            "action": "reply",
            "reason": "database_match",
            "reply": reply,
            "database_match": True,
            "company": self._company_identifier(company),
            "identifier_type": identifier_type,
            "identifier_value": identifier_value,
            "requested_information": requested_information,
            "record": record,
            "knowledge_base": kb_result,
        }

    # ========================================================
    # DYNAMIC COMPANY + RECORD RESOLUTION
    # ========================================================

    def _resolve_company_and_record(
        self,
        sender: str,
        extracted: dict[str, Any],
        identifier_type: str | None,
        identifier_value: str | None,
    ) -> tuple[Any | None, dict[str, Any] | None]:

        # ----------------------------------------------------
        # 1. Explicit company code/domain.
        #
        # These are only used when explicitly extracted from
        # the email and successfully validated against DB.
        # ----------------------------------------------------

        company_code = self._clean_value(
            extracted.get("company_code"),
        )

        company_domain = self._clean_value(
            extracted.get("company_domain"),
        )

        if company_code or company_domain:

            try:
                company = business_lookup_service.find_company(
                    company_code=company_code,
                    domain=company_domain,
                )

                if company:
                    logger.info(
                        "Company resolved from explicit "
                        "company information.",
                    )

                    if identifier_value:

                        record = self._lookup_business_record(
                            company_id=self._company_id(company),
                            identifier_type=identifier_type,
                            identifier_value=identifier_value,
                            extracted=extracted,
                        )

                        if record:
                            return company, record

                    return company, None

            except Exception:
                logger.warning(
                    "Explicit company lookup failed.",
                    exc_info=True,
                )

        # ----------------------------------------------------
        # 2. ORDER ID
        #
        # Search across active companies.
        # ----------------------------------------------------

        if (
            identifier_type == "order_id"
            and identifier_value
        ):

            try:
                orders = (
                    business_lookup_service
                    .find_orders_by_order_id(
                        identifier_value,
                    )
                )

                # Unique order = safe company resolution.
                if len(orders) == 1:

                    order = orders[0]

                    company = (
                        self._resolve_company_from_record(
                            order,
                        )
                    )

                    if company:
                        logger.info(
                            "Company resolved dynamically "
                            "from order_id=%s.",
                            identifier_value,
                        )
                        return company, order

                # Multiple companies may theoretically have
                # the same order ID.
                #
                # Use sender's customer relationship to
                # disambiguate.
                if len(orders) > 1:

                    sender_customer = (
                        self._find_customer_from_sender(
                            sender,
                        )
                    )

                    if sender_customer:

                        customer_company_id = (
                            sender_customer.get(
                                "company_id",
                            )
                        )

                        matching_orders = [
                            order
                            for order in orders
                            if str(
                                order.get("company_id")
                            )
                            == str(customer_company_id)
                        ]

                        if len(matching_orders) == 1:

                            order = matching_orders[0]

                            company = (
                                self._resolve_company_from_record(
                                    order,
                                )
                            )

                            if company:
                                return company, order

                        if len(matching_orders) > 1:
                            logger.warning(
                                "Multiple matching orders "
                                "remain after customer "
                                "disambiguation.",
                            )

                    return None, None

            except Exception:
                logger.warning(
                    "Cross-company order lookup failed.",
                    exc_info=True,
                )

        # ----------------------------------------------------
        # 3. CUSTOMER ID
        # ----------------------------------------------------

        if (
            identifier_type == "customer_id"
            and identifier_value
        ):

            try:
                customers = (
                    business_lookup_service
                    .find_customers_by_customer_id(
                        identifier_value,
                    )
                )

                if len(customers) == 1:

                    customer = customers[0]

                    company = (
                        self._resolve_company_from_record(
                            customer,
                        )
                    )

                    if company:
                        return company, customer

                if len(customers) > 1:

                    sender_customer = (
                        self._find_customer_from_sender(
                            sender,
                        )
                    )

                    if sender_customer:

                        sender_company_id = (
                            sender_customer.get(
                                "company_id",
                            )
                        )

                        matching_customers = [
                            customer
                            for customer in customers
                            if str(
                                customer.get("company_id")
                            )
                            == str(sender_company_id)
                        ]

                        if len(matching_customers) == 1:

                            customer = matching_customers[0]

                            company = (
                                self._resolve_company_from_record(
                                    customer,
                                )
                            )

                            if company:
                                return company, customer

                    return None, None

            except Exception:
                logger.warning(
                    "Cross-company customer lookup failed.",
                    exc_info=True,
                )

        # ----------------------------------------------------
        # 4. TRACKING NUMBER
        # ----------------------------------------------------

        if (
            identifier_type == "tracking_number"
            and identifier_value
        ):

            try:
                orders = (
                    business_lookup_service
                    .find_orders_by_tracking_number(
                        identifier_value,
                    )
                )

                if len(orders) == 1:

                    order = orders[0]

                    company = (
                        self._resolve_company_from_record(
                            order,
                        )
                    )

                    if company:
                        return company, order

                if len(orders) > 1:

                    sender_customer = (
                        self._find_customer_from_sender(
                            sender,
                        )
                    )

                    if sender_customer:

                        sender_company_id = (
                            sender_customer.get(
                                "company_id",
                            )
                        )

                        matching_orders = [
                            order
                            for order in orders
                            if str(
                                order.get("company_id")
                            )
                            == str(sender_company_id)
                        ]

                        if len(matching_orders) == 1:

                            order = matching_orders[0]

                            company = (
                                self._resolve_company_from_record(
                                    order,
                                )
                            )

                            if company:
                                return company, order

                    return None, None

            except Exception:
                logger.warning(
                    "Cross-company tracking lookup failed.",
                    exc_info=True,
                )

        # ----------------------------------------------------
        # 5. Sender email -> customer -> company.
        #
        # IMPORTANT:
        # This uses the full customer email address.
        #
        # It does NOT use:
        #
        #     example.com
        #
        # as a company identity.
        # ----------------------------------------------------

        customer = self._find_customer_from_sender(
            sender,
        )

        if customer:

            company = (
                self._resolve_company_from_record(
                    customer,
                )
            )

            if company:

                logger.info(
                    "Company resolved dynamically from "
                    "customer email.",
                )

                # If an identifier exists, try the
                # company-scoped lookup now.
                if identifier_value:

                    record = self._lookup_business_record(
                        company_id=self._company_id(company),
                        identifier_type=identifier_type,
                        identifier_value=identifier_value,
                        extracted=extracted,
                    )

                    if record:
                        return company, record

                return company, None

        # ----------------------------------------------------
        # No reliable company relationship was found.
        #
        # Do NOT fall back to a random/sole company.
        # Do NOT infer company from KB sample content.
        # ----------------------------------------------------

        return None, None

    # ========================================================
    # CUSTOMER FROM SENDER
    # ========================================================

    def _find_customer_from_sender(
        self,
        sender: str,
    ) -> dict[str, Any] | None:

        email_address = self._extract_email_address(
            sender,
        )

        if not email_address:
            return None

        try:
            customer = (
                business_lookup_service
                .find_unique_customer_by_email(
                    email_address,
                )
            )

            if customer:
                logger.info(
                    "Customer resolved from sender email.",
                )

                return customer

        except Exception:
            logger.warning(
                "Customer lookup from sender email failed.",
                exc_info=True,
            )

        return None

    # ========================================================
    # EMAIL ADDRESS EXTRACTION
    # ========================================================

    @staticmethod
    def _extract_email_address(
        sender: str,
    ) -> str | None:

        if not sender:
            return None

        try:
            _, address = parseaddr(sender)

            address = (
                address
                or ""
            ).strip().lower()

            if "@" in address:
                return address

        except Exception:
            logger.warning(
                "Unable to parse sender email.",
                exc_info=True,
            )

        # Simple fallback.
        value = sender.strip()

        if (
            "@" in value
            and "<" not in value
            and ">" not in value
        ):
            return value.strip(
                " <>\"'"
            ).lower()

        return None

    # ========================================================
    # RECORD -> COMPANY
    # ========================================================

    @staticmethod
    def _resolve_company_from_record(
        record: dict[str, Any] | None,
    ) -> Any | None:

        if not isinstance(
            record,
            dict,
        ):
            return None

        company_id = record.get(
            "company_id",
        )

        if company_id is None:
            return None

        try:
            return (
                business_lookup_service
                .find_company_by_id(
                    company_id,
                )
            )

        except Exception:
            logger.warning(
                "Unable to resolve company from "
                "company_id=%s.",
                company_id,
                exc_info=True,
            )

            return None

    # ========================================================
    # COMPANY HELPERS
    # ========================================================

    @staticmethod
    def _company_id(
        company: Any,
    ) -> Any:

        if company is None:
            return None

        if isinstance(
            company,
            dict,
        ):
            return company.get(
                "id",
            )

        return getattr(
            company,
            "id",
            None,
        )

    @staticmethod
    def _company_identifier(
        company: Any,
    ) -> str | None:

        if company is None:
            return None

        if isinstance(
            company,
            dict,
        ):
            return (
                company.get("company_code")
                or company.get("company_name")
            )

        return (
            getattr(
                company,
                "company_code",
                None,
            )
            or getattr(
                company,
                "company_name",
                None,
            )
        )

    # ========================================================
    # AMBIGUITY CHECK
    # ========================================================

    def _has_ambiguous_business_reference(
        self,
        identifier_type: str | None,
        identifier_value: str | None,
    ) -> bool:

        if (
            not identifier_type
            or not identifier_value
        ):
            return False

        try:

            if identifier_type == "order_id":

                matches = (
                    business_lookup_service
                    .find_orders_by_order_id(
                        identifier_value,
                    )
                )

                return len(matches) > 1

            if identifier_type == "tracking_number":

                matches = (
                    business_lookup_service
                    .find_orders_by_tracking_number(
                        identifier_value,
                    )
                )

                return len(matches) > 1

            if identifier_type == "customer_id":

                matches = (
                    business_lookup_service
                    .find_customers_by_customer_id(
                        identifier_value,
                    )
                )

                return len(matches) > 1

        except Exception:
            logger.warning(
                "Unable to check business-reference "
                "ambiguity.",
                exc_info=True,
            )

        return False

    # ========================================================
    # BEDROCK TEXT INVOCATION
    # ========================================================

    def _invoke_bedrock(
        self,
        prompt: str,
    ) -> str:

        return self.bedrock.invoke(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": prompt,
                        }
                    ],
                }
            ],
        )

    # ========================================================
    # IDENTIFIER EXTRACTION
    # ========================================================

    def _extract_identifiers(
        self,
        email_text: str,
    ) -> dict[str, Any]:

        prompt = f"""
You are a business customer-support information
extraction agent.

Read the customer email and extract only business
identifiers explicitly present in the email.

Return ONLY a JSON object.

Allowed fields:

company_code
company_domain
order_id
customer_id
invoice_id
ticket_id
tracking_number

Rules:

1. If a value is not present, return null.
2. Never invent a value.
3. Never infer an identifier that is not supported by
   the email.
4. Preserve identifiers exactly as written when possible.
5. Do not confuse an order ID with a customer ID.
6. Do not confuse a tracking number with an order ID.
7. Do not put an email address into order_id.
8. company_domain must ONLY contain a company domain when
   the company domain is explicitly mentioned as a
   company/business domain in the email.
9. The sender's email domain is NOT automatically a
   company domain.
10. If the sender is rahul@example.com, do NOT return
    example.com as company_domain unless the email
    explicitly identifies example.com as the company domain.
11. Return all allowed fields.

Example:

{{
    "company_code": null,
    "company_domain": null,
    "order_id": null,
    "customer_id": null,
    "invoice_id": null,
    "ticket_id": null,
    "tracking_number": null
}}

CUSTOMER EMAIL:
{email_text}
"""

        try:

            parsed = self.bedrock.invoke_json(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": prompt,
                            }
                        ],
                    }
                ],
                temperature=0.0,
            )

            if not isinstance(
                parsed,
                dict,
            ):
                raise ValueError(
                    "Bedrock identifier response must "
                    "be a JSON object."
                )

            return self._normalize_extracted_identifiers(
                parsed,
            )

        except Exception:
            logger.warning(
                "Unable to parse business identifier extraction.",
                exc_info=True,
            )

            return {}

    # ========================================================
    # REMOVE SENDER DOMAIN FROM COMPANY DOMAIN
    # ========================================================

    @staticmethod
    def _remove_sender_domain_as_company(
        extracted: dict[str, Any],
        sender: str,
    ) -> dict[str, Any]:

        result = dict(
            extracted,
        )

        company_domain = (
            BusinessAgent._clean_value(
                result.get("company_domain"),
            )
        )

        sender_email = (
            BusinessAgent._extract_email_address(
                sender,
            )
        )

        if (
            company_domain
            and sender_email
            and "@" in sender_email
        ):

            sender_domain = (
                sender_email
                .split("@", 1)[1]
                .strip()
                .lower()
            )

            normalized_company_domain = (
                company_domain
                .strip()
                .lower()
            )

            if normalized_company_domain == sender_domain:

                logger.info(
                    "Ignoring sender email domain as "
                    "company_domain: %s",
                    company_domain,
                )

                result["company_domain"] = None

        return result

    # ========================================================
    # BUSINESS PLAN
    # ========================================================

    def _determine_business_plan(
        self,
        email_text: str,
        extracted: dict[str, Any],
        kb_result: dict[str, Any],
    ) -> dict[str, Any]:

        prompt = f"""
You are the business-support reasoning agent.

Determine what business information the customer is
asking for and what identifier should be used to retrieve
the corresponding verified business record.

Return ONLY valid JSON.

Allowed identifier_type values:

order_id
customer_id
invoice_id
ticket_id
tracking_number
none

Determine:

1. identifier_type
2. requested_information
3. customer_intent
4. confidence

requested_information must be an array of short
descriptions of the information the customer wants.

Examples:

order status
payment status
tracking number
estimated delivery
delivery status
order total
shipping address
customer details
invoice information
ticket status
return eligibility
refund eligibility
cancellation eligibility
product details

Rules:

* Do not invent identifiers.
* Do not invent database records.
* Do not invent customer information.
* Use the extracted identifiers as evidence.
* Use the Knowledge Base for applicable business
  terminology or policy.
* If the customer is clearly asking about a specific
  order and an order ID is available, use order_id.
* If the customer is asking about customer/account
  information without referring to an order, use
  customer_id when appropriate.
* If the customer provides a tracking number and asks
  about shipment status, use tracking_number.
* If the customer refers to an invoice, use invoice_id.
* If the customer refers to a support ticket, use ticket_id.
* Do not default to order_id simply because another
  identifier is unavailable.
* If there is not enough information, use "none".

EXTRACTED IDENTIFIERS:
{json.dumps(
    extracted,
    indent=2,
    default=str,
)}

KNOWLEDGE BASE:
{self._kb_text(kb_result)}

CUSTOMER EMAIL:
{email_text}

Return exactly:

{{
    "identifier_type": "...",
    "requested_information": [],
    "customer_intent": "...",
    "confidence": 0.0
}}
"""

        try:

            parsed = self.bedrock.invoke_json(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": prompt,
                            }
                        ],
                    }
                ],
                temperature=0.0,
            )

            if isinstance(
                parsed,
                dict,
            ):
                return self._normalize_business_plan(
                    parsed,
                )

        except Exception:
            logger.warning(
                "Unable to parse business plan.",
                exc_info=True,
            )

        return {
            "identifier_type": None,
            "requested_information": [],
            "customer_intent": "",
            "confidence": 0.0,
        }

    # ========================================================
    # EXPLICIT IDENTIFIER INFERENCE
    # ========================================================

    @staticmethod
    def _infer_identifier_from_extracted(
        extracted: dict[str, Any],
    ) -> str | None:

        candidates = []

        for field_name in (
            "order_id",
            "customer_id",
            "invoice_id",
            "ticket_id",
            "tracking_number",
        ):

            value = extracted.get(
                field_name,
            )

            if value:
                candidates.append(
                    field_name,
                )

        if len(candidates) == 1:
            return candidates[0]

        return None

    # ========================================================
    # IDENTIFIER NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_identifier_type(
        value: Any,
    ) -> str | None:

        if not isinstance(
            value,
            str,
        ):
            return None

        value = (
            value
            .strip()
            .lower()
        )

        allowed = {
            "order_id",
            "customer_id",
            "invoice_id",
            "ticket_id",
            "tracking_number",
        }

        if value in allowed:
            return value

        aliases = {
            "order": "order_id",
            "order number": "order_id",
            "order id": "order_id",
            "customer": "customer_id",
            "customer number": "customer_id",
            "customer id": "customer_id",
            "account": "customer_id",
            "account id": "customer_id",
            "invoice": "invoice_id",
            "invoice number": "invoice_id",
            "invoice id": "invoice_id",
            "ticket": "ticket_id",
            "ticket number": "ticket_id",
            "ticket id": "ticket_id",
            "tracking": "tracking_number",
            "tracking number": "tracking_number",
            "tracking id": "tracking_number",
        }

        if value in aliases:
            return aliases[value]

        return None

    # ========================================================
    # GET IDENTIFIER VALUE
    # ========================================================

    @staticmethod
    def _get_identifier_value(
        extracted: dict[str, Any],
        identifier_type: str | None,
    ) -> str | None:

        if not identifier_type:
            return None

        value = extracted.get(
            identifier_type,
        )

        return BusinessAgent._clean_value(
            value,
        )

    # ========================================================
    # DATABASE LOOKUP
    # ========================================================

    def _lookup_business_record(
        self,
        company_id: Any,
        identifier_type: str | None,
        identifier_value: str,
        extracted: dict[str, Any],
    ) -> dict[str, Any] | None:

        if not identifier_type:
            return None

        # ----------------------------------------------------
        # ORDER
        # ----------------------------------------------------

        if identifier_type == "order_id":

            return (
                business_lookup_service.find_order(
                    company_id=company_id,
                    order_id=identifier_value,
                )
            )

        # ----------------------------------------------------
        # CUSTOMER
        # ----------------------------------------------------

        if identifier_type == "customer_id":

            lookup = getattr(
                business_lookup_service,
                "find_customer",
                None,
            )

            if callable(lookup):

                try:
                    return lookup(
                        company_id=company_id,
                        customer_id=identifier_value,
                    )

                except TypeError:
                    pass

            if "@" in identifier_value:

                return (
                    business_lookup_service
                    .find_customer_by_email(
                        company_id=company_id,
                        email=identifier_value,
                    )
                )

            return None

        # ----------------------------------------------------
        # TRACKING
        # ----------------------------------------------------

        if identifier_type == "tracking_number":

            lookup = getattr(
                business_lookup_service,
                "find_order_by_tracking_number",
                None,
            )

            if callable(lookup):

                return lookup(
                    company_id=company_id,
                    tracking_number=identifier_value,
                )

            return None

        # ----------------------------------------------------
        # INVOICE
        # ----------------------------------------------------

        if identifier_type == "invoice_id":

            lookup = getattr(
                business_lookup_service,
                "find_invoice",
                None,
            )

            if callable(lookup):

                return lookup(
                    company_id=company_id,
                    invoice_id=identifier_value,
                )

            return None

        # ----------------------------------------------------
        # TICKET
        # ----------------------------------------------------

        if identifier_type == "ticket_id":

            lookup = getattr(
                business_lookup_service,
                "find_ticket",
                None,
            )

            if callable(lookup):

                return lookup(
                    company_id=company_id,
                    ticket_id=identifier_value,
                )

            return None

        return None

    # ========================================================
    # COMPANY CLARIFICATION
    # ========================================================

    def _generate_company_clarification(
        self,
        email_text: str,
        kb_result: dict[str, Any],
    ) -> str:

        prompt = f"""
You are a professional customer-support email agent.

The customer's company or account could not be identified
reliably.

Customer email:
{email_text}

Knowledge Base:
{self._kb_text(kb_result)}

Ask the customer for the minimum information needed to
identify their account or business record.

Useful information may include an order number, customer
reference, invoice number, ticket number, tracking number,
or another reference mentioned in the company documentation.

Do not invent a specific identifier format.

Do not mention databases, internal systems, AI, or
implementation details.

Return only the email body.
"""

        return self._clean_reply(
            self._invoke_bedrock(
                prompt,
            )
        )

    # ========================================================
    # MISSING IDENTIFIER
    # ========================================================

    def _generate_missing_identifier_reply(
        self,
        email_text: str,
        identifier_type: str | None,
        requested_information: list[Any],
        kb_result: dict[str, Any],
    ) -> str:

        identifier_description = (
            self._human_identifier_name(
                identifier_type,
            )
            if identifier_type
            else (
                "order, customer, invoice, ticket, "
                "or other relevant reference"
            )
        )

        prompt = f"""
You are a professional customer-support email agent.

The customer contacted the company but did not provide
the business reference required to locate the requested
information.

Required reference:
{identifier_description}

Customer requested information:
{json.dumps(
    requested_information,
    ensure_ascii=False,
    default=str,
)}

Knowledge Base:
{self._kb_text(kb_result)}

Customer email:
{email_text}

Write a short, polite email asking the customer for the
required reference.

Rules:

* Do not invent a reference number.
* Do not invent company policy.
* Do not reveal database implementation details.
* Do not claim that a record exists.
* Ask only for information that is actually needed.
* Keep the response professional and concise.

Return only the email body.
"""

        return self._clean_reply(
            self._invoke_bedrock(
                prompt,
            )
        )

    # ========================================================
    # AMBIGUOUS REFERENCE
    # ========================================================

    def _generate_ambiguous_reference_reply(
        self,
        email_text: str,
        identifier_type: str | None,
        identifier_value: str,
        requested_information: list[Any],
        kb_result: dict[str, Any],
    ) -> str:

        identifier_description = (
            self._human_identifier_name(
                identifier_type,
            )
            if identifier_type
            else "business reference"
        )

        prompt = f"""
You are a professional customer-support email agent.

The customer provided this business reference:

{identifier_description}: {identifier_value}

That reference alone is not sufficient to uniquely
identify the customer's account.

Customer requested information:
{json.dumps(
    requested_information,
    ensure_ascii=False,
    default=str,
)}

Knowledge Base:
{self._kb_text(kb_result)}

Customer email:
{email_text}

Ask politely for one additional piece of information
that can identify the correct account or order.

Possible examples include the customer's registered
email, customer reference, company reference, or another
business reference.

Do not invent a specific value or format.

Do not mention databases, internal systems, or AI.

Return only the email body.
"""

        return self._clean_reply(
            self._invoke_bedrock(
                prompt,
            )
        )

    # ========================================================
    # NO MATCH
    # ========================================================

    def _generate_no_match_reply(
        self,
        email_text: str,
        identifier_type: str | None,
        identifier_value: str,
        requested_information: list[Any],
        kb_result: dict[str, Any],
    ) -> str:

        identifier_description = (
            self._human_identifier_name(
                identifier_type,
            )
            if identifier_type
            else "reference"
        )

        prompt = f"""
You are a professional customer-support email agent.

The customer provided this reference:

{identifier_description}: {identifier_value}

A matching business record could not be located.

Customer requested information:
{json.dumps(
    requested_information,
    ensure_ascii=False,
    default=str,
)}

Knowledge Base:
{self._kb_text(kb_result)}

Customer email:
{email_text}

Politely ask the customer to verify the reference or
provide the correct reference.

Rules:

* Do not reveal database implementation details.
* Do not claim that the customer's order or account does
  not exist.
* Do not invent an order status.
* Do not invent company policy.
* Keep the response professional and concise.

Return only the email body.
"""

        return self._clean_reply(
            self._invoke_bedrock(
                prompt,
            )
        )

    # ========================================================
    # DATABASE MATCH
    # ========================================================

    def _generate_answer_from_record(
        self,
        email_text: str,
        record: dict[str, Any],
        requested_information: list[Any],
        kb_result: dict[str, Any],
    ) -> str:

        prompt = f"""
You are a professional customer-support email agent.

Answer the customer's email using ONLY:

1. The customer's email.
2. The verified business record.
3. The retrieved Knowledge Base content.

VERIFIED BUSINESS RECORD:
{json.dumps(
    record,
    indent=2,
    ensure_ascii=False,
    default=str,
)}

CUSTOMER REQUESTED INFORMATION:
{json.dumps(
    requested_information,
    indent=2,
    ensure_ascii=False,
    default=str,
)}

KNOWLEDGE BASE:
{self._kb_text(kb_result)}

CUSTOMER EMAIL:
{email_text}

Rules:

* Never invent information.
* Never guess missing values.
* Never expose internal database details.
* Do not mention that you queried a database.
* Follow applicable company policy from the Knowledge Base.
* Use the verified business record for factual business data.
* If a requested value is not present in the verified
  record, say that the information is unavailable.
* Do not change dates, amounts, statuses, identifiers,
  tracking numbers, or other business values.
* Keep the response professional and concise.
* Answer the customer's actual question.
* Do not provide unrelated information unless it helps
  answer the customer's request.

Return only the email body.
"""

        return self._clean_reply(
            self._invoke_bedrock(
                prompt,
            )
        )

    # ========================================================
    # BUSINESS PLAN NORMALIZATION
    # ========================================================

    def _normalize_business_plan(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:

        identifier_type = (
            self._normalize_identifier_type(
                data.get("identifier_type"),
            )
        )

        requested_information = data.get(
            "requested_information",
        )

        if not isinstance(
            requested_information,
            list,
        ):
            requested_information = []

        requested_information = [
            str(item).strip()
            for item in requested_information
            if item is not None
            and str(item).strip()
        ]

        customer_intent = (
            self._clean_value(
                data.get("customer_intent"),
            )
            or ""
        )

        confidence = self._normalize_confidence(
            data.get("confidence"),
        )

        return {
            "identifier_type": identifier_type,
            "requested_information": requested_information,
            "customer_intent": customer_intent,
            "confidence": confidence,
        }

    # ========================================================
    # EXTRACTED IDENTIFIER NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_extracted_identifiers(
        data: dict[str, Any],
    ) -> dict[str, Any]:

        allowed_fields = (
            "company_code",
            "company_domain",
            "order_id",
            "customer_id",
            "invoice_id",
            "ticket_id",
            "tracking_number",
        )

        result = {}

        for field_name in allowed_fields:

            result[field_name] = (
                BusinessAgent._clean_value(
                    data.get(field_name),
                )
            )

        return result

    # ========================================================
    # CLEAN VALUE
    # ========================================================

    @staticmethod
    def _clean_value(
        value: Any,
    ) -> str | None:

        if value is None:
            return None

        if isinstance(
            value,
            str,
        ):

            value = value.strip()

            return value or None

        value = str(value).strip()

        return value or None

    # ========================================================
    # CONFIDENCE
    # ========================================================

    @staticmethod
    def _normalize_confidence(
        value: Any,
    ) -> float:

        try:
            confidence = float(value)

        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        return max(
            0.0,
            min(
                1.0,
                confidence,
            ),
        )

    # ========================================================
    # HUMAN IDENTIFIER NAME
    # ========================================================

    @staticmethod
    def _human_identifier_name(
        identifier_type: str | None,
    ) -> str:

        names = {
            "order_id": "order number",
            "customer_id": "customer reference",
            "invoice_id": "invoice number",
            "ticket_id": "ticket number",
            "tracking_number": "tracking number",
        }

        return names.get(
            identifier_type,
            "business reference",
        )

    # ========================================================
    # CLEAN MODEL RESPONSE
    # ========================================================

    @staticmethod
    def _clean_reply(
        response: Any,
    ) -> str:

        if response is None:
            return ""

        if isinstance(
            response,
            dict,
        ):

            value = response.get(
                "text",
            )

            if value is not None:
                response = value

        text = str(
            response,
        ).strip()

        # Remove accidental Markdown code fences.
        if text.startswith("```"):

            lines = text.splitlines()

            if lines:
                lines = lines[1:]

            if (
                lines
                and lines[-1].strip() == "```"
            ):
                lines = lines[:-1]

            text = "\n".join(
                lines,
            ).strip()

        return text

    # ========================================================
    # KB TEXT
    # ========================================================

    @staticmethod
    def _kb_text(
        kb_result: dict[str, Any],
    ) -> str:

        if not isinstance(
            kb_result,
            dict,
        ):
            return ""

        results = kb_result.get(
            "results",
            [],
        )

        if not isinstance(
            results,
            list,
        ):
            return ""

        chunks = []

        for result in results:

            if not isinstance(
                result,
                dict,
            ):
                continue

            text = result.get(
                "text",
                "",
            )

            if text:
                chunks.append(
                    str(text),
                )

        return "\n\n".join(
            chunks,
        )


# ============================================================
# GLOBAL BUSINESS AGENT
# ============================================================

business_agent = BusinessAgent(
    bedrock=BedrockService(),
)