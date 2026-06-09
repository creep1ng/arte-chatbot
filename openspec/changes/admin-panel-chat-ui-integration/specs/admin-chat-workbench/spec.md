# Admin Chat Workbench Specification

## Purpose

Define the authenticated admin Chat UI as the single supported browser workbench
for testing customer conversations, reviewing conversation history, and opening
datasheet sources without exposing chat secrets.

## Requirements

### Requirement: Authenticated Admin Chat Access

The system MUST provide chat access only as an authenticated admin-panel feature
and MUST preserve all existing admin features.

#### Scenario: Admin opens chat workbench

- GIVEN an authenticated admin user
- WHEN the user navigates to the admin chat feature
- THEN the chat workbench is displayed inside the admin panel
- AND existing admin routes remain reachable

#### Scenario: Unauthenticated access is blocked

- GIVEN a user without valid admin authentication
- WHEN the user attempts to open the admin chat feature
- THEN access is denied or redirected to admin login

### Requirement: Secure Chat Requests

The browser MUST NOT store or require `CHAT_API_KEY`; chat requests SHALL use the
admin-authenticated access path.

#### Scenario: Chat request uses admin authentication

- GIVEN an authenticated admin user has typed a prompt
- WHEN the user sends the prompt
- THEN the request is accepted through an admin-authenticated path
- AND no chat API key is read from or written to browser storage

### Requirement: ChatGPT-like Conversation Layout

The workbench MUST use a ChatGPT-like layout with a left recent-conversations
sidebar, selected conversation restore, right-aligned user messages, assistant
responses in the main/left region, and a bottom composer.

#### Scenario: Existing conversation restores history

- GIVEN recent conversations exist in admin-scoped browser storage
- WHEN the user selects a recent conversation
- THEN the full saved message history is restored in the thread

#### Scenario: Message alignment is distinct

- GIVEN a conversation contains user and assistant messages
- WHEN the thread is rendered
- THEN user messages are visually highlighted and right-aligned
- AND assistant responses occupy the main/left response region

### Requirement: Admin Chat Theme Palette

The chat UI MUST apply Smoky Black `#0F0F0F` and Amber `#FFC200` as primary
colors, supported by Dark Silver `#736F72`, Platinum `#D8DDDE`, and Caribbean
Green `#09BC8A` for secondary, surface, and state accents.

#### Scenario: Theme tokens are visible in chat UI

- GIVEN the admin chat workbench is displayed
- WHEN primary surfaces, actions, and status accents are visible
- THEN the required palette is used consistently

### Requirement: Split Assistant Message Rendering

The workbench MUST render `messages` as separate assistant messages when present
and MUST fall back to `response` when `messages` is absent or empty.

#### Scenario: Split response is rendered separately

- GIVEN a chat result includes non-empty `messages`
- WHEN the result is added to the thread
- THEN each entry is shown as a separate assistant message

#### Scenario: Legacy response fallback

- GIVEN a chat result has no usable `messages`
- WHEN the result is added to the thread
- THEN the `response` value is shown as the assistant message

### Requirement: Datasheet Source Modal

The workbench MUST show a datasheet-source action only when source documents
exist, and the modal SHALL list deduplicated datasheets using admin-authorized
open/download flows.

#### Scenario: Sources open in modal

- GIVEN a chat response includes duplicate or unique `source_documents`
- WHEN the user selects `Ver fichas técnicas`
- THEN a modal lists each source once by path or filename
- AND each listed source can be opened or downloaded through admin authorization

#### Scenario: No sources hides action

- GIVEN a chat response has no source documents
- WHEN the response is rendered
- THEN the datasheet-source action is not shown
