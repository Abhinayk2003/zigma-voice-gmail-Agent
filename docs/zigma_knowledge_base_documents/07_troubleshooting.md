# Zigma Voice Gmail Agent — Troubleshooting

## Gmail authentication failure

Gmail operations require an authenticated Gmail account.

If credentials cannot be found or are invalid, the application should return an authentication-related error instead of attempting to execute the Gmail operation.

Account identity should come from the authenticated session or request context.

It must not be hard-coded.

## Unresolvable message reference

If a user says:

"Read that email."

but there is no valid selected or recoverable message context, the application should ask the user to identify the message or perform a new search.

The system must not invent a Gmail message ID.

## Delete confirmation problems

If a delete request returns confirmation_required=true, the deletion has not happened yet.

The application must return a confirmation request.

Only explicit confirmation should execute the destructive action.

## Pending confirmation across processes

Pending confirmation actions are persisted in PostgreSQL.

If a delete request is made in one process and confirmation is received in another, the second process can recover the pending action from durable conversation/action storage.

## Conversation persistence

PostgreSQL stores conversation messages and actions so application history can survive process boundaries.

Live in-memory ConversationState is useful for active context, while durable database storage provides persistence.

## Bedrock intent parsing

Amazon Bedrock is responsible for interpreting natural-language intent and returning structured information.

If a model response contains a reference type and a separate position value, application parsing must combine those fields into a structured message reference.

Application validation should reject unsupported or malformed intent values.

## False success responses

The language model must not be trusted as the source of truth for whether a Gmail operation succeeded.

The application/Gmail operation result is authoritative.

For example, if a delete action requires confirmation, the response must not say the email was deleted.

## Database

The application uses SQLAlchemy to connect to PostgreSQL.

The database layer contains:

- users
- gmail_accounts
- conversations
- conversation_messages
- conversation_actions

The production database location is configurable through the application's database configuration.

## General diagnostic principle

When troubleshooting, verify the layers separately:

1. Authentication
2. Intent parsing
3. Conversation context
4. Database persistence
5. Gmail API operation
6. Final response generation

This makes it easier to determine which component is responsible for a failure.
