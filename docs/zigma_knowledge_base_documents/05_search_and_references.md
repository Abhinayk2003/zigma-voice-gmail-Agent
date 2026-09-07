# Zigma Voice Gmail Agent — Search and Message References

## Search results

A Gmail search produces a dynamically retrieved set of messages.

Users can refer to messages within that result set by natural-language position.

Examples:

- "first email"
- "second email"
- "third email"
- "the latest email"

## Reference types

The application supports common reference concepts including:

- Position
- Current
- Previous
- Latest
- None

## Position references

A position reference identifies a message by its position in the current result set.

Examples:

"first email" → position 1

"second email" → position 2

"3rd email" → position 3

The application resolves the position against actual Gmail results.

## Current references

Natural-language references such as:

- "that email"
- "same email"
- "the current email"

can refer to the currently selected message when application context contains a valid selection.

## Previous references

A reference such as "previous email" or "previous one" can refer to the previous relevant message or selection according to application conversation state.

## Latest references

A reference such as "latest email" or "newest email" identifies the latest applicable message according to the current Gmail result context.

## Deterministic resolution

The language model can identify the user's intended reference concept, but the application resolves the actual Gmail message.

The language model must never generate or guess a Gmail message ID or thread ID.

## Missing context

If a reference cannot be resolved because the required conversation or search context is unavailable, the application should ask the user for clarification rather than inventing a target.

## Dynamic search

Search criteria should be derived from the user's request and application logic.

Sender names, email addresses, dates, subjects, and other search values must not be hard-coded.
