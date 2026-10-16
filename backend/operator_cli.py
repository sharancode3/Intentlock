"""
IntentLock — Operator Administration CLI
Supervised operator bootstrap tooling for demo speaker mappings, dashboard linking,
preflight authenticity validation, and live Detectif operations.

Usage:
    python backend/operator_cli.py list-employees
    python backend/operator_cli.py map-speaker EMP-1001 emp_1001_aarav --alias primary_account
    python backend/operator_cli.py import-enrollment EMP-1001 emp_1001_aarav
    python backend/operator_cli.py inspect-speaker EMP-1001
    python backend/operator_cli.py enroll-audio EMP-1001 path/to/voice.wav
    python backend/operator_cli.py verify-audio EMP-1001 path/to/voice.wav
    python backend/operator_cli.py check-balance
"""

import os
import sys
import asyncio
import argparse
import logging
from typing import Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.config import settings
from backend.services.employee_knowledge_service import EmployeeKnowledgeService
from backend.adapters.identity_mapping_store import IdentityMappingStore
from backend.adapters.detectif_adapter import DetectifVoiceEvidenceAdapter, DetectifHTTPClient
from backend.adapters.audio_decoder import AudioDecoder
from backend.models.turn import OriginalAudioMetadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("intentlock.operator")


def cmd_list_employees(args: argparse.Namespace) -> None:
    """List canonical demo employees from the indexed dataset."""
    service = EmployeeKnowledgeService.get_instance()
    store = IdentityMappingStore.get_instance()
    mappings = {m.employee_id: m for m in store.list_mappings()}

    print("\n=========================================================================")
    print("                Canonical Employee Identities (Stage 3)                  ")
    print("=========================================================================")
    print(f"{'Employee ID':<12} {'Full Name':<22} {'Department':<16} {'Enrollment Status'}")
    print("-" * 73)

    for emp in service._raw_employees:  # Show all 31 canonical demo employees
        eid = emp["employee_id"]
        name = emp["identity"]["full_name"]
        dept = emp["employment"]["department"]
        mapping = mappings.get(eid)
        status = f"MAPPED ({mapping.provider_speaker_id}: {mapping.enrollment_status})" if mapping else "NOT MAPPED"
        print(f"{eid:<12} {name:<22} {dept:<16} {status}")
    print(f"\nTotal canonical employees loaded: {len(service._raw_employees)}")


def cmd_map_speaker(args: argparse.Namespace) -> None:
    """Supervised mapping of a canonical employee ID to a provider speaker ID."""
    service = EmployeeKnowledgeService.get_instance()
    emp = service.get_employee_by_id(args.employee_id)
    if not emp:
        print(f"[ERROR] Employee ID '{args.employee_id}' not found in canonical dataset.")
        sys.exit(1)

    name = emp["identity"]["full_name"]
    store = IdentityMappingStore.get_instance()
    rec = store.upsert_mapping(
        employee_id=args.employee_id,
        provider_speaker_id=args.speaker_id,
        account_alias=args.alias,
        display_name=name,
        enrollment_status="PENDING",
    )
    print(f"\n[SUCCESS] Mapped {rec.employee_id} ({name}) -> Provider Speaker ID '{rec.provider_speaker_id}'")
    print(f"Account Alias: {rec.account_alias} | Status: {rec.enrollment_status}")


async def async_import_enrollment(employee_id: str, speaker_id: str, alias: str, force: bool = False) -> None:
    """Link an existing dashboard speaker enrollment to a canonical employee ID with remote validation."""
    service = EmployeeKnowledgeService.get_instance()
    emp = service.get_employee_by_id(employee_id)
    if not emp:
        print(f"[ERROR] Employee ID '{employee_id}' not found in canonical dataset.")
        sys.exit(1)

    name = emp["identity"]["full_name"]
    adapter = DetectifVoiceEvidenceAdapter()
    if adapter.is_configured() and not force:
        print(f"Verifying remote speaker '{speaker_id}' in Detectif dashboard...")
        speaker_info = await adapter.get_speaker(speaker_id)
        if not speaker_info:
            print(f"[ERROR] Speaker ID '{speaker_id}' not found in remote Detectif dashboard.")
            print("To bypass this check, re-run with --force.")
            sys.exit(1)
        print(f"Remote speaker verified: {speaker_info}")

    store = IdentityMappingStore.get_instance()
    rec = store.upsert_mapping(
        employee_id=employee_id,
        provider_speaker_id=speaker_id,
        account_alias=alias,
        display_name=name,
        enrollment_status="ENROLLED",
        sample_count=1,
    )
    print(f"\n[SUCCESS] Linked dashboard enrollment for {rec.employee_id} ({name})")
    print(f"Provider Speaker ID: '{rec.provider_speaker_id}' | Status: ENROLLED")


