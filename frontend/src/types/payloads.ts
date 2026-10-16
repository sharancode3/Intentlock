/**
 * IntentLock — Typed Result Block Payloads
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * ARCHITECTURAL CONTRACTS:
 * This module defines the strongly-typed payload contracts for all nine
 * ResultBlockType discriminators defined in the IntentLock architecture.
 *
 * INVARIANTS:
 * 1. The frontend never computes authorization or alters backend session state.
 * 2. Every payload originates from the trusted FastAPI backend.
 * 3. Undocumented fields use conservative, explicit optional types.
 * 4. Never use `any`; use typed structures or `Record<string, unknown>`.
 * 5. Ticket history and timelines are future contracts; no new discriminators are invented.
 */

// ============================================================================
// 1. PUBLIC_FAQ (Anonymous Knowledge Base / Policy Cards)
// ============================================================================

/**
 * Payload for anonymous public FAQ entries and policy lookups.
 * Sourced from Supabase `faqs` where `visibility = 'public'`.
 */
export interface PublicFaqPayload {
  /** The question or topic heading (e.g. "What are public visitor hours?") */
  question?: string;
  /** Verified plain-text answer body */
  answer: string;
  /** Primary source citation or document name (e.g. "Reception_Policy_v1.2.md") */
  source_document?: string;
  /** Alternate document field name used in some backend endpoints */
  source_doc?: string;
  /** Knowledge domain or category (e.g. "IT Equipment & Peripherals") */
  category?: string;
  /** Legacy/transitional summary field supported for backward compatibility */
  summary?: string;
}

// ============================================================================
// 2. EMPLOYEE_PROFILE (Internal Verified Directory Card)
// ============================================================================

/**
 * Standard employee directory record.
 * Displayed only after successful biometric verification and scope check.
 */
export interface EmployeeRecord {
  /** Authoritative employee ID, e.g. "emp_1042" */
  id: string;
  /** Full employee display name */
  name: string;
  /** Role in organization: employee | manager | helpdesk | executive */
  role: 'employee' | 'manager' | 'helpdesk' | 'executive' | string;
  /** Team identifier, e.g. "team_eng_a" */
  team?: string;
  /** Department name, e.g. "Engineering" */
  department?: string;
  /** Corporate email address */
  email?: string;
  /** Optional active project names or assignments */
  active_projects?: string[];
}

export interface EmployeeProfilePayload {
  /** The employee record from the authoritative database */
  employee: EmployeeRecord;
}

// ============================================================================
// 3. TICKET_LIST (Scoped Support Ticket Grid / Cards)
// ============================================================================

export type TicketPriority = 'URGENT' | 'HIGH' | 'NORMAL' | 'LOW' | string;
export type TicketStatus = 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED' | string;

/**
 * Single support ticket item from Supabase `tickets`.
 */
export interface TicketRecord {
  /** Numeric or string ticket ID, e.g. 412 or "TCK-412" */
  ticket_id: number | string;
  /** Brief summary/title of the issue */
  title: string;
  /** Ticket priority level */
  priority: TicketPriority;
  /** Current lifecycle status */
  status: TicketStatus;
  /** Assigned employee or team member */
  assigned_to?: string;
  /** Creator / owner employee ID */
  owner_id?: string;
  /** Category or tag (e.g. "hardware", "software") */
  category?: string;
  /** Creation timestamp (ISO 8601 string) */
  created_at?: string;
  /** Last updated timestamp (ISO 8601 string) */
  updated_at?: string;
}

export interface TicketListPayload {
  /** Optional list title or filter description */
  title?: string;
  /** Array of tickets authorized for caller display */
  tickets: TicketRecord[];
  /** Optional count for pagination */
  total_count?: number;
}

// ============================================================================
// 4. TEAM_METRIC_CHART (Manager Analytics Data)
// ============================================================================

export interface MetricDataPoint {
  /** Category or bucket label (e.g. "Urgent", "Hardware") */
  label: string;
  /** Count computed strictly via backend SQL aggregation */
  count: number;
  /** Optional priority tier */
  priority?: string;
  /** Optional presentation color override */
  color?: string;
}

export interface TeamMetricChartPayload {
  /** Chart rendering format */
  chart_type: 'BAR' | 'PIE';
  /** Human-readable metric title */
  metric_name?: string;
  /** Filter or department scope represented */
  scope_description?: string;
  /** Data points bound strictly to SQL group-by counts */
  data: MetricDataPoint[];
}

// ============================================================================
// 5. READBACK_CONFIRMATION (Pre-Execution Spoken/Visual Confirmation)
// ============================================================================

