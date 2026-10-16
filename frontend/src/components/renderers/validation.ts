/**
 * IntentLock — Result Block Runtime Validation
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Lightweight, zero-dependency runtime validation and type guards for
 * ResultBlock payloads incoming from the FastAPI backend or local simulations.
 *
 * Prevents UI crashes, eliminates raw JSON dumps, and enforces data boundaries
 * without leaking protected employee information or internal stack traces.
 */

import type { PublicFaqPayload, DenialBannerPayload } from '../../types/payloads';

export interface ValidationSuccess<T> {
  readonly isValid: true;
  readonly data: T;
}

export interface ValidationFailure {
  readonly isValid: false;
  /** Sanitized, user-safe description of what went wrong */
  readonly error: string;
}

export type ValidationResult<T> = ValidationSuccess<T> | ValidationFailure;

/**
 * Type guard for non-null JavaScript objects.
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Validates that a value is a non-empty string.
 */
function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

/**
 * Validates that an optional value, if present, is a string.
 */
function isOptionalString(value: unknown): boolean {
  return value === undefined || value === null || typeof value === 'string';
}

// ============================================================================
// 1. PUBLIC_FAQ Runtime Validator
// ============================================================================

/**
 * Validates that an arbitrary payload matches the PublicFaqPayload contract.
 *
 * Rules:
 * - Must be a non-null object.
 * - Must contain a non-empty `answer` (or legacy `summary`).
 * - If present, `question`, `source_document`, `source_doc`, and `category` must be strings.
 */
export function validatePublicFaqPayload(raw: unknown): ValidationResult<PublicFaqPayload> {
  if (!isRecord(raw)) {
    return {
      isValid: false,
      error: 'Malformed FAQ payload: expected an object.',
    };
  }

  // Support both primary 'answer' and legacy 'summary' fields
  const answerCandidate = raw.answer ?? raw.summary;
  if (!isNonEmptyString(answerCandidate)) {
    return {
      isValid: false,
      error: 'Invalid FAQ payload: answer content is required and cannot be empty.',
    };
  }

  // Check optional fields if present
  if (!isOptionalString(raw.question)) {
    return { isValid: false, error: 'Invalid FAQ payload: question must be a string.' };
  }
  if (!isOptionalString(raw.source_document)) {
    return { isValid: false, error: 'Invalid FAQ payload: source_document must be a string.' };
  }
  if (!isOptionalString(raw.source_doc)) {
    return { isValid: false, error: 'Invalid FAQ payload: source_doc must be a string.' };
  }
  if (!isOptionalString(raw.category)) {
    return { isValid: false, error: 'Invalid FAQ payload: category must be a string.' };
  }
  if (!isOptionalString(raw.summary)) {
    return { isValid: false, error: 'Invalid FAQ payload: summary must be a string.' };
  }

  const normalized: PublicFaqPayload = {
    answer: answerCandidate.trim(),
    question: isNonEmptyString(raw.question) ? raw.question.trim() : undefined,
    source_document: isNonEmptyString(raw.source_document)
      ? raw.source_document.trim()
      : isNonEmptyString(raw.source_doc)
        ? raw.source_doc.trim()
        : undefined,
    source_doc: isNonEmptyString(raw.source_doc) ? raw.source_doc.trim() : undefined,
    category: isNonEmptyString(raw.category) ? raw.category.trim() : undefined,
    summary: isNonEmptyString(raw.summary) ? raw.summary.trim() : undefined,
  };

  return {
    isValid: true,
    data: normalized,
  };
}

/**
 * Fast TypeScript type guard for PublicFaqPayload.
 */
export function isPublicFaqPayload(raw: unknown): raw is PublicFaqPayload {
  return validatePublicFaqPayload(raw).isValid;
}

// ============================================================================
// 2. DENIAL_BANNER Runtime Validator
// ============================================================================

/**
 * Validates that an arbitrary payload matches the DenialBannerPayload contract.
 *
 * Rules:
 * - Must be a non-null object.
 * - Must contain a non-empty `message` (or safe `reason`).
 * - If present, `code`, `reason`, and `next_step` must be strings.
 */
export function validateDenialBannerPayload(raw: unknown): ValidationResult<DenialBannerPayload> {
  if (!isRecord(raw)) {
    return {
      isValid: false,
      error: 'Malformed denial payload: expected an object.',
    };
  }

  // Must have a primary user message (or fall back to reason)
  const messageCandidate = raw.message ?? raw.reason;
  if (!isNonEmptyString(messageCandidate)) {
    return {
      isValid: false,
      error: 'Invalid denial payload: display message is required.',
    };
  }

  if (!isOptionalString(raw.code)) {
    return { isValid: false, error: 'Invalid denial payload: code must be a string.' };
  }
  if (!isOptionalString(raw.reason)) {
    return { isValid: false, error: 'Invalid denial payload: reason must be a string.' };
  }
  if (!isOptionalString(raw.next_step)) {
    return { isValid: false, error: 'Invalid denial payload: next_step must be a string.' };
  }

  const normalized: DenialBannerPayload = {
    message: messageCandidate.trim(),
    code: isNonEmptyString(raw.code) ? raw.code.trim() : undefined,
    reason: isNonEmptyString(raw.reason) ? raw.reason.trim() : undefined,
    next_step: isNonEmptyString(raw.next_step) ? raw.next_step.trim() : undefined,
  };

  return {
    isValid: true,
    data: normalized,
  };
}

/**
 * Fast TypeScript type guard for DenialBannerPayload.
 */
export function isDenialBannerPayload(raw: unknown): raw is DenialBannerPayload {
  return validateDenialBannerPayload(raw).isValid;
}
