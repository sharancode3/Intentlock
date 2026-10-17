/**
 * IntentLock — Stage 1 Contracts and Fixtures Validation Test Suite
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Verifies that all 10 result block renderers, payload validators, and the
 * 5 shared coordination contracts validate and render correctly using fixtures.
 */

import {
  validatePublicFaqPayload,
  validateDenialBannerPayload,
  validateEmployeeProfilePayload,
  validateTicketListPayload,
  validateTeamMetricChartPayload,
  validateTrustTraceGraphPayload,
  validateReadbackConfirmationPayload,
  validateActionReceiptPayload,
  validateDataTablePayload,
  validateOrgTreePayload,
} from '../components/renderers/validation';

import {
  validPublicFaqCompleteFixture,
  validPublicFaqMinimalFixture,
  invalidPublicFaqMissingAnswerFixture,
  invalidPublicFaqWrongTypesFixture,
  validDenialBannerCompleteFixture,
  validDenialBannerMinimalFixture,
  invalidDenialBannerMissingMessageFixture,
  validEmployeeProfileCompleteFixture,
  validEmployeeProfileMinimalFixture,
  invalidEmployeeProfileMissingNameFixture,
  invalidEmployeeProfileInvalidProjectsFixture,
  validTicketListMultipleFixture,
  validTicketListEmptyFixture,
  invalidTicketListMissingIdFixture,
  invalidTicketListNotArrayFixture,
  validTeamMetricBarFixture,
  validTeamMetricPieFixture,
  emptyTeamMetricChartFixture,
  allZeroTeamMetricChartFixture,
  invalidTeamMetricChartTypeFixture,
  invalidTeamMetricChartMissingFieldsFixture,
  validTrustTraceSuccessFixture,
  validTrustTraceDeniedFixture,
  validTrustTraceSpeakerMismatchFixture,
  emptyTrustTraceFixture,
  invalidTrustTraceDanglingEdgeFixture,
  invalidTrustTraceDuplicateNodeFixture,
  validReadbackConfirmationPendingFixture,
  validReadbackConfirmationMinimalFixture,
  invalidReadbackConfirmationMissingActionFixture,
  invalidReadbackConfirmationMalformedParamsFixture,
  validActionReceiptSuccessFixture,
  validActionReceiptFailedFixture,
  validActionReceiptDeniedFixture,
  invalidActionReceiptMissingTxIdFixture,
  validDataTableFixture,
  validDataTableEmptyFixture,
  invalidDataTableDuplicateRowsFixture,
  validOrgTreeHierarchyFixture,
  invalidOrgTreeCycleFixture,
  contract1SuccessSessionFixture,
  contract1ClarificationSessionFixture,
  contract1DeniedSessionFixture,
  contract2SuccessProposalFixture,
  contract2ClarificationProposalFixture,
  contract2DeniedProposalFixture,
  contract2CommittedReceiptFixture,
  contract3SuccessSelectionFixture,
  contract3ClarificationSelectionFixture,
  contract3DeniedSelectionFixture,
  contract4SuccessMultiResultFixture,
  contract4ClarificationResultFixture,
  contract4DeniedResultFixture,
  contract5SuccessTurnReplyFixture,
  contract5ClarificationTurnReplyFixture,
  contract5DeniedTurnReplyFixture,
} from '../components/renderers/fixtures';

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

