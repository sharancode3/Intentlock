/**
 * IntentLock — Stage 5 Dynamic Renderer Integration Test Suite
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Validates dynamic renderer registry routing, payload contract enforcement,
 * multi-result extraction and switching, chart and tree data integrity,
 * and sensitive result filtering across all 10 registered renderer types.
 */

import '../components/renderers';
import { getResultRenderer, hasResultRenderer } from '../components/workspace/resultRegistry';
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
import { resolveSafeResultBlocks } from '../utils/statusPresentation';
import type { GenericResultBlock, ResultBlockType } from '../types';
import {
  validPublicFaqCompleteFixture,
  validDenialBannerCompleteFixture,
  validEmployeeProfileCompleteFixture,
  validTicketListMultipleFixture,
  validTeamMetricBarFixture,
  validTeamMetricPieFixture,
  validTrustTraceSuccessFixture,
  validReadbackConfirmationPendingFixture,
  validActionReceiptSuccessFixture,
  validDataTableFixture,
  validOrgTreeHierarchyFixture,
  invalidOrgTreeCycleFixture,
  emptyTeamMetricChartFixture,
  allZeroTeamMetricChartFixture,
  invalidTeamMetricChartTypeFixture,
  invalidTrustTraceDanglingEdgeFixture,
  contract4SuccessMultiResultFixture,
} from '../components/renderers/fixtures';

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