def cmd_inspect_speaker(args: argparse.Namespace) -> None:
    """Inspect current speaker mapping and status."""
    store = IdentityMappingStore.get_instance()
    mapping = store.get_mapping_by_employee_id(args.employee_id)
    if not mapping:
        print(f"No mapping found for employee ID: {args.employee_id}")
        return

    print("\n--- Speaker Mapping Record ---")
    print(f"Employee ID         : {mapping.employee_id}")
    print(f"Display Name        : {mapping.display_name}")
    print(f"Account Alias       : {mapping.account_alias}")
    print(f"Provider Speaker ID : {mapping.provider_speaker_id}")
    print(f"Enrollment Status   : {mapping.enrollment_status}")
    print(f"Sample Count        : {mapping.sample_count}")
    print(f"Created At          : {mapping.created_at}")
    print(f"Updated At          : {mapping.updated_at}")


async def async_enroll_audio(employee_id: str, audio_path: str) -> None:
    """Validate audio length and preflight authenticity, then enroll in Detectif."""
    if not os.path.exists(audio_path):
        print(f"[ERROR] Audio file not found at: {audio_path}")
        sys.exit(1)

    store = IdentityMappingStore.get_instance()
    mapping = store.get_mapping_by_employee_id(employee_id)
    if not mapping:
        print(f"[ERROR] Employee ID '{employee_id}' has not been mapped to a provider speaker ID yet.")
        print(f"Run: python backend/operator_cli.py map-speaker {employee_id} <speaker_id>")
        sys.exit(1)

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    # Step 1: Validate audio duration bounds (15-60s)
    try:
        pcm = AudioDecoder.decode_to_16k_mono(audio_bytes, max_duration_s=60.0, min_duration_s=0.1)
        duration_s = len(pcm) / 16000.0
        print(f"Audio duration: {duration_s:.1f} seconds")
        if duration_s < 15.0 or duration_s > 60.0:
            print(f"[ERROR] Enrollment audio must be between 15 and 60 seconds (got {duration_s:.1f}s).")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Audio decode failure: {e}")
        sys.exit(1)

    adapter = DetectifVoiceEvidenceAdapter()
    if not adapter.is_configured():
        print("[ERROR] DETECTIF_API_KEY is not configured in the environment.")
        sys.exit(1)

    # Step 2: Preflight authenticity check
    print("Running preflight deepfake detection check...")
    try:
        df_result = await adapter.detect_deepfake(audio_bytes)
        verdict = df_result.get("verdict")
        score = df_result.get("score")
        print(f"Authenticity verdict: {verdict} (score: {score})")
        if verdict != "real":
            print(f"[ERROR] Preflight failed: audio was classified as '{verdict}'. Enrollment aborted.")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Preflight authenticity check failed: {e}")
        sys.exit(1)

    # Step 3: Enroll speaker in Detectif
    print(f"Enrolling speaker '{mapping.provider_speaker_id}' in Detectif...")
    try:
        enroll_result = await adapter.enroll_speaker(
            speaker_id=mapping.provider_speaker_id,
            audio_bytes=audio_bytes,
            display_name=mapping.display_name,
        )
        print(f"[SUCCESS] Enrollment completed: {enroll_result}")
        store.update_enrollment_status(employee_id, "ENROLLED", sample_count=mapping.sample_count + 1)
    except Exception as e:
        print(f"[ERROR] Enrollment request failed: {e}")
        sys.exit(1)


