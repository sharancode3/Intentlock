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
// 3. EMPLOYEE_PROFILE Fixtures (Controlled Stage 3 Test Fixtures)
// ============================================================================

/** Valid comprehensive EMPLOYEE_PROFILE with department, team, email, and projects */
export const validEmployeeProfileCompleteFixture: GenericResultBlock = {
  id: 'fixture-emp-complete',
  type: 'EMPLOYEE_PROFILE',
  title: 'Employee Directory: Charlie Davis',
  timestamp: '10:30 AM',
  isSensitive: true,
  payload: {
    employee: {
      id: 'emp_1042',
      name: 'Charlie Davis',
      role: 'employee',
      department: 'Engineering',
      team: 'team_eng_a',
      email: 'charlie.davis@example.com',
      active_projects: ['Project Titan', 'Internal Tooling Gateway'],
      status: 'Active',
    },
  },
};

/** Valid minimal EMPLOYEE_PROFILE (required identity fields only) */
export const validEmployeeProfileMinimalFixture: GenericResultBlock = {
  id: 'fixture-emp-minimal',
  type: 'EMPLOYEE_PROFILE',
  title: 'Employee Directory: Alex Morgan',
  timestamp: '10:35 AM',
  isSensitive: true,
  payload: {
    employee: {
      id: 'emp_2099',
      name: 'Alex Morgan',
      role: 'helpdesk',
    },
  },
};

/** Valid EMPLOYEE_PROFILE with empty active project list */
export const validEmployeeProfileEmptyProjectsFixture: GenericResultBlock = {
  id: 'fixture-emp-empty-projects',
  type: 'EMPLOYEE_PROFILE',
  title: 'Employee Directory: Samira Khan',
  timestamp: '10:40 AM',
  isSensitive: true,
  payload: {
    employee: {
      id: 'emp_3050',
      name: 'Samira Khan',
      role: 'manager',
      department: 'Operations',
      team: 'team_ops_infra',
      active_projects: [],
      status: 'Active',
    },
  },
};

/** Valid EMPLOYEE_PROFILE with long name, long department, and long email for overflow testing */
export const validEmployeeProfileLongFieldsFixture: GenericResultBlock = {
  id: 'fixture-emp-long-fields',
  type: 'EMPLOYEE_PROFILE',
  title: 'Employee Directory: Dr. Elizabeth Alexandra Montgomery-Wellington III',
  timestamp: '10:45 AM',
  isSensitive: true,
  payload: {
    employee: {
      id: 'emp_9999',
      name: 'Dr. Elizabeth Alexandra Montgomery-Wellington III',
      role: 'executive',
      department: 'Strategic Corporate Infrastructure & International Security Architecture',
      team: 'team_executive_council',
      email: 'elizabeth.alexandra.montgomery-wellington.iii@enterprise.subdivision.example.com',
      active_projects: [
        'Global Infrastructure Modernization and Governance Phase IV',
        'Cross-Regional Identity Federation Protocol',
      ],
      status: 'Active',
    },
  },
};

/** Invalid EMPLOYEE_PROFILE: missing required name */
export const invalidEmployeeProfileMissingNameFixture: GenericResultBlock = {
  id: 'fixture-emp-invalid-no-name',
  type: 'EMPLOYEE_PROFILE',
  title: 'Corrupted Profile Record',
  timestamp: '10:50 AM',
  isSensitive: true,
  payload: {
    employee: {
      id: 'emp_1042',
      role: 'employee',
      department: 'Engineering',
      // Missing required name
    },
  },
};

/** Invalid EMPLOYEE_PROFILE: invalid project array structure */
export const invalidEmployeeProfileInvalidProjectsFixture: GenericResultBlock = {
  id: 'fixture-emp-invalid-projects',
  type: 'EMPLOYEE_PROFILE',
  title: 'Malformed Projects Record',
  timestamp: '10:55 AM',
  isSensitive: true,
  payload: {
    employee: {
      id: 'emp_1042',
      name: 'Charlie Davis',
      role: 'employee',
      active_projects: 'Not an array', // Invalid: must be string[]
    },
  },
};

/** Invalid EMPLOYEE_PROFILE: unexpected field types */
export const invalidEmployeeProfileWrongTypesFixture: GenericResultBlock = {
  id: 'fixture-emp-invalid-types',
  type: 'EMPLOYEE_PROFILE',
  title: 'Corrupted Profile Types',
  timestamp: '11:00 AM',
  isSensitive: true,
  payload: {
    employee: {
      id: 9942, // Invalid: must be string
      name: { first: 'Charlie', last: 'Davis' }, // Invalid: must be string
      role: ['employee'], // Invalid: must be string
    },
  },
};

// ============================================================================
// 4. TICKET_LIST Fixtures (Controlled Stage 4 Test Fixtures)
// ============================================================================

