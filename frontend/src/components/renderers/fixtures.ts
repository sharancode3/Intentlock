/**
 * IntentLock — Test Fixtures for Stage 1 Result Renderers
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Controlled test fixtures for local validation and verification.
 * Contains purely fictional and generic public sample payloads.
 * Contains ZERO real credentials, biometric keys, or private employee records.
 */

import type { GenericResultBlock } from '../../types';

// ============================================================================
// 1. PUBLIC_FAQ Fixtures
// ============================================================================

/** Valid minimal PUBLIC_FAQ */
export const validPublicFaqMinimalFixture: GenericResultBlock = {
  id: 'fixture-faq-min',
  type: 'PUBLIC_FAQ',
  title: 'Visitor Center Hours',
  timestamp: '10:00 AM',
  isSensitive: false,
  payload: {
    answer: 'The campus visitor center is open Monday through Friday from 8:00 AM to 5:00 PM.',
  },
};

/** Valid comprehensive PUBLIC_FAQ with source and category */
export const validPublicFaqCompleteFixture: GenericResultBlock = {
  id: 'fixture-faq-complete',
  type: 'PUBLIC_FAQ',
  title: 'Hardware Request Guidelines',
  timestamp: '10:05 AM',
  isSensitive: false,
  payload: {
    question: 'How do employees request ergonomic hardware peripherals?',
    answer: 'Standard keyboards and mice can be requested via self-service tickets without manager approval. Specialized ergonomic items require manager sign-off.',
    source_document: 'IT_Hardware_Policy_v2.4.pdf',
    category: 'IT Equipment & Peripherals',
  },
};

/** Invalid PUBLIC_FAQ: missing required answer */
export const invalidPublicFaqMissingAnswerFixture: GenericResultBlock = {
  id: 'fixture-faq-invalid-no-answer',
  type: 'PUBLIC_FAQ',
  title: 'Incomplete FAQ Item',
  timestamp: '10:10 AM',
  isSensitive: false,
  payload: {
    category: 'General',
    // Missing 'answer' and 'summary'
  },
};

/** Invalid PUBLIC_FAQ: incorrect field types */
export const invalidPublicFaqWrongTypesFixture: GenericResultBlock = {
  id: 'fixture-faq-invalid-types',
  type: 'PUBLIC_FAQ',
  title: 'Corrupted FAQ Record',
  timestamp: '10:15 AM',
  isSensitive: false,
  payload: {
    answer: 12345, // invalid: should be string
    question: ['Invalid Array'],
  },
};

// ============================================================================
// 2. DENIAL_BANNER Fixtures
// ============================================================================

/** Valid minimal DENIAL_BANNER */
export const validDenialBannerMinimalFixture: GenericResultBlock = {
  id: 'fixture-denial-min',
  type: 'DENIAL_BANNER',
  title: 'Action Denied',
  timestamp: '10:20 AM',
  isSensitive: false,
  payload: {
    message: 'Access to this operation was denied by policy.',
  },
};

/** Valid complete DENIAL_BANNER with code, reason, and next step */
export const validDenialBannerCompleteFixture: GenericResultBlock = {
  id: 'fixture-denial-complete',
  type: 'DENIAL_BANNER',
  title: 'Unauthorized Action Request',
  timestamp: '10:25 AM',
  isSensitive: false,
  payload: {
    message: 'You are not authorized to close tickets assigned to other teams.',
    code: 'INSUFFICIENT_SCOPE',
    reason: 'Ticket closure requires team ownership or Manager role.',
    next_step: 'Please contact the assigned team lead or desk supervisor for reassignment.',
  },
};

/** Invalid DENIAL_BANNER: missing message */
export const invalidDenialBannerMissingMessageFixture: GenericResultBlock = {
  id: 'fixture-denial-invalid',
  type: 'DENIAL_BANNER',
  title: 'Malformed Denial Record',
  timestamp: '10:30 AM',
  isSensitive: false,
  payload: {
    code: 'UNKNOWN_ERROR',
    // Missing message and reason
  },
};

// ============================================================================
// 3. Unimplemented / Unsupported Result Type Fixture
// ============================================================================

/** Unsupported / Future result type (e.g. TICKET_LIST before Stage 2) */
export const unsupportedResultTypeFixture: GenericResultBlock = {
  id: 'fixture-unsupported-ticket-list',
  type: 'TICKET_LIST',
  title: 'Active Support Tickets',
  timestamp: '10:35 AM',
  isSensitive: true,
  payload: {
    tickets: [
      {
        ticket_id: 101,
        title: 'Monitor flickering in Lab 2',
        priority: 'NORMAL',
        status: 'OPEN',
      },
    ],
  },
};
