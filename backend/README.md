# IntentLock — Backend Gateway & Biometric Voice Security (Stage 3)

This directory contains the FastAPI gateway and backend foundation for IntentLock, a voice-first employee helpdesk for the UNCLONE Agents track.

## Architecture & Responsibilities

- **Ingress Gateway**: Provides `POST /api/v1/voice/turn` with streaming upload byte bounds, SHA-256 calculation, MIME type normalization, and dual voice biometric verification.
- **Biometric Dual-Verification**: Integrates Detectif API (`POST /v1/speakers/verify` with deepfake detection), requiring both speaker match (`decision == "match"`) AND authenticity (`deepfake.verdict == "real"`). Audio must be > 4.0s.
- **Identity & Role Integrity**: Canonical identity store mapping employees to remote speakers. Spoken titles never elevate privileges. Rejects caller claim conflicts.
- **Pre-LLM Scoped Context & Grounded Answers**: Filters context strictly according to role policy before invoking the OpenAI Responses API (`gpt-5.4-mini`, `store=False`, `max_output_tokens=1024`).
- **Open-Source Speech Runtime**: Integrated Silero VAD, Faster-Whisper STT, and Kokoro-82M neural TTS for 24kHz synthesized audio playback.
- **Operator Tooling**: Supervised operator CLI (`backend/operator_cli.py`) for enrollment, mapping inspection, and credit diagnostics.

---

## Prerequisites & Installation

- Python 3.10 or 3.11
- Install dependencies:

```powershell
pip install -r backend/requirements.txt
```

---

## Configuration

In `backend/.env` (or project root `.env`):

```ini
DETECTIF_API_KEY=dtf_live_...
DETECTIF_BASE_URL=https://platform.detectif.ai/v1
DETECTIF_ACCOUNT_ALIAS=primary_account

LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-5.4-mini
OPENAI_MAX_OUTPUT_TOKENS=1024

ENABLE_SPEECH_PIPELINE=true
SPEECH_STT_MODEL=tiny.en
SPEECH_TTS_VOICE=af_heart
```

---

## Starting the Backend Server

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## Running Automated Tests

Run the full pytest suite (74 tests across 10 test suites, 0 live credit spend):

```powershell
python -m pytest tests
```

---

## Operator Administration CLI

```powershell
# List canonical employee identities and enrollment status
python backend/operator_cli.py list-employees

# Link dashboard speaker enrollment with remote verification
python backend/operator_cli.py import-enrollment EMP-1001 emp_1001_aarav

# Check Detectif account credits & diagnostics
python backend/operator_cli.py check-balance
```