/** Valid comprehensive ticket list with multiple priority and status tiers */
export const validTicketListMultipleFixture: GenericResultBlock = {
  id: 'fixture-tickets-multiple',
  type: 'TICKET_LIST',
  title: 'Assigned Support Tickets',
  timestamp: '11:10 AM',
  isSensitive: true,
  payload: {
    title: 'Active Engineering Support Tickets',
    total_count: 4,
    tickets: [
      {
        ticket_id: 412,
        title: 'Workstation monitor flickering violently under high refresh rate',
        description:
          'Primary Dell UltraSharp monitor in Hardware Lab 3 flickers black intermittently whenever 144Hz mode is enabled over DisplayPort. Swapping cables did not resolve the issue.',
        priority: 'URGENT',
        status: 'OPEN',
        category: 'Hardware',
        assigned_to: 'Alex Morgan (emp_2099)',
        owner_id: 'emp_1042',
        created_at: '2026-10-15 09:15 AM',
        updated_at: '2026-10-15 10:30 AM',
        events: [
          {
            id: 'ev-1',
            timestamp: '2026-10-15 09:15 AM',
            type: 'CREATED',
            actor: 'Charlie Davis (emp_1042)',
            description: 'Ticket created via Voice AI Helpdesk Kiosk.',
          },
          {
            id: 'ev-2',
            timestamp: '2026-10-15 09:30 AM',
            type: 'ASSIGNED',
            actor: 'AutoDispatcher',
            description: 'Ticket assigned to Helpdesk Specialist Alex Morgan.',
            new_value: 'Alex Morgan (emp_2099)',
          },
          {
            id: 'ev-3',
            timestamp: '2026-10-15 10:30 AM',
            type: 'STATUS_CHANGED',
            actor: 'Alex Morgan (emp_2099)',
            description: 'Dispatched replacement DisplayPort 1.4 certified cable to Lab 3.',
            old_value: 'OPEN',
            new_value: 'IN_PROGRESS',
          },
        ],
      },
      {
        ticket_id: 389,
        title: 'VPN gateway access denied for staging cluster subnet',
        description: 'Unable to reach the 10.240.0.0/16 private staging network after credentials rotation.',
        priority: 'HIGH',
        status: 'IN_PROGRESS',
        category: 'Network',
        assigned_to: 'NetworkOps Desk',
        owner_id: 'emp_1042',
        created_at: '2026-10-14 02:45 PM',
        updated_at: '2026-10-15 08:00 AM',
        // Deliberately no events array to test truthful "no ledger" rendering
      },
      {
        ticket_id: 301,
        title: 'Ergonomic mechanical split keyboard request',
        description: 'Self-service peripheral request for standard mechanical keyboard replacement.',
        priority: 'NORMAL',
        status: 'OPEN',
        category: 'Peripherals',
        assigned_to: 'IT Asset Depot',
        owner_id: 'emp_1042',
        created_at: '2026-10-12 11:20 AM',
        updated_at: '2026-10-12 11:20 AM',
      },
      {
        ticket_id: 284,
        title: 'Security badge NFC re-keying for Building C access',
        description: 'Physical security badge de-synced after turnstile firmware update.',
        priority: 'LOW',
        status: 'RESOLVED',
        category: 'Physical Security',
        assigned_to: 'Facilities Support',
        owner_id: 'emp_1042',
        created_at: '2026-10-10 08:10 AM',
        updated_at: '2026-10-11 04:30 PM',
        events: [
          {
            id: 'ev-284-1',
            timestamp: '2026-10-10 08:10 AM',
            type: 'CREATED',
            actor: 'Charlie Davis (emp_1042)',
            description: 'Badge issue reported at visitor reception.',
          },
          {
            id: 'ev-284-2',
            timestamp: '2026-10-11 04:30 PM',
            type: 'RESOLVED',
            actor: 'Facilities Staff',
            description: 'NFC chip reprogrammed and access verified at reader.',
            old_value: 'IN_PROGRESS',
            new_value: 'RESOLVED',
          },
        ],
      },
    ],
  },
};

/** Valid empty ticket list */
export const validTicketListEmptyFixture: GenericResultBlock = {
  id: 'fixture-tickets-empty',
  type: 'TICKET_LIST',
  title: 'Assigned Support Tickets',
  timestamp: '11:15 AM',
  isSensitive: true,
  payload: {
    title: 'Department Support Queue',
    total_count: 0,
    tickets: [],
  },
};

/** Invalid ticket list: missing ticket_id */
export const invalidTicketListMissingIdFixture: GenericResultBlock = {
  id: 'fixture-tickets-invalid-no-id',
  type: 'TICKET_LIST',
  title: 'Corrupted Ticket Record',
  timestamp: '11:20 AM',
  isSensitive: true,
  payload: {
    tickets: [
      {
        title: 'Missing ticket ID field',
        priority: 'NORMAL',
        status: 'OPEN',
      },
    ],
  },
};

/** Invalid ticket list: tickets is not an array */
export const invalidTicketListNotArrayFixture: GenericResultBlock = {
  id: 'fixture-tickets-invalid-not-array',
  type: 'TICKET_LIST',
  title: 'Malformed Ticket Payload',
  timestamp: '11:25 AM',
  isSensitive: true,
  payload: {
    tickets: 'Not an array',
  },
};

// ============================================================================
// 5. TEAM_METRIC_CHART Fixtures (Stage 5)
// ============================================================================

/** Valid BAR chart: Ticket Counts by Status with KPI summary cards */
export const validTeamMetricBarFixture: GenericResultBlock = {
  id: 'fixture-metrics-bar',
  type: 'TEAM_METRIC_CHART',
  title: 'Team Ticket Queue by Status',
  timestamp: '11:30 AM',
  isSensitive: true,
  payload: {
    chart_type: 'BAR',
    title: 'Tickets Grouped by Current Status',
    unit: 'tickets',
    team_id: 'TEAM-DEV-ALPHA',
    time_range: 'Past 30 Days',
    kpis: {
      total_tickets: 128,
      open_tickets: 24,
      in_progress_tickets: 18,
      resolved_tickets: 72,
      closed_tickets: 14,
      avg_resolution_time: '2.4 days',
      sla_compliance_pct: 94.2,
    },
    data: [
      { name: 'OPEN', value: 24 },
      { name: 'IN_PROGRESS', value: 18 },
      { name: 'RESOLVED', value: 72 },
      { name: 'CLOSED', value: 14 },
    ],
  },
};

/** Valid PIE chart: Ticket Priority Distribution */
export const validTeamMetricPieFixture: GenericResultBlock = {
  id: 'fixture-metrics-pie',
  type: 'TEAM_METRIC_CHART',
  title: 'Team Ticket Priority Distribution',
  timestamp: '11:35 AM',
  isSensitive: true,
  payload: {
    chart_type: 'PIE',
    title: 'Active Tickets by Priority Level',
    unit: 'tickets',
    team_id: 'TEAM-DEV-ALPHA',
    time_range: 'Current Quarter',
    kpis: {
      total_tickets: 42,
      open_tickets: 24,
      in_progress_tickets: 18,
    },
    data: [
      { name: 'URGENT', value: 4 },
      { name: 'HIGH', value: 12 },
      { name: 'NORMAL', value: 20 },
      { name: 'LOW', value: 6 },
    ],
  },
};

