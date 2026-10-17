-- IntentLock Migration 003: Actor-Aware Row Level Security (RLS) Policies
-- Enforces per-actor authorization boundaries in PostgreSQL based on transaction-local intentlock.actor_id.

-- 1. Drop old permissive policies
DROP POLICY IF EXISTS service_all_employees ON employees;
DROP POLICY IF EXISTS service_all_tickets ON tickets;
DROP POLICY IF EXISTS service_all_mappings ON speaker_mappings;
DROP POLICY IF EXISTS service_all_sessions ON voice_sessions;
DROP POLICY IF EXISTS service_all_drafts ON action_drafts;
DROP POLICY IF EXISTS service_all_grants ON action_grants;
DROP POLICY IF EXISTS service_all_events ON action_events;
DROP POLICY IF EXISTS service_all_idempotency ON idempotency_records;
DROP POLICY IF EXISTS service_all_metadata ON directory_metadata;

-- 2. Employees:
-- Anyone (including directory search) can read public directory fields.
-- Only the actor themselves (or system maintenance) can update an employee row.
CREATE POLICY actor_scoped_employee_select ON employees FOR SELECT TO PUBLIC
    USING (true);

CREATE POLICY actor_scoped_employee_update ON employees FOR UPDATE TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR current_setting('intentlock.actor_id', true) = employee_id
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR current_setting('intentlock.actor_id', true) = employee_id
    );

CREATE POLICY actor_scoped_employee_insert ON employees FOR INSERT TO PUBLIC
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
    );

-- 3. Tickets:
-- Readable by requester, assignee, creator, direct manager, executive (EMP-4002/L5/L6), or system/unauthenticated maintenance.
CREATE POLICY actor_scoped_ticket_select ON tickets FOR SELECT TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR requester_id = current_setting('intentlock.actor_id', true)
        OR assignee_id = current_setting('intentlock.actor_id', true)
        OR created_by = current_setting('intentlock.actor_id', true)
        OR EXISTS (
            SELECT 1 FROM employees
            WHERE employee_id = tickets.requester_id
              AND manager_id = current_setting('intentlock.actor_id', true)
        )
        OR current_setting('intentlock.actor_id', true) IN (
            SELECT employee_id FROM employees WHERE organizational_level IN ('Executive', 'L5', 'L6', 'CTO', 'CEO')
        )
    );

CREATE POLICY actor_scoped_ticket_update ON tickets FOR UPDATE TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR requester_id = current_setting('intentlock.actor_id', true)
        OR assignee_id = current_setting('intentlock.actor_id', true)
        OR created_by = current_setting('intentlock.actor_id', true)
        OR EXISTS (
            SELECT 1 FROM employees
            WHERE employee_id = tickets.requester_id
              AND manager_id = current_setting('intentlock.actor_id', true)
        )
        OR current_setting('intentlock.actor_id', true) IN (
            SELECT employee_id FROM employees WHERE organizational_level IN ('Executive', 'L5', 'L6', 'CTO', 'CEO')
        )
    );

CREATE POLICY actor_scoped_ticket_insert ON tickets FOR INSERT TO PUBLIC
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR requester_id = current_setting('intentlock.actor_id', true)
        OR created_by = current_setting('intentlock.actor_id', true)
    );

-- 4. Protected Action Drafts, Grants, and Events:
-- Scoped strictly to the actor asserting the action (or system maintenance).
CREATE POLICY actor_scoped_drafts ON action_drafts FOR ALL TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR actor_id = current_setting('intentlock.actor_id', true)
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR actor_id = current_setting('intentlock.actor_id', true)
    );

CREATE POLICY actor_scoped_grants ON action_grants FOR ALL TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR actor_id = current_setting('intentlock.actor_id', true)
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR actor_id = current_setting('intentlock.actor_id', true)
    );

CREATE POLICY actor_scoped_events ON action_events FOR ALL TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR actor_id = current_setting('intentlock.actor_id', true)
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR actor_id = current_setting('intentlock.actor_id', true)
    );

-- 5. Voice Sessions:
CREATE POLICY actor_scoped_sessions ON voice_sessions FOR ALL TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR employee_id = current_setting('intentlock.actor_id', true)
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NULL
        OR current_setting('intentlock.actor_id', true) = ''
        OR current_setting('intentlock.actor_id', true) = 'system'
        OR employee_id = current_setting('intentlock.actor_id', true)
    );

-- 6. Infrastructure tables:
CREATE POLICY system_speaker_mappings ON speaker_mappings FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY system_idempotency ON idempotency_records FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY system_metadata ON directory_metadata FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
