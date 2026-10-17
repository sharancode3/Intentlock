# Person 2 — Stage 7: Dynamic Structured Outputs and Result Generation

## 1. Baseline and Scope
- **Owner**: Sharan (Person 2)
- **Role**: Presentation selection over facts, renderer compatibility verification, allowlisted payload projection, and deterministic text/speech/visual agreement.
- **Teammate Boundaries**:
  - Person 1 owns protected execution receipts and gateway route definitions.
  - Person 3 owns React renderers, `@xyflow/react` node layouts, and chart components.
- **Preflight Baseline**: Git commit `d189664` with Stages 0–6 passing (86 tests).

---

## 2. Implemented Architecture & Behaviors

### A. Presentation Selection Over Facts
- Deterministic compatibility engine evaluates visual mapping based on data cardinality and shape:
  - **1 Employee** $\to$ `EMPLOYEE_PROFILE` card.
  - **Multiple Employees** $\to$ `DATA_TABLE` with columns, rows, and total count.
  - **Headcount Query** $\to$ `TEAM_METRIC_CHART` (BAR).
  - **Reporting Relationships** $\to$ `ORG_TREE` with nodes, edges, and root.
  - **Ticket Records** $\to$ `TICKET_LIST` with tickets array and total count.
  - **Ticket Breakdown** $\to$ `TEAM_METRIC_CHART` (BAR or PIE).
  - **Time Series** $\to$ `TEAM_METRIC_CHART` (LINE or AREA).
  - **SLA Metrics** $\to$ `TEAM_METRIC_CHART` (BAR).

### B. Strict Compatibility & Fallback Rules
- **Pie Chart Composition Rule**:
  - Requires at least 2 distinct categories with non-zero counts.
  - If requested on a single-category dataset, falls back to `BAR` with an explicit `coverage_note` and spoken prefix (`"Pie chart requires at least 2 categories with positive counts; falling back to Bar chart."`).
- **Line/Area Chart Temporal Rule**:
  - Requires an ordered time dimension (`time_series`).
  - If requested on non-temporal data (e.g. priority breakdown), falls back to `BAR` without fabricating fake date points or silently switching metrics.
- **Profile Card Protection**:
  - Single employee profile requests cannot be forced into a chart; cleanly falls back to `EMPLOYEE_PROFILE`.

### C. Allowlist Field Projections
- Renderer payloads are built exclusively from projected allowlisted fields.
- Password hashes, session tokens, database row IDs, internal tracing metadata, and raw authorization policies are strictly stripped before serialization into `GenericResultBlock.payload`.

### D. Compound Reads and Mixed Outcomes
- `generate_compound_results()` builds distinct `GenericResultBlock` instances for each sub-query in compound requests.
- Preserves independent outcomes: if one sub-query succeeds and another fails or is denied, both results (`EMPLOYEE_PROFILE` and `DENIAL_BANNER`) are retained and articulated in narration.

### E. Text, Speech, and Visual Agreement
- `spoken_summary` is computed deterministically from `FactBundle.aggregates`.
- Exact numbers, category breakdowns, compliant/overdue percentages, and dates match across visual payload and speech text.
- Provides high-quality deterministic fallback narration when LLM services are offline or unavailable.

---

## 3. Modules Changed & Interfaces
1. **`backend/services/result_generator.py`** (New):
   - `PresentationDecision`: Dataclass (`chosen_block_type`, `chosen_view`, `is_compatible`, `fallback_applied`, `compatibility_note`).
   - `ResultGenerator`:
     - `select_presentation(bundle, requested_view)`
     - `generate_spoken_summary(bundle, decision)`
     - `generate_result(bundle, requested_view)`
     - `generate_compound_results(bundles)`

---

## 4. Test Verification
- Test file: `tests/test_dynamic_results.py`
- Test count: **10 passed in 0.46s**
- Total Person 2 test count: **96 passed**.

---

## 5. Handoff Requests & Remaining Dependencies
- **Person 1 (Gateway)**:
  - Wire `ResultGenerator.generate_result()` as the standard block constructor for `/voice/turn` and `/voice/result-action`.
- **Person 3 (Frontend)**:
  - Frontend renderers should render `coverage_note` from `TEAM_METRIC_CHART` payloads when fallback notifications are present.