/** Valid Empty Chart: Zero data points */
export const emptyTeamMetricChartFixture: GenericResultBlock = {
  id: 'fixture-metrics-empty',
  type: 'TEAM_METRIC_CHART',
  title: 'Empty Team Metric Dataset',
  timestamp: '11:40 AM',
  isSensitive: true,
  payload: {
    chart_type: 'BAR',
    title: 'New Team (No Historical Tickets)',
    team_id: 'TEAM-NEW-ONBOARDING',
    time_range: 'Current Week',
    data: [],
  },
};

/** Valid All-Zero Metric Chart */
export const allZeroTeamMetricChartFixture: GenericResultBlock = {
  id: 'fixture-metrics-all-zero',
  type: 'TEAM_METRIC_CHART',
  title: 'Zero Incident Metric Dataset',
  timestamp: '11:45 AM',
  isSensitive: true,
  payload: {
    chart_type: 'PIE',
    title: 'Security Escalations by Severity',
    unit: 'incidents',
    team_id: 'TEAM-SEC-OPS',
    time_range: 'Past 7 Days',
    kpis: {
      total_tickets: 0,
      open_tickets: 0,
      resolved_tickets: 0,
      sla_compliance_pct: 100.0,
    },
    data: [
      { name: 'CRITICAL', value: 0 },
      { name: 'HIGH', value: 0 },
      { name: 'MEDIUM', value: 0 },
      { name: 'LOW', value: 0 },
    ],
  },
};

/** Valid Long Labels Chart */
export const longLabelsTeamMetricChartFixture: GenericResultBlock = {
  id: 'fixture-metrics-long-labels',
  type: 'TEAM_METRIC_CHART',
  title: 'Detailed Category Breakdown',
  timestamp: '11:50 AM',
  isSensitive: true,
  payload: {
    chart_type: 'BAR',
    title: 'Requests by Infrastructure Domain',
    team_id: 'TEAM-INFRA',
    time_range: 'Year to Date',
    data: [
      { name: 'Kubernetes Cluster Provisioning & Autoscaling', value: 45 },
      { name: 'IAM Federation & Biometric Smart Card Access', value: 38 },
      { name: 'Zero-Trust Network Tunnel Termination Endpoints', value: 29 },
      { name: 'Continuous Security Audit & SAST Vulnerability Remediation', value: 61 },
    ],
  },
};

/** Invalid chart: Unsupported chart type */
export const invalidTeamMetricChartTypeFixture: GenericResultBlock = {
  id: 'fixture-metrics-invalid-type',
  type: 'TEAM_METRIC_CHART',
  title: 'Unsupported Chart Specification',
  timestamp: '11:55 AM',
  isSensitive: true,
  payload: {
    chart_type: 'SCATTER_PLOT', // Invalid
    title: 'Scatter metrics',
    data: [{ name: 'A', value: 10 }],
  },
};

/** Invalid chart: Missing required data / malformed values */
export const invalidTeamMetricChartMissingFieldsFixture: GenericResultBlock = {
  id: 'fixture-metrics-invalid-fields',
  type: 'TEAM_METRIC_CHART',
  title: 'Malformed Metric Specification',
  timestamp: '12:00 PM',
  isSensitive: true,
  payload: {
    chart_type: 'BAR',
    title: 'Corrupted Data Structure',
    data: [
      { name: 'VALID', value: 10 },
      { name: 'CORRUPTED', value: 'Not a number' }, // Invalid value
    ],
  },
};

// ============================================================================
// 6. TRUST_TRACE_GRAPH Fixtures (Stage 6)
// ============================================================================

/** Valid Complete Trust Trace: Full positive verified creation path */
export const validTrustTraceSuccessFixture: GenericResultBlock = {
  id: 'fixture-trust-success',
  type: 'TRUST_TRACE_GRAPH',
  title: 'Verified Security Pipeline Trace',
  timestamp: '12:05 PM',
  isSensitive: true,
  payload: {
    trace_id: 'trc-v4-99120',
    turn_id: 'turn-charlie-04',
    session_id: 'sess_charlie_1042',
    summary: 'Voice Ticket Creation (Charlie Davis — emp_1042)',
    final_verdict: 'ALLOW',
    nodes: [
      {
        id: 'node-ingress',
        label: 'Kiosk Audio Ingress',
        stage: 'ingress',
        status: 'PASS',
        detail: '16kHz PCM Stream Captured (2.8s)',
        timestamp: '12:05:01 PM',
      },
      {
        id: 'node-deepfake',
        label: 'DetectifAI Deepfake Check',
        stage: 'deepfake',
        status: 'PASS',
        detail: 'Genuine Human Audio (Score: 0.94)',
        timestamp: '12:05:02 PM',
      },
      {
        id: 'node-speaker',
        label: 'DetectifAI Speaker Match',
        stage: 'speaker_match',
        status: 'PASS',
        detail: 'Verified: Charlie Davis (ref_charlie_1042)',
        timestamp: '12:05:02 PM',
      },
      {
        id: 'node-handshake',
        label: 'Agent Identity Handshake',
        stage: 'handshake',
        status: 'PASS',
        detail: 'Service: agent_intentlock_kiosk_v1 Attested',
        timestamp: '12:05:03 PM',
        requesting_agent: 'agent_intentlock_kiosk_v1',
        receiving_agent: 'auth_gateway_internal',
        requested_capability: 'create_ticket',
        handshake_outcome: 'MUTUALLY_AUTHENTICATED',
      },
      {
        id: 'node-policy',
        label: 'Deterministic Policy Engine',
        stage: 'policy',
        status: 'PASS',
        detail: 'Rule EMP_SELF_SERVICE ALLOWED',
        timestamp: '12:05:03 PM',
        policy_decision: 'Caller emp_1042 authorized to create own hardware ticket',
      },
      {
        id: 'node-grant',
        label: 'ActionGrant Issuer',
        stage: 'grant',
        status: 'PASS',
        detail: 'Grant: SHA-256 bound, Single-Use 90s',
        timestamp: '12:05:04 PM',
        receipt_id: 'grant_9912_a8f3',
      },
      {
        id: 'node-commit',
        label: 'Protected Executor (Supabase DB)',
        stage: 'commit',
        status: 'PASS',
        detail: 'Atomic PostgreSQL Tx Committed (Ticket #412)',
        timestamp: '12:05:04 PM',
        receipt_id: 'tx_99120_committed',
      },
    ],
    edges: [
      { id: 'e1-2', source: 'node-ingress', target: 'node-deepfake', animated: true },
      { id: 'e2-3', source: 'node-deepfake', target: 'node-speaker', animated: true },
      { id: 'e3-4', source: 'node-speaker', target: 'node-handshake', animated: true },
      { id: 'e4-5', source: 'node-handshake', target: 'node-policy', animated: true },
      { id: 'e5-6', source: 'node-policy', target: 'node-grant', animated: true },
      { id: 'e6-7', source: 'node-grant', target: 'node-commit', animated: true },
    ],
  },
};

