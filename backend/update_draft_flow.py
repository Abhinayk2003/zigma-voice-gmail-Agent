from pathlib import Path
import shutil


BASE = Path(__file__).resolve().parent

INTENT = BASE / "app/agent/intent.py"
STATE = BASE / "app/agent/state.py"
EXECUTOR = BASE / "app/agent/executor.py"
ORCHESTRATOR = BASE / "app/agent/orchestrator.py"


# =============================================================
# Backup
# =============================================================

for path in (
    INTENT,
    STATE,
    EXECUTOR,
    ORCHESTRATOR,
):
    backup = path.with_suffix(path.suffix + ".before_draft")
    shutil.copy2(path, backup)
    print(f"Backup created: {backup}")


# =============================================================
# Helper
# =============================================================

def replace_once(
    path: Path,
    old: str,
    new: str,
    description: str,
) -> None:

    text = path.read_text()

    count = text.count(old)

    if count != 1:
        raise RuntimeError(
            f"{description}: expected exactly 1 occurrence, "
            f"found {count} in {path}"
        )

    path.write_text(
        text.replace(
            old,
            new,
            1,
        )
    )

    print(f"Updated: {path} -> {description}")


# =============================================================
# 1. INTENT.PY
# =============================================================

replace_once(
    INTENT,

    '''    SEND = "send"
    REPLY = "reply"
''',

    '''    SEND = "send"
    DRAFT = "draft"
    REPLY = "reply"
''',

    "added DRAFT intent",
)


replace_once(
    INTENT,

    '''    def is_send(self) -> bool:
        return self.intent == GmailIntent.SEND

    def has_body(self) -> bool:
''',

    '''    def is_send(self) -> bool:
        return self.intent == GmailIntent.SEND

    def is_draft(self) -> bool:
        return self.intent == GmailIntent.DRAFT

    def has_body(self) -> bool:
''',

    "added is_draft helper",
)


# =============================================================
# 2. STATE.PY
# =============================================================

replace_once(
    STATE,

    '''    def has_pending_action(self) -> bool:
''',

    '''    def set_pending_draft(
        self,
        *,
        subject: str,
        body: str,
        recipient: str | None = None,
        cc: str | None = None,
        bcc: str | None = None,
        account_email: str | None = None,
    ) -> None:
        """
        Store an AI-generated draft awaiting user confirmation.

        This does NOT send anything to Gmail.

        The draft content comes from the AI planner/composer.
        The authenticated account comes from the application.
        """

        if not subject or not subject.strip():
            raise ValueError(
                "Draft subject is required."
            )

        if not body or not body.strip():
            raise ValueError(
                "Draft body is required."
            )

        self.pending_action = {
            "action": "draft_send",
            "subject": subject.strip(),
            "body": body.strip(),
            "recipient": (
                recipient.strip()
                if recipient
                else None
            ),
            "cc": (
                cc.strip()
                if cc
                else None
            ),
            "bcc": (
                bcc.strip()
                if bcc
                else None
            ),
            "account_email": (
                account_email.strip()
                if account_email
                else self.account_email
            ),
        }

        self.last_action = "draft_confirmation_required"


    def has_pending_action(self) -> bool:
''',

    "added pending draft state",
)


# =============================================================
# 3. EXECUTOR.PY
# =============================================================

replace_once(
    EXECUTOR,

    '''            GmailIntent.SEND:
                self._send,

            GmailIntent.REPLY:
''',

    '''            GmailIntent.SEND:
                self._send,

            GmailIntent.DRAFT:
                self._draft,

            GmailIntent.REPLY:
''',

    "registered DRAFT executor",
)


# -------------------------------------------------------------
# Add _draft before _send
# -------------------------------------------------------------

