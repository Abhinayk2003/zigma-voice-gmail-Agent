from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database.connection import SessionLocal
from app.database.models import (
    Company,
    Customer,
    Order,
)


class BusinessLookupService:
    """
    Performs deterministic business-data lookups.

    The LLM never directly queries the database.

    The LLM identifies the relevant business identifier.
    Python validates the identifier.
    SQLAlchemy performs the actual database lookup.

    Supported lookups:
        - Company by company_code
        - Company by domain
        - Company by database ID
        - Order by order_id
        - Order by external_reference
        - Order by tracking_number
        - Order by order_id across all active companies
        - Order by external_reference across all active companies
        - Order by tracking_number across all active companies
        - Customer by customer_id
        - Customer by email
        - Customer by email across all active companies

    Dynamic resolution:
        - Order -> Company
        - Order -> Customer
        - Customer -> Company

    No business-specific IDs or company names are hardcoded here.
    """

    # ========================================================
    # COMPANY LOOKUP
    # ========================================================

    def find_company(
        self,
        company_code: str | None = None,
        domain: str | None = None,
    ) -> Company | None:
        """
        Find an active company using an explicit company identifier.

        Either company_code or domain may be supplied.
        """

        if not company_code and not domain:
            return None

        db = SessionLocal()

        try:
            query = select(Company).where(
                Company.active.is_(True)
            )

            if company_code:
                query = query.where(
                    Company.company_code == company_code.strip()
                )

            elif domain:
                query = query.where(
                    Company.domain == domain.strip()
                )

            return db.scalar(query)

        finally:
            db.close()

    # ========================================================
    # COMPANY LOOKUP BY DATABASE ID
    # ========================================================

    def find_company_by_id(
        self,
        company_id: int | None,
    ) -> Company | None:
        """
        Find an active company by its database primary key.

        This is used internally after an order/customer has already
        established the company relationship.
        """

        if company_id is None:
            return None

        db = SessionLocal()

        try:
            return db.scalar(
                select(Company).where(
                    Company.id == company_id,
                    Company.active.is_(True),
                )
            )

        finally:
            db.close()

    # ========================================================
    # ORDER LOOKUP WITH COMPANY ID
    # ========================================================

    def find_order(
        self,
        company_id: int,
        order_id: str,
    ) -> dict[str, Any] | None:
        """
        Find an order when the company is already known.
        """

        if company_id is None or not order_id:
            return None

        db = SessionLocal()

        try:
            order = db.scalar(
                select(Order)
                .options(
                    joinedload(Order.customer),
                    joinedload(Order.items),
                    joinedload(Order.events),
                )
                .where(
                    Order.company_id == company_id,
                    Order.order_id == order_id.strip(),
                )
            )

            if order is None:
                return None

            return self._serialize_order(order)

        finally:
            db.close()

    # ========================================================
    # ORDER LOOKUP ACROSS ALL ACTIVE COMPANIES
    # ========================================================

    def find_orders_by_order_id(
        self,
        order_id: str,
    ) -> list[dict[str, Any]]:
        """
        Find orders by order_id without requiring company_id.

        This is important for dynamic business-agent behavior.

        Example:

            User:
                "What is the status of ORD-10001?"

        The caller does NOT need to know the company beforehand.

        If exactly one matching order exists, the caller can safely
        resolve the company from that order.
        """

        if not order_id:
            return []

        db = SessionLocal()

        try:
            orders = db.scalars(
                select(Order)
                .join(
                    Company,
                    Company.id == Order.company_id,
                )
                .options(
                    joinedload(Order.customer),
                    joinedload(Order.items),
                    joinedload(Order.events),
                )
                .where(
                    Company.active.is_(True),
                    Order.order_id == order_id.strip(),
                )
            ).unique().all()

            return [
                self._serialize_order_with_relationships(order)
                for order in orders
            ]

        finally:
            db.close()

    # ========================================================
    # SINGLE ORDER RESOLUTION BY ORDER ID
    # ========================================================

    def find_order_by_order_id(
        self,
        order_id: str,
    ) -> dict[str, Any] | None:
        """
        Resolve an order by order_id across all active companies.

        Returns the order only when there is exactly one match.

        Returns None when:
            - no order exists
            - multiple companies have the same order_id

        This prevents the system from guessing when an identifier
        is ambiguous.
        """

        matches = self.find_orders_by_order_id(order_id)

        if len(matches) != 1:
            return None

        return matches[0]

    # ========================================================
    # ORDER LOOKUP BY EXTERNAL REFERENCE
    # ========================================================

    def find_order_by_external_reference(
        self,
        company_id: int,
        external_reference: str,
    ) -> dict[str, Any] | None:
        """
        Find an order when company_id is already known.
        """

        if company_id is None or not external_reference:
            return None

        db = SessionLocal()

        try:
            order = db.scalar(
                select(Order)
                .options(
                    joinedload(Order.customer),
                    joinedload(Order.items),
                    joinedload(Order.events),
                )
                .where(
                    Order.company_id == company_id,
                    Order.external_reference
                    == external_reference.strip(),
                )
            )

            if order is None:
                return None

            return self._serialize_order(order)

        finally:
            db.close()

    # ========================================================
    # EXTERNAL REFERENCE ACROSS ALL ACTIVE COMPANIES
    # ========================================================

    def find_orders_by_external_reference(
        self,
        external_reference: str,
    ) -> list[dict[str, Any]]:
        """
        Find orders by external reference without requiring company_id.
        """

        if not external_reference:
            return []

        db = SessionLocal()

        try:
            orders = db.scalars(
                select(Order)
                .join(
                    Company,
                    Company.id == Order.company_id,
                )
                .options(
                    joinedload(Order.customer),
                    joinedload(Order.items),
                    joinedload(Order.events),
                )
                .where(
                    Company.active.is_(True),
                    Order.external_reference
                    == external_reference.strip(),
                )
            ).unique().all()

            return [
                self._serialize_order_with_relationships(order)
                for order in orders
            ]

        finally:
            db.close()

    # ========================================================
    # SINGLE ORDER BY EXTERNAL REFERENCE
    # ========================================================

    def find_unique_order_by_external_reference(
        self,
        external_reference: str,
    ) -> dict[str, Any] | None:
        """
        Return an order only when the external reference uniquely
        identifies one active order.
        """

        matches = self.find_orders_by_external_reference(
            external_reference
        )

        if len(matches) != 1:
            return None

        return matches[0]

    # ========================================================
    # ORDER LOOKUP BY TRACKING NUMBER
    # ========================================================

    def find_order_by_tracking_number(
        self,
        company_id: int,
        tracking_number: str,
    ) -> dict[str, Any] | None:
        """
        Find an order when company_id is already known.
        """

        if company_id is None or not tracking_number:
            return None

        db = SessionLocal()

        try:
            order = db.scalar(
                select(Order)
                .options(
                    joinedload(Order.customer),
                    joinedload(Order.items),
                    joinedload(Order.events),
                )
                .where(
                    Order.company_id == company_id,
                    Order.tracking_number
                    == tracking_number.strip(),
                )
            )

            if order is None:
                return None

            return self._serialize_order(order)

        finally:
            db.close()

    # ========================================================
    # TRACKING NUMBER ACROSS ALL ACTIVE COMPANIES
    # ========================================================

    def find_orders_by_tracking_number(
        self,
        tracking_number: str,
    ) -> list[dict[str, Any]]:
        """
        Find orders by tracking number without requiring company_id.
        """

        if not tracking_number:
            return []

        db = SessionLocal()

        try:
            orders = db.scalars(
                select(Order)
                .join(
                    Company,
                    Company.id == Order.company_id,
                )
                .options(
                    joinedload(Order.customer),
                    joinedload(Order.items),
                    joinedload(Order.events),
                )
                .where(
                    Company.active.is_(True),
                    Order.tracking_number
                    == tracking_number.strip(),
                )
            ).unique().all()

            return [
                self._serialize_order_with_relationships(order)
                for order in orders
            ]

        finally:
            db.close()

    # ========================================================
    # SINGLE ORDER BY TRACKING NUMBER
    # ========================================================

    def find_unique_order_by_tracking_number(
        self,
        tracking_number: str,
    ) -> dict[str, Any] | None:
        """
        Return an order only when the tracking number uniquely
        identifies one active order.
        """

        matches = self.find_orders_by_tracking_number(
            tracking_number
        )

        if len(matches) != 1:
            return None

        return matches[0]

    # ========================================================
    # CUSTOMER LOOKUP BY CUSTOMER ID
    # ========================================================

    def find_customer(
        self,
        company_id: int,
        customer_id: str,
    ) -> dict[str, Any] | None:
        """
        Find a customer when company_id is already known.
        """

        if company_id is None or not customer_id:
            return None

        db = SessionLocal()

        try:
            customer = db.scalar(
                select(Customer).where(
                    Customer.company_id == company_id,
                    Customer.customer_id
                    == customer_id.strip(),
                )
            )

            if customer is None:
                return None

            return self._serialize_customer(customer)

        finally:
            db.close()

    # ========================================================
    # CUSTOMER LOOKUP BY EMAIL
    # ========================================================

    def find_customer_by_email(
        self,
        company_id: int,
        email: str,
    ) -> dict[str, Any] | None:
        """
        Find a customer when company_id is already known.
        """

        if company_id is None or not email:
            return None

        db = SessionLocal()

        try:
            customer = db.scalar(
                select(Customer).where(
                    Customer.company_id == company_id,
                    Customer.email.ilike(
                        email.strip()
                    ),
                )
            )

            if customer is None:
                return None

            return self._serialize_customer(customer)

        finally:
            db.close()

    # ========================================================
    # CUSTOMER LOOKUP BY EMAIL ACROSS ALL COMPANIES
    # ========================================================

    def find_customers_by_email(
        self,
        email: str,
    ) -> list[dict[str, Any]]:
        """
        Find customers by email across all active companies.

        The company is obtained from the Customer.company_id
        relationship rather than inferred from the email domain.
        """

        if not email:
            return []

        db = SessionLocal()

        try:
            customers = db.scalars(
                select(Customer)
                .join(
                    Company,
                    Company.id == Customer.company_id,
                )
                .where(
                    Company.active.is_(True),
                    Customer.email.ilike(
                        email.strip()
                    ),
                )
            ).all()

            return [
                self._serialize_customer_with_company(
                    customer
                )
                for customer in customers
            ]

        finally:
            db.close()

    # ========================================================
    # SINGLE CUSTOMER RESOLUTION BY EMAIL
    # ========================================================

    def find_unique_customer_by_email(
        self,
        email: str,
    ) -> dict[str, Any] | None:
        """
        Return a customer only when the email uniquely identifies
        one active customer.
        """

        matches = self.find_customers_by_email(email)

        if len(matches) != 1:
            return None

        return matches[0]

    # ========================================================
    # CUSTOMER LOOKUP ACROSS ALL COMPANIES
    # ========================================================

    def find_customers_by_customer_id(
        self,
        customer_id: str,
    ) -> list[dict[str, Any]]:
        """
        Find customers by customer_id across all active companies.
        """

        if not customer_id:
            return []

        db = SessionLocal()

        try:
            customers = db.scalars(
                select(Customer)
                .join(
                    Company,
                    Company.id == Customer.company_id,
                )
                .where(
                    Company.active.is_(True),
                    Customer.customer_id
                    == customer_id.strip(),
                )
            ).all()

            return [
                self._serialize_customer_with_company(
                    customer
                )
                for customer in customers
            ]

        finally:
            db.close()

    # ========================================================
    # SINGLE CUSTOMER RESOLUTION BY CUSTOMER ID
    # ========================================================

    def find_unique_customer_by_customer_id(
        self,
        customer_id: str,
    ) -> dict[str, Any] | None:
        """
        Return a customer only when the customer_id uniquely
        identifies one active customer.
        """

        matches = self.find_customers_by_customer_id(
            customer_id
        )

        if len(matches) != 1:
            return None

        return matches[0]

    # ========================================================
    # RESOLVE COMPANY FROM ORDER
    # ========================================================

    def resolve_company_from_order(
        self,
        order: dict[str, Any] | None,
    ) -> Company | None:
        """
        Resolve the company using the company_id attached to
        an already verified order.

        No company name or order ID is hardcoded.
        """

        if not order:
            return None

        company_id = order.get("company_id")

        if company_id is None:
            return None

        return self.find_company_by_id(company_id)

    # ========================================================
    # RESOLVE CUSTOMER FROM ORDER
    # ========================================================

    def resolve_customer_from_order(
        self,
        order: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """
        Return the customer already attached to an order.
        """

        if not order:
            return None

        return order.get("customer")

    # ========================================================
    # RESOLVE COMPANY FROM CUSTOMER
    # ========================================================

    def resolve_company_from_customer(
        self,
        customer: dict[str, Any] | None,
    ) -> Company | None:
        """
        Resolve company using customer.company_id.
        """

        if not customer:
            return None

        company_id = customer.get("company_id")

        if company_id is None:
            return None

        return self.find_company_by_id(company_id)

    # ========================================================
    # SERIALIZE CUSTOMER
    # ========================================================

    @staticmethod
    def _serialize_customer(
        customer: Customer,
    ) -> dict[str, Any]:
        """
        Serialize customer without exposing SQLAlchemy objects.
        """

        return {
            "customer_id": customer.customer_id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "status": customer.status,
        }

    # ========================================================
    # SERIALIZE CUSTOMER WITH COMPANY CONTEXT
    # ========================================================

    @staticmethod
    def _serialize_customer_with_company(
        customer: Customer,
    ) -> dict[str, Any]:
        """
        Serialize customer together with the company relationship
        required for dynamic company resolution.
        """

        return {
            "customer_id": customer.customer_id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "status": customer.status,
            "company_id": customer.company_id,
        }

    # ========================================================
    # SERIALIZE ORDER
    # ========================================================

    @staticmethod
    def _serialize_order(
        order: Order,
    ) -> dict[str, Any]:
        """
        Serialize an order using the existing business fields.
        """

        return {
            "order_id": order.order_id,

            "external_reference": (
                order.external_reference
            ),

            "status": order.status,

            "payment_status": (
                order.payment_status
            ),

            "fulfillment_status": (
                order.fulfillment_status
            ),

            "currency": order.currency,

            "total_amount": (
                float(order.total_amount)
                if order.total_amount is not None
                else None
            ),

            "tracking_number": (
                order.tracking_number
            ),

            "estimated_delivery": (
                order.estimated_delivery.isoformat()
                if order.estimated_delivery
                else None
            ),

            "delivered_at": (
                order.delivered_at.isoformat()
                if order.delivered_at
                else None
            ),

            "cancellation_eligible": (
                order.cancellation_eligible
            ),

            "refund_eligible": (
                order.refund_eligible
            ),

            "return_eligible": (
                order.return_eligible
            ),

            "customer": (
                {
                    "customer_id": (
                        order.customer.customer_id
                    ),
                    "name": (
                        order.customer.name
                    ),
                    "email": (
                        order.customer.email
                    ),
                }
                if order.customer
                else None
            ),

            "items": [
                {
                    "product_id": (
                        item.product_id
                    ),
                    "product_name": (
                        item.product_name
                    ),
                    "quantity": item.quantity,
                    "unit_price": (
                        float(item.unit_price)
                        if item.unit_price is not None
                        else None
                    ),
                }
                for item in order.items
            ],

            "events": [
                {
                    "event_type": (
                        event.event_type
                    ),
                    "description": (
                        event.description
                    ),
                    "event_at": (
                        event.event_at.isoformat()
                        if event.event_at
                        else None
                    ),
                }
                for event in order.events
            ],
        }

    # ========================================================
    # SERIALIZE ORDER WITH RELATIONSHIP CONTEXT
    # ========================================================

    @staticmethod
    def _serialize_order_with_relationships(
        order: Order,
    ) -> dict[str, Any]:
        """
        Serialize an order and retain the database relationship
        information needed by the business agent.

        company_id is intentionally included here because the
        business agent needs it to resolve the company dynamically.
        """

        result = BusinessLookupService._serialize_order(order)

        result["company_id"] = order.company_id

        if order.customer:
            result["customer"] = {
                "customer_id": order.customer.customer_id,
                "name": order.customer.name,
                "email": order.customer.email,
                "company_id": order.customer.company_id,
            }

        return result


# ============================================================
# GLOBAL SERVICE INSTANCE
# ============================================================

business_lookup_service = BusinessLookupService()