/** Valid Denied Trust Trace: Cross-scope authorization failure */
export const validTrustTraceDeniedFixture: GenericResultBlock = {
  id: 'fixture-trust-denied',
  type: 'TRUST_TRACE_GRAPH',
  title: 'Access Denied Security Trace',
  timestamp: '12:10 PM',
  isSensitive: true,
  payload: {
    trace_id: 'trc-v4-denial-01',
    turn_id: 'turn-charlie-05',
    session_id: 'sess_charlie_1042',
    summary: 'Executive Payroll Query Attempt (Charlie Davis — emp_1042)',
    final_verdict: 'DENY',
    nodes: [
      {
        id: 'node-ingress',
        label: 'Kiosk Audio Ingress',
        stage: 'ingress',
        status: 'PASS',
        detail: '16kHz PCM Audio (1.9s)',
        timestamp: '12:10:01 PM',
      },
      {
        id: 'node-deepfake',
        label: 'DetectifAI Deepfake Check',
        stage: 'deepfake',
        status: 'PASS',
        detail: 'Genuine Speech (Score: 0.96)',
        timestamp: '12:10:02 PM',
      },
      {
        id: 'node-speaker',
        label: 'DetectifAI Speaker Match',
        stage: 'speaker_match',
        status: 'PASS',
        detail: 'Verified: Charlie Davis (emp_1042)',
        timestamp: '12:10:02 PM',
      },
      {
        id: 'node-policy',
        label: 'Deterministic Policy Engine',
        stage: 'policy',
        status: 'DENIED',
        detail: 'ROLE_SCOPE_VIOLATION',
        timestamp: '12:10:03 PM',
        reason: 'Employee role is barred from querying executive payroll records',
        policy_decision: 'Default-deny evaluation: Required role EXECUTIVE, caller holds EMPLOYEE',
      },
      {
        id: 'node-grant',
        label: 'ActionGrant Issuer',
        stage: 'grant',
        status: 'SKIPPED',
        detail: 'Zero Grants Minted',
        timestamp: '12:10:03 PM',
      },
      {
        id: 'node-commit',
        label: 'Protected Executor',
        stage: 'commit',
        status: 'SKIPPED',
        detail: 'Zero Rows Altered (0 writes)',
        timestamp: '12:10:03 PM',
      },
    ],
    edges: [
      { id: 'ed-1', source: 'node-ingress', target: 'node-deepfake', animated: true },
      { id: 'ed-2', source: 'node-deepfake', target: 'node-speaker', animated: true },
      { id: 'ed-3', source: 'node-speaker', target: 'node-policy', animated: true },
      { id: 'ed-4', source: 'node-policy', target: 'node-grant', animated: false },
      { id: 'ed-5', source: 'node-grant', target: 'node-commit', animated: false },
    ],
  },
};

/** Valid Speaker Mismatch Trace: Voice spoofing / impersonation negative test */
export const validTrustTraceSpeakerMismatchFixture: GenericResultBlock = {
  id: 'fixture-trust-speaker-failed',
  type: 'TRUST_TRACE_GRAPH',
  title: 'Speaker Verification Mismatch Trace',
  timestamp: '12:15 PM',
  isSensitive: true,
  payload: {
    trace_id: 'trc-v4-mismatch-88',
    turn_id: 'turn-unknown-01',
    summary: 'Voice Claim Mismatch (Claimed: Bob Miller — emp_1020)',
    final_verdict: 'ABORT',
    nodes: [
      {
        id: 'node-ingress',
        label: 'Kiosk Audio Ingress',
        stage: 'ingress',
        status: 'PASS',
        detail: 'Audio Stream Received',
        timestamp: '12:15:01 PM',
      },
      {
        id: 'node-deepfake',
        label: 'DetectifAI Deepfake Check',
        stage: 'deepfake',
        status: 'PASS',
        detail: 'Genuine Acoustic Profile',
        timestamp: '12:15:02 PM',
      },
      {
        id: 'node-speaker',
        label: 'DetectifAI Speaker Match',
        stage: 'speaker_match',
        status: 'FAIL',
        detail: 'Speaker Mismatch (Score: 0.21 < 0.75)',
        timestamp: '12:15:02 PM',
        reason: 'Acoustic embeddings differ significantly from registered profile for emp_1020',
      },
      {
        id: 'node-policy',
        label: 'Deterministic Policy Engine',
        stage: 'policy',
        status: 'ABORTED',
        detail: 'Pipeline Aborted on Identity Failure',
        timestamp: '12:15:02 PM',
      },
      {
        id: 'node-commit',
        label: 'Protected Executor',
        stage: 'commit',
        status: 'ABORTED',
        detail: 'Execution Denied',
        timestamp: '12:15:02 PM',
      },
    ],
    edges: [
      { id: 'em-1', source: 'node-ingress', target: 'node-deepfake', animated: true },
      { id: 'em-2', source: 'node-deepfake', target: 'node-speaker', animated: true },
      { id: 'em-3', source: 'node-speaker', target: 'node-policy', animated: false },
      { id: 'em-4', source: 'node-policy', target: 'node-commit', animated: false },
    ],
  },
};

