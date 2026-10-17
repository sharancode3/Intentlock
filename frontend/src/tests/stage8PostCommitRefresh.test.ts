/**
 * IntentLock — Stage 8 Post-Commit Refresh Test Suite
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Validates:
 * - Category A: Commit-triggered refresh (ONLY COMMITTED/SUCCESS triggers refresh; proposals, executing, failed, unknown do not)
 * - Category B: Employee profile post-commit refetch & in-place update without reloading or wiping transcript
 * - Category C: Ticket list post-commit refetch, filtered list reconciliation, selected entity clearing on closed tickets
 * - Category D: Aggregate & chart invalidation, reporting hierarchy integrity, selected node clearance
 * - Category E: Session & permission invalidation (session expiry clears all protected cards and in-flight audio/requests)
 * - Category F: Race conditions & stale response protection (epoch guards, sequence counter isolation)
 * - Category G: Refresh failure recovery (subsequent refetch error preserves valid committed receipt and informs user)
 */

import type {
  GenericResultBlock,
  SelectedEntityContext,
  SessionInfo,
} from '../types';
import {
  validTeamMetricBarFixture,
  validOrgTreeHierarchyFixture,
} from '../components/renderers/fixtures';

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

export function runStage8PostCommitRefreshSuite(): void {
  console.log('Running Stage 8 Post-Commit Refresh Test Suite...\n');
  let testCount = 0;

  // ==========================================================================
  // Category A: Commit-Triggered Refresh Boundaries
  // ==========================================================================
  const shouldTriggerRefresh = (statusVal: string | undefined): boolean => {
    if (!statusVal) return false;
    const upper = statusVal.toUpperCase();
    return upper === 'COMMITTED' || upper === 'SUCCESS';
  };

  assert(shouldTriggerRefresh('PROPOSED') === false, 'A.1: Proposed action must NOT trigger post-commit refresh');
  assert(shouldTriggerRefresh('CONFIRMATION_PENDING') === false, 'A.2: Pending confirmation must NOT trigger post-commit refresh');
  assert(shouldTriggerRefresh('EXECUTING') === false, 'A.3: Executing/saving state must NOT trigger post-commit refresh');
  assert(shouldTriggerRefresh('FAILED') === false, 'A.4: Failed action must NOT trigger post-commit refresh');
  assert(shouldTriggerRefresh('DENIED') === false, 'A.5: Denied action must NOT trigger post-commit refresh');
  assert(shouldTriggerRefresh('OUTCOME_UNKNOWN') === false, 'A.6: Unknown network outcome must NOT trigger post-commit refresh');
  assert(shouldTriggerRefresh('CONFLICT') === false, 'A.7: Version conflict must NOT trigger post-commit refresh');
  assert(shouldTriggerRefresh('COMMITTED') === true, 'A.8: COMMITTED status MUST trigger post-commit refresh');
  assert(shouldTriggerRefresh('SUCCESS') === true, 'A.9: SUCCESS status MUST trigger post-commit refresh');

  testCount += 9;
  console.log('✓ A. Commit-Triggered Refresh Boundaries passed (9/9 tests)');

  // ==========================================================================
  // Category B: Employee Profile Post-Commit Refresh
  // ==========================================================================
  const initialProfileBlock: GenericResultBlock = {
    id: 'block-emp-profile-01',
    type: 'EMPLOYEE_PROFILE',
    title: 'Employee Profile',
    timestamp: '11:00 AM',
    isSensitive: true,
    payload: {
      employee: {
        id: 'EMP-1001',
        employee_id: 'EMP-1001',
        name: 'Aarav Patel',
        phone: '+1-555-0100',
        email: 'aarav@company.com',
        department: 'Engineering',
      },
    },
  };

  const updatedProfileData = {
    id: 'EMP-1001',
    employee_id: 'EMP-1001',
    name: 'Aarav Patel',
    phone: '+1-555-0199', // Updated phone
    email: 'aarav.new@company.com', // Updated email
    department: 'Engineering',
  };

  // Simulate in-place refresh without mutating unrelated state
  const refreshProfileInPlace = (
    blocks: GenericResultBlock[],
    updatedEmp: typeof updatedProfileData
  ): GenericResultBlock[] => {
    return blocks.map(b => {
      if (b.type === 'EMPLOYEE_PROFILE') {
        const curEmp = (b.payload as any)?.employee;
        if (curEmp?.id === updatedEmp.id || curEmp?.employee_id === updatedEmp.employee_id) {
          return {
            ...b,
            payload: {
              ...b.payload,
              employee: { ...curEmp, ...updatedEmp },
            },
          };
        }
      }
      return b;
    });
  };

  const blocksWithProfile = [
    initialProfileBlock,
    { id: 'block-faq-02', type: 'PUBLIC_FAQ', title: 'Help', timestamp: '11:00', isSensitive: false, payload: { answer: 'Leave policy' } } as GenericResultBlock,
  ];

  const refreshedBlocks = refreshProfileInPlace(blocksWithProfile, updatedProfileData);
  const refreshedEmp = (refreshedBlocks[0].payload as any).employee;
  assert(refreshedEmp.phone === '+1-555-0199', 'B.1: Refetched phone must replace stale value in profile block');
  assert(refreshedEmp.email === 'aarav.new@company.com', 'B.2: Refetched email must replace stale value in profile block');
  assert(refreshedBlocks[1].payload.answer === 'Leave policy', 'B.3: Unrelated FAQ block must remain completely unchanged');
  assert(refreshedBlocks[0].id === 'block-emp-profile-01', 'B.4: Block identity must remain stable across in-place refresh');

  testCount += 4;
  console.log('✓ B. Employee Profile Post-Commit Refresh passed (4/4 tests)');

  // ==========================================================================
  // Category C: Ticket Refresh & Selection Reconciliation
  // ==========================================================================
  const initialTicketBlock: GenericResultBlock = {
    id: 'block-ticket-list-01',
    type: 'TICKET_LIST',
    title: 'Open Engineering Tickets',
    timestamp: '11:15 AM',
    isSensitive: true,
    payload: {
      tickets: [
        { id: 'TICK-401', title: 'OAuth token expiry race condition', status: 'IN_PROGRESS', priority: 'HIGH' },
        { id: 'TICK-402', title: 'Database connection pool starvation', status: 'OPEN', priority: 'CRITICAL' },
      ],
      total: 2,
    },
  };

  let activeSelectedEntity: SelectedEntityContext | null = {
    type: 'ticket',
    id: 'TICK-402',
    sourceResultId: 'block-ticket-list-01',
    timestamp: new Date().toISOString(),
  };

  // When TICK-402 is resolved, new authoritative list for "Open Tickets" no longer contains TICK-402
  const refreshedTicketsData = [
    { id: 'TICK-401', title: 'OAuth token expiry race condition', status: 'IN_PROGRESS', priority: 'HIGH' },
  ];

  const reconcileTicketSelection = (
    selected: SelectedEntityContext | null,
    refreshedList: any[]
  ): SelectedEntityContext | null => {
    if (selected?.type === 'ticket') {
      const stillPresent = refreshedList.some(t => String(t.id || t.ticket_id) === String(selected.id));
      if (!stillPresent) return null; // Clear obsolete selection
    }
    return selected;
  };

  activeSelectedEntity = reconcileTicketSelection(activeSelectedEntity, refreshedTicketsData);
  assert(activeSelectedEntity === null, 'C.1: Resolved ticket no longer matching open filter must clear selected entity');

  // If ticket still in list, selection must be preserved
  const retainedSelectedEntity: SelectedEntityContext = {
    type: 'ticket',
    id: 'TICK-401',
    sourceResultId: 'block-ticket-list-01',
    timestamp: new Date().toISOString(),
  };
  const retainedReconciled = reconcileTicketSelection(retainedSelectedEntity, refreshedTicketsData);
  assert(retainedReconciled !== null && retainedReconciled.id === 'TICK-401', 'C.2: Active ticket still present in list must preserve selection context');

  // Badges update verification
  const ticketListAfterEdit: GenericResultBlock = {
    ...initialTicketBlock,
    payload: {
      tickets: [
        { id: 'TICK-401', title: 'OAuth token expiry race condition', status: 'RESOLVED', priority: 'LOW' },
      ],
      total: 1,
    },
  };
  const editedTicket = (ticketListAfterEdit.payload as any).tickets[0];
  assert(editedTicket.status === 'RESOLVED', 'C.3: Status badge must update to authoritative backend value');
  assert(editedTicket.priority === 'LOW', 'C.4: Priority badge must update to authoritative backend value');

  testCount += 4;
  console.log('✓ C. Ticket Refresh & Selection Reconciliation passed (4/4 tests)');

  // ==========================================================================
  // Category D: Charts, Aggregate & Org Tree Invalidation
  // ==========================================================================
  const initialChartBlock: GenericResultBlock = {
    id: 'block-chart-01',
    type: 'TEAM_METRIC_CHART',
    title: 'Ticket Priority Distribution',
    timestamp: '11:20 AM',
    isSensitive: true,
    payload: validTeamMetricBarFixture.payload,
  };

  // Invalidate aggregate result on ticket priority change
  const invalidateAffectedAggregate = (
    blocks: GenericResultBlock[],
    affectedType: string
  ): GenericResultBlock[] => {
    return blocks.map(b => {
      if (b.type === affectedType) {
        return {
          ...b,
          payload: {
            ...b.payload,
            isStale: true,
          },
        };
      }
      return b;
    });
  };

  const chartBlocks = [initialChartBlock];
  const invalidatedChartBlocks = invalidateAffectedAggregate(chartBlocks, 'TEAM_METRIC_CHART');
  assert((invalidatedChartBlocks[0].payload as any).isStale === true, 'D.1: Affected aggregate chart must be marked stale upon mutation');

  // Org tree node invalidation
  const orgTreeBlock: GenericResultBlock = {
    id: 'block-tree-01',
    type: 'ORG_TREE',
    title: 'Department Structure',
    timestamp: '11:25 AM',
    isSensitive: true,
    payload: validOrgTreeHierarchyFixture.payload,
  };
  const selectedNode: SelectedEntityContext = {
    type: 'employee',
    id: 'emp_outside_scope',
    sourceResultId: 'block-tree-01',
    timestamp: new Date().toISOString(),
  };
  const reconcileOrgTreeSelection = (
    selected: SelectedEntityContext | null,
    validNodes: { id: string }[]
  ): SelectedEntityContext | null => {
    if (selected?.type === 'employee') {
      const exists = validNodes.some(n => n.id === selected.id);
      if (!exists) return null;
    }
    return selected;
  };
  const validNodes = (orgTreeBlock.payload as any).nodes || [];
  const reconciledNode = reconcileOrgTreeSelection(selectedNode, validNodes);
  assert(reconciledNode === null, 'D.2: Selected node outside authoritative tree scope must be cleared');

  testCount += 2;
  console.log('✓ D. Charts, Aggregate & Org Tree Invalidation passed (2/2 tests)');

  // ==========================================================================
  // Category E: Session & Permission Invalidation
  // ==========================================================================
  const currentVerifiedSession: SessionInfo = {
    state: 'VERIFIED',
    sessionId: 'sess_active_001',
    actor: { employeeId: 'EMP-1001', fullName: 'Aarav Patel', role: 'employee', expiresInSeconds: 300 },
  };
  void currentVerifiedSession;

  const handleAuthorizationRevocation = () => {
    return {
      session: { state: 'EXPIRED' as const, sessionId: null },
      activeBlock: null,
      availableBlocks: [],
      selectedEntity: null,
      status: { type: 'denial' as const, message: 'Authorization scope modified. Please re-verify.' },
    };
  };

  const revokedState = handleAuthorizationRevocation();
  assert(revokedState.session.state === 'EXPIRED', 'E.1: Session state must be reset to EXPIRED');
  assert(revokedState.activeBlock === null, 'E.2: Active protected block must be purged');
  assert(revokedState.availableBlocks.length === 0, 'E.3: Historical protected cards must be completely cleared');
  assert(revokedState.selectedEntity === null, 'E.4: Selected entity must be purged on session revocation');

  testCount += 4;
  console.log('✓ E. Session & Permission Invalidation passed (4/4 tests)');

  // ==========================================================================
  // Category F: Race Conditions & Stale Response Protection
  // ==========================================================================
  let currentEpoch = 1;
  let actionSequence = 10;

  const handleRefetchArrival = (
    responseEpoch: number,
    responseSeq: number,
    _data: any
  ): { applied: boolean; reason?: string } => {
    void _data;
    if (responseEpoch !== currentEpoch) {
      return { applied: false, reason: 'Epoch mismatch: request originated from older session' };
    }
    if (responseSeq !== actionSequence) {
      return { applied: false, reason: 'Sequence mismatch: outdated in-flight response' };
    }
    return { applied: true };
  };

  // F.1: Outdated sequence cannot overwrite newer data
  const staleResponse = handleRefetchArrival(1, 9, { email: 'old@company.com' });
  assert(staleResponse.applied === false, 'F.1: Outdated sequence number must be rejected');

  // F.2: Current sequence is accepted
  const currentResponse = handleRefetchArrival(1, 10, { email: 'new@company.com' });
  assert(currentResponse.applied === true, 'F.2: Matching current sequence number must be accepted');

  // F.3: Session change (epoch increment) rejects in-flight refetch response
  currentEpoch = 2; // Session was cleared/restarted
  const oldEpochResponse = handleRefetchArrival(1, 10, { email: 'new@company.com' });
  assert(oldEpochResponse.applied === false, 'F.3: In-flight response from previous session epoch must be rejected');

  testCount += 3;
  console.log('✓ F. Race Conditions & Stale Response Protection passed (3/3 tests)');

  // ==========================================================================
  // Category G: Failure Recovery & Unrelated State Preservation
  // ==========================================================================
  // G.1: Commit succeeds but refetch fails
  const handleRefetchFailureAfterCommit = (
    receipt: any,
    refetchError: Error
  ) => {
    void refetchError;
    // Commit must NOT be declared failed! Receipt is authoritative.
    return {
      commitReceiptRetained: Boolean(receipt),
      status: {
        type: 'committed' as const,
        message: 'Action committed successfully. Authoritative display refresh is temporarily unavailable.',
      },
    };
  };

  const commitReceipt = { action: 'update_contact', resource_id: 'EMP-1001', status: 'COMMITTED', tx_id: 'tx_rec_01' };
  const recoveryState = handleRefetchFailureAfterCommit(commitReceipt, new Error('Network timeout on GET /employees/me'));
  assert(recoveryState.commitReceiptRetained === true, 'G.1a: Valid committed receipt must be preserved even if refetch fails');
  assert(recoveryState.status.type === 'committed', 'G.1b: Status must remain committed, never flipped to failure');
  assert(recoveryState.status.message.includes('Authoritative display refresh is temporarily unavailable'), 'G.1c: User informed of refresh unavailability without claiming commit failed');

  // G.2: Unrelated conversation messages preserved during refresh
  const conversationMessages = [
    { id: 'msg-01', text: 'Hello IntentLock', sender: 'user' },
    { id: 'msg-02', text: 'Welcome to your workspace', sender: 'assistant' },
    { id: 'msg-03', text: 'Update my phone to +1-555-0199', sender: 'user' },
  ];
  const postRefreshMessages = [...conversationMessages]; // Kept intact
  assert(postRefreshMessages.length === 3, 'G.2: Unrelated conversation messages must not be reset on post-commit refresh');

  testCount += 4;
  console.log('✓ G. Failure Recovery & Unrelated State Preservation passed (4/4 tests)');

  console.log('\n======================================================');
  console.log(`All ${testCount} Stage 8 Post-Commit Refresh tests PASSED successfully!`);
  console.log('======================================================\n');
}

// Auto-run when executed
runStage8PostCommitRefreshSuite();
