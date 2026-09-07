# Zigma Voice Gmail Agent — Confirmation Policy

## Destructive actions

Deleting an email is a destructive operation.

Zigma must require explicit user confirmation before executing a delete request.

## Required flow

### Step 1 — User requests deletion

Example:

"Delete the first email."

The application:

1. Interprets the request as a DELETE intent.
2. Resolves the referenced Gmail message.
3. Creates a pending confirmation action.
4. Does not execute the Gmail deletion.
5. Responds that confirmation is required.

### Step 2 — User confirms

Example:

"Yes."

The application:

1. Retrieves the pending action.
2. Resolves the stored target.
3. Executes the Gmail delete operation.
4. Moves the message to Trash.
5. Marks the pending action as completed/resolved.
6. Returns a success response.

### Step 3 — User cancels

Example:

"No."

The application:

1. Retrieves the pending action.
2. Does not execute the Gmail deletion.
3. Marks the pending action as cancelled/resolved.
4. Tells the user that the deletion was cancelled.

## Safety rule

Application state is authoritative for confirmation status.

The language model must not claim that a destructive operation was completed when the application result says confirmation is still required.

The application must enforce the confirmation gate before execution.

## Persistence

Pending confirmation actions are stored durably in PostgreSQL.

This allows confirmation to continue across Python process boundaries.

## Dynamic target information

The pending action stores the actual dynamically resolved Gmail information needed to safely execute the requested operation.

The system must never use hard-coded message IDs, thread IDs, recipients, senders, or subjects.
