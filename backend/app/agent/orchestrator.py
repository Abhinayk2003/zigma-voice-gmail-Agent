from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from app.agent.bedrock import bedrock_service
from app.agent.executor import gmail_executor
from app.agent.intent import (
    GmailIntent,
    GmailIntentRequest,
    MessageReference,
    MessageReferenceType,
    parse_bedrock_intent,
)
from app.agent.state import (
    ConversationState,
    conversation_state,
)

from app.database.connection import SessionLocal
from app.services.database_service import DatabaseService
from app.services.conversation_service import ConversationService


class GmailOrchestrator:
    """
    Main orchestration layer for the Zigma Voice Gmail Agent.

    Architecture:

        User request
             |
             v
        Persistent Conversation
             |
             v
        Amazon Bedrock
             |
             v
        Structured Gmail Intent
             |
             v
        Dynamic Context Resolution
             |
             v
        Dynamic SEND Completion
             |
             v
        Gmail Executor
             |
             v
        Gmail API
             |
             v
        Actual Gmail Result
             |
             v
        Amazon Bedrock
             |
             v
        Natural-language response
             |
             v
        Persistent Conversation
             |
             v
        PostgreSQL

    Design principles:

        1. Bedrock understands natural language.
        2. Bedrock produces structured intent only.
        3. Python performs deterministic application logic.
        4. GmailExecutor performs Gmail operations.
        5. Gmail IDs come only from Gmail.
        6. Gmail thread IDs come only from Gmail.
        7. Authenticated account identity comes from authentication.
        8. ConversationState stores active Gmail context.
        9. PostgreSQL stores durable conversation history.
        10. PostgreSQL stores pending destructive confirmations.
        11. Relative dates are resolved dynamically in Python.
        12. SEND completion is generated dynamically.
        13. Destructive operations require confirmation.
        14. Final responses are generated from actual Gmail results.
        15. No user-specific Gmail data is hard-coded.
        16. Natural conversational references are resolved dynamically.
    """

    def __init__(
        self,
        state: ConversationState | None = None,
    ) -> None:

        self.state = (
            state
            if state is not None
            else conversation_state
        )

        self.executor = gmail_executor

    # =========================================================
    # PUBLIC PROCESS
    # =========================================================

    def process(
        self,
        user_text: str,
        account_email: str | None = None,
    ) -> dict[str, Any]:

        if not user_text or not user_text.strip():
            raise ValueError(
                "User message cannot be empty."
            )

        text = user_text.strip()

        # -----------------------------------------------------
        # Store authenticated account in live state.
        # -----------------------------------------------------

        if account_email:

            self.state.set_account(
                account_email
            )

        account = (
            account_email
            or self.state.account_email
        )

        if not account:

            raise ValueError(
                "Authenticated Gmail account is required."
            )

        # -----------------------------------------------------
        # PostgreSQL conversation.
        # -----------------------------------------------------

        db = SessionLocal()

        try:

            user = (
                DatabaseService.get_or_create_user(
                    db=db,
                    email=account,
                )
            )

            gmail_account = (
                DatabaseService.get_or_create_gmail_account(
                    db=db,
                    user=user,
                    email=account,
                )
            )

            conversation = (
                ConversationService.get_or_create_conversation(
                    db=db,
                    user=user,
                    gmail_account=gmail_account,
                )
            )

            # -------------------------------------------------
            # IMPORTANT:
            #
            # Restore pending destructive action from
            # PostgreSQL into live ConversationState.
            #
            # This allows:
            #
            # Process 1:
            #   Delete the first email
            #
            # Process 2:
            #   yes
            #
            # to work correctly.
            # -------------------------------------------------

            self._restore_pending_action(
                db=db,
                conversation=conversation,
                account_email=account,
            )

            # -------------------------------------------------
            # Persist current user message.
            # -------------------------------------------------

            ConversationService.save_user_message(
                db=db,
                conversation=conversation,
                content=text,
                intent=None,
            )

            # -------------------------------------------------
            # Central response finalizer.
            # -------------------------------------------------

            def finalize_response(
                response: dict[str, Any],
            ) -> dict[str, Any]:

                intent_value = response.get(
                    "intent"
                )

                if not intent_value:

                    intent_value = (
                        GmailIntent.UNKNOWN.value
                    )

                user_message = response.get(
                    "user_message"
                )

                if user_message is None:

                    user_message = ""

                # ---------------------------------------------
                # Persist assistant response.
                # ---------------------------------------------

                ConversationService.save_assistant_message(
                    db=db,
                    conversation=conversation,
                    content=str(user_message),
                    intent=str(intent_value),
                )

                # ---------------------------------------------
                # Determine action status.
                # ---------------------------------------------

                if response.get(
                    "cancelled"
                ):

                    action_status = "cancelled"

                elif response.get(
                    "success"
                ) is False:

                    action_status = "failed"

                elif (
                    isinstance(
                        response.get("result"),
                        dict,
                    )
                    and response.get(
                        "result",
                        {},
                    ).get(
                        "confirmation_required"
                    )
                ):

                    action_status = (
                        "pending_confirmation"
                    )

                else:

                    action_status = "success"

                # ---------------------------------------------
                # Persist action.
                # ---------------------------------------------

                action_details = {
                    "user_text": text,
                    "intent": intent_value,
                    "account_email": account,
                    "success": response.get(
                        "success"
                    ),
                    "result": response.get(
                        "result"
                    ),
                    "error": response.get(
                        "error"
                    ),
                }

                ConversationService.save_action(
                    db=db,
                    conversation=conversation,
                    action_type=str(
                        intent_value
                    ),
                    status=action_status,
                    details=json.dumps(
                        action_details,
                        ensure_ascii=False,
                        default=str,
                    ),
                )

                return response

            # =================================================
            # PENDING DESTRUCTIVE CONFIRMATION
            # =================================================

            if self.state.has_pending_action():

                confirmation_result = (
                    self._handle_pending_confirmation(
                        text=text,
                        account_email=account,
                        db=db,
                        conversation=conversation,
                    )
                )

                if confirmation_result is not None:
                    return finalize_response(
                        confirmation_result
                    )
            # =================================================
            # ACTIVE PERSISTENT WORKFLOW
            # =================================================

            workflow_response = (
                self._handle_active_workflow(
                    db=db,
                    conversation=conversation,
                    user_text=text,
                )
            )

            if workflow_response is not None:
                return finalize_response(
                    workflow_response
                )

            

                

            # =================================================
            # STORE CURRENT USER REQUEST
            # =================================================

            self.state.current_query = text

            # =================================================
            # BEDROCK INTENT UNDERSTANDING
            # =================================================

            try:

                intent_data = self._understand(
                    text
                )

                intent_request = (
                    parse_bedrock_intent(
                        intent_data,
                        raw_text=text,
                    )
                )
                print("\nDEBUG AFTER PARSE")
                print("INTENT DATA:", intent_data)
                print("PARSED REQUEST:", intent_request)
                print("PARSED REFERENCE:", intent_request.message_reference)
                print(
                    "PARSED REFERENCE TYPE:",
                    intent_request.message_reference.type,
                )
                print(
                    "PARSED REFERENCE POSITION:",
                    intent_request.message_reference.position,
                )

            except ValueError as exc:

                return finalize_response(
                    self._unknown_response(
                        text=text,
                        reason=str(exc),
                    )
                )

            except RuntimeError as exc:

                return finalize_response(
                    {
                        "success": False,
                        "intent": (
                            GmailIntent.UNKNOWN.value
                        ),
                        "error": str(exc),
                        "user_message": (
                            "I couldn't understand the request."
                        ),
                        "state": self.state.to_dict(),
                    }
                )

            # =================================================
            # DYNAMIC CONVERSATION CONTEXT RESOLUTION
            # =================================================

            intent_request = (
                self._resolve_conversation_context(
                    request=intent_request,
                    user_text=text,
                )
            )

            # =================================================
            # UNKNOWN INTENT
            # =================================================

            if (
                intent_request.intent
                == GmailIntent.UNKNOWN
            ):

                return finalize_response(
                    self._unknown_response(
                        text=text,
                        reason=(
                            "Unable to determine the Gmail action."
                        ),
                    )
                )

            # =================================================
            # DYNAMIC SEND COMPLETION
            # =================================================

            if (
                intent_request.intent
                == GmailIntent.SEND
            ):

                try:

                    intent_request = (
                        self._complete_send_request(
                            request=intent_request,
                            user_text=text,
                        )
                    )

                except RuntimeError as exc:

                    return finalize_response(
                        {
                            "success": False,
                            "intent": (
                                GmailIntent.SEND.value
                            ),
                            "error": str(exc),
                            "user_message": (
                                "I couldn't prepare the email."
                            ),
                            "state": self.state.to_dict(),
                        }
                    )

            # =================================================
            # EXECUTE GMAIL OPERATION
            # =================================================

            try:

                result = self.executor.execute(
                    request=intent_request,
                    account_email=account,
                )

            except ValueError as exc:

                return finalize_response(
                    {
                        "success": False,
                        "intent": (
                            intent_request.intent.value
                        ),
                        "error": str(exc),
                        "user_message": (
                            self._generate_error_response(
                                user_text=text,
                                intent=(
                                    intent_request.intent.value
                                ),
                                error=str(exc),
                            )
                        ),
                        "state": self.state.to_dict(),
                    }
                )

            except RuntimeError as exc:

                return finalize_response(
                    {
                        "success": False,
                        "intent": (
                            intent_request.intent.value
                        ),
                        "error": str(exc),
                        "user_message": (
                            self._generate_error_response(
                                user_text=text,
                                intent=(
                                    intent_request.intent.value
                                ),
                                error=str(exc),
                            )
                        ),
                        "state": self.state.to_dict(),
                    }
                )

            # =================================================
            # RECORD LIVE ORCHESTRATION STATE
            # =================================================

            self.state.record_action(
                action="orchestrate",
                details={
                    "user_text": text,
                    "intent": (
                        intent_request.intent.value
                    ),
                    "confidence": (
                        intent_request.confidence
                    ),
                },
            )

            # =================================================
            # FINAL USER RESPONSE
            # =================================================

            user_message = (
                self._generate_user_response(
                    user_text=text,
                    request=intent_request,
                    result=result,
                )
            )

            operation_success = True

            if isinstance(
                result,
                dict,
            ):

                if result.get(
                    "success"
                ) is False:

                    operation_success = False

            response = {
                "success": operation_success,
                "intent": (
                    intent_request.intent.value
                ),
                "confidence": (
                    intent_request.confidence
                ),
                "result": result,
                "user_message": user_message,
                "state": self.state.to_dict(),
            }

            return finalize_response(
                response
            )

        finally:

            db.close()

    # =========================================================
    # RESTORE PENDING ACTION
    # =========================================================

    def _restore_pending_action(
        self,
        db,
        conversation,
        account_email: str,
    ) -> None:
        """
        Restore pending confirmation from PostgreSQL
        into the current in-memory ConversationState.

        This is required because each Python process has
        its own ConversationState instance.
        """

        try:

            pending = (
                ConversationService.get_pending_action(
                    db=db,
                    conversation=conversation,
                )
            )

        except Exception:
            db.rollback()

            pending = None

        if not pending:

            return

        pending_account = (
            pending.get(
                "account_email"
            )
        )

        # -----------------------------------------------------
        # Never restore a pending action belonging to a
        # different authenticated account.
        # -----------------------------------------------------

        if (
            pending_account
            and str(
                pending_account
            ).strip().lower()
            != str(
                account_email
            ).strip().lower()
        ):

            return

        # -----------------------------------------------------
        # Do not overwrite an already existing live action.
        # -----------------------------------------------------

        if self.state.has_pending_action():

            return

        self.state.pending_action = dict(
            pending
        )

    # =========================================================
    # CONVERSATION CONTEXT
    # =========================================================

    def _resolve_conversation_context(
        self,
        request: GmailIntentRequest,
        user_text: str,
    ) -> GmailIntentRequest:

        selected = (
            self.state.get_selected_result()
        )
        print("\nDEBUG CONTEXT")
        print("INTENT:", request.intent)

        print(
            "REFERENCE BEFORE:",
            request.message_reference
        )

        print(
            "IS PRESENT:",
            request.message_reference.is_present()
        )

        print(
            "SELECTED:",
            selected
        )

        # -----------------------------------------------------
        # SEND
        # -----------------------------------------------------

        if request.intent == GmailIntent.SEND:

            if self._looks_like_contextual_reply(
                request=request,
                user_text=user_text,
                selected=selected,
            ):

                return self._convert_to_reply(
                    request
                )

            return request

        # -----------------------------------------------------
        # Contextual Gmail operations.
        # -----------------------------------------------------

        contextual_intents = {
            GmailIntent.READ,
            GmailIntent.REPLY,
            GmailIntent.STAR,
            GmailIntent.UNSTAR,
            GmailIntent.DELETE,
            GmailIntent.MARK_READ,
            GmailIntent.MARK_UNREAD,
            GmailIntent.THREAD,
        }

        if request.intent in contextual_intents:

            if (
                not request.message_reference.is_present()
                and selected is not None
            ):

                return self._with_message_reference(
                    request=request,
                    reference=MessageReference(
                        type=MessageReferenceType.CURRENT,
                        raw="current",
                    ),
                )

        return request

    # =========================================================
    # CONTEXTUAL REPLY DETECTION
    # =========================================================

    def _looks_like_contextual_reply(
        self,
        request: GmailIntentRequest,
        user_text: str,
        selected: Any,
    ) -> bool:

        if selected is None:

            return False

        normalized = (
            self._clean_text(
                user_text
            )
            .lower()
        )

        if self._contains_new_email_command(
            normalized
        ):

            return False

        if not self._contains_context_reference(
            normalized
        ):

            return False

        body = self._clean_text(
            request.body
        )

        if not body:

            body = self._extract_followup_body(
                request=request,
                user_text=user_text,
            )

        return bool(body)

    # =========================================================
    # SEND -> REPLY
    # =========================================================

    def _convert_to_reply(
        self,
        request: GmailIntentRequest,
    ) -> GmailIntentRequest:

        body = self._clean_text(
            request.body
        )

        if not body:

            body = self._extract_followup_body(
                request=request,
                user_text=request.raw_text,
            )

        if not body:

            body = self._clean_text(
                request.raw_text
            )

        return GmailIntentRequest(
            intent=GmailIntent.REPLY,
            query=None,
            message_reference=MessageReference(
                type=MessageReferenceType.CURRENT,
                raw="current",
            ),
            recipient=None,
            subject=None,
            body=body,
            cc=request.cc,
            bcc=request.bcc,
            page=request.page,
            max_results=request.max_results,
            thread_reference=MessageReference(),
            confidence=max(
                request.confidence,
                0.90,
            ),
            raw_text=request.raw_text,
            metadata={
                **self._metadata(
                    request
                ),
                "resolved_from_context": True,
                "original_intent": (
                    request.intent.value
                ),
            },
        )

    # =========================================================
    # ENSURE REPLY REFERENCE
    # =========================================================

    def _ensure_reply_reference(
        self,
        request: GmailIntentRequest,
    ) -> GmailIntentRequest:

        if request.message_reference.is_present():

            return request

        selected = (
            self.state.get_selected_result()
        )

        if selected is None:

            return request

        return GmailIntentRequest(
            intent=GmailIntent.REPLY,
            query=request.query,
            message_reference=MessageReference(
                type=MessageReferenceType.CURRENT,
                raw="current",
            ),
            recipient=None,
            subject=None,
            body=request.body,
            cc=request.cc,
            bcc=request.bcc,
            page=request.page,
            max_results=request.max_results,
            thread_reference=request.thread_reference,
            confidence=request.confidence,
            raw_text=request.raw_text,
            metadata={
                **self._metadata(
                    request
                ),
                "resolved_from_selected_message": True,
            },
        )

    # =========================================================
    # MESSAGE REFERENCE
    # =========================================================

    def _with_message_reference(
        self,
        request: GmailIntentRequest,
        reference: MessageReference,
    ) -> GmailIntentRequest:

        return GmailIntentRequest(
            intent=request.intent,
            query=request.query,
            message_reference=reference,
            recipient=request.recipient,
            subject=request.subject,
            body=request.body,
            cc=request.cc,
            bcc=request.bcc,
            page=request.page,
            max_results=request.max_results,
            thread_reference=request.thread_reference,
            confidence=request.confidence,
            raw_text=request.raw_text,
            metadata=request.metadata,
        )

    # =========================================================
    # TEXT HELPERS
    # =========================================================

    @staticmethod
    def _clean_text(
        value: Any,
    ) -> str:

        if value is None:

            return ""

        return str(value).strip()

    @staticmethod
    def _metadata(
        request: GmailIntentRequest,
    ) -> dict[str, Any]:

        if isinstance(
            request.metadata,
            dict,
        ):

            return dict(
                request.metadata
            )

        return {}

    # =========================================================
    # NEW EMAIL DETECTION
    # =========================================================

    @staticmethod
    def _contains_new_email_command(
        text: str,
    ) -> bool:

        normalized = (
            text.strip()
            .lower()
        )

        patterns = (
            r"\bsend\s+(?:an?\s+)?email\b",
            r"\bsend\s+(?:an?\s+)?mail\b",
            r"\bcompose\s+(?:an?\s+)?email\b",
            r"\bcompose\s+(?:an?\s+)?mail\b",
            r"\bnew\s+email\b",
            r"\bnew\s+mail\b",
            r"\bcreate\s+(?:an?\s+)?email\b",
            r"\bwrite\s+(?:an?\s+)?email\b",
        )

        return any(
            re.search(
                pattern,
                normalized,
            )
            for pattern in patterns
        )

    # =========================================================
    # CONTEXT REFERENCE DETECTION
    # =========================================================

    @staticmethod
    def _contains_context_reference(
        text: str,
    ) -> bool:

        normalized = (
            text.strip()
            .lower()
        )

        patterns = (
            r"\bthat\s+(?:email|mail|message)\b",
            r"\bthis\s+(?:email|mail|message)\b",
            r"\bthe\s+(?:email|mail|message)\b",
            r"\bprevious\s+(?:email|mail|message)\b",
            r"\blast\s+(?:email|mail|message)\b",
            r"\bcurrent\s+(?:email|mail|message)\b",
            r"\bselected\s+(?:email|mail|message)\b",
            r"\bthe\s+same\s+(?:email|mail|thread)\b",
            r"\bsame\s+(?:email|mail|thread)\b",
            r"\bthat\s+thread\b",
            r"\bthis\s+thread\b",
            r"\bprevious\s+thread\b",
            r"\blast\s+thread\b",
            r"\bit\b",
        )

        return any(
            re.search(
                pattern,
                normalized,
            )
            for pattern in patterns
        )

    # =========================================================
    # FOLLOW-UP BODY
    # =========================================================

    def _extract_followup_body(
        self,
        request: GmailIntentRequest,
        user_text: str,
    ) -> str:

        body = self._clean_text(
            request.body
        )

        if body:

            return body

        text = self._clean_text(
            user_text
        )

        patterns = (
            r"^(?:tell\s+them|tell\s+him|tell\s+her)\s+(.+)$",
            r"^(?:say|write)\s+(.+)$",
            r"^(?:reply\s+)?(?:with|saying)\s+(.+)$",
            r"^(?:respond|reply)\s+(.+)$",
        )

        for pattern in patterns:

            match = re.match(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            if match:

                extracted = (
                    match.group(1).strip()
                )

                if extracted:

                    return extracted

        return ""

    # =========================================================
    # SEND COMPLETION
    # =========================================================

    def _complete_send_request(
        self,
        request: GmailIntentRequest,
        user_text: str,
    ) -> GmailIntentRequest:

        recipient = self._clean_text(
            request.recipient
        )

        subject = self._clean_text(
            request.subject
        )

        body = self._clean_text(
            request.body
        )

        if not recipient:

            raise RuntimeError(
                "Recipient email address is required."
            )

        if subject and body:

            return request

        missing_fields = []

        if not subject:

            missing_fields.append(
                "subject"
            )

        if not body:

            missing_fields.append(
                "body"
            )

        prompt = """
You are the email drafting component of a production
Gmail AI agent.

The user explicitly requested a NEW email.

Your task is to complete ONLY the missing email fields.

Rules:

1. Never invent personal facts.
2. Never invent names.
3. Never invent dates.
4. Never invent commitments.
5. Never invent meeting details.
6. Never invent amounts.
7. Never invent recipients.
8. Preserve the user's existing subject exactly.
9. Preserve the user's existing body exactly.
10. Generate only missing fields.
11. Keep generated content concise and natural.
12. Do not modify the recipient.
13. Return ONLY valid JSON.
14. Do not add markdown.
15. Do not add explanations.

Required JSON:

{
  "subject": "...",
  "body": "..."
}

User request:
"""

        prompt += (
            "\n"
            + user_text
            + "\n\nRecipient:\n"
            + recipient
            + "\n\nExisting subject:\n"
            + (
                subject
                if subject
                else "(missing)"
            )
            + "\n\nExisting body:\n"
            + (
                body
                if body
                else "(missing)"
            )
            + "\n\nMissing fields:\n"
            + ", ".join(
                missing_fields
            )
        )

        response = (
            bedrock_service.invoke_json(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": prompt
                            }
                        ],
                    }
                ],
                temperature=0.2,
            )
        )

        generated_subject = None
        generated_body = None

        if isinstance(
            response,
            dict,
        ):

            generated_subject = (
                response.get(
                    "subject"
                )
            )

            generated_body = (
                response.get(
                    "body"
                )
            )

        if not subject:

            subject = self._clean_text(
                generated_subject
            )

        if not body:

            body = self._clean_text(
                generated_body
            )

        if not subject:

            raise RuntimeError(
                "Bedrock could not generate an email subject."
            )

        if not body:

            raise RuntimeError(
                "Bedrock could not generate an email body."
            )

        return GmailIntentRequest(
            intent=GmailIntent.SEND,
            query=request.query,
            message_reference=request.message_reference,
            recipient=recipient,
            subject=subject,
            body=body,
            cc=request.cc,
            bcc=request.bcc,
            page=request.page,
            max_results=request.max_results,
            thread_reference=request.thread_reference,
            confidence=max(
                request.confidence,
                0.90,
            ),
            raw_text=request.raw_text,
            metadata={
                **self._metadata(
                    request
                ),
                "send_fields_completed": True,
                "subject_generated": (
                    not bool(
                        self._clean_text(
                            request.subject
                        )
                    )
                ),
                "body_generated": (
                    not bool(
                        self._clean_text(
                            request.body
                        )
                    )
                ),
            },
        )

    # =========================================================
    # RELATIVE / EXPLICIT DATE RESOLUTION
    # =========================================================

    @staticmethod
    def _resolve_relative_date_query(
        user_text: str,
        query: str | None,
    ) -> str | None:

        text = (
            user_text
            .strip()
            .lower()
        )

        current_date = (
            datetime.now().date()
        )

        def _clean_existing_query(
            value: str | None,
        ) -> str | None:

            if not value:

                return None

            cleaned = str(
                value
            ).strip()

            if not cleaned:

                return None

            cleaned = re.sub(
                r"\b(?:after|before):(?:today|tomorrow|yesterday)\b",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )

            cleaned = re.sub(
                r"\b(?:newer_than|older_than):\S+",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )

            cleaned = re.sub(
                r"\b(?:after|before|older|newer):"
                r"\d{4}/\d{1,2}/\d{1,2}",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )

            cleaned = re.sub(
                r"\s+",
                " ",
                cleaned,
            ).strip()

            return cleaned or None

        base_query = (
            _clean_existing_query(
                query
            )
        )

        def _calendar_day_query(
            day,
        ) -> str:

            next_day = (
                day
                + timedelta(days=1)
            )

            date_query = (
                f"after:{day.strftime('%Y/%m/%d')} "
                f"before:{next_day.strftime('%Y/%m/%d')}"
            )

            if base_query:

                return (
                    f"{base_query} "
                    f"{date_query}"
                )

            return date_query

        month_numbers = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }

        month_pattern = (
            r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|"
            r"apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
            r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
            r"nov(?:ember)?|dec(?:ember)?)"
        )

        explicit_date = None

        match = re.search(
            rf"\b(?P<month>{month_pattern})\s+"
            rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?"
            rf"(?:\s*,?\s*(?P<year>\d{{4}}))?\b",
            text,
            flags=re.IGNORECASE,
        )

        if match:

            month = month_numbers[
                match.group(
                    "month"
                ).lower()
            ]

            day = int(
                match.group(
                    "day"
                )
            )

            year = int(
                match.group(
                    "year"
                )
                or current_date.year
            )

            try:

                explicit_date = datetime(
                    year,
                    month,
                    day,
                ).date()

            except ValueError:

                explicit_date = None

        if explicit_date is None:

            match = re.search(
                rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+"
                rf"(?P<month>{month_pattern})"
                rf"(?:\s*,?\s*(?P<year>\d{{4}}))?\b",
                text,
                flags=re.IGNORECASE,
            )

            if match:

                month = month_numbers[
                    match.group(
                        "month"
                    ).lower()
                ]

                day = int(
                    match.group(
                        "day"
                    )
                )

                year = int(
                    match.group(
                        "year"
                    )
                    or current_date.year
                )

                try:

                    explicit_date = datetime(
                        year,
                        month,
                        day,
                    ).date()

                except ValueError:

                    explicit_date = None

        if explicit_date is not None:

            return _calendar_day_query(
                explicit_date
            )

        if re.search(
            r"\btoday(?:'s)?\b",
            text,
        ):

            return _calendar_day_query(
                current_date
            )

        if re.search(
            r"\byesterday(?:'s)?\b",
            text,
        ):

            return _calendar_day_query(
                current_date
                - timedelta(days=1)
            )

        if re.search(
            r"\bthis\s+week\b",
            text,
        ):

            week_start = (
                current_date
                - timedelta(
                    days=current_date.weekday()
                )
            )

            next_week = (
                week_start
                + timedelta(days=7)
            )

            week_query = (
                f"after:{week_start.strftime('%Y/%m/%d')} "
                f"before:{next_week.strftime('%Y/%m/%d')}"
            )

            if base_query:

                return (
                    f"{base_query} "
                    f"{week_query}"
                )

            return week_query

        if re.search(
            r"\blast\s+week\b",
            text,
        ):

            this_week_start = (
                current_date
                - timedelta(
                    days=current_date.weekday()
                )
            )

            last_week_start = (
                this_week_start
                - timedelta(days=7)
            )

            week_query = (
                f"after:{last_week_start.strftime('%Y/%m/%d')} "
                f"before:{this_week_start.strftime('%Y/%m/%d')}"
            )

            if base_query:

                return (
                    f"{base_query} "
                    f"{week_query}"
                )

            return week_query

        if re.search(
            r"\bthis\s+month\b",
            text,
        ):

            month_start = (
                current_date.replace(
                    day=1
                )
            )

            if month_start.month == 12:

                next_month = (
                    month_start.replace(
                        year=(
                            month_start.year
                            + 1
                        ),
                        month=1,
                    )
                )

            else:

                next_month = (
                    month_start.replace(
                        month=(
                            month_start.month
                            + 1
                        )
                    )
                )

            month_query = (
                f"after:{month_start.strftime('%Y/%m/%d')} "
                f"before:{next_month.strftime('%Y/%m/%d')}"
            )

            if base_query:

                return (
                    f"{base_query} "
                    f"{month_query}"
                )

            return month_query

        return query

    # =========================================================
    # PENDING CONFIRMATION
    # =========================================================

    def _handle_pending_confirmation(
        self,
        text: str,
        account_email: str,
        db=None,
        conversation=None,
    ) -> dict[str, Any] | None:

        normalized = (
            text.strip()
            .lower()
        )

        # =====================================================
        # CONFIRM
        # =====================================================

        if self._is_confirmation(
            normalized
        ):

            pending = (
                self.state.get_pending_action()
            )

            try:

                result = (
                    self.executor.confirm_pending_delete(
                        account_email=account_email
                    )
                )

            except ValueError as exc:

                return {
                    "success": False,
                    "intent": (
                        GmailIntent.DELETE.value
                    ),
                    "error": str(exc),
                    "user_message": (
                        self._generate_error_response(
                            user_text=text,
                            intent=(
                                GmailIntent.DELETE.value
                            ),
                            error=str(exc),
                        )
                    ),
                    "state": self.state.to_dict(),
                }

            except RuntimeError as exc:

                return {
                    "success": False,
                    "intent": (
                        GmailIntent.DELETE.value
                    ),
                    "error": str(exc),
                    "user_message": (
                        self._generate_error_response(
                            user_text=text,
                            intent=(
                                GmailIntent.DELETE.value
                            ),
                            error=str(exc),
                        )
                    ),
                    "state": self.state.to_dict(),
                }

            # -------------------------------------------------
            # PostgreSQL pending action is now resolved.
            # -------------------------------------------------

            if (
                db is not None
                and conversation is not None
            ):

                ConversationService.resolve_pending_actions(
                    db=db,
                    conversation=conversation,
                    status="completed",
                )

            self.state.record_action(
                action="confirmation_accepted",
                details={
                    "action": (
                        pending.get("action")
                        if pending
                        else None
                    ),
                },
            )

            user_message = (
                self._generate_user_response(
                    user_text=text,
                    request=GmailIntentRequest(
                        intent=GmailIntent.DELETE,
                        raw_text=text,
                    ),
                    result=result,
                )
            )

            operation_success = True

            if isinstance(
                result,
                dict,
            ):

                if result.get(
                    "success"
                ) is False:

                    operation_success = False

            return {
                "success": operation_success,
                "intent": (
                    GmailIntent.DELETE.value
                ),
                "confidence": 1.0,
                "result": result,
                "user_message": user_message,
                "state": self.state.to_dict(),
            }

        # =====================================================
        # REJECT
        # =====================================================

        if self._is_rejection(
            normalized
        ):

            pending = (
                self.state.get_pending_action()
            )

            self.state.clear_pending_action()

            if (
                db is not None
                and conversation is not None
            ):

                ConversationService.resolve_pending_actions(
                    db=db,
                    conversation=conversation,
                    status="cancelled",
                )

            self.state.record_action(
                action="confirmation_rejected",
                details={
                    "action": (
                        pending.get("action")
                        if pending
                        else None
                    ),
                },
            )

            cancelled_result = {
                "success": False,
                "cancelled": True,
                "pending_action": pending,
            }

            user_message = (
                self._generate_user_response(
                    user_text=text,
                    request=GmailIntentRequest(
                        intent=GmailIntent.DELETE,
                        raw_text=text,
                    ),
                    result=cancelled_result,
                )
            )

            return {
                "success": True,
                "intent": (
                    GmailIntent.DELETE.value
                ),
                "confidence": 1.0,
                "result": cancelled_result,
                "user_message": user_message,
                "state": self.state.to_dict(),
                "cancelled": True,
            }

        # =====================================================
        # NEW REQUEST
        # =====================================================

        self.state.clear_pending_action()

        if (
            db is not None
            and conversation is not None
        ):

            ConversationService.resolve_pending_actions(
                db=db,
                conversation=conversation,
                status="cancelled",
            )

        self.state.record_action(
            action="pending_confirmation_cancelled",
            details={
                "reason": "new_user_request",
            },
        )

        return None

    # =========================================================
    # CONFIRMATION DETECTION
    # =========================================================

    @staticmethod
    def _is_confirmation(
        text: str,
    ) -> bool:

        values = {
            "yes",
            "yes please",
            "yeah",
            "yeah please",
            "yep",
            "yup",
            "sure",
            "sure please",
            "okay",
            "ok",
            "ok please",
            "confirm",
            "confirmed",
            "do it",
            "go ahead",
            "delete it",
            "delete",
        }

        return text in values

    # =========================================================
    # REJECTION DETECTION
    # =========================================================

    @staticmethod
    def _is_rejection(
        text: str,
    ) -> bool:

        values = {
            "no",
            "no thanks",
            "no thank you",
            "cancel",
            "cancel it",
            "don't",
            "do not",
            "don't delete",
            "do not delete",
            "stop",
            "never mind",
            "nevermind",
        }

        return text in values

    # =========================================================
    # BEDROCK INTENT UNDERSTANDING
    # =========================================================

    def _understand(
        self,
        user_text: str,
    ) -> dict[str, Any]:

        conversation_context = {}

        try:

            state_data = (
                self.state.to_dict()
            )

            if isinstance(
                state_data,
                dict,
            ):

                conversation_context = (
                    state_data
                )

        except Exception:

            conversation_context = {}

        system_prompt = """
You are the intent planner for a production Gmail AI agent.

Understand the user's request and return ONLY valid JSON.

You are NOT the Gmail executor.

You must NOT:

- call Gmail
- execute Gmail operations
- create Gmail message IDs
- create Gmail thread IDs
- create authenticated accounts
- invent recipients
- invent senders
- invent subjects
- invent email content

The application will perform all actual Gmail operations.

Supported intents:

search
read
send
reply
star
unstar
delete
mark_read
mark_unread
thread
unknown

Supported message reference types:

position
current
previous
latest
none

REFERENCE RULES:

- "first email" means position 1.
- "second email" means position 2.
- "third email" means position 3.
- "3rd email" means position 3.
- "tenth email" means position 10.
- "that email" means current.
- "this email" means current.
- "that mail" means current.
- "this mail" means current.
- "that message" means current.
- "this message" means current.
- "it" means current when the conversation is clearly referring
  to an email.
- "previous email" means previous.
- "last email" means previous when referring to the previously
  selected email.
- "latest email" means latest.
- "newest email" means latest.
- "same email" means current.
- "same mail" means current.
- "same message" means current.
- "same thread" refers to the current conversation/thread.

IMPORTANT:

Never create an ID from these references.

The application resolves references to actual Gmail data.

For SEND:

- SEND means a NEW email.
- Extract recipient only when explicitly supplied.
- Extract subject only when explicitly supplied.
- Extract body only when explicitly supplied.
- Missing subject must be null.
- Missing body must be null.
- Never invent missing values.

For REPLY:

- Extract the actual reply body supplied by the user.
- Resolve the reference semantically.
- Do not create Gmail IDs.

For SEARCH:

- Generate a Gmail-compatible query from the user's actual
  request.
- Preserve explicit filters.
- Do not invent people.
- Do not invent email addresses.
- Do not invent subjects.
- Do not invent labels or categories.
- Do not regroup search results into categories.
- If the user says "related to X", search for the actual term X
  unless the user explicitly supplied another Gmail filter.
- If the user supplies a quoted phrase, preserve that phrase as the
  search meaning.
- Relative date expressions such as today, yesterday,
  this week, last week and this month should remain semantic.
- Python resolves relative calendar dates.

SEARCH OUTPUT RULE:
The query must represent the user's requested search, not a summary
of what Gmail might contain. The application will execute the query
and will display only the messages actually returned by Gmail.

For STAR / UNSTAR / DELETE / MARK_READ / MARK_UNREAD:

- Understand the user's target email reference.
- Do not create Gmail IDs.
- The Python application will resolve the target using
  ConversationState and Gmail data.

For THREAD:

- Understand whether the user is referring to the current,
  previous, latest or explicitly positioned email/thread.
- Do not create thread IDs.

Conversation context is supplied only to help resolve natural
references. Treat it as application state, not as permission
to invent new Gmail data.

Return ONLY JSON.
"""

        context_prompt = (
            "\n\nCURRENT APPLICATION CONVERSATION CONTEXT:\n"
            + json.dumps(
                conversation_context,
                ensure_ascii=False,
                default=str,
            )
        )

        user_prompt = (
            "\n\nUSER REQUEST:\n"
            + user_text
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "text": (
                            system_prompt
                            + context_prompt
                            + user_prompt
                        )
                    }
                ],
            }
        ]

        response = (
            bedrock_service.invoke(
                messages
            )
        )

        parsed = (
            self._parse_bedrock_response(
                response
            )
        )

        if (
            parsed.get("intent")
            == GmailIntent.SEARCH.value
        ):

            parsed["query"] = (
                self._resolve_relative_date_query(
                    user_text=user_text,
                    query=parsed.get(
                        "query"
                    ),
                )
            )

        return parsed

    # =========================================================
    # PARSE BEDROCK JSON
    # =========================================================

    @staticmethod
    def _parse_bedrock_response(
        response: Any,
    ) -> dict[str, Any]:

        if isinstance(
            response,
            dict,
        ):

            if "text" in response:

                response = response[
                    "text"
                ]

            else:

                return response

        if isinstance(
            response,
            list,
        ):

            parts = []

            for item in response:

                if not isinstance(
                    item,
                    dict,
                ):

                    continue

                value = item.get(
                    "text"
                )

                if value:

                    parts.append(
                        str(value)
                    )

            response = "\n".join(
                parts
            )

        text = str(
            response
        ).strip()

        if not text:

            raise RuntimeError(
                "Amazon Bedrock returned an empty response."
            )

        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

        text = text.strip()

        try:

            parsed = json.loads(
                text
            )

            if isinstance(
                parsed,
                dict,
            ):

                return parsed

        except json.JSONDecodeError:

            pass

        start = text.find(
            "{"
        )

        end = text.rfind(
            "}"
        )

        if (
            start != -1
            and end != -1
            and end > start
        ):

            try:

                parsed = json.loads(
                    text[
                        start:end + 1
                    ]
                )

                if isinstance(
                    parsed,
                    dict,
                ):

                    return parsed

            except json.JSONDecodeError:

                pass

        raise RuntimeError(
            "Amazon Bedrock returned an invalid JSON response."
        )

    # =========================================================
    # FINAL BEDROCK RESPONSE
    # =========================================================

    def _generate_user_response(
        self,
        user_text: str,
        request: GmailIntentRequest,
        result: Any,
    ) -> str:

        # -----------------------------------------------------
        # COLLECTION RESULTS
        # -----------------------------------------------------
        # Search/list operations are rendered deterministically.
        # This prevents the final LLM from regrouping actual Gmail
        # results into invented categories such as "Promotional",
        # "Drafts", "Sent", etc. The result set returned by
        # Gmail is authoritative.
        # -----------------------------------------------------
        if request.intent in {
            GmailIntent.SEARCH,
            GmailIntent.LIST_UNREAD,
        }:
            return self._format_collection_response(
                request=request,
                result=result,
            )

        safe_result = (
            self._prepare_result_for_llm(
                result
            )
        )

        # -----------------------------------------------------
        # CONFIRMATION SAFETY GATE
        # -----------------------------------------------------
        # A destructive action that requires confirmation has
        # NOT been executed yet. Do not allow the LLM to describe
        # it as completed. The application state is authoritative.
        # -----------------------------------------------------

        if (
            isinstance(result, dict)
            and result.get("confirmation_required")
        ):

            return self._fallback_response(
                request=request,
                result=result,
            )

        prompt = """
You are the final response generator for a production
Gmail AI assistant.

The Gmail operation has already been processed by the
application.

Your ONLY job is to explain the ACTUAL result to the user.

Use ONLY information contained in the supplied Gmail result.

Rules:

1. Never invent information.
2. Never invent Gmail message IDs.
3. Never invent Gmail thread IDs.
4. Never invent email addresses.
5. Never invent subjects.
6. Never invent message bodies.
7. Never invent dates.
8. Never invent recipients.
9. Never invent senders.
10. Never claim success when the result failed.
11. Never claim failure when the result succeeded.
12. Never execute another Gmail operation.
13. Never modify the Gmail result.
14. Never assume information missing from the result.
15. Never mention internal Python code.
16. Never mention internal prompts.
17. Never mention model implementation.
18. Never mention internal architecture.
19. Be concise and natural.
20. If multiple emails are returned, summarize the actual
    returned emails.
21. If a subject exists in the result, use the actual subject.
22. If a sender exists in the result, use the actual sender.
23. If a recipient exists in the result, use the actual recipient.
24. If a date exists in the result, use the actual date.
25. If the result requires confirmation, clearly ask for
    confirmation.
26. If the operation was cancelled, explain that it was cancelled.
27. If the operation failed, explain the actual failure.
28. Respond directly to the user.
29. Do not output JSON unless the user explicitly asks for JSON.

The user's request was supplied separately.

The actual Gmail result is supplied below.
"""

        payload = {
            "user_request": user_text,
            "intent": request.intent.value,
            "gmail_result": safe_result,
        }

        prompt += (
            "\n\nACTUAL DATA:\n"
            + json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            )
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt
                    }
                ],
            }
        ]

        try:

            response = (
                bedrock_service.invoke(
                    messages
                )
            )

            text = (
                self._extract_text_response(
                    response
                )
            )

            if text:

                return text

        except Exception:

            pass

        return self._fallback_response(
            request=request,
            result=result,
        )

    # =========================================================
    # DETERMINISTIC COLLECTION RESPONSE
    # =========================================================

    @staticmethod
    def _format_collection_response(
        request: GmailIntentRequest,
        result: Any,
    ) -> str:
        """
        Format Gmail collection results without asking the LLM
        to reinterpret or regroup the returned messages.

        This is intentionally deterministic. Gmail's returned
        messages are the source of truth, so the assistant must
        not invent categories or combine unrelated messages.
        """

        if not isinstance(result, dict):
            return "I couldn't retrieve the email results."

        if result.get("success") is False:
            error = result.get("error")
            return str(error) if error else "I couldn't retrieve the email results."

        raw_messages = result.get("messages", [])
        if not isinstance(raw_messages, list):
            raw_messages = []

        messages: list[dict[str, Any]] = []

        for index, message in enumerate(raw_messages, start=1):
            if not isinstance(message, dict):
                continue

            # Gmail service responses normally use these keys.
            # The fallbacks make this formatter tolerant of older
            # service response shapes without inventing data.
            position = message.get("position", index)
            sender = message.get("from") or message.get("sender")
            recipient = message.get("to") or message.get("recipient")
            subject = message.get("subject")
            date = message.get("date")
            snippet = message.get("snippet")

            messages.append({
                "position": position,
                "sender": sender,
                "recipient": recipient,
                "subject": subject,
                "date": date,
                "snippet": snippet,
            })

        intent_label = (
            "unread emails"
            if request.intent == GmailIntent.LIST_UNREAD
            else "emails"
        )

        if not messages:
            query = result.get("query") or request.query
            if query:
                return f"I couldn't find any {intent_label} matching \"{query}\"."
            return f"I couldn't find any {intent_label}."

        query = result.get("query") or request.query
        if query:
            response_lines = [
                f"I found {len(messages)} {intent_label} matching \"{query}\":"
            ]
        else:
            response_lines = [
                f"I found {len(messages)} {intent_label}:"
            ]

        for item in messages:
            position = item["position"]
            response_lines.append("")
            response_lines.append(f"{position}.")

            if item["sender"]:
                response_lines.append(f"From: {item["sender"]}")

            if item["recipient"]:
                response_lines.append(f"To: {item["recipient"]}")

            if item["subject"]:
                response_lines.append(f"Subject: {item["subject"]}")

            if item["date"]:
                response_lines.append(f"Date: {item["date"]}")

            if item["snippet"]:
                response_lines.append(f"Preview: {item["snippet"]}")

        return "\n".join(response_lines)

    # =========================================================
    # PREPARE RESULT FOR LLM
    # =========================================================

    @staticmethod
    def _prepare_result_for_llm(
        result: Any,
    ) -> Any:

        if isinstance(
            result,
            dict,
        ):

            return result

        if isinstance(
            result,
            list,
        ):

            return {
                "results": result
            }

        return {
            "result": str(result)
        }

    # =========================================================
    # EXTRACT BEDROCK TEXT
    # =========================================================

    @staticmethod
    def _extract_text_response(
        response: Any,
    ) -> str:

        if isinstance(
            response,
            str,
        ):

            text = response.strip()

            if text:

                return text

        if isinstance(
            response,
            dict,
        ):

            if response.get(
                "text"
            ):

                return str(
                    response["text"]
                ).strip()

            content = response.get(
                "content"
            )

            if isinstance(
                content,
                list,
            ):

                parts = []

                for item in content:

                    if not isinstance(
                        item,
                        dict,
                    ):

                        continue

                    value = item.get(
                        "text"
                    )

                    if value:

                        parts.append(
                            str(value)
                        )

                if parts:

                    return "\n".join(
                        parts
                    ).strip()

        if isinstance(
            response,
            list,
        ):

            parts = []

            for item in response:

                if not isinstance(
                    item,
                    dict,
                ):

                    continue

                value = item.get(
                    "text"
                )

                if value:

                    parts.append(
                        str(value)
                    )

            if parts:

                return "\n".join(
                    parts
                ).strip()

        return ""

    # =========================================================
    # BEDROCK ERROR RESPONSE
    # =========================================================

    def _generate_error_response(
        self,
        user_text: str,
        intent: str,
        error: str,
    ) -> str:

        prompt = """
You are a Gmail AI assistant.

The requested Gmail operation could not be completed.

Explain the problem to the user clearly and briefly.

Use ONLY the supplied error information.

Rules:

- Do not invent information.
- Do not claim the operation succeeded.
- Do not mention internal implementation.
- Do not mention Python.
- Do not mention prompts.
- Do not mention model details.
- Do not execute another Gmail operation.
- Return only the user-facing response.

User request:
"""

        prompt += (
            "\n"
            + user_text
            + "\n\nIntent:\n"
            + intent
            + "\n\nActual error:\n"
            + error
        )

        try:

            response = (
                bedrock_service.invoke(
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": prompt
                                }
                            ],
                        }
                    ]
                )
            )

            generated = (
                self._extract_text_response(
                    response
                )
            )

            if generated:

                return generated

        except Exception:

            pass

        return str(
            error
        )

    # =========================================================
    # FALLBACK RESPONSE
    # =========================================================

    @staticmethod
    def _fallback_response(
        request: GmailIntentRequest,
        result: Any,
    ) -> str:

        if not isinstance(
            result,
            dict,
        ):

            return (
                "The Gmail operation completed."
            )

        if result.get(
            "confirmation_required"
        ):

            return (
                "This Gmail action requires your confirmation."
            )

        if result.get(
            "cancelled"
        ):

            return (
                "The requested action was cancelled."
            )

        if result.get(
            "success"
        ) is False:

            error = result.get(
                "error"
            )

            if error:

                return str(
                    error
                )

            return (
                "The Gmail operation could not be completed."
            )

        return (
            "The Gmail operation was completed successfully."
        )

    # =========================================================
    # UNKNOWN INTENT
    # =========================================================

    def _unknown_response(
        self,
        text: str,
        reason: str,
    ) -> dict[str, Any]:

        self.state.record_action(
            action="unknown",
            details={
                "user_text": text,
                "reason": reason,
            },
        )

        prompt = """
You are a Gmail AI assistant.

The user's request could not be mapped to a supported
Gmail operation.

Explain briefly that the request was not understood and
ask the user to rephrase it.

Rules:

- Do not invent Gmail information.
- Do not mention internal implementation.
- Do not mention Python.
- Do not mention prompts.
- Return only the user-facing response.

User request:
"""

        prompt += (
            "\n"
            + text
            + "\n\nReason:\n"
            + reason
        )

        try:

            response = (
                bedrock_service.invoke(
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": prompt
                                }
                            ],
                        }
                    ]
                )
            )

            generated = (
                self._extract_text_response(
                    response
                )
            )

            if generated:

                user_message = (
                    generated
                )

            else:

                user_message = (
                    "I couldn't understand the Gmail request."
                )

        except Exception:

            user_message = (
                "I couldn't understand the Gmail request."
            )

        return {
            "success": False,
            "intent": (
                GmailIntent.UNKNOWN.value
            ),
            "error": reason,
            "user_message": user_message,
            "state": self.state.to_dict(),
        }
    # =========================================================
    # WORKFLOW PERSISTENCE
    # =========================================================

    def _get_active_workflow(
        self,
        db,
        conversation,
    ):
        """
        Retrieve the current unfinished workflow
        from PostgreSQL.
        """

        try:
            return ConversationService.get_active_workflow(
                db=db,
                conversation=conversation,
            )
        except Exception:
            return None

    def _create_workflow(
        self,
        db,
        conversation,
        workflow_type: str,
        required_field: str | None = None,
        collected_data: dict | None = None,
    ):
        """
        Create a new generic persistent workflow.
        """

        return ConversationService.create_workflow(
            db=db,
            conversation=conversation,
            workflow_type=workflow_type,
            status="WAITING_FOR_INPUT",
            required_field=required_field,
            collected_data=collected_data or {},
        )

    def _update_workflow(
        self,
        db,
        workflow,
        *,
        status: str | None = None,
        required_field: str | None = None,
        collected_data: dict | None = None,
    ):
        """
        Update an existing persistent workflow.
        """

        return ConversationService.update_workflow(
            db=db,
            workflow=workflow,
            status=status,
            required_field=required_field,
            collected_data=collected_data,
        )

    def _complete_workflow(
        self,
        db,
        workflow,
    ):
        """
        Mark the current workflow as completed.
        """

        return ConversationService.complete_workflow(
            db=db,
            workflow=workflow,
        )

    def _cancel_workflow(
        self,
        db,
        workflow,
    ):
        """
        Mark the current workflow as cancelled.
        """

        return ConversationService.cancel_workflow(
            db=db,
            workflow=workflow,
        )
    # =========================================================
    # ACTIVE WORKFLOW RESOLUTION
    # =========================================================

    def _handle_active_workflow(
        self,
        db,
        conversation,
        user_text: str,
    ) -> dict[str, Any] | None:
        """
        Resume an existing persistent workflow.

        This method only handles workflow state.
        It does not execute Gmail operations.
        """

        workflow = self._get_active_workflow(
            db=db,
            conversation=conversation,
        )

        if workflow is None:
            return None

        collected_data = (
            dict(workflow.collected_data)
            if isinstance(
                workflow.collected_data,
                dict,
            )
            else {}
        )

        required_field = workflow.required_field

        if not required_field:
            return None

        value = self._extract_workflow_value(
            user_text=user_text,
            field_name=required_field,
        )

        if not value:
            return {
                "success": False,
                "intent": GmailIntent.UNKNOWN.value,
                "workflow_active": True,
                "workflow_id": workflow.id,
                "workflow_type": workflow.workflow_type,
                "required_field": required_field,
                "user_message": (
                    f"I still need the "
                    f"{required_field.replace('_', ' ')}."
                ),
                "state": self.state.to_dict(),
            }

        collected_data[required_field] = value

        self._update_workflow(
            db=db,
            workflow=workflow,
            status="READY",
            required_field=None,
            collected_data=collected_data,
        )

        return {
            "success": True,
            "intent": GmailIntent.UNKNOWN.value,
            "workflow_active": True,
            "workflow_ready": True,
            "workflow_id": workflow.id,
            "workflow_type": workflow.workflow_type,
            "collected_data": collected_data,
            "user_message": (
                "I have the information needed to continue."
            ),
            "state": self.state.to_dict(),
        }
    # =========================================================
    # WORKFLOW VALUE EXTRACTION
    # =========================================================

    @staticmethod
    def _extract_workflow_value(
        user_text: str,
        field_name: str,
    ) -> str:
        """
        Extract a simple value supplied by the user.

        This remains generic and does not know anything
        about a particular business domain.
        """

        text = (
            user_text or ""
        ).strip()

        if not text:
            return ""

        cleaned = re.sub(
            r"^(?:it is|it's|is|the|my|that is)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        field_label = (
            field_name.replace("_", " ")
        )

        pattern = (
            rf"^(?:{re.escape(field_label)}"
            rf"|{re.escape(field_name)})"
            rf"\s*(?:is|:|-)?\s*(.+)$"
        )

        match = re.match(
            pattern,
            cleaned,
            flags=re.IGNORECASE,
        )

        if match:
            value = match.group(1).strip()

            if value:
                return value

        return cleaned

# =============================================================
# SHARED ORCHESTRATOR
# =============================================================

gmail_orchestrator = GmailOrchestrator(
    state=conversation_state
)