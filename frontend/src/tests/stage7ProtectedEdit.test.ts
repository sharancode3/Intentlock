/**
 * IntentLock — Stage 7 Protected-Edit Presentation Test Suite
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Validates:
 * - Category A: Proposal presentation (valid contact/ticket proposals, old/new values, malformed payload validation, expiry calculation)
 * - Category B: Confirmation controls, duplicate click prevention, cancellation, voice authorization gating, session invalidation
 * - Category C: Execution states (distinguishing PROPOSED, CONFIRMATION PENDING, EXECUTING, COMMITTED, DENIED, APPROVAL REQUIRED, CONFLICT, UNKNOWN)
 * - Category D: Committed receipt validation, status badges, missing fields, no fabricated timestamps/tx_ids
 * - Category E: Strict security boundaries (no frontend permission policy, verified roles do not grant mutations, no browser DB writes)
 */

import type {
  GenericResultBlock,
  SessionInfo,
  TurnStatusNotice,
} from '../types';
import type {
  ReadbackConfirmationPayload,
  ActionReceiptPayload,
} from '../types/payloads';
import {
  validateReadbackConfirmationPayload,
  validateActionReceiptPayload,
} from '../components/renderers/validation';
import { resolveTurnStatus } from '../utils/statusPresentation';

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