export function runContractValidationSuite(): void {
  console.log('Running Stage 1 Contract and Fixture Validation Suite...\n');
  let testCount = 0;

  // 1. PUBLIC_FAQ
  assert(validatePublicFaqPayload(validPublicFaqCompleteFixture.payload).isValid, 'validPublicFaqCompleteFixture should be valid');
  assert(validatePublicFaqPayload(validPublicFaqMinimalFixture.payload).isValid, 'validPublicFaqMinimalFixture should be valid');
  assert(!validatePublicFaqPayload(invalidPublicFaqMissingAnswerFixture.payload).isValid, 'invalidPublicFaqMissingAnswerFixture should be invalid');
  assert(!validatePublicFaqPayload(invalidPublicFaqWrongTypesFixture.payload).isValid, 'invalidPublicFaqWrongTypesFixture should be invalid');
  testCount += 4;
  console.log('✓ PUBLIC_FAQ validation passed (4/4 tests)');

  // 2. DENIAL_BANNER
  assert(validateDenialBannerPayload(validDenialBannerCompleteFixture.payload).isValid, 'validDenialBannerCompleteFixture should be valid');
  assert(validateDenialBannerPayload(validDenialBannerMinimalFixture.payload).isValid, 'validDenialBannerMinimalFixture should be valid');
  assert(!validateDenialBannerPayload(invalidDenialBannerMissingMessageFixture.payload).isValid, 'invalidDenialBannerMissingMessageFixture should be invalid');
  testCount += 3;
  console.log('✓ DENIAL_BANNER validation passed (3/3 tests)');

  // 3. EMPLOYEE_PROFILE
  assert(validateEmployeeProfilePayload(validEmployeeProfileCompleteFixture.payload).isValid, 'validEmployeeProfileCompleteFixture should be valid');
  assert(validateEmployeeProfilePayload(validEmployeeProfileMinimalFixture.payload).isValid, 'validEmployeeProfileMinimalFixture should be valid');
  assert(!validateEmployeeProfilePayload(invalidEmployeeProfileMissingNameFixture.payload).isValid, 'invalidEmployeeProfileMissingNameFixture should be invalid');
  assert(!validateEmployeeProfilePayload(invalidEmployeeProfileInvalidProjectsFixture.payload).isValid, 'invalidEmployeeProfileInvalidProjectsFixture should be invalid');
  testCount += 4;
  console.log('✓ EMPLOYEE_PROFILE validation passed (4/4 tests)');

  // 4. TICKET_LIST
  assert(validateTicketListPayload(validTicketListMultipleFixture.payload).isValid, 'validTicketListMultipleFixture should be valid');
  assert(validateTicketListPayload(validTicketListEmptyFixture.payload).isValid, 'validTicketListEmptyFixture should be valid');
  assert(!validateTicketListPayload(invalidTicketListMissingIdFixture.payload).isValid, 'invalidTicketListMissingIdFixture should be invalid');
  assert(!validateTicketListPayload(invalidTicketListNotArrayFixture.payload).isValid, 'invalidTicketListNotArrayFixture should be invalid');
  testCount += 4;
  console.log('✓ TICKET_LIST validation passed (4/4 tests)');

  // 5. TEAM_METRIC_CHART
  assert(validateTeamMetricChartPayload(validTeamMetricBarFixture.payload).isValid, 'validTeamMetricBarFixture should be valid');
  assert(validateTeamMetricChartPayload(validTeamMetricPieFixture.payload).isValid, 'validTeamMetricPieFixture should be valid');
  assert(validateTeamMetricChartPayload(emptyTeamMetricChartFixture.payload).isValid, 'emptyTeamMetricChartFixture should be valid');
  assert(validateTeamMetricChartPayload(allZeroTeamMetricChartFixture.payload).isValid, 'allZeroTeamMetricChartFixture should be valid');
  assert(!validateTeamMetricChartPayload(invalidTeamMetricChartTypeFixture.payload).isValid, 'invalidTeamMetricChartTypeFixture should be invalid');
  assert(!validateTeamMetricChartPayload(invalidTeamMetricChartMissingFieldsFixture.payload).isValid, 'invalidTeamMetricChartMissingFieldsFixture should be invalid');
  testCount += 6;
  console.log('✓ TEAM_METRIC_CHART validation passed (6/6 tests)');

  // 6. TRUST_TRACE_GRAPH
  assert(validateTrustTraceGraphPayload(validTrustTraceSuccessFixture.payload).isValid, 'validTrustTraceSuccessFixture should be valid');
  assert(validateTrustTraceGraphPayload(validTrustTraceDeniedFixture.payload).isValid, 'validTrustTraceDeniedFixture should be valid');
  assert(validateTrustTraceGraphPayload(validTrustTraceSpeakerMismatchFixture.payload).isValid, 'validTrustTraceSpeakerMismatchFixture should be valid');
  assert(validateTrustTraceGraphPayload(emptyTrustTraceFixture.payload).isValid, 'emptyTrustTraceFixture should be valid');
  assert(!validateTrustTraceGraphPayload(invalidTrustTraceDanglingEdgeFixture.payload).isValid, 'invalidTrustTraceDanglingEdgeFixture should be invalid');
  assert(!validateTrustTraceGraphPayload(invalidTrustTraceDuplicateNodeFixture.payload).isValid, 'invalidTrustTraceDuplicateNodeFixture should be invalid');
  testCount += 6;
  console.log('✓ TRUST_TRACE_GRAPH validation passed (6/6 tests)');

  // 7. READBACK_CONFIRMATION
  assert(validateReadbackConfirmationPayload(validReadbackConfirmationPendingFixture.payload).isValid, 'validReadbackConfirmationPendingFixture should be valid');
  assert(validateReadbackConfirmationPayload(validReadbackConfirmationMinimalFixture.payload).isValid, 'validReadbackConfirmationMinimalFixture should be valid');
  assert(!validateReadbackConfirmationPayload(invalidReadbackConfirmationMissingActionFixture.payload).isValid, 'invalidReadbackConfirmationMissingActionFixture should be invalid');
  assert(!validateReadbackConfirmationPayload(invalidReadbackConfirmationMalformedParamsFixture.payload).isValid, 'invalidReadbackConfirmationMalformedParamsFixture should be invalid');
  testCount += 4;
  console.log('✓ READBACK_CONFIRMATION validation passed (4/4 tests)');

  // 8. ACTION_RECEIPT
  assert(validateActionReceiptPayload(validActionReceiptSuccessFixture.payload).isValid, 'validActionReceiptSuccessFixture should be valid');
  assert(validateActionReceiptPayload(validActionReceiptFailedFixture.payload).isValid, 'validActionReceiptFailedFixture should be valid');
  assert(validateActionReceiptPayload(validActionReceiptDeniedFixture.payload).isValid, 'validActionReceiptDeniedFixture should be valid');
  assert(!validateActionReceiptPayload(invalidActionReceiptMissingTxIdFixture.payload).isValid, 'invalidActionReceiptMissingTxIdFixture should be invalid');
  testCount += 4;
  console.log('✓ ACTION_RECEIPT validation passed (4/4 tests)');

  // 9. DATA_TABLE
  assert(validateDataTablePayload(validDataTableFixture.payload).isValid, 'validDataTableFixture should be valid');
  assert(validateDataTablePayload(validDataTableEmptyFixture.payload).isValid, 'validDataTableEmptyFixture should be valid');
  assert(!validateDataTablePayload(invalidDataTableDuplicateRowsFixture.payload).isValid, 'invalidDataTableDuplicateRowsFixture should be invalid');
  testCount += 3;
  console.log('✓ DATA_TABLE validation passed (3/3 tests)');

  // 10. ORG_TREE
  assert(validateOrgTreePayload(validOrgTreeHierarchyFixture.payload).isValid, 'validOrgTreeHierarchyFixture should be valid');
  assert(!validateOrgTreePayload(invalidOrgTreeCycleFixture.payload).isValid, 'invalidOrgTreeCycleFixture should be invalid');
  testCount += 2;
  console.log('✓ ORG_TREE validation passed (2/2 tests)');

  // 11. CONTRACT 1: Verified Actor, Session & Evidence
  assert(contract1SuccessSessionFixture.state === 'VERIFIED', 'Contract 1 success state must be VERIFIED');
  assert(contract1SuccessSessionFixture.actor.employeeId === 'EMP-1001', 'Contract 1 actor ID must be EMP-1001');
  assert(contract1SuccessSessionFixture.evidence.speaker_decision === 'PASS', 'Contract 1 speaker must PASS');
  assert(contract1ClarificationSessionFixture.state === 'ANONYMOUS', 'Contract 1 clarification state must be ANONYMOUS');
  assert(contract1DeniedSessionFixture.error.code === 'SPEAKER_MISMATCH', 'Contract 1 denial must have error code');
  testCount += 5;
  console.log('✓ CONTRACT 1: Verified Actor & Evidence contracts passed (5/5 tests)');

  // 12. CONTRACT 2: Protected Action Proposal, Confirmation & Receipt
  assert(validateReadbackConfirmationPayload(contract2SuccessProposalFixture.payload).isValid, 'Contract 2 proposal should validate as valid READBACK_CONFIRMATION');
  assert(contract2ClarificationProposalFixture.status === 'clarification', 'Contract 2 clarification status');
  assert(validateDenialBannerPayload(contract2DeniedProposalFixture.payload).isValid, 'Contract 2 denial should validate as valid DENIAL_BANNER');
  assert(validateActionReceiptPayload(contract2CommittedReceiptFixture.payload).isValid, 'Contract 2 receipt should validate as valid ACTION_RECEIPT');
  testCount += 4;
  console.log('✓ CONTRACT 2: Action Proposal, Confirmation & Receipt contracts passed (4/4 tests)');

  // 13. CONTRACT 3: Intent Plan & Conversation Selection
  assert(contract3SuccessSelectionFixture.action === 'select_ticket', 'Contract 3 action name');
  assert(contract3SuccessSelectionFixture.target_id === '412', 'Contract 3 target ID');
  assert(contract3ClarificationSelectionFixture.status === 'clarification', 'Contract 3 clarification');
  assert(contract3DeniedSelectionFixture.status === 'denial', 'Contract 3 denial');
  testCount += 4;
  console.log('✓ CONTRACT 3: Intent Plan & Selection contracts passed (4/4 tests)');

  // 14. CONTRACT 4: Result Payloads & Multi-Result Handling
  assert(contract4SuccessMultiResultFixture.result_blocks.length === 2, 'Contract 4 multi-result contains 2 blocks');
  assert(contract4SuccessMultiResultFixture.primary_result_id === 'fixture-tickets-multiple', 'Contract 4 primary ID');
  assert(validatePublicFaqPayload(contract4ClarificationResultFixture.payload).isValid, 'Contract 4 clarification result validates as FAQ');
  assert(validateDenialBannerPayload(contract4DeniedResultFixture.payload).isValid, 'Contract 4 denial validates as DENIAL_BANNER');
  testCount += 4;
  console.log('✓ CONTRACT 4: Result Payloads & Multi-Result contracts passed (4/4 tests)');

  // 15. CONTRACT 5: Audio-Turn Submission Envelope
  assert(contract5SuccessTurnReplyFixture.status === 'success', 'Contract 5 turn reply status is success');
  assert(Boolean(contract5SuccessTurnReplyFixture.speech_audio.base64_audio), 'Contract 5 turn reply contains speech audio');
  assert(contract5ClarificationTurnReplyFixture.status === 'clarification', 'Contract 5 turn reply clarification');
  assert(contract5DeniedTurnReplyFixture.status === 'denial', 'Contract 5 turn reply denial');
  testCount += 4;
  console.log('✓ CONTRACT 5: Audio-Turn Submission contracts passed (4/4 tests)');

  console.log(`\n======================================================`);
  console.log(`All ${testCount} Stage 1 Contract Validation tests PASSED successfully!`);
  console.log(`======================================================`);
}

// Auto-run if executed directly via tsx
runContractValidationSuite();
