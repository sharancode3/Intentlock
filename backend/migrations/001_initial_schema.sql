-- =============================================================================
-- Migration 001: IntentLock Canonical Schema & Row-Level Security
-- Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026)
-- Author: IntentLock Engineering Team
-- =============================================================================

-- 1. Schema Migration History Ledger
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum VARCHAR(64) NOT NULL
);

-- 2. Directory Metadata & Invalidation Revision Tracking
CREATE TABLE IF NOT EXISTS directory_metadata (
    key VARCHAR(64) PRIMARY KEY,
    revision BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO directory_metadata (key, revision, updated_at)
VALUES ('directory_revision', 1, NOW())
ON CONFLICT (key) DO NOTHING;

-- 3. Canonical Employee Business Records
CREATE TABLE IF NOT EXISTS employees (
    employee_id VARCHAR(32) PRIMARY KEY,
    version INT NOT NULL DEFAULT 1,
    full_name VARCHAR(128) NOT NULL,
    preferred_name VARCHAR(128),
    work_email VARCHAR(128) NOT NULL,
    work_phone VARCHAR(64), -- Nullable contact number (preserves leading '+', format-checked)
    department VARCHAR(64) NOT NULL,
    designation VARCHAR(128) NOT NULL,
    organizational_level VARCHAR(32) NOT NULL,
    location VARCHAR(64) NOT NULL DEFAULT 'Bengaluru',
    work_mode VARCHAR(32) NOT NULL DEFAULT 'Hybrid',
    manager_id VARCHAR(32) REFERENCES employees(employee_id) ON DELETE SET NULL,
    skills JSONB NOT NULL DEFAULT '{}'::jsonb,
    projects JSONB NOT NULL DEFAULT '{}'::jsonb,
    experience JSONB NOT NULL DEFAULT '{}'::jsonb,
    education JSONB NOT NULL DEFAULT '[]'::jsonb,
    responsibilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    achievements JSONB NOT NULL DEFAULT '[]'::jsonb,
    research JSONB,
    executive_authority JSONB,
    policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employees_dept ON employees(department);
CREATE INDEX IF NOT EXISTS idx_employees_manager ON employees(manager_id);
CREATE INDEX IF NOT EXISTS idx_employees_location ON employees(location);

-- 4. Canonical Tickets & Action State
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id VARCHAR(32) PRIMARY KEY,
    version INT NOT NULL DEFAULT 1,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    ticket_type VARCHAR(64) NOT NULL,
    category VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    priority VARCHAR(32) NOT NULL,
    requester_id VARCHAR(32) NOT NULL,
    assignee_id VARCHAR(32),
    created_by VARCHAR(32) NOT NULL,
    department VARCHAR(64),
    project VARCHAR(64),
    document JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tickets_requester ON tickets(requester_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assignee ON tickets(assignee_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);

-- 5. Speaker Mappings (Detectif Voice Identity Links)
CREATE TABLE IF NOT EXISTS speaker_mappings (
    employee_id VARCHAR(32) PRIMARY KEY REFERENCES employees(employee_id) ON DELETE CASCADE,
    account_alias VARCHAR(64) NOT NULL,
    provider_speaker_id VARCHAR(128) NOT NULL UNIQUE,
    display_name VARCHAR(128),
    enrollment_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    sample_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mappings_speaker ON speaker_mappings(provider_speaker_id);

-- 6. Voice Sessions (Short-lived Opaque Verified State)
CREATE TABLE IF NOT EXISTS voice_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    employee_id VARCHAR(32) NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    full_name VARCHAR(128) NOT NULL,
    role VARCHAR(64) NOT NULL,
    department VARCHAR(64) NOT NULL,
    team_id VARCHAR(64),
    account_alias VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires ON voice_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_employee ON voice_sessions(employee_id);

-- 7. Action Drafts (Protected Proposals)
CREATE TABLE IF NOT EXISTS action_drafts (
    draft_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    actor_id VARCHAR(32) NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    operation VARCHAR(64) NOT NULL,
    ticket_id VARCHAR(32) NOT NULL, -- Target resource (ticket_id or employee_id)
    parameters JSONB NOT NULL,
    expected_version INT NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    readback TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(32) NOT NULL,
    receipt JSONB,
    proposal_digest VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_drafts_session_status ON action_drafts(session_id, status);

-- 8. Single-Use Action Grants
CREATE TABLE IF NOT EXISTS action_grants (
    grant_id VARCHAR(64) PRIMARY KEY,
    draft_id VARCHAR(64) NOT NULL UNIQUE REFERENCES action_drafts(draft_id) ON DELETE CASCADE,
    actor_id VARCHAR(32) NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    payload_hash VARCHAR(64) NOT NULL,
    evidence_digest VARCHAR(64) NOT NULL,
    expected_version INT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);

-- 9. Committed Action Audit Events
CREATE TABLE IF NOT EXISTS action_events (
    event_id VARCHAR(64) PRIMARY KEY,
    draft_id VARCHAR(64) NOT NULL UNIQUE REFERENCES action_drafts(draft_id) ON DELETE CASCADE,
    ticket_id VARCHAR(32) NOT NULL,
    actor_id VARCHAR(32) NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    operation VARCHAR(64) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    version INT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. Turn Delivery Idempotency Cache
CREATE TABLE IF NOT EXISTS idempotency_records (
    operation_key VARCHAR(128) PRIMARY KEY,
    audio_digest VARCHAR(64) NOT NULL,
    employee_id VARCHAR(32) NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency_records(created_at);

-- =============================================================================
-- Security Hardening & Row Level Security (RLS)
-- =============================================================================

-- Explicitly revoke browser direct access (anon / authenticated roles) to private application tables
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
        REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
        REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM authenticated;
    END IF;
END $$;

-- Enable Row Level Security on all core tables
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE speaker_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE voice_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE directory_metadata ENABLE ROW LEVEL SECURITY;

-- Service role & backend connection policy:
-- The FastAPI backend connects with trusted credentials, setting intentlock.actor_id per turn transaction.
CREATE POLICY service_all_employees ON employees FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY service_all_tickets ON tickets FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY service_all_mappings ON speaker_mappings FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY service_all_sessions ON voice_sessions FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY service_all_drafts ON action_drafts FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY service_all_grants ON action_grants FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY service_all_events ON action_events FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY service_all_idempotency ON idempotency_records FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY service_all_metadata ON directory_metadata FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