/** Valid Pending Trace: Checkpoint still in progress */
export const validTrustTracePendingFixture: GenericResultBlock = {
  id: 'fixture-trust-pending',
  type: 'TRUST_TRACE_GRAPH',
  title: 'In-Flight Verification Trace',
  timestamp: '12:20 PM',
  isSensitive: true,
  payload: {
    trace_id: 'trc-v4-inflight-09',
    summary: 'Evaluating Live Speaker Features',
    final_verdict: 'PENDING',
    nodes: [
      {
        id: 'node-ingress',
        label: 'Kiosk Audio Ingress',
        stage: 'ingress',
        status: 'PASS',
        detail: '16kHz Audio Received',
        timestamp: '12:20:00 PM',
      },
      {
        id: 'node-deepfake',
        label: 'DetectifAI Deepfake Check',
        stage: 'deepfake',
        status: 'PASS',
        detail: 'Deepfake Check Completed',
        timestamp: '12:20:01 PM',
      },
      {
        id: 'node-speaker',
        label: 'DetectifAI Speaker Match',
        stage: 'speaker_match',
        status: 'PENDING',
        detail: 'Computing Vector Cosine Distance...',
        timestamp: '12:20:02 PM',
      },
    ],
    edges: [
      { id: 'ep-1', source: 'node-ingress', target: 'node-deepfake', animated: true },
      { id: 'ep-2', source: 'node-deepfake', target: 'node-speaker', animated: true },
    ],
  },
};

/** Valid Parallel Branch Trace: Multi-branch evaluation pipeline */
export const validTrustTraceParallelFixture: GenericResultBlock = {
  id: 'fixture-trust-parallel',
  type: 'TRUST_TRACE_GRAPH',
  title: 'Parallel Security Verification DAG',
  timestamp: '12:25 PM',
  isSensitive: true,
  payload: {
    trace_id: 'trc-parallel-branch-01',
    summary: 'Concurrent Dual Biometric & Intent Validation',
    final_verdict: 'ALLOW',
    nodes: [
      { id: 'p-in', label: 'Audio Ingress', stage: 'ingress', status: 'PASS', detail: 'Single Utterance' },
      { id: 'p-df', label: 'DetectifAI Deepfake', stage: 'deepfake', status: 'PASS', detail: 'Score 0.97' },
      { id: 'p-spk', label: 'DetectifAI Speaker', stage: 'speaker_match', status: 'PASS', detail: 'Verified Voice' },
      { id: 'p-stt', label: 'Speech-to-Text Parsing', stage: 'ingress', status: 'PASS', detail: 'Confidence 0.99' },
      { id: 'p-pol', label: 'Policy Engine Gate', stage: 'policy', status: 'PASS', detail: 'All Checks Concur' },
      { id: 'p-com', label: 'Atomic SQL Mutation', stage: 'commit', status: 'PASS', detail: 'Committed TX-1082' },
    ],
    edges: [
      { id: 'e-in-df', source: 'p-in', target: 'p-df', animated: true },
      { id: 'e-in-spk', source: 'p-in', target: 'p-spk', animated: true },
      { id: 'e-in-stt', source: 'p-in', target: 'p-stt', animated: true },
      { id: 'e-df-pol', source: 'p-df', target: 'p-pol', animated: true },
      { id: 'e-spk-pol', source: 'p-spk', target: 'p-pol', animated: true },
      { id: 'e-stt-pol', source: 'p-stt', target: 'p-pol', animated: true },
      { id: 'e-pol-com', source: 'p-pol', target: 'p-com', animated: true },
    ],
  },
};

/** Valid Empty Trace: Zero recorded events */
export const emptyTrustTraceFixture: GenericResultBlock = {
  id: 'fixture-trust-empty',
  type: 'TRUST_TRACE_GRAPH',
  title: 'Empty Security Trace',
  timestamp: '12:30 PM',
  isSensitive: true,
  payload: {
    trace_id: 'trc-empty-00',
    nodes: [],
  },
};

/** Invalid Trace: Edge references nonexistent node */
export const invalidTrustTraceDanglingEdgeFixture: GenericResultBlock = {
  id: 'fixture-trust-invalid-edge',
  type: 'TRUST_TRACE_GRAPH',
  title: 'Corrupted Trust Trace (Dangling Edge)',
  timestamp: '12:35 PM',
  isSensitive: true,
  payload: {
    trace_id: 'trc-invalid-edge',
    nodes: [
      { id: 'node-1', label: 'Check 1', stage: 'ingress', status: 'PASS' },
    ],
    edges: [
      { id: 'e-bad', source: 'node-1', target: 'nonexistent-node-999' },
    ],
  },
};

/** Invalid Trace: Duplicate node identifiers */
export const invalidTrustTraceDuplicateNodeFixture: GenericResultBlock = {
  id: 'fixture-trust-invalid-dup',
  type: 'TRUST_TRACE_GRAPH',
  title: 'Corrupted Trust Trace (Duplicate IDs)',
  timestamp: '12:40 PM',
  isSensitive: true,
  payload: {
    trace_id: 'trc-invalid-dup',
    nodes: [
      { id: 'node-dup', label: 'Checkpoint A', stage: 'ingress', status: 'PASS' },
      { id: 'node-dup', label: 'Checkpoint B', stage: 'policy', status: 'PASS' },
    ],
  },
};

// ============================================================================
// 7. READBACK_CONFIRMATION Fixtures (Stage 7)
// ============================================================================

