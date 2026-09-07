# Zigma Voice Gmail Agent — Conversation Memory

## Purpose

Zigma maintains conversational context so users can refer naturally to information from earlier turns.

Examples:

- "that email"
- "same email"
- "the previous one"
- "the first email"
- "the second email"
- "the latest email"

## Memory layers

Zigma uses two complementary application-level memory layers.

### ConversationState

ConversationState maintains live conversational context during an active interaction.

It can be used to resolve the currently selected Gmail message and related context.

### PostgreSQL persistence

PostgreSQL provides durable storage for conversation history and application actions.

The database contains the following logical tables:

- users
- gmail_accounts
- conversations
- conversation_messages
- conversation_actions

Conversation messages store user and assistant interaction history.

Conversation actions store Gmail actions and their statuses, including pending confirmation actions.

## Reference resolution

The application, not the language model, determines which Gmail message a reference identifies.

For example:

User:
"Show me emails from Ravi."

User:
"Read the second email."

The application resolves "second email" to the second message in the current result set.

If the user then says:

"Reply to that email."

The application resolves "that email" using the current conversational context.

## Persistence principle

Conversation memory must be recoverable across application process boundaries when durable context is required.

Pending destructive actions are persisted so that a confirmation such as "yes" can be processed even if it occurs in a new application process.

## Important separation

Conversation memory is not the same as the Knowledge Base.

Conversation memory contains user-specific and interaction-specific context.

The Knowledge Base contains stable reference information about Zigma, its capabilities, policies, and documented behavior.

Actual Gmail messages remain live data retrieved through the Gmail API.

## Dynamic data rule

The system must not hard-code:

- Message IDs
- Thread IDs
- Sender addresses
- Recipient addresses
- User-specific subjects
- User-specific Gmail content

These values must be obtained dynamically.