export function runStage5DynamicRenderersSuite(): void {
  console.log('Running Stage 5 Dynamic Renderer Integration Test Suite...\n');
  let testCount = 0;

  // ==========================================================================
  // 1. All 10 Registered Renderer Types
  // ==========================================================================
  const allTenTypes: ResultBlockType[] = [
    'PUBLIC_FAQ',
    'DENIAL_BANNER',
    'EMPLOYEE_PROFILE',
    'TICKET_LIST',
    'TEAM_METRIC_CHART',
    'TRUST_TRACE_GRAPH',
    'READBACK_CONFIRMATION',
    'ACTION_RECEIPT',
    'DATA_TABLE',
    'ORG_TREE',
  ];

  for (const type of allTenTypes) {
    assert(hasResultRenderer(type), `Registry must contain registered renderer for ${type}`);
    const renderer = getResultRenderer(type);
    assert(typeof renderer === 'function', `Renderer component for ${type} must be a valid React functional component`);
    testCount += 2;
  }

  // Graceful unknown type handling
  assert(!hasResultRenderer('UNKNOWN_NONEXISTENT_TYPE'), 'Unknown result type must return false for hasResultRenderer');
  assert(!getResultRenderer('UNKNOWN_NONEXISTENT_TYPE'), 'Unknown result type must return undefined safely');
  testCount += 2;
  console.log('✓ 1. Renderer Registry Coverage passed (22/22 tests)');

  // ==========================================================================
  // 2. Strict Payload Contract Validation & Safe Failure
  // ==========================================================================
  // A. Public FAQ
  assert(validatePublicFaqPayload(validPublicFaqCompleteFixture.payload).isValid, 'Valid FAQ must pass validation');
  assert(!validatePublicFaqPayload({}).isValid, 'Empty FAQ must fail validation');
  assert(!validatePublicFaqPayload({ question: 'Hi' }).isValid, 'FAQ missing answer must fail validation');

  // B. Denial Banner
  assert(validateDenialBannerPayload(validDenialBannerCompleteFixture.payload).isValid, 'Valid Denial Banner must pass validation');
  assert(!validateDenialBannerPayload({}).isValid, 'Empty Denial Banner must fail validation');

  // C. Employee Profile
  assert(validateEmployeeProfilePayload(validEmployeeProfileCompleteFixture.payload).isValid, 'Valid Employee Profile must pass validation');
  assert(!validateEmployeeProfilePayload({ id: 'EMP-1' }).isValid, 'Profile missing name must fail validation');
  assert(!validateEmployeeProfilePayload({ id: 'EMP-1', name: 'Test', projects: 'invalid-string-not-array' }).isValid, 'Profile with malformed projects must fail');

  // D. Ticket List
  assert(validateTicketListPayload(validTicketListMultipleFixture.payload).isValid, 'Valid Ticket List must pass validation');
  assert(!validateTicketListPayload({ tickets: [{ title: 'Missing ID' }] }).isValid, 'Ticket missing ticket_id must fail');
  assert(!validateTicketListPayload({ tickets: 'not-an-array' }).isValid, 'Ticket list must reject non-array tickets');

  // E. Team Metric Chart
  assert(validateTeamMetricChartPayload(validTeamMetricBarFixture.payload).isValid, 'Valid Bar Chart must pass validation');
  assert(validateTeamMetricChartPayload(validTeamMetricPieFixture.payload).isValid, 'Valid Pie Chart must pass validation');
  assert(!validateTeamMetricChartPayload(invalidTeamMetricChartTypeFixture.payload).isValid, 'Chart with unsupported type must fail');

  // F. Trust Trace Graph
  assert(validateTrustTraceGraphPayload(validTrustTraceSuccessFixture.payload).isValid, 'Valid Trust Trace must pass validation');
  assert(!validateTrustTraceGraphPayload({}).isValid, 'Empty object Trust Trace payload must fail validation');
  assert(!validateTrustTraceGraphPayload(invalidTrustTraceDanglingEdgeFixture.payload).isValid, 'Dangling edge Trust Trace must fail validation');

  // G. Readback Confirmation
  assert(validateReadbackConfirmationPayload(validReadbackConfirmationPendingFixture.payload).isValid, 'Valid Readback must pass');
  assert(!validateReadbackConfirmationPayload({ action: 'update' }).isValid, 'Readback missing proposal parameters must fail');

  // H. Action Receipt
  assert(validateActionReceiptPayload(validActionReceiptSuccessFixture.payload).isValid, 'Valid Receipt must pass');
  assert(!validateActionReceiptPayload({ status: 'committed' }).isValid, 'Receipt missing transaction_id must fail');

  // I. Data Table
  assert(validateDataTablePayload(validDataTableFixture.payload).isValid, 'Valid Data Table must pass');
  assert(!validateDataTablePayload({ columns: [] }).isValid, 'Data table without rows must fail');

  // J. Org Tree
  assert(validateOrgTreePayload(validOrgTreeHierarchyFixture.payload).isValid, 'Valid Org Tree must pass');
  assert(!validateOrgTreePayload(invalidOrgTreeCycleFixture.payload).isValid, 'Cyclic Org Tree must fail validation');

  testCount += 19;
  console.log('✓ 2. Strict Payload Validation passed (19/19 tests)');

  // ==========================================================================
  // 3. Multi-Result Extraction, Primary Selection & Preservation
  // ==========================================================================
  const treeBlock: GenericResultBlock = {
    id: 'block-tree-100',
    type: 'ORG_TREE',
    title: 'Engineering Org Hierarchy',
    timestamp: '12:00 PM',
    payload: validOrgTreeHierarchyFixture.payload,
    isSensitive: true,
  };
  const chartBlock: GenericResultBlock = {
    id: 'block-chart-200',
    type: 'TEAM_METRIC_CHART',
    title: 'Ticket Priority Distribution',
    timestamp: '12:00 PM',
    payload: validTeamMetricBarFixture.payload,
    isSensitive: true,
  };
  const tableBlock: GenericResultBlock = {
    id: 'block-table-300',
    type: 'DATA_TABLE',
    title: 'Department Open Tickets',
    timestamp: '12:00 PM',
    payload: validDataTableFixture.payload,
    isSensitive: true,
  };

  // Case A: 3 valid blocks, primary explicitly designated as ORG_TREE
  const multiResultA = resolveSafeResultBlocks([treeBlock, chartBlock, tableBlock], 'block-tree-100', true);
  assert(multiResultA.safePrimary?.id === 'block-tree-100', 'Designated primary block must be selected as primary');
  assert(multiResultA.safeBlocks.length === 3, 'All 3 valid result blocks must be preserved in collection');
  assert(multiResultA.safeBlocks.some(b => b.id === 'block-chart-200'), 'Additional chart block must be preserved');
  assert(multiResultA.safeBlocks.some(b => b.id === 'block-table-300'), 'Additional table block must be preserved');

  // Case B: 3 valid blocks, primary explicitly designated as TEAM_METRIC_CHART
  const multiResultB = resolveSafeResultBlocks([treeBlock, chartBlock, tableBlock], 'block-chart-200', true);
  assert(multiResultB.safePrimary?.id === 'block-chart-200', 'Primary selection must update when designated id changes');
  assert(multiResultB.safeBlocks.length === 3, 'Collection must retain all blocks regardless of primary selection');

  // Case C: Malformed block fails validator safely while valid blocks pass
  const malformedBlock: GenericResultBlock = {
    id: 'block-malformed-999',
    type: 'ORG_TREE',
    title: 'Corrupted Hierarchy',
    timestamp: '12:00 PM',
    payload: invalidOrgTreeCycleFixture.payload,
    isSensitive: true,
  };
  const malformedCheck = validateOrgTreePayload(malformedBlock.payload);
  assert(!malformedCheck.isValid, 'Malformed block payload must be rejected by its validator');
  const validTreeCheck = validateOrgTreePayload(treeBlock.payload);
  assert(validTreeCheck.isValid, 'Valid tree block payload must pass validator');
  const validChartCheck = validateTeamMetricChartPayload(chartBlock.payload);
  assert(validChartCheck.isValid, 'Valid chart block payload must pass validator');

  // Case D: Fixture multi-result envelope conformance
  const fixtureMulti = resolveSafeResultBlocks(
    contract4SuccessMultiResultFixture.result_blocks || [],
    contract4SuccessMultiResultFixture.primary_result_id,
    true
  );
  assert(fixtureMulti.safeBlocks.length >= 2, 'contract4SuccessMultiResultFixture must extract multiple safe blocks');

  testCount += 8;
  console.log('✓ 3. Multi-Result Extraction & Preservation passed (8/8 tests)');

  // ==========================================================================
  // 4. Chart Data Integrity & Consistency
  // ==========================================================================
  // Bar Chart
  const barPayload = validTeamMetricBarFixture.payload as any;
  assert(Array.isArray(barPayload.data) && barPayload.data.length > 0, 'Bar chart must have valid data points');
  assert(barPayload.data.every((d: any) => typeof d.name === 'string' && typeof d.value === 'number'), 'Bar chart data items must have name string and value number');
  assert(barPayload.kpis && barPayload.kpis.total_tickets === 128, 'Bar chart KPIs must accurately match reported backend totals');

  // Pie Chart
  const piePayload = validTeamMetricPieFixture.payload as any;
  assert(Array.isArray(piePayload.data) && piePayload.data.length > 0, 'Pie chart data must be a non-empty array');
  const sumSlices = piePayload.data.reduce((acc: number, s: any) => acc + (s.value || 0), 0);
  assert(sumSlices > 0, 'Pie chart slices sum must be strictly positive');
  assert(piePayload.data.every((s: any) => typeof s.name === 'string' && s.name.length > 0), 'Every pie slice must retain its category label');

  // Empty / All-Zero Chart
  assert(validateTeamMetricChartPayload(emptyTeamMetricChartFixture.payload).isValid, 'Empty chart payload structure must validate');
  assert(validateTeamMetricChartPayload(allZeroTeamMetricChartFixture.payload).isValid, 'All-zero chart payload must validate cleanly without fabricating metrics');

  testCount += 6;
  console.log('✓ 4. Chart Data Integrity passed (6/6 tests)');

  // ==========================================================================
  // 5. Org Tree Hierarchy & Structure Integrity
  // ==========================================================================
  const treePayload = validOrgTreeHierarchyFixture.payload as any;
  assert(treePayload.root_id && typeof treePayload.root_id === 'string', 'Tree must define root_id');
  assert(Array.isArray(treePayload.nodes) && treePayload.nodes.length >= 3, 'Tree must contain hierarchy nodes');
  assert(Array.isArray(treePayload.edges) && treePayload.edges.length >= 2, 'Tree must contain directional reporting edges');

  // Verify all edges link valid nodes
  const nodeIds = new Set(treePayload.nodes.map((n: any) => n.id));
  assert(treePayload.edges.every((e: any) => nodeIds.has(e.source || e.from) && nodeIds.has(e.target || e.to)), 'All reporting edges must link existing node IDs');

  testCount += 4;
  console.log('✓ 5. Org Tree Hierarchy Integrity passed (4/4 tests)');

  // ==========================================================================
  // 6. Sensitive Result Filtering & Session Invalidation
  // ==========================================================================
  const sensitiveProfile: GenericResultBlock = {
    id: 'block-prof-1',
    type: 'EMPLOYEE_PROFILE',
    title: 'Restricted Profile',
    timestamp: '12:00 PM',
    payload: validEmployeeProfileCompleteFixture.payload,
    isSensitive: true,
  };
  const publicFaq: GenericResultBlock = {
    id: 'block-faq-1',
    type: 'PUBLIC_FAQ',
    title: 'Public Knowledge',
    timestamp: '12:00 PM',
    payload: validPublicFaqCompleteFixture.payload,
    isSensitive: false,
  };

  // Case A: Anonymous session must filter sensitive results
  const anonBlocks = resolveSafeResultBlocks([sensitiveProfile, publicFaq], 'block-prof-1', false);
  assert(anonBlocks.safeBlocks.length === 1, 'Anonymous session must filter out sensitive profile block');
  assert(anonBlocks.safeBlocks[0].id === 'block-faq-1', 'Public FAQ must remain accessible in anonymous session');
  assert(anonBlocks.safePrimary === null, 'Safe primary must be null when requested primary is sensitive and session is unverified');

  // Case B: Verified session includes sensitive blocks
  const verifiedBlocks = resolveSafeResultBlocks([sensitiveProfile, publicFaq], 'block-prof-1', true);
  assert(verifiedBlocks.safeBlocks.length === 2, 'Verified session must preserve authorized sensitive block');
  assert(verifiedBlocks.safePrimary?.id === 'block-prof-1', 'Verified primary profile must be preserved');

  // Case C: Expiry / Invalidation clears sensitive blocks
  const expiredBlocks = resolveSafeResultBlocks([sensitiveProfile], 'block-prof-1', false);
  assert(expiredBlocks.safeBlocks.length === 0, 'Expired unverified state must not expose sensitive profile');
  assert(expiredBlocks.safePrimary === null, 'Primary must be null when all blocks are filtered out');

  testCount += 6;
  console.log('✓ 6. Sensitive Result Filtering passed (6/6 tests)');

  // ==========================================================================
  // 7. Trust Trace, Readback Proposal & Action Receipt Delineation
  // ==========================================================================
  // Trust Trace
  const tracePayload = validTrustTraceSuccessFixture.payload as any;
  assert(tracePayload.final_verdict === 'ALLOW', 'Success trace verdict must be ALLOW');
  assert(Array.isArray(tracePayload.nodes) && tracePayload.nodes.length > 0, 'Trust trace must report discrete security nodes');

  // Readback vs. Receipt
  const readbackPayload = validReadbackConfirmationPendingFixture.payload as any;
  assert(readbackPayload.status === 'PENDING', 'Readback must be explicitly pending proposal, not committed');
  assert(readbackPayload.requires_voice_confirmation === true, 'Readback must require voice readback confirmation');

  const receiptPayload = validActionReceiptSuccessFixture.payload as any;
  assert(receiptPayload.receipt?.status === 'COMMITTED', 'Action receipt must confirm committed transaction');
  assert(typeof receiptPayload.receipt?.tx_id === 'string' && receiptPayload.receipt.tx_id.length > 0, 'Receipt must supply stable transaction ID');

  testCount += 5;
  console.log('✓ 7. Trust Trace, Proposal & Receipt Delineation passed (5/5 tests)');

  console.log('\n======================================================');
  console.log(`All ${testCount} Stage 5 Dynamic Renderer Integration tests PASSED successfully!`);
  console.log('======================================================');
}

// Auto-run when executed
runStage5DynamicRenderersSuite();