/** Valid Complete Readback: Canonical Ticket Creation */
export const validReadbackConfirmationPendingFixture: GenericResultBlock = {
  id: 'fixture-readback-canonical',
  type: 'READBACK_CONFIRMATION',
  title: 'Action Confirmation Required',
  timestamp: '12:04 PM',
  isSensitive: true,
  payload: {
    confirmation_id: 'conf_99120_a1',
    status: 'PENDING',
    requires_voice_confirmation: true,
    draft: {
      action: 'create_ticket',
      target: 'emp_1042 (Charlie Davis)',
      params: {
        title: 'Monitor flickering violently',
        priority: 'urgent',
        category: 'hardware',
        device_serial: 'MON-DELL-8821X',
      },
      summary_readback:
        'Create urgent hardware ticket for monitor flickering violently assigned to Charlie Davis?',
      expires_in_seconds: 60,
    },
  },
};

/** Valid Minimal Readback: Flat parameters format */
export const validReadbackConfirmationMinimalFixture: GenericResultBlock = {
  id: 'fixture-readback-minimal',
  type: 'READBACK_CONFIRMATION',
  title: 'Action Confirmation: Reset Kiosk Session',
  timestamp: '12:06 PM',
  isSensitive: true,
  payload: {
    action: 'reset_session',
    target: 'kiosk_terminal_04',
    params: {
      reason: 'Caller requested session wipe',
    },
    summary_readback: 'Reset and wipe current kiosk session context?',
    expires_in_seconds: 30,
    requires_voice_confirmation: true,
  },
};

/** Invalid Readback: Missing action verb */
export const invalidReadbackConfirmationMissingActionFixture: GenericResultBlock = {
  id: 'fixture-readback-invalid-no-action',
  type: 'READBACK_CONFIRMATION',
  title: 'Malformed Readback Payload',
  timestamp: '12:08 PM',
  isSensitive: true,
  payload: {
    draft: {
      // Missing 'action' verb
      params: { title: 'Test ticket' },
    },
  },
};

/** Invalid Readback: Malformed params (string instead of record) */
export const invalidReadbackConfirmationMalformedParamsFixture: GenericResultBlock = {
  id: 'fixture-readback-invalid-bad-params',
  type: 'READBACK_CONFIRMATION',
  title: 'Corrupted Readback Parameters',
  timestamp: '12:09 PM',
  isSensitive: true,
  payload: {
    draft: {
      action: 'create_ticket',
      params: 'Invalid non-object parameters string',
    },
  },
};

// ============================================================================
// 8. ACTION_RECEIPT Fixtures (Stage 7)
// ============================================================================

/** Valid Canonical Committed Receipt: Ticket #412 Created */
export const validActionReceiptSuccessFixture: GenericResultBlock = {
  id: 'fixture-receipt-canonical-success',
  type: 'ACTION_RECEIPT',
  title: 'Cryptographic Action Receipt: Ticket #412',
  timestamp: '12:05 PM',
  isSensitive: true,
  payload: {
    summary: 'Ticket #412 successfully created and committed to Supabase PostgreSQL.',
    receipt: {
      req_id: 'req_88190_turn04',
      tx_id: 'tx_pg_commit_99120_shard01',
      actor: 'emp_1042 (Charlie Davis)',
      action: 'create_ticket',
      resource_id: 412,
      status: 'COMMITTED',
      grant_hash_prefix: 'a8f3b29c',
      timestamp: '2026-10-16T12:05:04Z',
    },
  },
};

/** Valid Failed Transaction Receipt: Rolled Back Mutation */
export const validActionReceiptFailedFixture: GenericResultBlock = {
  id: 'fixture-receipt-failed-rollback',
  type: 'ACTION_RECEIPT',
  title: 'Action Execution Failed: Rolled Back',
  timestamp: '12:07 PM',
  isSensitive: true,
  payload: {
    summary: 'Database transaction aborted: Foreign key integrity constraint violation.',
    receipt: {
      req_id: 'req_88192_turn06',
      tx_id: 'tx_pg_rollback_99121_shard01',
      actor: 'emp_1042 (Charlie Davis)',
      action: 'assign_ticket',
      resource_id: 99999,
      status: 'FAILED',
      grant_hash_prefix: '7c12d44a',
      timestamp: '2026-10-16T12:07:11Z',
    },
  },
};

/** Valid Denied Action Receipt */
export const validActionReceiptDeniedFixture: GenericResultBlock = {
  id: 'fixture-receipt-denied',
  type: 'ACTION_RECEIPT',
  title: 'Action Execution Denied',
  timestamp: '12:11 PM',
  isSensitive: true,
  payload: {
    summary: 'Mutation aborted by Protected Executor: Invalid or expired ActionGrant.',
    receipt: {
      req_id: 'req_88194_turn08',
      tx_id: 'tx_denial_record_99122',
      actor: 'emp_1042 (Charlie Davis)',
      action: 'delete_ticket',
      status: 'DENIED',
      timestamp: '2026-10-16T12:11:03Z',
    },
  },
};

/** Invalid Action Receipt: Missing required tx_id */
export const invalidActionReceiptMissingTxIdFixture: GenericResultBlock = {
  id: 'fixture-receipt-invalid-no-tx',
  type: 'ACTION_RECEIPT',
  title: 'Malformed Action Receipt',
  timestamp: '12:13 PM',
  isSensitive: true,
  payload: {
    receipt: {
      // Missing required tx_id
      actor: 'emp_1042',
      timestamp: '2026-10-16T12:13:00Z',
    },
  },
};

// ============================================================================
// 9. Unimplemented / Unsupported Result Type Fixture (Stage 8 Target)
// ============================================================================

/** Unsupported / Future result type (PROTECTED_DOCUMENT_PREVIEW for Stage 8) */
export const unsupportedResultTypeFixture: GenericResultBlock = {
  id: 'fixture-unsupported-doc-preview',
  type: 'PROTECTED_DOCUMENT_PREVIEW',
  title: 'Confidential Document Preview',
  timestamp: '12:15 PM',
  isSensitive: true,
  payload: {
    document_id: 'doc_sec_audit_2026',
    title: 'Q3_Security_Audit_Report.pdf',
    classification: 'CONFIDENTIAL',
    file_size_bytes: 2048576,
  },
};

// ============================================================================
// 10. DATA_TABLE Fixtures (Stage 1 Contracts)
// ============================================================================