replace_once(
    EXECUTOR,

    '''    # =========================================================
    # Send
    # =========================================================

    def _send(
''',

    '''    # =========================================================
    # Draft
    # =========================================================

    def _draft(
        self,
        request: GmailIntentRequest,
        account_email: str,
    ) -> dict[str, Any]:
        """
        Prepare a Gmail draft for user confirmation.

        IMPORTANT:

        This method does NOT send the email.

        The user may provide:
            - recipient
            - subject
            - body

        Missing subject/body should already have been
        completed by the Bedrock drafting layer.

        Recipient is optional for a draft.

        Nothing is hard-coded about the recipient.
        """

        subject = (
            request.subject.strip()
            if request.subject
            else ""
        )

        body = (
            request.body.strip()
            if request.body
            else ""
        )

        recipient = (
            request.recipient.strip()
            if request.recipient
            else None
        )

        cc = (
            request.cc.strip()
            if request.cc
            else None
        )

        bcc = (
            request.bcc.strip()
            if request.bcc
            else None
        )

        if not subject:
            raise ValueError(
                "Draft subject is required."
            )

        if not body:
            raise ValueError(
                "Draft body is required."
            )

        # -----------------------------------------------------
        # Store draft in conversation state.
        #
        # No Gmail API call happens here.
        # -----------------------------------------------------

        self.state.set_pending_draft(
            subject=subject,
            body=body,
            recipient=recipient,
            cc=cc,
            bcc=bcc,
            account_email=account_email,
        )

        self.state.record_action(
            action="draft_confirmation_required",
            details={
                "subject": subject,
                "recipient": recipient,
            },
        )

        return {
            "success": True,
            "intent": GmailIntent.DRAFT.value,
            "draft": {
                "recipient": recipient,
                "cc": cc,
                "bcc": bcc,
                "subject": subject,
                "body": body,
            },
            "confirmation_required": True,
        }


    # =========================================================
    # Confirm Pending Draft
    # =========================================================

    def confirm_pending_draft(
        self,
        account_email: str | None = None,
    ) -> dict[str, Any]:
        """
        Send the draft after explicit user confirmation.

        The draft itself comes from ConversationState.
        The authenticated account comes from authentication/state.
        """

        pending = (
            self.state.get_pending_action()
        )

        if not pending:
            raise ValueError(
                "There is no draft awaiting confirmation."
            )

        if pending.get("action") != "draft_send":
            raise ValueError(
                "The pending operation is not a draft."
            )

        account = (
            account_email
            or pending.get("account_email")
            or self.state.account_email
        )

        if not account:
            raise ValueError(
                "Authenticated Gmail account is required."
            )

        subject = (
            pending.get("subject")
        )

        body = (
            pending.get("body")
        )

        recipient = (
            pending.get("recipient")
        )

        cc = (
            pending.get("cc")
        )

        bcc = (
            pending.get("bcc")
        )

        if not subject:
            self.state.clear_pending_action()
            raise ValueError(
                "The pending draft has no subject."
            )

        if not body:
            self.state.clear_pending_action()
            raise ValueError(
                "The pending draft has no body."
            )

        # -----------------------------------------------------
        # Recipient is required only when sending.
        # -----------------------------------------------------

        if not recipient:
            raise ValueError(
                "A recipient email address is required "
                "before the draft can be sent."
            )

        # -----------------------------------------------------
        # Send through Gmail.
        # -----------------------------------------------------

        result = (
            gmail_send_service.send_email(
                account_email=account,
                recipient=recipient,
                subject=subject,
                body=body,
                cc=cc,
                bcc=bcc,
            )
        )

        message_id = (
            result.get("message_id")
        )

        thread_id = (
            result.get("thread_id")
        )

        # -----------------------------------------------------
        # Clear pending draft.
        # -----------------------------------------------------

        self.state.clear_pending_action()

        # -----------------------------------------------------
        # Remember sent message.
        # -----------------------------------------------------

        if message_id:

            self.state.remember_sent_message(
                message_id=message_id,
                thread_id=thread_id,
                recipient=recipient,
                subject=subject,
                body=body,
            )

            if self.state.selected_message_id:

                self.state.previous_message_id = (
                    self.state.selected_message_id
                )

                self.state.previous_thread_id = (
                    self.state.selected_thread_id
                )

            self.state.selected_message_id = (
                message_id
            )

            self.state.selected_thread_id = (
                thread_id
            )

        self.state.record_action(
            action="draft_send",
            details={
                "message_id": message_id,
                "thread_id": thread_id,
                "recipient": recipient,
                "subject": subject,
            },
        )

        return {
            "success": True,
            "intent": GmailIntent.SEND.value,
            "source_intent": GmailIntent.DRAFT.value,
            "recipient": recipient,
            "subject": subject,
            "message_id": message_id,
            "thread_id": thread_id,
            **result,
        }


    # =========================================================
    # Send
    # =========================================================

    def _send(
''',

    "added draft creation and confirmation",
)


# =============================================================
# 4. ORCHESTRATOR.PY
# =============================================================

# -------------------------------------------------------------
# Add DRAFT completion before SEND completion.
# -------------------------------------------------------------

