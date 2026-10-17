-- =============================================================================
-- Migration 004: Departments, Teams, Projects, Memberships & RLS Security Repair
-- IntentLock Persistence Foundation & Authoritative Entity Relations
-- =============================================================================

-- 1. Departments Table
CREATE TABLE IF NOT EXISTS departments (
    department_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'Active',
    department_type VARCHAR(64) DEFAULT 'Technical',
    head_id VARCHAR(32) REFERENCES employees(employee_id) ON DELETE SET NULL,
    executive_owner_id VARCHAR(32) REFERENCES employees(employee_id) ON DELETE SET NULL,
    parent_department_id VARCHAR(32) REFERENCES departments(department_id) ON DELETE SET NULL,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_departments_head ON departments(head_id);
CREATE INDEX IF NOT EXISTS idx_departments_exec ON departments(executive_owner_id);

-- 2. Teams Table
CREATE TABLE IF NOT EXISTS teams (
    team_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    department VARCHAR(64) NOT NULL,
    department_id VARCHAR(32) REFERENCES departments(department_id) ON DELETE SET NULL,
    team_lead_id VARCHAR(32) REFERENCES employees(employee_id) ON DELETE SET NULL,
    manager_id VARCHAR(32) REFERENCES employees(employee_id) ON DELETE SET NULL,
    location VARCHAR(64) DEFAULT 'Bengaluru',
    responsibilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    technologies JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'Active',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_teams_dept_id ON teams(department_id);
CREATE INDEX IF NOT EXISTS idx_teams_manager ON teams(manager_id);
CREATE INDEX IF NOT EXISTS idx_teams_lead ON teams(team_lead_id);

-- 3. Projects Table
CREATE TABLE IF NOT EXISTS projects (
    project_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'Active',
    project_type VARCHAR(64) DEFAULT 'Product Development',
    owning_team_id VARCHAR(32) REFERENCES teams(team_id) ON DELETE SET NULL,
    owning_department_id VARCHAR(32) REFERENCES departments(department_id) ON DELETE SET NULL,
    project_manager_id VARCHAR(32) REFERENCES employees(employee_id) ON DELETE SET NULL,
    project_lead_id VARCHAR(32) REFERENCES employees(employee_id) ON DELETE SET NULL,
    department VARCHAR(64),
    technologies JSONB NOT NULL DEFAULT '[]'::jsonb,
    objectives JSONB NOT NULL DEFAULT '[]'::jsonb,
    responsibilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    start_date VARCHAR(32),
    target_end_date VARCHAR(32),
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_team ON projects(owning_team_id);
CREATE INDEX IF NOT EXISTS idx_projects_dept ON projects(owning_department_id);
CREATE INDEX IF NOT EXISTS idx_projects_pm ON projects(project_manager_id);

-- 4. Project Memberships & Allocations
CREATE TABLE IF NOT EXISTS project_memberships (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(32) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    employee_id VARCHAR(32) NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    role VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'Active',
    allocation_percent INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_proj_emp UNIQUE (project_id, employee_id)
);

CREATE INDEX IF NOT EXISTS idx_proj_mem_emp ON project_memberships(employee_id);
CREATE INDEX IF NOT EXISTS idx_proj_mem_prj ON project_memberships(project_id);

-- 5. Foreign Key & Relationship Columns on Employees & Tickets
ALTER TABLE employees ADD COLUMN IF NOT EXISTS team_id VARCHAR(32) REFERENCES teams(team_id) ON DELETE SET NULL;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS department_id VARCHAR(32) REFERENCES departments(department_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_employees_team ON employees(team_id);
CREATE INDEX IF NOT EXISTS idx_employees_dept_id ON employees(department_id);

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS project_id VARCHAR(32) REFERENCES projects(project_id) ON DELETE SET NULL;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS department_id VARCHAR(32) REFERENCES departments(department_id) ON DELETE SET NULL;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS owner_team_id VARCHAR(32) REFERENCES teams(team_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tickets_project_id ON tickets(project_id);
CREATE INDEX IF NOT EXISTS idx_tickets_dept_id ON tickets(department_id);
CREATE INDEX IF NOT EXISTS idx_tickets_team_id ON tickets(owner_team_id);

-- 6. Ticket Revision Metadata Entry
INSERT INTO directory_metadata (key, revision, updated_at)
VALUES ('ticket_revision', 1, NOW())
ON CONFLICT (key) DO NOTHING;

-- 7. Security & RLS Hardening for New and Existing Tables
ALTER TABLE departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_memberships ENABLE ROW LEVEL SECURITY;

-- Revoke browser direct access to new tables
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON departments, teams, projects, project_memberships FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON departments, teams, projects, project_memberships FROM authenticated;
    END IF;
END $$;

-- Reference data read policies (public directory reference info is readable)
CREATE POLICY read_departments ON departments FOR SELECT TO PUBLIC USING (true);
CREATE POLICY read_teams ON teams FOR SELECT TO PUBLIC USING (true);
CREATE POLICY read_projects ON projects FOR SELECT TO PUBLIC USING (true);
CREATE POLICY read_project_memberships ON project_memberships FOR SELECT TO PUBLIC USING (true);

-- Maintenance policies on organizational structure (strict: non-empty system actor required)
CREATE POLICY manage_departments ON departments FOR ALL TO PUBLIC
    USING (current_setting('intentlock.actor_id', true) = 'system')
    WITH CHECK (current_setting('intentlock.actor_id', true) = 'system');

CREATE POLICY manage_teams ON teams FOR ALL TO PUBLIC
    USING (current_setting('intentlock.actor_id', true) = 'system')
    WITH CHECK (current_setting('intentlock.actor_id', true) = 'system');

CREATE POLICY manage_projects ON projects FOR ALL TO PUBLIC
    USING (current_setting('intentlock.actor_id', true) = 'system')
    WITH CHECK (current_setting('intentlock.actor_id', true) = 'system');

CREATE POLICY manage_memberships ON project_memberships FOR ALL TO PUBLIC
    USING (current_setting('intentlock.actor_id', true) = 'system')
    WITH CHECK (current_setting('intentlock.actor_id', true) = 'system');

-- 8. Repair Permissive Missing/Empty Actor Bypass on Existing Tables
-- Drop vulnerable policies from migration 003 that allowed NULL or empty actor bypass
DROP POLICY IF EXISTS actor_scoped_employee_update ON employees;
DROP POLICY IF EXISTS actor_scoped_employee_insert ON employees;
DROP POLICY IF EXISTS actor_scoped_ticket_update ON tickets;
DROP POLICY IF EXISTS actor_scoped_ticket_insert ON tickets;
DROP POLICY IF EXISTS actor_scoped_drafts ON action_drafts;
DROP POLICY IF EXISTS actor_scoped_grants ON action_grants;
DROP POLICY IF EXISTS actor_scoped_events ON action_events;
DROP POLICY IF EXISTS actor_scoped_sessions ON voice_sessions;

-- Re-create with strict actor enforcement (empty/missing actor FAILS CLOSED)
CREATE POLICY actor_scoped_employee_update ON employees FOR UPDATE TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = employee_id
            OR current_setting('intentlock.actor_id', true) = 'system'
        )
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = employee_id
            OR current_setting('intentlock.actor_id', true) = 'system'
        )
    );

CREATE POLICY actor_scoped_employee_insert ON employees FOR INSERT TO PUBLIC
    WITH CHECK (
        current_setting('intentlock.actor_id', true) = 'system'
    );

CREATE POLICY actor_scoped_ticket_update ON tickets FOR UPDATE TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
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
        )
    );

