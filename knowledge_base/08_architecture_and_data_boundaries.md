# Zigma Voice Gmail Agent — Architecture and Data Boundaries

## Core flow

The Zigma agent follows this conceptual flow:

User voice or text
→ intent understanding
→ structured Gmail intent
→ deterministic application resolution
→ GmailExecutor
→ Gmail API
→ conversation state and persistence
→ user response

## Component responsibilities

### Amazon Bedrock

Bedrock is used for natural-language understanding and structured intent interpretation.

It should determine what the user wants, not invent application identifiers.

### Orchestrator

The orchestrator coordinates the agent workflow.

It handles:

- Pending confirmation checks
- Intent processing
- Relative date resolution
- Conversation-context resolution
- Email completion where required
- Executor invocation
- Persistence
- Final response handling

### ConversationState

ConversationState maintains active conversational selections and context.

### ConversationService

ConversationService persists conversations, messages, and actions in PostgreSQL.

### GmailExecutor

GmailExecutor performs the requested Gmail operation after the application has resolved the target and validated the action.

### Gmail API

Gmail is the source of truth for live email data and Gmail identifiers.

## Data boundaries

### Knowledge Base

Contains stable project/reference information such as:

- Agent capabilities
- Gmail operation descriptions
- Reference-resolution rules
- Confirmation policy
- Architecture documentation
- Troubleshooting information

### PostgreSQL

Contains application-specific durable data such as:

- Users
- Gmail account associations
- Conversations
- Conversation messages
- Conversation actions

### Gmail

Contains live user email data, message IDs, thread IDs, labels, senders, recipients, subjects, and message content.

### Authentication/credential storage

OAuth credentials are handled by the authentication/credential layer and should not be placed in the Knowledge Base.

## Security principles

Never place the following in Knowledge Base documents:

- OAuth access tokens
- OAuth refresh tokens
- Client secrets
- Database passwords
- API keys
- Private credentials
- User-specific Gmail message IDs
- User-specific email contents

## Dynamic application principle

All user-specific and Gmail-specific identifiers must be obtained dynamically.

The Knowledge Base should provide rules and reference information, while the live application layers provide current user and Gmail data.