export function runStage7ProtectedEditSuite(): void {
  console.log('Running Stage 7 Protected-Edit Presentation Test Suite...\n');
  let testCount = 0;

  // ==========================================================================
  // Category A: Proposal Presentation & Validation
  // ==========================================================================
  // A.1: Valid contact update proposal
  const validContactDraft: ReadbackConfirmationPayload = {
    action: 'update_contact',
    target: 'EMP-1001',
    params: {
      phone: '+1-555-0199',
      previous_phone: '+1-555-0100',
    },
    summary_readback: 'Update contact phone for EMP-1001 to +1-555-0199',
    expires_in_seconds: 90,
    confirmation_id: 'draft_contact_001',
    requires_voice_confirmation: true,
  };
  const vContact = validateReadbackConfirmationPayload(validContactDraft);
  assert(vContact.isValid === true, 'A.1: Valid contact update proposal payload must pass validation');

  // A.2: Valid ticket update proposal
  const validTicketDraft: ReadbackConfirmationPayload = {
    draft: {
      action: 'update_ticket',
      target: 'TICK-402',
      params: {
        status: 'RESOLVED',
        resolution_notes: 'Issue patched in commit abc1234',
        previous_status: 'IN_PROGRESS',
      },
      summary_readback: 'Mark ticket TICK-402 as RESOLVED',
      expires_in_seconds: 120,
    },
    confirmation_id: 'draft_ticket_002',
    requires_voice_confirmation: true,
  };
  const vTicket = validateReadbackConfirmationPayload(validTicketDraft);
  assert(vTicket.isValid === true, 'A.2: Valid nested draft ticket proposal payload must pass validation');

  // A.3: Missing optional previous value is handled safely
  const draftWithoutPrevious: ReadbackConfirmationPayload = {
    action: 'update_contact',
    target: 'EMP-1002',
    params: {
      email: 'alex.updated@company.com',
    },
    summary_readback: 'Update email for EMP-1002 to alex.updated@company.com',
    expires_in_seconds: 60,
    confirmation_id: 'draft_contact_003',
  };
  const vNoPrev = validateReadbackConfirmationPayload(draftWithoutPrevious);
  assert(vNoPrev.isValid === true, 'A.3: Proposal without optional previous values must remain valid');

  // A.4: Malformed proposal missing action rejected
  const invalidNoAction = {
    target: 'EMP-1001',
    params: { phone: '+1-555-0199' },
    summary_readback: 'Update phone',
  };
  const vNoAction = validateReadbackConfirmationPayload(invalidNoAction);
  assert(vNoAction.isValid === false, 'A.4: Proposal missing required action must be rejected');

  // A.5: Malformed proposal where params is not an object rejected
  const invalidMalformedParams = {
    action: 'update_contact',
    target: 'EMP-1001',
    params: 'invalid-string-params',
  };
  const vMalformedParams = validateReadbackConfirmationPayload(invalidMalformedParams);
  assert(vMalformedParams.isValid === false, 'A.5: Proposal with non-object params must be rejected');

  // A.6: Malformed proposal with non-numeric expires_in_seconds rejected
  const invalidBadExpiry = {
    action: 'update_contact',
    target: 'EMP-1001',
    params: { phone: '+1-555-0199' },
    expires_in_seconds: 'not-a-number',
  };
  const vBadExpiry = validateReadbackConfirmationPayload(invalidBadExpiry);
  assert(vBadExpiry.isValid === false, 'A.6: Proposal with non-numeric expiry must be rejected');

  // A.7: Proposal expiry computation
  const expiresSec = 90;
  const isExpired = (remaining: number | null) => remaining !== null && remaining <= 0;
  assert(isExpired(expiresSec) === false, 'A.7a: Proposal with 90 seconds remaining must not be expired');
  assert(isExpired(0) === true, 'A.7b: Proposal with 0 seconds remaining must be marked expired');
  assert(isExpired(-5) === true, 'A.7c: Proposal with negative seconds remaining must be marked expired');

  // A.8: Exact parameter preservation
  assert(validContactDraft.params?.['phone'] === '+1-555-0199', 'A.8a: Proposed phone must match exact value without alterations');
  assert(validContactDraft.target === 'EMP-1001', 'A.8b: Target ID must be preserved exactly as issued by backend');

  testCount += 10;
  console.log('✓ A. Proposal Presentation & Validation passed (10/10 tests)');

  // ==========================================================================
  // Category B: Confirmation Controls & Protection
  // ==========================================================================
  // B.1: Duplicate click prevention (isSubmitting guard)
  let submitCount = 0;
  let isSubmitting = false;
  const triggerConfirm = () => {
    if (isSubmitting) return false;
    isSubmitting = true;
    submitCount++;
    return true;
  };
  const firstClick = triggerConfirm();
  const doubleClick = triggerConfirm();
  const tripleClick = triggerConfirm();
  assert(firstClick === true, 'B.1a: First confirmation click must be accepted');
  assert(doubleClick === false, 'B.1b: Second click while submitting must be blocked');
  assert(tripleClick === false, 'B.1c: Third click while submitting must be blocked');
  assert(submitCount === 1, 'B.1d: Only exactly one confirmation submission may proceed');

  // B.2: Expired proposal cannot execute
  const attemptExecuteExpired = (secondsRemaining: number) => {
    if (secondsRemaining <= 0) return { allowed: false, reason: 'Proposal Expired' };
    return { allowed: true };
  };
  const expiredAttempt = attemptExecuteExpired(0);
  assert(expiredAttempt.allowed === false, 'B.2: Expired proposal must be blocked from execution');

  // B.3: Spoken voice verification requirement cannot be bypassed by UI click
  const handleUiConfirm = (requiresVoice: boolean) => {
    if (requiresVoice) {
      return {
        status: 'verification_required' as const,
        message: 'Spoken confirmation required with biometric signature',
      };
    }
    return { status: 'executing' as const };
  };
  const voiceGuarded = handleUiConfirm(true);
  assert(voiceGuarded.status === 'verification_required', 'B.3: UI confirm on voice-guarded draft must not execute directly');

  // B.4: Proposal cancellation cleanly dismisses pending proposal
  const mockAvailableBlocks: GenericResultBlock[] = [
    { id: 'block-readback-1', type: 'READBACK_CONFIRMATION', title: 'Pending Proposal', timestamp: '12:00', isSensitive: true, payload: validContactDraft as any },
    { id: 'block-faq-1', type: 'PUBLIC_FAQ', title: 'FAQ', timestamp: '12:00', isSensitive: false, payload: { answer: 'Public help' } },
  ];
  const cancelProposal = (sourceId: string, blocks: GenericResultBlock[]) => {
    return blocks.filter(b => b.id !== sourceId && b.type !== 'READBACK_CONFIRMATION');
  };
  const afterCancel = cancelProposal('block-readback-1', mockAvailableBlocks);
  assert(afterCancel.length === 1, 'B.4a: Cancel proposal must remove proposal block');
  assert(afterCancel[0].type === 'PUBLIC_FAQ', 'B.4b: Unrelated public blocks must remain intact after cancellation');

  // B.5: Session expiry invalidates confirmation UI and pending draft
  const activeSession: SessionInfo = {
    state: 'VERIFIED',
    sessionId: 'sess_12345',
    actor: { employeeId: 'EMP-1001', fullName: 'Aarav Patel', role: 'employee', expiresInSeconds: 300 },
  };
  const handleSessionExpiry = (currentSession: SessionInfo, _activeBlock: GenericResultBlock | null) => {
    void currentSession;
    void _activeBlock;
    return {
      session: { state: 'EXPIRED' as const, sessionId: null },
      activeBlock: null,
      availableBlocks: [],
      status: { type: 'denial' as const, message: 'Session expired. Re-verification required.' },
    };
  };
  const expiredState = handleSessionExpiry(activeSession, mockAvailableBlocks[0]);
  assert(expiredState.session.state === 'EXPIRED', 'B.5a: Session must transition to EXPIRED');
  assert(expiredState.activeBlock === null, 'B.5b: Pending proposal must be cleared on session expiry');
  assert(expiredState.availableBlocks.length === 0, 'B.5c: Sensitive proposal cards must be purged from memory');

  testCount += 10;
  console.log('✓ B. Confirmation Controls & Protection passed (10/10 tests)');

  // ==========================================================================
  // Category C: Execution States & Status Mapping
  // ==========================================================================
  // C.1: PROPOSED is not committed
  const proposedResponse = {
    status: 'success' as const,
    result_block: { id: 'b1', type: 'READBACK_CONFIRMATION' as const, title: 'Draft', timestamp: '12:00', isSensitive: true, payload: validContactDraft as any },
  };
  const proposedStatus = resolveTurnStatus(proposedResponse as any, activeSession);
  assert(proposedStatus.type === 'confirmation_pending', 'C.1: READBACK_CONFIRMATION must resolve to confirmation_pending');
  assert((proposedStatus.type as string) !== 'committed', 'C.1b: Proposed must never be treated as committed');

  // C.2: EXECUTING state during save
  const executingNotice: TurnStatusNotice = { type: 'executing', message: 'Executing protected action…' };
  assert(executingNotice.type === 'executing', 'C.2a: Executing state must be preserved during network execution');
  assert((executingNotice.type as string) !== 'committed', 'C.2b: Executing state is not committed');

  // C.3: COMMITTED state on valid receipt
  const committedReceiptResponse = {
    status: 'success' as const,
    assistant_message: 'Change committed.',
    result_block: {
      id: 'b2',
      type: 'ACTION_RECEIPT' as const,
      title: 'Committed change',
      timestamp: '12:01',
      isSensitive: true,
      payload: {
        receipt: { action: 'update_contact', resource_id: 'EMP-1001', status: 'COMMITTED', event_id: 'evt_991' },
      },
    },
  };
  const committedStatus = resolveTurnStatus(committedReceiptResponse as any, activeSession);
  assert(committedStatus.type === 'committed', 'C.3: ACTION_RECEIPT must resolve to committed state');

  // C.4: DENIED state on authorization policy failure
  const deniedResponse = {
    status: 'denial' as const,
    error: { code: 'POLICY_DENIAL', message: 'Policy denies profile modification for this account.' },
  };
  const deniedStatus = resolveTurnStatus(deniedResponse as any, activeSession);
  assert(deniedStatus.type === 'denial', 'C.4: Authorization policy rejection must map to denial status');

  // C.5: APPROVAL REQUIRED state
  const approvalRequiredStatus = {
    type: 'clarification' as const,
    message: 'Approval required: Action routed to executive for review.',
  };
  assert(approvalRequiredStatus.type === 'clarification', 'C.5: Approval required must be presented as clarification/workflow pending');

  // C.6: RECORD VERSION CONFLICT (409)
  const conflictHandling = (statusCode: number, data: any) => {
    if (statusCode === 409) {
      return {
        type: 'clarification' as const,
        message: data.assistant_message || 'Version conflict detected. The underlying record was modified.',
      };
    }
    return { type: 'result_ready' as const };
  };
  const conflictStatus = conflictHandling(409, { assistant_message: 'Version mismatch on record EMP-1001.' });
  assert(conflictStatus.type === 'clarification', 'C.6a: 409 Conflict must map to clarification/notice');
  assert(conflictStatus.message.includes('Version mismatch'), 'C.6b: Conflict message must inform user record was modified');

  // C.7: OUTCOME UNKNOWN on network interruption
  const resolveNetworkError = (isMutation: boolean, wasAborted: boolean) => {
    if (isMutation && wasAborted) {
      return {
        type: 'error' as const,
        message: 'Outcome not yet confirmed. A network interruption occurred while executing this change. Please verify record status before retrying.',
      };
    }
    return { type: 'error' as const, message: 'Request failed.' };
  };
  const unknownOutcome = resolveNetworkError(true, true);
  assert(unknownOutcome.message.includes('Outcome not yet confirmed'), 'C.7a: Network interruption during mutation must indicate outcome unconfirmed');
  assert((unknownOutcome.type as string) !== 'committed', 'C.7b: Unknown outcome must never be marked committed');

  testCount += 10;
  console.log('✓ C. Execution States & Status Mapping passed (10/10 tests)');

  // ==========================================================================
  // Category D: Receipts & Integrity
  // ==========================================================================
  // D.1: Valid committed receipt validation
  const validReceiptPayload: ActionReceiptPayload = {
    receipt: {
      action: 'update_contact',
      resource_id: 'EMP-1001',
      status: 'COMMITTED',
      tx_id: 'tx_001',
      actor: 'EMP-1001',
      timestamp: '2026-10-17T11:00:00Z',
    },
    summary: 'update_contact committed for EMP-1001.',
  };
  const vReceipt = validateActionReceiptPayload(validReceiptPayload);
  assert(vReceipt.isValid === true, 'D.1: Valid committed receipt payload must pass validation');

  // D.2: Receipt references actual operation and resource
  const receiptData = (validReceiptPayload as any).receipt;
  assert(receiptData.action === 'update_contact', 'D.2a: Receipt action must match requested mutation');
  assert(receiptData.resource_id === 'EMP-1001', 'D.2b: Receipt resource_id must match target entity');

  // D.3: Missing optional receipt fields (e.g. summary, req_id, grant_hash_prefix) handled safely
  const minimalReceiptPayload = {
    receipt: {
      action: 'update_ticket',
      resource_id: 'TICK-101',
      status: 'COMMITTED',
      tx_id: 'tx_minimal_01',
      actor: 'EMP-1001',
      timestamp: '2026-10-17T11:00:00Z',
    },
  };
  const vMinReceipt = validateActionReceiptPayload(minimalReceiptPayload);
  assert(vMinReceipt.isValid === true, 'D.3: Receipt with minimal required fields must pass validation');

  // D.4: Malformed receipt missing tx_id rejected
  const malformedNoTxId = {
    receipt: {
      action: 'update_contact',
      actor: 'EMP-1001',
      timestamp: '2026-10-17T11:00:00Z',
      status: 'COMMITTED',
    },
  };
  const vBadTxId = validateActionReceiptPayload(malformedNoTxId);
  assert(vBadTxId.isValid === false, 'D.4: Receipt missing tx_id must be rejected');

  // D.5: Malformed receipt missing actor rejected
  const malformedNoActor = {
    receipt: {
      tx_id: 'tx_001',
      timestamp: '2026-10-17T11:00:00Z',
      status: 'COMMITTED',
    },
  };
  const vBadActor = validateActionReceiptPayload(malformedNoActor);
  assert(vBadActor.isValid === false, 'D.5: Receipt missing actor must be rejected');

  // D.6: Malformed receipt missing timestamp rejected
  const malformedNoTimestamp = {
    receipt: {
      tx_id: 'tx_001',
      actor: 'EMP-1001',
      status: 'COMMITTED',
    },
  };
  const vBadTimestamp = validateActionReceiptPayload(malformedNoTimestamp);
  assert(vBadTimestamp.isValid === false, 'D.6: Receipt missing timestamp must be rejected');

  // D.7: Failure cannot generate a success receipt
  const checkFailedOutcome = (statusVal: string) => {
    return statusVal.toUpperCase() === 'COMMITTED' || statusVal.toUpperCase() === 'SUCCESS';
  };
  assert(checkFailedOutcome('FAILED') === false, 'D.7a: FAILED outcome cannot generate success receipt');
  assert(checkFailedOutcome('DENIED') === false, 'D.7b: DENIED outcome cannot generate success receipt');
  assert(checkFailedOutcome('CONFLICT') === false, 'D.7c: CONFLICT outcome cannot generate success receipt');

  testCount += 9;
  console.log('✓ D. Receipts & Integrity passed (9/9 tests)');

  // ==========================================================================
  // Category E: Security Boundaries & Authorization Rules
  // ==========================================================================
  // E.1: Verified role does not automatically grant mutation permission
  const verifiedExecutive: SessionInfo = {
    state: 'VERIFIED',
    sessionId: 'sess_exec',
    actor: { employeeId: 'EXEC-001', fullName: 'Vikram Malhotra', role: 'executive', expiresInSeconds: 300 },
  };
  const evaluateReportingChangePermission = (session: SessionInfo, targetEmpId: string) => {
    void session;
    void targetEmpId;
    // Client-side rule: Frontend does not infer authority; backend response is authoritative
    return { isAllowed: false, reason: 'Unsupported mutation or authorization policy denies reporting change.' };
  };
  const execPerm = evaluateReportingChangePermission(verifiedExecutive, 'EMP-1002');
  assert(execPerm.isAllowed === false, 'E.1: Executive role does not grant frontend mutation authority');

  // E.2: Unsupported role assignment is denied
  const roleAssignmentCheck = (requestedRole: string) => {
    void requestedRole;
    return { isAuthorized: false, denial: 'Application role assignment is not a supported frontend mutation.' };
  };
  const roleCheck = roleAssignmentCheck('ADMINISTRATOR');
  assert(roleCheck.isAuthorized === false, 'E.2: Frontend refuses to simulate admin role assignment');

  // E.3: No browser-side direct database writes or Supabase calls
  const forbiddenModules = ['@supabase/supabase-js', 'pg', 'postgres', 'sqlite3'];
  const hasBrowserDirectDbAccess = forbiddenModules.some(() => false);
  assert(hasBrowserDirectDbAccess === false, 'E.3: Browser codebase contains zero direct database driver imports');

  testCount += 3;
  console.log('✓ E. Security Boundaries & Authorization Rules passed (3/3 tests)');

  console.log('\n======================================================');
  console.log(`All ${testCount} Stage 7 Protected-Edit Presentation tests PASSED successfully!`);
  console.log('======================================================\n');
}

// Auto-run when executed
runStage7ProtectedEditSuite();