CREATE POLICY actor_scoped_ticket_insert ON tickets FOR INSERT TO PUBLIC
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
            OR requester_id = current_setting('intentlock.actor_id', true)
            OR created_by = current_setting('intentlock.actor_id', true)
        )
    );

CREATE POLICY actor_scoped_drafts ON action_drafts FOR ALL TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
            OR actor_id = current_setting('intentlock.actor_id', true)
        )
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
            OR actor_id = current_setting('intentlock.actor_id', true)
        )
    );

CREATE POLICY actor_scoped_grants ON action_grants FOR ALL TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
            OR actor_id = current_setting('intentlock.actor_id', true)
        )
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
            OR actor_id = current_setting('intentlock.actor_id', true)
        )
    );

CREATE POLICY actor_scoped_events ON action_events FOR ALL TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
            OR actor_id = current_setting('intentlock.actor_id', true)
        )
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
            OR actor_id = current_setting('intentlock.actor_id', true)
        )
    );

CREATE POLICY actor_scoped_sessions ON voice_sessions FOR ALL TO PUBLIC
    USING (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
            OR employee_id = current_setting('intentlock.actor_id', true)
        )
    )
    WITH CHECK (
        current_setting('intentlock.actor_id', true) IS NOT NULL
        AND current_setting('intentlock.actor_id', true) != ''
        AND (
            current_setting('intentlock.actor_id', true) = 'system'
            OR employee_id = current_setting('intentlock.actor_id', true)
        )
    );