replace_once(
    ORCHESTRATOR,

    '''        # -----------------------------------------------------
        # Dynamic SEND completion
        # -----------------------------------------------------

        if (
            intent_request.intent
            == GmailIntent.SEND
        ):
''',

    '''        # -----------------------------------------------------
        # Dynamic DRAFT completion
        # -----------------------------------------------------

        if (
            intent_request.intent
            == GmailIntent.DRAFT
        ):

            try:

                intent_request = (
                    self._complete_draft_request(
                        request=intent_request,
                        user_text=text,
                    )
                )

            except RuntimeError as exc:

                return {
                    "success": False,
                    "intent": GmailIntent.DRAFT.value,
                    "error": str(exc),
                    "user_message": (
                        self._generate_error_response(
                            user_text=text,
                            intent=GmailIntent.DRAFT.value,
                            error=str(exc),
                        )
                    ),
                    "state": self.state.to_dict(),
                }


        # -----------------------------------------------------
        # Dynamic SEND completion
        # -----------------------------------------------------

        if (
            intent_request.intent
            == GmailIntent.SEND
        ):
''',

    "added DRAFT completion flow",
)


# -------------------------------------------------------------
# Add draft completion method before send completion.
# -------------------------------------------------------------

replace_once(
    ORCHESTRATOR,

    '''    # =========================================================
    # SEND COMPLETION USING BEDROCK
    # =========================================================

    def _complete_send_request(
''',

    '''    # =========================================================
    # DRAFT COMPLETION USING BEDROCK
    # =========================================================

    def _complete_draft_request(
        self,
        request: GmailIntentRequest,
        user_text: str,
    ) -> GmailIntentRequest:
        """
        Complete a draft using Bedrock.

        IMPORTANT:

        No natural-language trigger phrases are checked here.

        Bedrock has already determined that the user's intent
        is DRAFT.

        This method only asks Bedrock to generate missing
        subject/body fields.

        Recipient is intentionally optional for a draft.
        """

        subject = self._clean_text(
            request.subject
        )

        body = self._clean_text(
            request.body
        )

        missing_fields: list[str] = []

        if not subject:
            missing_fields.append(
                "subject"
            )

        if not body:
            missing_fields.append(
                "body"
            )

        if not missing_fields:

            return request

        prompt = """
You are the email drafting component of a production
Gmail AI assistant.

The user's intent has already been classified by another
AI component as DRAFT.

Your job is ONLY to complete the missing email fields.

Rules:

1. Understand the user's meaning.
2. Generate only the missing fields.
3. Never invent personal facts.
4. Never invent names.
5. Never invent dates.
6. Never invent commitments.
7. Never invent meeting details.
8. Never invent amounts.
9. Preserve any supplied subject exactly.
10. Preserve any supplied body exactly.
11. Do not invent a recipient.
12. Do not invent an email address.
13. The recipient may be missing because this is only a draft.
14. Keep the generated email natural and useful.
15. Return ONLY valid JSON.

Required JSON:

{
  "subject": "...",
  "body": "..."
}

User request:
"""

        payload = {
            "user_request": user_text,
            "existing_subject": (
                subject
                if subject
                else None
            ),
            "existing_body": (
                body
                if body
                else None
            ),
            "missing_fields": missing_fields,
        }

        prompt += json.dumps(
            payload,
            ensure_ascii=False,
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
                max_tokens=700,
                temperature=0.2,
                top_p=1.0,
            )
        )

        generated_subject = (
            response.get("subject")
            if isinstance(
                response,
                dict,
            )
            else None
        )

        generated_body = (
            response.get("body")
            if isinstance(
                response,
                dict,
            )
            else None
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
                "Bedrock could not generate a draft subject."
            )

        if not body:
            raise RuntimeError(
                "Bedrock could not generate a draft body."
            )

        return GmailIntentRequest(
            intent=GmailIntent.DRAFT,
            query=request.query,
            message_reference=request.message_reference,
            recipient=request.recipient,
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
                **self._metadata(request),
                "draft_fields_completed": True,
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
    # SEND COMPLETION USING BEDROCK
    # =========================================================

    def _complete_send_request(
''',

    "added Bedrock draft completion",
)


# -------------------------------------------------------------
# Update pending confirmation handler.
# -------------------------------------------------------------