/** Valid comprehensive DATA_TABLE fixture */
export const validDataTableFixture: GenericResultBlock = {
  id: 'fixture-datatable-authorized-people',
  type: 'DATA_TABLE',
  title: 'Engineering Team Roster',
  timestamp: '12:20 PM',
  isSensitive: true,
  payload: {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'title', label: 'Role / Title' },
      { key: 'department', label: 'Department' },
    ],
    rows: [
      { id: 'EMP-1001', name: 'Aarav Mehta', title: 'Senior Software Engineer', department: 'Engineering' },
      { id: 'EMP-1002', name: 'Neha Gupta', title: 'Frontend Engineer', department: 'Engineering' },
      { id: 'EMP-2001', name: 'Priya Sharma', title: 'Engineering Manager', department: 'Engineering' },
    ],
    total_count: 3,
  },
};

/** Valid empty DATA_TABLE fixture */
export const validDataTableEmptyFixture: GenericResultBlock = {
  id: 'fixture-datatable-empty',
  type: 'DATA_TABLE',
  title: 'Empty Directory Search',
  timestamp: '12:22 PM',
  isSensitive: true,
  payload: {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'title', label: 'Role / Title' },
      { key: 'department', label: 'Department' },
    ],
    rows: [],
    total_count: 0,
  },
};

/** Invalid DATA_TABLE: duplicate row IDs */
export const invalidDataTableDuplicateRowsFixture: GenericResultBlock = {
  id: 'fixture-datatable-invalid-dup',
  type: 'DATA_TABLE',
  title: 'Corrupted Table (Duplicate IDs)',
  timestamp: '12:25 PM',
  isSensitive: true,
  payload: {
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'title', label: 'Title' },
      { key: 'department', label: 'Department' },
    ],
    rows: [
      { id: 'EMP-1001', name: 'Aarav Mehta', title: 'Engineer', department: 'Engineering' },
      { id: 'EMP-1001', name: 'Aarav Duplicate', title: 'Engineer', department: 'Engineering' },
    ],
    total_count: 2,
  },
};

// ============================================================================
// 11. ORG_TREE Fixtures (Stage 1 Contracts)
// ============================================================================

/** Valid hierarchical ORG_TREE fixture */
export const validOrgTreeHierarchyFixture: GenericResultBlock = {
  id: 'fixture-orgtree-engineering',
  type: 'ORG_TREE',
  title: 'Engineering Reporting Tree',
  timestamp: '12:30 PM',
  isSensitive: true,
  payload: {
    root_id: 'EMP-4002',
    nodes: [
      { id: 'EMP-4002', name: 'Arvind Rao', title: 'CTO / VP Engineering', direct_count: 1 },
      { id: 'EMP-2001', name: 'Priya Sharma', title: 'Engineering Manager', direct_count: 2 },
      { id: 'EMP-1001', name: 'Aarav Mehta', title: 'Senior Software Engineer', direct_count: 0 },
      { id: 'EMP-1002', name: 'Neha Gupta', title: 'Frontend Engineer', direct_count: 0 },
    ],
    edges: [
      { source: 'EMP-4002', target: 'EMP-2001' },
      { source: 'EMP-2001', target: 'EMP-1001' },
      { source: 'EMP-2001', target: 'EMP-1002' },
    ],
    direct_count: 1,
    descendant_count: 3,
  },
};

/** Invalid ORG_TREE: cyclical relationship */
export const invalidOrgTreeCycleFixture: GenericResultBlock = {
  id: 'fixture-orgtree-cycle',
  type: 'ORG_TREE',
  title: 'Corrupted Org Tree (Cycle)',
  timestamp: '12:32 PM',
  isSensitive: true,
  payload: {
    root_id: 'EMP-2001',
    nodes: [
      { id: 'EMP-2001', name: 'Priya Sharma', title: 'Manager', direct_count: 1 },
      { id: 'EMP-1001', name: 'Aarav Mehta', title: 'Lead', direct_count: 1 },
    ],
    edges: [
      { source: 'EMP-2001', target: 'EMP-1001' },
      { source: 'EMP-1001', target: 'EMP-2001' },
    ],
    direct_count: 1,
    descendant_count: 1,
  },
};

// ============================================================================
// 12. Five Shared Coordination Contracts (Success, Clarification, Denied)
// ============================================================================

/** Contract 1: Success — Verified Actor & Dual Biometric Pass */
export const contract1SuccessSessionFixture = {
  state: 'VERIFIED' as const,
  sessionId: 'sess_aarav_99120_auth',
  actor: {
    employeeId: 'EMP-1001',
    fullName: 'Aarav Mehta',
    role: 'employee' as const,
    teamId: 'team_eng_a',
    expiresInSeconds: 90,
  },
  evidence: {
    speaker_decision: 'PASS',
    authenticity_verdict: 'PASS',
    speaker_score: 0.94,
    authenticity_score: 0.97,
  },
};

/** Contract 1: Clarification — Unclaimed session requires employee ID */
export const contract1ClarificationSessionFixture = {
  state: 'ANONYMOUS' as const,
  sessionId: null,
  status: 'clarification' as const,
  message: 'Please state your employee ID to view private records.',
  evidence: {
    speaker_decision: 'SKIPPED',
    authenticity_verdict: 'SKIPPED',
    reason: 'Anonymous public inquiry requires no biometric verification',
  },
};

/** Contract 1: Denied — Biometric voice mismatch or synthetic speech */
export const contract1DeniedSessionFixture = {
  state: 'ANONYMOUS' as const,
  sessionId: null,
  status: 'denial' as const,
  error: {
    code: 'SPEAKER_MISMATCH',
    message: 'Spoken voice does not match the enrolled voice profile for EMP-1001.',
  },
  evidence: {
    speaker_decision: 'FAIL',
    authenticity_verdict: 'PASS',
    speaker_score: 0.22,
    reason: 'Cosine similarity below verification threshold (0.22 < 0.75)',
  },
};