/**
 * Proposed action draft awaiting spoken or explicit user confirmation.
 * The conversational LLM produces proposals; the policy engine issues the draft.
 */
export interface ProposedActionDraft {
  /** Operation verb, e.g. "create_ticket", "close_ticket" */
  action: string;
  /** Target entity or identifier, e.g. "emp_1042" */
  target?: string;
  /** Exact parameters bound to the pending action */
  params: Record<string, unknown>;
  /** Concise spoken summary read back to caller */
  summary_readback?: string;
  /** Expiration window for this confirmation in seconds */
  expires_in_seconds?: number;
}

export interface ReadbackConfirmationPayload {
  /** The action draft to be confirmed */
  draft: ProposedActionDraft;
  /** Whether confirmation requires matching voice audio re-check */
  requires_voice_confirmation?: boolean;
}

// ============================================================================
// 6. DENIAL_BANNER (Access & Policy Denial Card)
// ============================================================================

/**
 * Payload communicating an access denial returned by the backend policy engine.
 * Never displays internal policy rules, secret implementation keys, or raw traces.
 */
export interface DenialBannerPayload {
  /** User-facing explanation of the denial decision */
  message: string;
  /** High-level denial code (e.g. "ACCESS_DENIED", "INSUFFICIENT_SCOPE", "UNVERIFIED_CALLER") */
  code?: string;
  /** Safe high-level category reason (e.g. "Action requires Manager role or ticket ownership.") */
  reason?: string;
  /** Safe actionable next step or guidance (e.g. "Contact the helpdesk desk supervisor.") */
  next_step?: string;
}

// ============================================================================
// 7. ACTION_RECEIPT (Immutable PostgreSQL Commit Receipt)
// ============================================================================

/**
 * Cryptographic execution receipt generated post-commit by the Protected Executor.
 * Reflects genuine PostgreSQL transaction commits.
 */
export interface ExecutionReceipt {
  /** Ingress request identifier */
  req_id?: string;
  /** PostgreSQL transaction commit identifier */
  tx_id: string;
  /** Authenticated employee ID who executed the action */
  actor: string;
  /** Action executed, e.g. "create_ticket" */
  action?: string;
  /** ISO 8601 execution timestamp */
  timestamp: string;
  /** Identifier of created/mutated resource, e.g. 412 */
  resource_id?: string | number;
  /** Commit status */
  status?: 'COMMITTED' | 'FAILED' | string;
  /** Short prefix of the consumed ActionGrant SHA-256 parameter hash */
  grant_hash_prefix?: string;
}

export interface ActionReceiptPayload {
  /** The committed execution receipt */
  receipt: ExecutionReceipt;
}

// ============================================================================
// 8. TRUST_TRACE_GRAPH (React Flow Real-Time Security Telemetry)
// ============================================================================

export type TrustTraceNodeStatus = 'PASS' | 'FAIL' | 'PENDING' | 'SKIPPED' | 'ABORTED';

export interface TrustTraceNode {
  /** Unique node identifier matching stage */
  id: string;
  /** Human-readable node label */
  label: string;
  /** Pipeline stage represented */
  stage: 'ingress' | 'deepfake' | 'speaker_match' | 'policy' | 'grant' | 'commit' | string;
  /** Verdict status of this security checkpoint */
  status: TrustTraceNodeStatus;
  /** High-level non-secret summary or score label */
  detail?: string;
  /** Timestamp when stage completed */
  timestamp?: string;
}

export interface TrustTraceEdge {
  id: string;
  source: string;
  target: string;
  animated?: boolean;
}

export interface TrustTraceGraphPayload {
  /** Ingress turn or trace identifier */
  trace_id?: string;
  /** Nodes for the security pipeline */
  nodes: TrustTraceNode[];
  /** Optional edge connections between nodes */
  edges?: TrustTraceEdge[];
}

// ============================================================================
// 9. PROTECTED_DOCUMENT_PREVIEW (Confidential Document Metadata Preview)
// ============================================================================

/**
 * Preview envelope for confidential documents retrieved via short-lived signed URLs.
 */
export interface ProtectedDocumentPreviewPayload {
  /** Unique document identifier */
  document_id: string;
  /** Document display title */
  title: string;
  /** MIME type, e.g. "application/pdf" */
  mime_type?: string;
  /** File size in bytes */
  file_size_bytes?: number;
  /** Ephemeral signed preview URL issued by backend */
  preview_url?: string;
  /** Timestamp when the preview URL expires */
  expires_at?: string;
  /** Classification tier */
  classification?: 'CONFIDENTIAL' | 'INTERNAL' | 'RESTRICTED' | string;
}
