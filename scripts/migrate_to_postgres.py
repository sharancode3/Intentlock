"""
IntentLock — Supabase Postgres Schema Migration & Data Importer
Applies versioned migrations with advisory locking, validates employee graph integrity,
and imports canonical employees, authoritative tickets, and speaker mappings additively.
Supports strictly read-only dry-run and controlled repair mode.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("intentlock.migrate")

ADVISORY_LOCK_ID = 0x494E5445  # "INTE" in hex


def sanitize(text: str) -> str:
    redacted = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", str(text))
    redacted = re.sub(r"password=([^\s]+)", "password=***", redacted, flags=re.I)
    return redacted


def compute_checksum(content: str) -> str:
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()[:16]


def validate_employee_graph(employees: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """Bidirectional employee reporting tree validation."""
    errors = []
    emp_map = {e["employee_id"]: e for e in employees}

    if len(emp_map) != len(employees):
        errors.append(f"Duplicate employee IDs found: expected {len(employees)}, got {len(emp_map)}")

    for eid, emp in emp_map.items():
        mgr_id = emp.get("reporting", {}).get("manager_id")
        if mgr_id and mgr_id not in emp_map:
            errors.append(f"Employee {eid} has nonexistent manager_id {mgr_id}")
        if mgr_id == eid:
            errors.append(f"Employee {eid} manages themselves (self-cycle)")

        # Cycle check
        visited = set()
        curr = eid
        while curr:
            if curr in visited:
                errors.append(f"Reporting cycle detected starting at employee {curr}")
                break
            visited.add(curr)
            curr = emp_map[curr].get("reporting", {}).get("manager_id") if curr in emp_map else None

    return len(errors) == 0, errors


async def run_migration(
    db_url: str,
    dry_run: bool = True,
    repair_mode: bool = False,
) -> Dict[str, Any]:
    logger.info("Connecting to Supabase Postgres (dry_run=%s, repair=%s)...", dry_run, repair_mode)
    sanitized_url = sanitize(db_url)
    logger.info("Target: %s", sanitized_url)

    conn = await asyncpg.connect(db_url, ssl="require", timeout=15.0)
    report: Dict[str, Any] = {
        "dry_run": dry_run,
        "repair_mode": repair_mode,
        "migrations_applied": [],
        "migrations_pending": [],
        "employees_found_in_seed": 0,
        "employees_imported": 0,
        "employees_repaired": 0,
        "tickets_imported": 0,
        "mappings_imported": 0,
        "unmigrated_ephemeral_states": {
            "active_sessions": "Excluded by policy (Section 7)",
            "pending_drafts": "Excluded by policy (Section 7)",
            "action_grants": "Excluded by policy (Section 7)",
            "idempotency_cache": "Excluded by policy (Section 7)",
        },
        "errors": [],
    }

    try:
        # Acquire advisory transaction lock (or session lock for dry run)
        logger.info("Acquiring Postgres migration advisory lock...")
        await conn.execute("SELECT pg_advisory_lock($1)", ADVISORY_LOCK_ID)

        # 1. Inspect existing migrations table without modifying DB in dry-run
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'schema_migrations'
            )
        """)

        applied_versions = set()
        if table_exists:
            rows = await conn.fetch("SELECT version FROM schema_migrations")
            applied_versions = {r["version"] for r in rows}

        migration_files = [
            ("001_initial_schema", "001_initial_schema.sql", "Initial Canonical Schema & RLS"),
            ("002_schema_enhancements", "002_schema_enhancements.sql", "Canonical Employee Schema Enhancements"),
            ("003_actor_rls_policies", "003_actor_rls_policies.sql", "Actor-Aware Row Level Security Policies"),
        ]

        # 2. Check pending migrations
        for version_tag, filename, name in migration_files:
            migration_path = os.path.join(settings.BASE_DIR, "backend", "migrations", filename)
            if not os.path.exists(migration_path):
                continue
            if version_tag in applied_versions:
                logger.info("Migration %s already applied.", filename)
            else:
                report["migrations_pending"].append(filename)

        # 3. Read and validate source employee records
        emp_file = settings.DATA_PATH if os.path.exists(settings.DATA_PATH) else os.path.join(
            settings.BASE_DIR, "backend", "data", "all_employees.json"
        )
        with open(emp_file, "r", encoding="utf-8") as f:
            employees = json.load(f)

        report["employees_found_in_seed"] = len(employees)
        valid_graph, graph_errors = validate_employee_graph(employees)
        if not valid_graph:
            raise ValueError(f"Employee dataset graph validation failed: {graph_errors}")
        logger.info("Validated %d canonical employees (graph is 100%% cycle-free).", len(employees))

        # 4. Prepare Employee Records with 100% field preservation
        emp_records_to_insert = []
        for e in employees:
            eid = e["employee_id"]
            identity = e.get("identity", {})
            employment = e.get("employment", {})
            reporting = e.get("reporting", {})
            policy = e.get("permissions", {})
            contact = identity.get("contact", {})

            # Source work_email is authoritative; fall back to contact.email or internal domain
            canonical_email = (
                identity.get("work_email")
                or contact.get("email")
                or f"{eid.lower()}@intentlock-demo.example"
            )
            work_phone = contact.get("phone") or identity.get("work_phone") or None

            emp_records_to_insert.append({
                "employee_id": eid,
                "version": 1,
                "full_name": identity.get("full_name", ""),
                "preferred_name": identity.get("preferred_name") or None,
                "work_email": canonical_email,
                "work_phone": work_phone,
                "department": employment.get("department", "Engineering"),
                "designation": employment.get("designation", "Staff"),
                "organizational_level": employment.get("organizational_level", "L1"),
                "location": employment.get("location", "Bengaluru"),
                "work_mode": employment.get("work_mode", "Hybrid"),
                "manager_id": reporting.get("manager_id") or None,
                "skills": json.dumps(e.get("skills", {})),
                "projects": json.dumps(e.get("projects", {})),
                "experience": json.dumps(e.get("experience", {})),
                "education": json.dumps(e.get("education", [])),
                "responsibilities": json.dumps(e.get("responsibilities", [])),
                "achievements": json.dumps(e.get("achievements", [])),
                "research": json.dumps(e.get("research")) if "research" in e else None,
                "executive_authority": json.dumps(e.get("executive_authority")) if "executive_authority" in e else None,
                "policy": json.dumps(policy),
                "provenance": json.dumps(e.get("provenance", {})),
                "employment_status": employment.get("status", "Active"),
                "employment_type": employment.get("employment_type", "Full-Time"),
                "date_of_joining": employment.get("date_of_joining"),
                "sub_department": employment.get("sub_department"),
                "research_level": employment.get("research_level"),
                "security_scope": json.dumps(e.get("security_scope", {})),
                "voice_authority": json.dumps(e.get("voice_authority", {})),
                "recent_activity": json.dumps(e.get("recent_activity", [])),
                "extra_data": json.dumps(e),
            })

        # 5. Read tickets from configured APP_DB_PATH
        sqlite_tickets_db = settings.APP_DB_PATH
        tickets_to_insert = []
        if os.path.exists(sqlite_tickets_db):
            scon = sqlite3.connect(sqlite_tickets_db)
            scur = scon.cursor()
            try:
                rows = scur.execute("SELECT ticket_id, version, document FROM tickets").fetchall()
                for tid, ver, doc_str in rows:
                    doc = json.loads(doc_str)
                    tickets_to_insert.append((
                        tid,
                        ver,
                        doc.get("title", ""),
                        doc.get("description", ""),
                        doc.get("ticket_type", "General"),
                        doc.get("category", "Support"),
                        doc.get("status", "Open"),
                        doc.get("priority", "Medium"),
                        doc.get("requester_id", ""),
                        doc.get("assignee_id") or None,
                        doc.get("created_by", ""),
                        doc.get("department") or None,
                        doc.get("project") or None,
                        json.dumps(doc),
                    ))
                logger.info("Loaded %d authoritative tickets from %s.", len(tickets_to_insert), sqlite_tickets_db)
            except Exception as exc:
                logger.warning("Could not read tickets table from %s: %s", sqlite_tickets_db, exc)
            finally:
                scon.close()
        else:
            ticket_file = os.path.join(settings.BASE_DIR, "backend", "data", "all_tickets.json")
            if os.path.exists(ticket_file):
                with open(ticket_file, "r", encoding="utf-8") as f:
                    seed_tickets = json.load(f)
                for doc in seed_tickets:
                    tickets_to_insert.append((
                        doc["ticket_id"],
                        1,
                        doc.get("title", ""),
                        doc.get("description", ""),
                        doc.get("ticket_type", "General"),
                        doc.get("category", "Support"),
                        doc.get("status", "Open"),
                        doc.get("priority", "Medium"),
                        doc.get("requester_id", ""),
                        doc.get("assignee_id") or None,
                        doc.get("created_by", ""),
                        doc.get("department") or None,
                        doc.get("project") or None,
                        json.dumps(doc),
                    ))

        # 6. Read speaker mappings from configured MAPPING_DB_PATH
        sqlite_mappings_db = settings.MAPPING_DB_PATH
        mappings_to_insert = []
        if os.path.exists(sqlite_mappings_db):
            icon = sqlite3.connect(sqlite_mappings_db)
            icur = icon.cursor()
            try:
                rows = icur.execute("""
                    SELECT employee_id, account_alias, provider_speaker_id, display_name,
                           enrollment_status, sample_count, created_at, updated_at
                    FROM speaker_mappings
                """).fetchall()
                for r in rows:
                    mappings_to_insert.append(r)
                logger.info("Loaded %d speaker mappings from %s.", len(mappings_to_insert), sqlite_mappings_db)
            except Exception as exc:
                logger.warning("Could not read speaker_mappings from %s: %s", sqlite_mappings_db, exc)
            finally:
                icon.close()

        # 7. Execute in a Single Atomic Transaction if not dry-run
        if not dry_run:
            async with conn.transaction():
                # Apply migrations
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version VARCHAR(64) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        checksum VARCHAR(64) NOT NULL
                    );
                """)

                for version_tag, filename, name in migration_files:
                    migration_path = os.path.join(settings.BASE_DIR, "backend", "migrations", filename)
                    if not os.path.exists(migration_path):
                        continue
                    if version_tag not in applied_versions:
                        with open(migration_path, "r", encoding="utf-8") as f:
                            sql_text = f.read()
                        checksum = compute_checksum(sql_text)
                        logger.info("Applying migration %s (checksum: %s)...", filename, checksum)
                        await conn.execute(sql_text)
                        await conn.execute(
                            "INSERT INTO schema_migrations (version, name, applied_at, checksum) VALUES ($1, $2, $3, $4)",
                            version_tag, name, datetime.now(timezone.utc), checksum
                        )
                        report["migrations_applied"].append(filename)

                # Insert/Repair Employees
                for rec in emp_records_to_insert:
                    if repair_mode:
                        # Controlled repair: update email if placeholder/missing, fill extra fields
                        # Do NOT overwrite designation, organizational_level, policy, or active phone updates
                        res = await conn.execute("""
                            UPDATE employees SET
                                work_email = CASE 
                                    WHEN work_email LIKE '%@intentlock.internal' THEN $2
                                    ELSE work_email
                                END,
                                employment_status = $3,
                                employment_type = $4,
                                date_of_joining = $5,
                                sub_department = $6,
                                research_level = $7,
                                security_scope = $8::jsonb,
                                voice_authority = $9::jsonb,
                                recent_activity = $10::jsonb,
                                extra_data = $11::jsonb
                            WHERE employee_id = $1
                        """,
                            rec["employee_id"],
                            rec["work_email"],
                            rec["employment_status"],
                            rec["employment_type"],
                            rec["date_of_joining"],
                            rec["sub_department"],
                            rec["research_level"],
                            rec["security_scope"],
                            rec["voice_authority"],
                            rec["recent_activity"],
                            rec["extra_data"],
                        )
                        if res and int(res.split()[-1]) > 0:
                            report["employees_repaired"] += 1
                    else:
                        # Additive non-destructive insert: DO NOTHING ON CONFLICT
                        await conn.execute("""
                            INSERT INTO employees (
                                employee_id, version, full_name, preferred_name, work_email,
                                work_phone, department, designation, organizational_level,
                                location, work_mode, manager_id, skills, projects, experience,
                                education, responsibilities, achievements, research,
                                executive_authority, policy, provenance,
                                employment_status, employment_type, date_of_joining,
                                sub_department, research_level, security_scope,
                                voice_authority, recent_activity, extra_data
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                                $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb, $17::jsonb,
                                $18::jsonb, $19::jsonb, $20::jsonb, $21::jsonb, $22::jsonb,
                                $23, $24, $25, $26, $27, $28::jsonb, $29::jsonb, $30::jsonb, $31::jsonb
                            )
                            ON CONFLICT (employee_id) DO NOTHING;
                        """,
                            rec["employee_id"], rec["version"], rec["full_name"], rec["preferred_name"],
                            rec["work_email"], rec["work_phone"], rec["department"], rec["designation"],
                            rec["organizational_level"], rec["location"], rec["work_mode"], rec["manager_id"],
                            rec["skills"], rec["projects"], rec["experience"], rec["education"],
                            rec["responsibilities"], rec["achievements"], rec["research"], rec["executive_authority"],
                            rec["policy"], rec["provenance"], rec["employment_status"], rec["employment_type"],
                            rec["date_of_joining"], rec["sub_department"], rec["research_level"],
                            rec["security_scope"], rec["voice_authority"], rec["recent_activity"], rec["extra_data"]
                        )
                        report["employees_imported"] += 1

                # Link manager_ids if inserting new records
                if not repair_mode:
                    for rec in emp_records_to_insert:
                        if rec["manager_id"]:
                            await conn.execute(
                                "UPDATE employees SET manager_id = $1 WHERE employee_id = $2 AND manager_id IS NULL",
                                rec["manager_id"], rec["employee_id"]
                            )

                # Insert tickets additively
                for trec in tickets_to_insert:
                    await conn.execute("""
                        INSERT INTO tickets (
                            ticket_id, version, title, description, ticket_type, category,
                            status, priority, requester_id, assignee_id, created_by,
                            department, project, document
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb
                        )
                        ON CONFLICT (ticket_id) DO NOTHING;
                    """, *trec)
                    report["tickets_imported"] += 1

                # Insert speaker mappings additively
                for mrec in mappings_to_insert:
                    await conn.execute("""
                        INSERT INTO speaker_mappings (
                            employee_id, account_alias, provider_speaker_id, display_name,
                            enrollment_status, sample_count
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (employee_id) DO NOTHING;
                    """, mrec[0], mrec[1], mrec[2], mrec[3], mrec[4], mrec[5])
                    report["mappings_imported"] += 1

                # Post-migration verification counts
                post_emp_count = await conn.fetchval("SELECT COUNT(*) FROM employees")
                post_tkt_count = await conn.fetchval("SELECT COUNT(*) FROM tickets")
                post_map_count = await conn.fetchval("SELECT COUNT(*) FROM speaker_mappings")
                report["db_final_counts"] = {
                    "employees": post_emp_count,
                    "tickets": post_tkt_count,
                    "speaker_mappings": post_map_count,
                }
        else:
            # Strictly read-only dry-run report
            curr_emp_count = await conn.fetchval("SELECT COUNT(*) FROM employees") if table_exists else 0
            curr_tkt_count = await conn.fetchval("SELECT COUNT(*) FROM tickets") if table_exists else 0
            curr_map_count = await conn.fetchval("SELECT COUNT(*) FROM speaker_mappings") if table_exists else 0
            report["db_current_counts"] = {
                "employees": curr_emp_count,
                "tickets": curr_tkt_count,
                "speaker_mappings": curr_map_count,
            }
            report["dry_run_summary"] = (
                f"Would apply {len(report['migrations_pending'])} pending migrations, "
                f"reconcile {len(emp_records_to_insert)} employees, "
                f"{len(tickets_to_insert)} tickets, and {len(mappings_to_insert)} mappings."
            )

    except Exception as exc:
        redacted_err = sanitize(str(exc))
        logger.error("Migration failed: %s", redacted_err)
        report["errors"].append(redacted_err)
        raise RuntimeError(f"Migration error: {redacted_err}") from None
    finally:
        try:
            await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_ID)
        except Exception:
            pass
        await conn.close()

    return report


def main():
    parser = argparse.ArgumentParser(description="IntentLock Supabase Postgres Migrator & Data Importer")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Perform strictly read-only inspection")
    parser.add_argument("--run", action="store_true", default=False, help="Execute migrations and data import")
    parser.add_argument("--repair", action="store_true", default=False, help="Perform controlled field repair on existing records")
    args = parser.parse_args()

    db_url = settings.SUPABASE_DATABASE_URL
    if not db_url:
        logger.error("SUPABASE_DATABASE_URL is not set. Please set the environment variable.")
        sys.exit(1)

    is_dry_run = not (args.run or args.repair)
    try:
        report = asyncio.run(run_migration(db_url, dry_run=is_dry_run, repair_mode=args.repair))
        print("\n" + "=" * 60)
        print("IntentLock Postgres Migration & Parity Report")
        print("=" * 60)
        print(json.dumps(report, indent=2))
        print("=" * 60)
    except Exception as e:
        print(f"\nFATAL: Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
