# IntentLock — Person 2 Integration Requests for Person 3 (Frontend, Renderers & Speech Owner)
**Author:** Sharan (Person 2) — Intelligence, Semantic Planning & Results  
**Baseline Commit:** `d189664ddfe789da0b22e1269e5ba0d42fdb4bf6`  
**Date:** 2026-10-17  
**Status:** Stage 1 Contract Alignment  

---

## Overview

Person 2 owns semantic parsing, natural language intent modeling, conversation context state, and structured result block generation.  
Person 3 owns the React frontend (`frontend/src/**`), card renderer components, user interactions (clicks and speech), and event dispatching.

To enable follow-up queries on selected entities, honest feedback on ambiguous queries, and active filter visualization, Person 2 requests the following three integration updates from Person 3.

---

## Request 1: Emit `select_employee` Action on Tree Node and Table Row Clicks

### 1. Concrete Need
When an authorized user views an organization tree (`OrgTreeCard`) or an employee directory table (`DataTableCard`), clicking on an individual employee should establish that employee as the active context target for follow-up voice queries (e.g. *"Show their open tickets"*, *"Who is their manager?"*).  
Currently, `LiveApp.tsx` handles ticket selection via `select_ticket`, but does not yet handle employee selection.

### 2. Current Call in `frontend/src/LiveApp.tsx` (Lines 288–294)
```typescript
const handleResultAction = (actionVerb: string, parameters: Record<string, unknown>) => {
  if (actionVerb === 'select_ticket') {
    const ticketId = String(parameters.ticket_id || '');
    setSelectedTicketId(ticketId);
  }
};
```

### 3. Proposed Signature & Handler Logic
```typescript
// Proposed update in LiveApp.tsx:
const [selectedEmployeeId, setSelectedEmployeeId] = useState<string | null>(null);

const handleResultAction = (actionVerb: string, parameters: Record<string, unknown>) => {
  if (actionVerb === 'select_ticket') {
    const ticketId = String(parameters.ticket_id || '');
    setSelectedTicketId(ticketId);
  } else if (actionVerb === 'select_employee') {
    const employeeId = String(parameters.employee_id || '');
    setSelectedEmployeeId(employeeId);
  }
};

// When sending subsequent voice/text turns, include selectedEmployeeId in payload if present:
// { utterance, session_token, selected_ticket_id, selected_employee_id }
```

And in `frontend/src/components/renderers/OrgTreeCard.tsx` and `DataTableCard.tsx`:
```typescript
// On employee node or row click:
onAction?.('select_employee', { employee_id: node.id });
```

### 4. Error Semantics
- If `parameters.employee_id` is missing or undefined, do not modify `selectedEmployeeId`.
- Clicking outside or clearing selection should reset `selectedEmployeeId` to `null`.

### 5. Contract Fixture Reference
- `tests/fixtures/person2/selected_employee_followup.json`
  - Demonstrates state transition where `selected_id="EMP-1001"` resolves relative follow-up requests.

### 6. What Remains Mocked
In Person 2 unit tests, UI click events are simulated by passing `selected_id` or setting `ConversationState.selected_employee_id`.

### 7. Dependency
Required for **Person 2 Stage 5** (Context-Aware Entity Follow-Up).

---

## Request 2: Render Amber "Clarification Needed" Card on `status="clarification"`

### 1. Concrete Need
Previously, queries requiring clarification (e.g. asking for headcount in an unknown location like "Tulum", or supplying an ambiguous name) fell back to `PUBLIC_FAQ` with a green `status="success"` banner.  
This produced a misleading visual state where the user saw green success despite the system failing to fulfill the request.  
The backend now emits `status="clarification"` with honest reason codes (`UNRESOLVED_LOCATION`, `AMBIGUOUS_PERSON_NAME`). The frontend needs a dedicated visual presentation for clarification turns.

### 2. Current Behavior in Frontend
- Frontend treats turns as binary: `success` (emerald card) or `error` (red toast).
- Clarifications with `PUBLIC_FAQ` are styled in emerald green `#10B981`.

### 3. Proposed UI Contract
When `response.status === "clarification"`:
- Render an **amber status card** using WCAG AA compliant colors:
  - Header background: `bg-amber-50 border-amber-200`
  - Text: `text-amber-900`
  - Badge: `text-amber-700 bg-amber-100 border border-amber-300` with label `"Clarification Needed"`.
- Display the backend's `response.message` prominently.
- If `payload.suggested_prompts` exists, render clickable quick-reply chips (e.g., `["Bengaluru headcount", "List departments"]`).

### 4. Error Semantics
- If `response.status === "clarification"` has no payload, render a generic amber card containing `response.message`.

### 5. Contract Fixture Reference
- `tests/fixtures/person2/unknown_location.json` (`clarification_reason="UNRESOLVED_LOCATION"`)
- `tests/fixtures/person2/ambiguous_name.json` (`clarification_reason="AMBIGUOUS_PERSON_NAME"`)

### 6. What Remains Mocked
Verified via Person 2 offline dispatch tests in `tests/test_conversation_dispatch.py`.

### 7. Dependency
Required for **Person 2 Stage 3** (Semantic Routing & Location Clarification UX).

---

## Request 3: Active Filter Chips in `DataTableCard`

### 1. Concrete Need
When a user says *"Now filter to urgent priority only"*, the backend replaces the priority filter dimension while retaining the base dataset.  
Users need visual feedback indicating which filters are currently applied to the table.

### 2. Current Call in `DataTableCard.tsx`
- Renders table headers and rows directly from `payload.columns` and `payload.rows`.
- Does not render active filter badges.

### 3. Proposed Schema & Component Props
```typescript
export interface DataTablePayload {
  title?: string;
  columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, unknown>>;
  active_filters?: Record<string, string>; // e.g. { priority: "urgent", status: "open" }
}
```
When `active_filters` is present, render filter chips above the table grid:
- Chip format: `Priority: urgent [✕]`
- Clicking `[✕]` emits `onAction("clear_filter", { field: "priority" })`.

### 4. Error Semantics
- If `active_filters` is omitted, render the table as-is without chips.

### 5. Contract Fixture Reference
- `tests/fixtures/person2/priority_filter_replacement.json`

### 6. What Remains Mocked
In Person 2 tests, filter modification is tested against `ResultSnapshot.filters`.

### 7. Dependency
Required for **Person 2 Stage 5** (Context-Aware Filter Replacement & Refinement).
