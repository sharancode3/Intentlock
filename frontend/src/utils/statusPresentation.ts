/**
 * IntentLock — State Presentation & Selector Utilities
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Provides deterministic, centralized mapping from authoritative backend
 * responses to coherent UI presentation states across header, chat, evidence,
 * and result containers.
 */

import type {
  GenericResultBlock,
  SessionInfo,
  TurnStatusNotice,
  VoiceTurnResponse,
} from '../types';

/**
 * Resolves the visual turn lifecycle state from a server VoiceTurnResponse.
 * Strictly distinguishes success, denial, clarification, confirmation pending,
 * action committed, provider unavailable, and error states.
 */
export function resolveTurnStatus(
  response: VoiceTurnResponse,
  existingSession: SessionInfo
): TurnStatusNotice {
  const code = response.error?.code?.toUpperCase();

  // 1. Backend / Provider Unavailable
  if (code === 'PROVIDER_UNAVAILABLE' || code === 'DETECTIF_UNAVAILABLE') {
    return {
      type: 'provider_unavailable',
      message: 'Identity verification service is temporarily unavailable. Private access cannot continue.',
    };
  }

  // 2. Security Denial / Verification Required
  if (response.status === 'denial') {
    if (code === 'VERIFICATION_REQUIRED') {
      return {
        type: 'verification_required',
        message: response.assistant_message || 'Additional identity verification is required before this request can continue.',
      };
    }
    if (code === 'SPEAKER_MISMATCH') {
      return {
        type: 'denial',
        message: 'Your voice could not be verified. Speaker biometrics do not match.',
      };
    }
    if (code === 'SYNTHETIC_AUDIO') {
      return {
        type: 'denial',
        message: 'Voice verification failed: synthetic or replayed audio detected.',
      };
    }
    if (code === 'SESSION_EXPIRED' || code === 'TOKEN_EXPIRED') {
      return {
        type: 'denial',
        message: 'Your session has expired. Please state your employee ID to re-verify.',
      };
    }
    if (existingSession.state === 'VERIFIED') {
      return {
        type: 'denial',
        message: response.assistant_message || response.error?.message || 'Access denied by security policy: insufficient role or resource permission.',
      };
    }
    return {
      type: 'denial',
      message: response.assistant_message || response.error?.message || 'Access denied by security policy.',
    };
  }

  // 3. Clarification Required
  if (response.status === 'clarification') {
    return {
      type: 'clarification',
      message: response.assistant_message || response.error?.message || 'Please clarify your request.',
    };
  }

  // 4. Error
  if (response.status === 'error') {
    return {
      type: 'error',
      message: response.error?.message || response.assistant_message || 'Voice request failed.',
    };
  }

  // 5. Successful Response: Inspect primary result block type
  const rawPrimary =
    response.result_blocks?.find(b => b.id === response.primary_result_id) ||
    response.result_block ||
    null;

  if (rawPrimary?.type === 'READBACK_CONFIRMATION') {
    return {
      type: 'confirmation_pending',
      message: 'Action proposal: review the parameters and confirm to commit.',
    };
  }

  if (rawPrimary?.type === 'ACTION_RECEIPT') {
    return {
      type: 'committed',
      message: response.assistant_message || 'Action executed and committed successfully.',
    };
  }

  if (rawPrimary?.type === 'DENIAL_BANNER') {
    return {
      type: 'denial',
      message: response.assistant_message || 'Access to this resource was denied.',
    };
  }

  return {
    type: 'result_ready',
    message: response.assistant_message,
  };
}

/**
 * Derives a coherent trust/evidence banner string from backend response and session state.
 */
export function resolveEvidenceSummary(
  response: VoiceTurnResponse,
  session: SessionInfo
): string {
  const isVerified = session.state === 'VERIFIED' && Boolean(session.actor);
  const trust = response.trust_evidence;
  const code = response.error?.code?.toUpperCase();

  // Explicit provider failure
  if (code === 'PROVIDER_UNAVAILABLE' || code === 'DETECTIF_UNAVAILABLE') {
    return 'Identity verification temporarily unavailable';
  }

  // Specific biometric rejection: Check authenticity/synthetic first
  if (trust?.authenticity_verdict === 'FAIL' || code === 'SYNTHETIC_AUDIO') {
    return 'Audio authenticity failed: Synthetic or replayed speech';
  }
  if (trust?.speaker_decision === 'REJECT') {
    return 'Voice verification failed: Speaker biometric mismatch';
  }

  // Verification Required
  if (response.status === 'denial' && code === 'VERIFICATION_REQUIRED') {
    return 'Additional voice verification required for this operation';
  }

  // Verified Actor Session
  if (isVerified && session.actor) {
    if (response.status === 'denial') {
      return `Access denied by policy · Verified actor: ${session.actor.fullName} (${session.actor.employeeId})`;
    }
    const rawPrimary =
      response.result_blocks?.find(b => b.id === response.primary_result_id) ||
      response.result_block ||
      null;

    if (rawPrimary?.type === 'ACTION_RECEIPT') {
      return `Action committed to database · Actor: ${session.actor.fullName}`;
    }
    if (rawPrimary?.type === 'READBACK_CONFIRMATION') {
      return `Proposed action draft awaiting confirmation · Actor: ${session.actor.fullName}`;
    }
    return `Identity Verified: ${session.actor.fullName} (${session.actor.employeeId}) · Role: ${session.actor.role.toUpperCase()}`;
  }

  // General Biometrics Summary
  if (trust && trust.speaker_decision && trust.authenticity_verdict) {
    return `Speaker: ${trust.speaker_decision} · Authenticity: ${trust.authenticity_verdict}`;
  }

  // Public Query (No biometrics needed)
  if (response.status === 'success') {
    return 'Public query processed · No employee identity required';
  }

  // Session Expired
  if (session.state === 'EXPIRED') {
    return 'Session expired · Re-verification required for private workspace';
  }

  return 'Verification required for private workspace access';
}

/**
 * Filters result blocks strictly enforcing that sensitive blocks (isSensitive: true)
 * can NEVER be returned or displayed unless the session is currently VERIFIED.
 */
export function resolveSafeResultBlocks(
  blocks: GenericResultBlock[] | undefined,
  primaryId: string | null | undefined,
  isVerified: boolean
): { safePrimary: GenericResultBlock | null; safeBlocks: GenericResultBlock[] } {
  const allRaw = blocks || [];
  const rawPrimary = allRaw.find(b => b.id === primaryId) || (allRaw.length > 0 ? allRaw[0] : null);

  const safePrimary = rawPrimary && (!rawPrimary.isSensitive || isVerified) ? rawPrimary : null;
  const safeBlocks = allRaw.filter(b => !b.isSensitive || isVerified);

  return { safePrimary, safeBlocks };
}

/**
 * Derives a human-readable reason why microphone input is disabled.
 */
export function deriveDisabledReason(
  status: TurnStatusNotice,
  isPlayingAudio: boolean
): string {
  if (isPlayingAudio) return 'Playing response…';
  if (status.type === 'executing') return 'Executing action…';
  if (status.type === 'verifying') return 'Verifying voice…';
  if (status.type === 'transcribing') return 'Finalizing request…';
  if (status.type === 'confirmation_pending') return 'Confirmation required';
  if (status.message) return status.message;
  return 'Processing voice turn…';
}
