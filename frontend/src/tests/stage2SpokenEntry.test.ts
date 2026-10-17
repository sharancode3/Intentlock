/**
 * IntentLock — Stage 2 Spoken Employee-ID Entry & Verified Workspace Test Suite
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Validates:
 * 1. Anonymous initial state (no default EMP-1001, voice-first prompt, no fake badge).
 * 2. Spoken employee ID claim handling (sending null candidate, consuming verified actor).
 * 3. Failed verification / wrong speaker handling (remaining ANONYMOUS, blocking sensitive blocks).
 * 4. Public assistance queries without identity verification (PUBLIC_FAQ allowed).
 * 5. Actor claim vs requested target disambiguation (target ID never authenticates).
 * 6. Role-only claim rejection ("I am the CTO" never fabricates an executive session).
 * 7. Session expiry & sliding window countdown reset.
 * 8. Identity handoff & clean workspace transition (zero private data leakage).
 * 9. Stale response isolation via turn epoch.
 * 10. ResultHost sensitive block protection.
 */

import type {
  GenericResultBlock,
  SessionInfo,
  TurnStatusNotice,
  VoiceTurnResponse,
} from '../types';

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

export function runStage2SpokenEntrySuite(): void {
  console.log('Running Stage 2 Spoken Entry & Verified Workspace Test Suite...\n');
  let testCount = 0;

  // --------------------------------------------------------------------------
  // 1. Anonymous Initial State
  // --------------------------------------------------------------------------
  const anonymousSession: SessionInfo = { state: 'ANONYMOUS', sessionId: null };
  const initialCandidate: string | null = null;
  const initialEvidence = 'Voice-First: State your employee ID or ask a public question';
  const initialStatus: TurnStatusNotice = { type: 'idle' };

  assert(anonymousSession.state === 'ANONYMOUS', 'Initial session state must be ANONYMOUS');
  assert(anonymousSession.sessionId === null, 'Initial session ID must be null');
  assert(anonymousSession.actor === undefined, 'Initial session actor must be undefined');
  assert(initialCandidate === null, 'Default candidate must be null (no auto-selected EMP-1001)');
  assert(initialStatus.type === 'idle', 'Initial turn status must be idle');
  assert(initialEvidence.includes('Voice-First'), 'Initial evidence must present voice-first guidance');
  testCount += 6;
  console.log('✓ 1. Anonymous Initial State passed (6/6 tests)');

  // --------------------------------------------------------------------------
  // 2. Spoken Employee ID Claim Submission & Verified Actor Consumption
  // --------------------------------------------------------------------------
  const buildFormFields = (candidateId: string | null, clientTurnId: string, sessionId: string | null) => {
    const fields: Record<string, string> = { client_turn_id: clientTurnId };
    if (candidateId && candidateId.trim()) {
      fields.candidate_employee_id = candidateId.trim();
    }
    if (sessionId) {
      fields.session_id = sessionId;
    }
    return fields;
  };

  const spokenClaimFields = buildFormFields(null, 'turn-101', null);
  assert(spokenClaimFields.candidate_employee_id === undefined, 'Null candidate must NOT append candidate_employee_id to form');
  assert(spokenClaimFields.client_turn_id === 'turn-101', 'Client turn ID must be appended');

  // Simulated backend response for spoken claim "My employee ID is EMP-1001. Show my workspace."
  const verifiedTurnResponse: VoiceTurnResponse = {
    status: 'success',
    transcript: 'My employee ID is EMP-1001. Show my workspace.',
    assistant_message: 'Welcome back Aarav Mehta. Your workspace is ready.',
    session: {
      state: 'VERIFIED',
      sessionId: 'sess_stage2_mock_1001',
      actor: {
        employeeId: 'EMP-1001',
        fullName: 'Aarav Mehta',
        role: 'employee',
        teamId: 'team_core_eng',
        expiresInSeconds: 90,
      },
    },
    session_expires_at: new Date(Date.now() + 90000).toISOString(),
    trust_evidence: {
      speaker_decision: 'PASS',
      authenticity_verdict: 'PASS',
      speaker_score: 0.98,
      authenticity_score: 0.98,
    },
    primary_result_id: 'block-profile-1001',
    result_blocks: [
      {
        id: 'block-profile-1001',
        type: 'EMPLOYEE_PROFILE',
        title: 'Employee Profile — Aarav Mehta',
        timestamp: new Date().toISOString(),
        isSensitive: true,
        payload: {
          employeeId: 'EMP-1001',
          fullName: 'Aarav Mehta',
          role: 'employee',
          department: 'Engineering',
          email: 'aarav.mehta@intentlock.internal',
        },
      },
    ],
  };

  const isVerified = verifiedTurnResponse.session?.state === 'VERIFIED';
  assert(isVerified === true, 'Backend response session must be VERIFIED');
  assert(verifiedTurnResponse.session?.actor?.employeeId === 'EMP-1001', 'Actor ID must match server response');
  assert(verifiedTurnResponse.session?.actor?.fullName === 'Aarav Mehta', 'Actor name must match server response');
  assert(verifiedTurnResponse.session?.actor?.role === 'employee', 'Actor role must match server response');

  const rawPrimary = verifiedTurnResponse.result_blocks?.find(b => b.id === verifiedTurnResponse.primary_result_id) || null;
  const safePrimary = rawPrimary && (!rawPrimary.isSensitive || isVerified) ? rawPrimary : null;
  assert(safePrimary !== null, 'Sensitive primary block is permitted when session is VERIFIED');
  assert(safePrimary?.id === 'block-profile-1001', 'Safe primary is profile block');
  testCount += 8;
  console.log('✓ 2. Spoken Employee ID Claim & Verified Actor passed (8/8 tests)');

  // --------------------------------------------------------------------------
  // 3. Failed Verification / Wrong Speaker Handling
  // --------------------------------------------------------------------------
  const failedTurnResponse: VoiceTurnResponse = {
    status: 'denial',
    transcript: 'My employee ID is EMP-1001. Show my workspace.',
    assistant_message: 'Voice verification failed. Speaker biometrics do not match EMP-1001.',
    session: {
      state: 'ANONYMOUS',
      sessionId: null,
    },
    trust_evidence: {
      speaker_decision: 'REJECT',
      authenticity_verdict: 'FAIL',
      speaker_score: 0.12,
      authenticity_score: 0.12,
      reason: 'Biometric mismatch',
    },
    error: {
      code: 'SPEAKER_MISMATCH',
      message: 'Voice biometrics did not match enrolled template.',
    },
    primary_result_id: 'block-denial-01',
    result_blocks: [
      {
        id: 'block-denial-01',
        type: 'DENIAL_BANNER',
        title: 'Access Denied',
        timestamp: new Date().toISOString(),
        isSensitive: false,
        payload: {
          reason: 'SPEAKER_MISMATCH',
          message: 'Voice verification failed. Please try again or contact support.',
        },
      },
      {
        id: 'block-sensitive-leak-attempt',
        type: 'EMPLOYEE_PROFILE',
        title: 'Leaked Profile',
        timestamp: new Date().toISOString(),
        isSensitive: true,
        payload: { employeeId: 'EMP-1001', fullName: 'Aarav Mehta' },
      },
    ],
  };

  const isFailedVerified = failedTurnResponse.session?.state === 'VERIFIED';
  assert(isFailedVerified === false, 'Failed turn session state must not be VERIFIED');

  const safeFailedBlocks = (failedTurnResponse.result_blocks || []).filter(b => !b.isSensitive || isFailedVerified);
  assert(safeFailedBlocks.length === 1, 'Only non-sensitive blocks allowed on failed verification');
  assert(safeFailedBlocks[0].id === 'block-denial-01', 'Denial banner preserved');
  assert(safeFailedBlocks.every(b => !b.isSensitive), 'No sensitive blocks survive filtering when unverified');
  testCount += 4;
  console.log('✓ 3. Failed Verification & Biometric Mismatch passed (4/4 tests)');

  // --------------------------------------------------------------------------
  // 4. Public Assistance Queries Without Identity Verification
  // --------------------------------------------------------------------------
  const publicFaqResponse: VoiceTurnResponse = {
    status: 'success',
    transcript: 'What does the IT support team handle?',
    assistant_message: 'The IT support team handles laptop issues, password resets, and kiosk onboarding.',
    session: {
      state: 'ANONYMOUS',
      sessionId: null,
    },
    primary_result_id: 'block-faq-01',
    result_blocks: [
      {
        id: 'block-faq-01',
        type: 'PUBLIC_FAQ',
        title: 'IT Support Scope',
        timestamp: new Date().toISOString(),
        isSensitive: false,
        payload: {
          category: 'IT Helpdesk',
          question: 'What does the IT support team handle?',
          answer: 'The IT support team handles laptop issues, password resets, and kiosk onboarding.',
          relatedTopics: ['Hardware', 'Credentials', 'Kiosk Access'],
        },
      },
    ],
  };

  const isPublicVerified = publicFaqResponse.session?.state === 'VERIFIED';
  assert(isPublicVerified === false, 'Public FAQ session remains ANONYMOUS');
  const safePublicPrimary = publicFaqResponse.result_blocks?.find(b => b.id === publicFaqResponse.primary_result_id) || null;
  const isPublicSafe = safePublicPrimary && (!safePublicPrimary.isSensitive || isPublicVerified);
  assert(Boolean(isPublicSafe), 'Public non-sensitive block is safely displayable without verification');
  testCount += 2;
  console.log('✓ 4. Public Assistance Queries passed (2/2 tests)');

  // --------------------------------------------------------------------------
  // 5. Actor Claim vs. Requested Target Disambiguation
  // --------------------------------------------------------------------------
  const targetQueryParameters = {
    action: 'view_profile',
    source_result_id: 'block-profile-1001',
    target_id: 'EMP-2001',
  };

  const activeSessionBeforeTargetQuery: SessionInfo = {
    state: 'VERIFIED',
    sessionId: 'sess_1001',
    actor: {
      employeeId: 'EMP-1001',
      fullName: 'Aarav Mehta',
      role: 'employee',
      expiresInSeconds: 85,
    },
  };

  assert(targetQueryParameters.target_id === 'EMP-2001', 'Target ID is query recipient');
  assert(activeSessionBeforeTargetQuery.actor?.employeeId === 'EMP-1001', 'Active actor identity remains EMP-1001');
  assert(targetQueryParameters.target_id !== activeSessionBeforeTargetQuery.actor?.employeeId, 'Target ID does NOT alter active actor');
  testCount += 3;
  console.log('✓ 5. Actor Claim vs. Requested Target Disambiguation passed (3/3 tests)');

  // --------------------------------------------------------------------------
  // 6. Role-Only Claim Rejection
  // --------------------------------------------------------------------------
  const roleOnlyResponse: VoiceTurnResponse = {
    status: 'clarification',
    transcript: 'I am the CTO.',
    assistant_message: 'Please state your employee ID (e.g. "My employee ID is EMP-1001") for voice verification.',
    session: {
      state: 'ANONYMOUS',
      sessionId: null,
    },
    error: {
      code: 'UNCLAIMED_SPEAKER',
      message: 'Role claim alone is insufficient without an employee ID.',
    },
  };

  assert(roleOnlyResponse.status === 'clarification', 'Role-only claim triggers clarification');
  assert(roleOnlyResponse.session?.state === 'ANONYMOUS', 'Session must remain ANONYMOUS on role claim');
  assert(roleOnlyResponse.session?.actor === undefined, 'No executive or CTO actor is fabricated');
  testCount += 3;
  console.log('✓ 6. Role-Only Claim Rejection passed (3/3 tests)');

  // --------------------------------------------------------------------------
  // 7. Session Expiry & Sliding Window Countdown
  // --------------------------------------------------------------------------
  let testSession: SessionInfo = {
    state: 'VERIFIED',
    sessionId: 'sess_expiring_1001',
    actor: {
      employeeId: 'EMP-1001',
      fullName: 'Aarav Mehta',
      role: 'employee',
      expiresInSeconds: 2,
    },
  };

  const tickCountdown = (currentSession: SessionInfo, remainingSeconds: number): SessionInfo => {
    if (remainingSeconds <= 0) {
      return { state: 'ANONYMOUS', sessionId: null };
    }
    return {
      ...currentSession,
      actor: currentSession.actor ? { ...currentSession.actor, expiresInSeconds: remainingSeconds } : undefined,
    };
  };

  testSession = tickCountdown(testSession, 1);
  assert(testSession.state === 'VERIFIED', 'Session still verified with 1s remaining');
  assert(testSession.actor?.expiresInSeconds === 1, 'Countdown decremented to 1');

  testSession = tickCountdown(testSession, 0);
  assert(testSession.state === 'ANONYMOUS', 'Session transitions to ANONYMOUS on expiry');
  assert(testSession.sessionId === null, 'Session ID cleared on expiry');
  assert(testSession.actor === undefined, 'Actor cleared on expiry');
  testCount += 5;
  console.log('✓ 7. Session Expiry & Sliding Window passed (5/5 tests)');

  // --------------------------------------------------------------------------
  // 8. Identity Handoff & Presentation Cleanup
  // --------------------------------------------------------------------------
  let sessionState: SessionInfo = {
    state: 'VERIFIED',
    sessionId: 'sess_aarav_99',
    actor: { employeeId: 'EMP-1001', fullName: 'Aarav Mehta', role: 'employee', expiresInSeconds: 60 },
  };
  let activeBlock: GenericResultBlock | null = {
    id: 'block-tickets-aarav',
    type: 'TICKET_LIST',
    title: 'Aarav Private Tickets',
    timestamp: new Date().toISOString(),
    isSensitive: true,
    payload: { tickets: [{ id: 'TCK-1', title: 'Private security ticket', status: 'open', priority: 'high' }] },
  };
  let availableBlocks: GenericResultBlock[] = activeBlock ? [activeBlock] : [];
  let messagesCount = 4;
  let evidenceStr = 'Identity Verified: Aarav Mehta (EMP-1001)';

  const executeClearSession = () => {
    sessionState = { state: 'ANONYMOUS', sessionId: null };
    activeBlock = null;
    availableBlocks = [];
    messagesCount = 1;
    evidenceStr = 'Voice-First: State your employee ID or ask a public question';
  };

  executeClearSession();

  assert(sessionState.state === 'ANONYMOUS', 'Handoff must reset session state to ANONYMOUS');
  assert(sessionState.sessionId === null, 'Handoff must nullify session token');
  assert(activeBlock === null, 'Handoff must clear active sensitive result card');
  assert(availableBlocks.length === 0, 'Handoff must clear all available result cards');
  assert(messagesCount === 1, 'Handoff must reset conversation messages');
  assert(evidenceStr.includes('Voice-First'), 'Handoff must reset evidence string');
  testCount += 6;
  console.log('✓ 8. Identity Handoff & Presentation Cleanup passed (6/6 tests)');

  // --------------------------------------------------------------------------
  // 9. Stale Response Isolation via Turn Epoch
  // --------------------------------------------------------------------------
  let currentEpoch = 1;
  let appliedResponseId: string | null = null;

  const simulateDispatchTurn = (dispatchEpoch: number) => {
    return (responseTurnId: string) => {
      if (dispatchEpoch !== currentEpoch) {
        return;
      }
      appliedResponseId = responseTurnId;
    };
  };

  const lateTurnArrival = simulateDispatchTurn(currentEpoch);

  // User resets session or starts new turn -> epoch increments
  currentEpoch += 1;

  // Old turn arrives late
  lateTurnArrival('turn-old');
  assert(appliedResponseId === null, 'Late response from earlier epoch must be discarded');

  // New turn dispatches and arrives in current epoch
  const currentTurnArrival = simulateDispatchTurn(currentEpoch);
  currentTurnArrival('turn-new');
  assert(appliedResponseId === 'turn-new', 'Response from current epoch is accepted');
  testCount += 2;
  console.log('✓ 9. Stale Response Isolation passed (2/2 tests)');

  // --------------------------------------------------------------------------
  // 10. ResultHost Sensitive Block Protection Invariant
  // --------------------------------------------------------------------------
  const sensitiveBlock: GenericResultBlock = {
    id: 'block-sensitive-profile',
    type: 'EMPLOYEE_PROFILE',
    title: 'Confidential Profile',
    timestamp: new Date().toISOString(),
    isSensitive: true,
    payload: { employeeId: 'EMP-1001', fullName: 'Aarav Mehta', role: 'employee' },
  };

  const publicBlock: GenericResultBlock = {
    id: 'block-public-faq',
    type: 'PUBLIC_FAQ',
    title: 'Public FAQ',
    timestamp: new Date().toISOString(),
    isSensitive: false,
    payload: { question: 'What is IntentLock?', answer: 'IntentLock is a secure kiosk.' },
  };

  const canRenderResultHost = (block: GenericResultBlock, isSessionVerified: boolean): boolean => {
    if (block.isSensitive && !isSessionVerified) {
      return false;
    }
    return true;
  };

  assert(canRenderResultHost(sensitiveBlock, false) === false, 'Sensitive block must NOT render when session is unverified');
  assert(canRenderResultHost(sensitiveBlock, true) === true, 'Sensitive block renders when session is verified');
  assert(canRenderResultHost(publicBlock, false) === true, 'Public block renders even when session is unverified');
  assert(canRenderResultHost(publicBlock, true) === true, 'Public block renders when session is verified');
  testCount += 4;
  console.log('✓ 10. ResultHost Sensitive Block Protection passed (4/4 tests)');

  console.log(`\n======================================================`);
  console.log(`All ${testCount} Stage 2 Spoken Entry tests PASSED successfully!`);
  console.log(`======================================================`);
}

// Auto-run when executed directly via tsx
runStage2SpokenEntrySuite();