replace_once(
    ORCHESTRATOR,

    '''        if decision == "confirm":
            pending = self.state.get_pending_action()

            try:
                result = self.executor.confirm_pending_delete(
                    account_email=account_email
                )
            except ValueError as exc:
''',

    '''        if decision == "confirm":

            pending = (
                self.state.get_pending_action()
            )

            pending_action = (
                pending.get("action")
                if pending
                else None
            )

            try:

                if pending_action == "delete":

                    result = (
                        self.executor.confirm_pending_delete(
                            account_email=account_email
                        )
                    )

                    confirmation_intent = (
                        GmailIntent.DELETE
                    )

                elif pending_action == "draft_send":

                    result = (
                        self.executor.confirm_pending_draft(
                            account_email=account_email
                        )
                    )

                    confirmation_intent = (
                        GmailIntent.SEND
                    )

                else:

                    raise ValueError(
                        "The pending Gmail operation "
                        "could not be identified."
                    )

            except ValueError as exc:
''',

    "updated confirmation execution",
)


# -------------------------------------------------------------
# Replace hardcoded DELETE intent in accepted confirmation.
# -------------------------------------------------------------

replace_once(
    ORCHESTRATOR,

    '''                request=GmailIntentRequest(
                    intent=GmailIntent.DELETE,
                    raw_text=text,
                ),
                result=result,
''',

    '''                request=GmailIntentRequest(
                    intent=confirmation_intent,
                    raw_text=text,
                ),
                result=result,
''',

    "updated accepted confirmation intent",
)


# -------------------------------------------------------------
# There are two occurrences in the confirmation method.
# The first replacement above changes the accepted branch.
# Change the rejection branch separately.
# -------------------------------------------------------------

replace_once(
    ORCHESTRATOR,

    '''            user_message = self._generate_user_response(
                user_text=text,
                request=GmailIntentRequest(
                    intent=GmailIntent.DELETE,
                    raw_text=text,
                ),
                result=cancelled_result,
            )

            return {
                "success": True,
                "intent": GmailIntent.DELETE.value,
''',

    '''            user_message = self._generate_user_response(
                user_text=text,
                request=GmailIntentRequest(
                    intent=(
                        GmailIntent.SEND
                        if pending
                        and pending.get("action")
                        == "draft_send"
                        else GmailIntent.DELETE
                    ),
                    raw_text=text,
                ),
                result=cancelled_result,
            )

            return {
                "success": True,
                "intent": (
                    GmailIntent.SEND.value
                    if pending
                    and pending.get("action")
                    == "draft_send"
                    else GmailIntent.DELETE.value
                ),
''',

    "updated rejected confirmation intent",
)


# -------------------------------------------------------------
# Update Bedrock allowed intents.
# -------------------------------------------------------------

replace_once(
    ORCHESTRATOR,

    '''Allowed intent values:
search, read, send, reply, star, unstar, delete, mark_read, mark_unread, thread, unknown
''',

    '''Allowed intent values:
search, read, draft, send, reply, star, unstar, delete, mark_read, mark_unread, thread, unknown
''',

    "added DRAFT to Bedrock intent contract",
)


# -------------------------------------------------------------
# Add DRAFT planner instructions.
# -------------------------------------------------------------

replace_once(
    ORCHESTRATOR,

    '''For SEND:
- Return a new-message request only.
- Extract recipient, subject, body, cc and bcc only when present.
- Do not invent missing values.

For REPLY:
''',

    '''For DRAFT:
- The user wants an email prepared but not sent yet.
- Extract recipient, subject, body, cc and bcc only when present.
- A recipient is optional because the user may only want a draft.
- If subject/body are missing, leave them null.
- Do not invent recipient addresses.
- Do not send or imply that the email has been sent.

For SEND:
- Return a new-message request only.
- Extract recipient, subject, body, cc and bcc only when present.
- Do not invent missing values.

For REPLY:
''',

    "added DRAFT planner instructions",
)


# =============================================================
# Final
# =============================================================

print()
print("=" * 70)
print("DRAFT FLOW UPDATE COMPLETED")
print("=" * 70)
print()
print("Updated:")
print("  app/agent/intent.py")
print("  app/agent/state.py")
print("  app/agent/executor.py")
print("  app/agent/orchestrator.py")
print()
print("Backups:")
print("  *.before_draft")
print()
print("IMPORTANT:")
print("DRAFT is now a real structured intent.")
print("No natural-language phrase mapping was added.")
print("Bedrock remains responsible for understanding the user's meaning.")
print()
