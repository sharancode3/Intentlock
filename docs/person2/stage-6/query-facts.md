# Person 2 — Stage 6: Authorized Queries and Deterministic Facts

## 1. Baseline and Scope
- **Owner**: Sharan (Person 2)
- **Role**: Query specification, deterministic calculations over authorized data, and internal FactBundles.
- **Teammate Boundaries**:
  - Person 1 owns database connections, Supabase queries, and authorization scoping.
  - Person 3 owns frontend renderers and charts.
- **Preflight Baseline**: Git commit `d189664` with Stages 0–5 passing (76 tests).

---

## 2. Implemented Architecture & Behaviors

### A. Normalized Query Specification
- `NormalizedQuerySpec` enforces a typed, safe query contract:
  - Specifies `resource_domain`, `requested_operation`, `root_target_id`, `scope`, `filters`, `dates`, `grouping`, and `metric`.
  - Strictly prohibits arbitrary SQL, executable expressions, and model-controlled permissions.

### B. Authorize Before Aggregating
- Strict architectural order:
  $$\text{Resolve Request} \to \text{Authorize Scope} \to \text{Fetch Data} \to \text{Calculate Facts} \to \text{Project Allowlist} \to \text{Build Result}$$
- Aggregate queries evaluate only permitted records. Totals reflect authorized scope, never silent org-wide aggregation.

### C. Internal Fact Bundle
- `FactBundle` represents the immutable source of truth for downstream presentation:
  - Query specification and metadata.
  - Calculated aggregates and breakdowns.
  - Coverage description and explicit as-of timestamp.
  - Missing and unknown counts.
  - Bounded allowlisted records.
  - Truthfulness notes (e.g. unknown offices or missing SLA targets).

### D. Deterministic Metrics & Truthfulness Invariants
1. **SLA Metrics with Injectable Clock**:
   - `calculate_sla_metrics(tickets, metric_type, now=None)`:
     - Uses an injectable clock for reproducible evaluations.
     - Classifies overdue tickets (`Breached` or past `due_date`).
     - **Non-zero Denominator Guarantee**: If zero tickets have defined SLAs, reports `status="no_eligible_data"`, `rate=None`, and human-readable string `"N/A (No eligible SLA targets)"`. It **never** reports `0%` as a substitute for unknown.
2. **Resolution-Time Metrics**:
   - Evaluates only completed tickets (`status in ("Resolved", "Closed")`).
   - Rejects negative intervals and excludes unresolved tickets.
   - Computes average, median, min, and max hours.
3. **Time-Series Truthfulness**:
   - `calculate_created_date_time_series()` groups strictly by ticket creation date.
   - Labeled explicitly as "Tickets created by date" — **never** claimed as historical backlog or resolution trend.
4. **Dynamic Location Headcount**:
   - Uses dynamic location coverage from `entity_scope_resolver`.
   - An unknown/uncovered office (e.g. Tulum) returns `unknown_location` status and coverage explanation, **never** a fabricated zero headcount or silent fallback to Bengaluru.
5. **Allowlist Field Projections**:
   - `project_ticket_record()` and `project_employee_record()` strictly allowlist safe presentation fields.
   - Credentials, password hashes, salary bands, internal database IDs, and raw policy objects are stripped before reaching the UI/narration layers.
6. **Query Outage Handling**:
   - Database/repository exceptions set `is_outage_or_error=True` with explicit `error_message`, preserving truthfulness instead of masquerading as an empty dataset.

---

## 3. Modules Changed & Interfaces
1. **`backend/services/query_fact_service.py`** (New):
   - `NormalizedQuerySpec`: Dataclass.
   - `FactBundle`: Dataclass.
   - `QueryFactService`:
     - `project_ticket_record(ticket)`
     - `project_employee_record(emp)`
     - `calculate_ticket_breakdown(tickets, group_by)`
     - `calculate_created_date_time_series(tickets)`
     - `calculate_resolution_time_metrics(tickets)`
     - `calculate_sla_metrics(tickets, metric_type, now=None)`
     - `calculate_team_headcount(team_members, location_filter, department_filter)`
     - `build_fact_bundle(query_spec, authorized_records, scope_description, ...)`

---

## 4. Test Verification
- Test file: `tests/test_query_facts.py`
- Test count: **10 passed in 0.44s**
- Total Person 2 test count: **86 passed**.

---

## 5. Handoff Requests & Remaining Dependencies
- **Person 1 (Persistence & Scoping)**:
  - Wire repository queries through `NormalizedQuerySpec` to enforce consistent authorization boundaries.
  - Return revision tags (`data_revision`) to support FactBundle cache invalidation.
- **Person 3 (Frontend)**:
  - Render `FactBundle.truncation_metadata` and truthfulness notes when present.