/** Contract 2: Success Proposal — Contact edit draft awaiting spoken readback */
export const contract2SuccessProposalFixture: GenericResultBlock = {
  id: 'fixture-contract2-proposal-success',
  type: 'READBACK_CONFIRMATION',
  title: 'Action Confirmation Required',
  timestamp: '12:40 PM',
  isSensitive: true,
  payload: {
    confirmation_id: 'conf_contact_emp1001_01',
    status: 'PENDING',
    requires_voice_confirmation: true,
    draft: {
      action: 'update_contact',
      target: 'EMP-1001 (Aarav Mehta)',
      params: {
        field: 'phone',
        current_value: '+1-555-0100',
        proposed_value: '+1-555-0199',
      },
      summary_readback: 'Update your contact phone number to +1-555-0199?',
      expires_in_seconds: 60,
    },
  },
};

/** Contract 2: Clarification Proposal — Missing mutation field */
export const contract2ClarificationProposalFixture = {
  status: 'clarification' as const,
  message: 'Which contact field would you like to update? You can change your phone number or corporate email.',
};

/** Contract 2: Denied Proposal — Cross-employee promotion unauthorized */
export const contract2DeniedProposalFixture: GenericResultBlock = {
  id: 'fixture-contract2-proposal-denied',
  type: 'DENIAL_BANNER',
  title: 'Unauthorized Action Request',
  timestamp: '12:42 PM',
  isSensitive: false,
  payload: {
    code: 'INSUFFICIENT_ROLE_AUTHORITY',
    message: 'You are not authorized to modify designations or reporting managers.',
    reason: 'Role and reporting mutations require executive authorization and formal HR sign-off.',
    next_step: 'Contact the corporate HR operations desk for reporting adjustments.',
  },
};

/** Contract 2: Committed Write — Transaction receipt committed to Supabase */
export const contract2CommittedReceiptFixture: GenericResultBlock = {
  id: 'fixture-contract2-receipt-committed',
  type: 'ACTION_RECEIPT',
  title: 'Cryptographic Action Receipt: Contact Update',
  timestamp: '12:43 PM',
  isSensitive: true,
  payload: {
    summary: 'Contact phone number updated and committed to PostgreSQL.',
    receipt: {
      req_id: 'req_88195_turn05',
      tx_id: 'tx_pg_commit_emp1001_phone',
      actor: 'EMP-1001 (Aarav Mehta)',
      action: 'update_contact',
      resource_id: 'EMP-1001',
      status: 'COMMITTED',
      grant_hash_prefix: '4c8e1a',
      timestamp: '2026-10-17T12:43:00Z',
    },
  },
};

/** Contract 3: Success Selection — Context references stable target ID */
export const contract3SuccessSelectionFixture = {
  action: 'select_ticket',
  source_result_id: 'fixture-tickets-multiple',
  target_id: '412',
  view: 'detail',
};

/** Contract 3: Clarification Selection — Ambiguous natural reference */
export const contract3ClarificationSelectionFixture = {
  status: 'clarification' as const,
  assistant_message: 'Multiple tickets match "the urgent one". Did you mean ticket #412 (monitor flickering) or ticket #389 (VPN access)?',
};

/** Contract 3: Denied Selection — Target out of permitted scope */
export const contract3DeniedSelectionFixture = {
  status: 'denial' as const,
  error: {
    code: 'OUT_OF_SCOPE',
    message: 'Ticket #999 belongs to an unauthorized security team partition.',
  },
};

/** Contract 4: Success Multi-Result — Primary list + secondary metric breakdown */
export const contract4SuccessMultiResultFixture = {
  primary_result_id: 'fixture-tickets-multiple',
  result_blocks: [
    validTicketListMultipleFixture,
    validTeamMetricBarFixture,
  ],
};

/** Contract 4: Clarification Result — Unresolved entity disambiguation */
export const contract4ClarificationResultFixture: GenericResultBlock = {
  id: 'fixture-contract4-clarification',
  type: 'PUBLIC_FAQ',
  title: 'Topic Disambiguation',
  timestamp: '12:46 PM',
  isSensitive: false,
  payload: {
    question: 'Hardware vs Software Support Guidelines',
    answer: 'Standard laptop hardware issues are handled via self-service tickets. Cloud infrastructure requests require team lead endorsement.',
    category: 'Helpdesk Guidance',
  },
};

/** Contract 4: Denied Result — Policy denial with actionable next step */
export const contract4DeniedResultFixture = validDenialBannerCompleteFixture;

/** Contract 5: Success Turn Reply — Complete logical turn with TTS audio */
export const contract5SuccessTurnReplyFixture = {
  transcript: 'Show my assigned support tickets.',
  assistant_message: 'Here are your 4 active engineering support tickets.',
  status: 'success' as const,
  session: contract1SuccessSessionFixture,
  result_block: validTicketListMultipleFixture,
  result_blocks: [validTicketListMultipleFixture],
  primary_result_id: 'fixture-tickets-multiple',
  speech_audio: {
    base64_audio: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=',
    mime_type: 'audio/wav',
  },
  trust_evidence: {
    speaker_decision: 'PASS',
    authenticity_verdict: 'PASS',
  },
};

/** Contract 5: Clarification Turn Reply — Low confidence / ambiguous speech */
export const contract5ClarificationTurnReplyFixture = {
  transcript: 'Show me...',
  assistant_message: 'I heard "Show me...", but could not determine which records you wanted. You can ask for your profile, tickets, or team chart.',
  status: 'clarification' as const,
  session: contract1SuccessSessionFixture,
};

/** Contract 5: Denied Turn Reply — Voice verification failure */
export const contract5DeniedTurnReplyFixture = {
  transcript: 'Show executive payroll.',
  assistant_message: 'Access to executive payroll records is restricted to executive leadership.',
  status: 'denial' as const,
  error: {
    code: 'ACCESS_DENIED',
    message: 'Policy evaluation DENIED: caller role EMPLOYEE lacks EXECUTIVE capability.',
  },
  session: contract1SuccessSessionFixture,
  result_block: validDenialBannerCompleteFixture,
};

