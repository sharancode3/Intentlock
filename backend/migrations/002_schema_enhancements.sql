-- IntentLock Migration 002: Canonical Employee Schema Enhancements & Fidelity
-- Adds missing canonical employee fields to guarantee 100% data parity with all_employees.json.

ALTER TABLE employees ADD COLUMN IF NOT EXISTS employment_status VARCHAR(32) DEFAULT 'Active';
ALTER TABLE employees ADD COLUMN IF NOT EXISTS employment_type VARCHAR(64) DEFAULT 'Full-Time';
ALTER TABLE employees ADD COLUMN IF NOT EXISTS date_of_joining VARCHAR(32);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS sub_department VARCHAR(64);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS research_level VARCHAR(32);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS security_scope JSONB DEFAULT '{}'::jsonb;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS voice_authority JSONB DEFAULT '{}'::jsonb;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS recent_activity JSONB DEFAULT '[]'::jsonb;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS extra_data JSONB DEFAULT '{}'::jsonb;
