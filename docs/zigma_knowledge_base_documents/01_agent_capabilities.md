# Zigma Voice Gmail Agent — Agent Capabilities

## Overview

Zigma is a conversational Gmail agent that allows users to interact with Gmail using natural language. The agent can process text requests and can be integrated with voice input and multilingual responses.

The agent converts a natural-language request into a structured Gmail intent, resolves the required application context, performs the Gmail operation, and returns a conversational result.

## Supported Gmail capabilities

Zigma supports the following Gmail operations:

- Search emails
- Read emails
- Send emails
- Draft emails
- Reply to emails
- Star emails
- Unstar emails
- Delete emails
- Mark emails as read
- Mark emails as unread
- Work with email threads

## Conversational interaction

Users can express Gmail requests naturally rather than providing technical API parameters.

Examples include:

- "Show me emails from Ravi."
- "Read the first email."
- "Read the second one."
- "Reply to that email."
- "Star this email."
- "Delete the first email."

The application is responsible for resolving actual Gmail messages and identifiers.

## Responsibility boundaries

Amazon Bedrock is used for intent understanding and structured interpretation of the user's request.

Application code is responsible for deterministic business logic, including:

- Resolving Gmail message references
- Resolving relative dates
- Resolving conversation context
- Obtaining authenticated account identity
- Selecting actual Gmail messages
- Executing Gmail operations

Gmail message IDs and thread IDs must come from Gmail API results or application state. They must never be invented by the language model.

## Dynamic behavior

Zigma should remain dynamic and configurable.

The application must not hard-code:

- Gmail account addresses
- Recipient addresses
- Sender addresses
- Message IDs
- Thread IDs
- User-specific subjects
- User-specific message content

These values must come from authentication, Gmail data, user input, or application state.