async def async_verify_audio(employee_id: str, audio_path: str) -> None:
    """Run a test verification on a fresh local recording."""
    if not os.path.exists(audio_path):
        print(f"[ERROR] Audio file not found: {audio_path}")
        sys.exit(1)

    store = IdentityMappingStore.get_instance()
    mapping = store.get_mapping_by_employee_id(employee_id)
    if not mapping:
        print(f"[ERROR] Employee ID '{employee_id}' has not been mapped.")
        sys.exit(1)

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    adapter = DetectifVoiceEvidenceAdapter()
    if not adapter.is_configured():
        print("[ERROR] DETECTIF_API_KEY is not configured in the environment.")
        sys.exit(1)

    import hashlib
    digest = hashlib.sha256(audio_bytes).hexdigest()
    meta = OriginalAudioMetadata(
        safe_filename=os.path.basename(audio_path),
        declared_content_type="audio/wav",
        normalized_mime_type="audio/wav",
        byte_count=len(audio_bytes),
        sha256_digest=digest,
    )

    print(f"Verifying against speaker '{mapping.provider_speaker_id}'...")
    res = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id=mapping.provider_speaker_id,
        correlation_id="cli_verify_test",
    )

    print("\n--- Verification Evidence ---")
    print(f"Available          : {res.is_available}")
    print(f"Speaker Decision   : {res.decision}")
    print(f"Similarity Score   : {res.similarity_score} (thresh: {res.similarity_threshold})")
    print(f"Deepfake Verdict   : {res.deepfake_verdict} (score: {res.deepfake_score})")
    print(f"Dual Verified      : {res.is_dual_verified}")
    print(f"Latency            : {res.latency_ms} ms")
    if res.error_message:
        print(f"Error              : [{res.error_code}] {res.error_message}")


async def async_check_balance() -> None:
    """Check account credits and diagnostics."""
    adapter = DetectifVoiceEvidenceAdapter()
    if not adapter.is_configured():
        print("[ERROR] DETECTIF_API_KEY is not configured in the environment.")
        sys.exit(1)
    try:
        balance = await adapter.get_balance()
        print(f"\nAccount Balance & Usage Diagnostics:")
        print(balance)
    except Exception as e:
        print(f"[ERROR] Failed to retrieve balance: {e}")


def main():
    parser = argparse.ArgumentParser(description="IntentLock Operator Administration CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list-employees
    subparsers.add_parser("list-employees", help="List canonical demo employee identities")

    # map-speaker
    map_p = subparsers.add_parser("map-speaker", help="Map employee ID to a provider speaker ID")
    map_p.add_argument("employee_id", help="Canonical employee ID (e.g. EMP-1001)")
    map_p.add_argument("speaker_id", help="Provider speaker ID (e.g. emp_1001_aarav)")
    map_p.add_argument("--alias", default="primary_account", help="Account alias")

    # import-enrollment
    imp_p = subparsers.add_parser("import-enrollment", help="Link an existing dashboard speaker")
    imp_p.add_argument("employee_id", help="Canonical employee ID")
    imp_p.add_argument("speaker_id", help="Provider speaker ID")
    imp_p.add_argument("--alias", default="primary_account", help="Account alias")
    imp_p.add_argument("--force", action="store_true", help="Bypass remote speaker verification")

    # inspect-speaker
    ins_p = subparsers.add_parser("inspect-speaker", help="Inspect mapping and enrollment status")
    ins_p.add_argument("employee_id", help="Canonical employee ID")

    # enroll-audio
    enr_p = subparsers.add_parser("enroll-audio", help="Enroll local audio file with preflight check")
    enr_p.add_argument("employee_id", help="Canonical employee ID")
    enr_p.add_argument("audio_path", help="Path to local audio file")

    # verify-audio
    ver_p = subparsers.add_parser("verify-audio", help="Test verification of candidate audio file")
    ver_p.add_argument("employee_id", help="Canonical employee ID")
    ver_p.add_argument("audio_path", help="Path to local audio file")

    # check-balance
    subparsers.add_parser("check-balance", help="Check account balance and credits")

    args = parser.parse_args()

    if args.command == "list-employees":
        cmd_list_employees(args)
    elif args.command == "map-speaker":
        cmd_map_speaker(args)
    elif args.command == "import-enrollment":
        asyncio.run(async_import_enrollment(args.employee_id, args.speaker_id, args.alias, args.force))
    elif args.command == "inspect-speaker":
        cmd_inspect_speaker(args)
    elif args.command == "enroll-audio":
        asyncio.run(async_enroll_audio(args.employee_id, args.audio_path))
    elif args.command == "verify-audio":
        asyncio.run(async_verify_audio(args.employee_id, args.audio_path))
    elif args.command == "check-balance":
        asyncio.run(async_check_balance())


if __name__ == "__main__":
    main()
