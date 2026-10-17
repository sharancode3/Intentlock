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

import type {
  PublicFaqPayload,
  DenialBannerPayload,
  EmployeeProfilePayload,
  EmployeeRecord,
  TicketListPayload,
  TicketRecord,
  TicketEvent,
  TeamMetricChartPayload,
  MetricDataPoint,
  MetricKpiSummary,
  TrustTraceGraphPayload,
  TrustTraceNode,
  TrustTraceEdge,
  ReadbackConfirmationPayload,
  ProposedActionDraft,
  ActionReceiptPayload,
  ExecutionReceipt,
  DataTablePayload,
  OrgTreePayload,
} from '../../types/payloads';

export function validateDataTablePayload(raw: unknown): ValidationResult<DataTablePayload> {
  if (!isRecord(raw) || !Array.isArray(raw.columns) || !Array.isArray(raw.rows) ||
      raw.columns.length === 0 || raw.columns.length > 5 || raw.rows.length > 100 ||
      typeof raw.total_count !== 'number' || raw.total_count < raw.rows.length) {
    return { isValid: false, error: 'The table data is unavailable.' };
  }
  const allowed = new Set(['name', 'title', 'department', 'manager']);
  if (raw.columns.some((column: unknown) => !isRecord(column) || !allowed.has(String(column.key)) || !isNonEmptyString(column.label)) ||
      raw.rows.some((row: unknown) => !isRecord(row) || !isNonEmptyString(row.id) ||
        !isNonEmptyString(row.name) || !isNonEmptyString(row.title) || !isNonEmptyString(row.department))) {
    return { isValid: false, error: 'The table data is malformed.' };
  }
  const rows = raw.rows as DataTablePayload['rows'];
  if (new Set(rows.map(row => row.id)).size !== rows.length) {
    return { isValid: false, error: 'The table contains duplicate rows.' };
  }
  return { isValid: true, data: raw as unknown as DataTablePayload };
}

export function validateOrgTreePayload(raw: unknown): ValidationResult<OrgTreePayload> {
  if (!isRecord(raw) || !isNonEmptyString(raw.root_id) || !Array.isArray(raw.nodes) || !Array.isArray(raw.edges) ||
      raw.nodes.length === 0 || raw.nodes.length > 30 || raw.edges.length > 29 ||
      typeof raw.direct_count !== 'number' || typeof raw.descendant_count !== 'number') {
    return { isValid: false, error: 'The reporting tree is unavailable.' };
  }
  if (raw.nodes.some((node: unknown) => !isRecord(node) || !isNonEmptyString(node.id) || !isNonEmptyString(node.name) ||
      !isNonEmptyString(node.title) || typeof node.direct_count !== 'number') ||
      raw.edges.some((edge: unknown) => !isRecord(edge) || !isNonEmptyString(edge.source) || !isNonEmptyString(edge.target))) {
    return { isValid: false, error: 'The reporting tree is malformed.' };
  }
  const nodes = raw.nodes as OrgTreePayload['nodes'];
  const edges = raw.edges as OrgTreePayload['edges'];
  const ids = new Set(nodes.map(node => node.id));
  if (ids.size !== nodes.length || !ids.has(raw.root_id as string) ||
      edges.some(edge => !ids.has(edge.source) || !ids.has(edge.target) || edge.source === edge.target)) {
    return { isValid: false, error: 'The reporting tree has invalid relationships.' };
  }
  const children = new Map<string, string[]>();
  edges.forEach(edge => children.set(edge.source, [...(children.get(edge.source) || []), edge.target]));
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const hasCycle = (id: string): boolean => {
    if (visiting.has(id)) return true;
    if (visited.has(id)) return false;
    visiting.add(id);
    for (const child of children.get(id) || []) if (hasCycle(child)) return true;
    visiting.delete(id); visited.add(id); return false;
  };
  if (nodes.some(node => hasCycle(node.id))) {
    return { isValid: false, error: 'The reporting tree contains a cycle.' };
  }
  return { isValid: true, data: raw as unknown as OrgTreePayload };
}

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

// ============================================================================
// 3. EMPLOYEE_PROFILE Runtime Validator
// ============================================================================

/**
 * Validates that an arbitrary payload matches the EmployeeProfilePayload contract.
 *
 * Rules:
 * - Must be a non-null object.
 * - Supports payload with nested `employee` record or direct flat employee fields.
 * - Required identity fields: `id`, `name`, `role` (must be non-empty strings).
 * - Optional fields: `department`, `team`, `email`, `status` (must be strings if provided).
 * - Optional `active_projects`: if provided, must be an array of strings.
 * - Rejects malformed protected payloads safely without leaking sensitive values.
 */
export function validateEmployeeProfilePayload(
  raw: unknown
): ValidationResult<EmployeeProfilePayload> {
  if (!isRecord(raw)) {
    return {
      isValid: false,
      error: 'Malformed employee profile payload: expected an object.',
    };
  }

  // Support both canonical { employee: { ... } } and direct flat fields
  const candidate = isRecord(raw.employee) ? raw.employee : raw;

  if (!isNonEmptyString(candidate.id)) {
    return {
      isValid: false,
      error: 'Invalid employee profile: employee ID is required and must be a non-empty string.',
    };
  }

  if (!isNonEmptyString(candidate.name)) {
    return {
      isValid: false,
      error: 'Invalid employee profile: employee name is required and must be a non-empty string.',
    };
  }

  if (!isNonEmptyString(candidate.role)) {
    return {
      isValid: false,
      error: 'Invalid employee profile: role is required and must be a non-empty string.',
    };
  }

  if (!isOptionalString(candidate.department)) {
    return {
      isValid: false,
      error: 'Invalid employee profile: department must be a string.',
    };
  }

  if (!isOptionalString(candidate.team)) {
    return {
      isValid: false,
      error: 'Invalid employee profile: team must be a string.',
    };
  }

  if (!isOptionalString(candidate.email)) {
    return {
      isValid: false,
      error: 'Invalid employee profile: email must be a string.',
    };
  }

  if (!isOptionalString(candidate.phone)) {
    return {
      isValid: false,
      error: 'Invalid employee profile: phone must be a string.',
    };
  }

  if (!isOptionalString(candidate.status)) {
    return {
      isValid: false,
      error: 'Invalid employee profile: status must be a string.',
    };
  }
  if (!isOptionalString(candidate.manager_name)) {
    return { isValid: false, error: 'Invalid employee profile: manager name must be a string.' };
  }
  if (candidate.skills !== undefined && (!Array.isArray(candidate.skills) ||
      candidate.skills.length > 30 || candidate.skills.some((item: unknown) => typeof item !== 'string'))) {
    return { isValid: false, error: 'Invalid employee profile: skills must be a bounded list of names.' };
  }

  let normalizedProjects: string[] | undefined = undefined;
  if (candidate.active_projects !== undefined && candidate.active_projects !== null) {
    if (!Array.isArray(candidate.active_projects)) {
      return {
        isValid: false,
        error: 'Invalid employee profile: active_projects must be an array of project names.',
      };
    }

    for (let i = 0; i < candidate.active_projects.length; i++) {
      if (typeof candidate.active_projects[i] !== 'string') {
        return {
          isValid: false,
          error: 'Invalid employee profile: active_projects items must be strings.',
        };
      }
    }
    normalizedProjects = (candidate.active_projects as string[])
      .map((p) => p.trim())
      .filter((p) => p.length > 0);
  }

  const normalizedEmployee: EmployeeRecord = {
    id: candidate.id.trim(),
    name: candidate.name.trim(),
    role: candidate.role.trim(),
    department: isNonEmptyString(candidate.department) ? candidate.department.trim() : undefined,
    team: isNonEmptyString(candidate.team) ? candidate.team.trim() : undefined,
    email: isNonEmptyString(candidate.email) ? candidate.email.trim() : undefined,
    phone: isNonEmptyString(candidate.phone) ? candidate.phone.trim() : undefined,
    active_projects: normalizedProjects,
    status: isNonEmptyString(candidate.status) ? candidate.status.trim() : undefined,
    skills: Array.isArray(candidate.skills) ? candidate.skills.map((item: string) => item.trim()) : undefined,
    manager_name: isNonEmptyString(candidate.manager_name) ? candidate.manager_name.trim() : undefined,
  };

  return {
    isValid: true,
    data: {
      employee: normalizedEmployee,
    },
  };
}

/**
 * Fast TypeScript type guard for EmployeeProfilePayload.
 */
export function isEmployeeProfilePayload(raw: unknown): raw is EmployeeProfilePayload {
  return validateEmployeeProfilePayload(raw).isValid;
}

// ============================================================================
// 4. TICKET_LIST Runtime Validator
// ============================================================================

/**
 * Validates that an arbitrary payload matches the TicketListPayload contract.
 *
 * Rules:
 * - Must be a non-null object.
 * - Must contain a `tickets` array.
 * - Each ticket must have valid `ticket_id`, `title`, `priority`, and `status`.
 * - Optional metadata: `description`, `assigned_to`, `owner_id`, `category`, `created_at`, `updated_at`.
 * - If `events` are present on a ticket, each event must have `timestamp`, `type`, and `description`.
 * - Rejects malformed protected payloads safely without leaking sensitive values.
 */
export function validateTicketListPayload(raw: unknown): ValidationResult<TicketListPayload> {
  if (!isRecord(raw)) {
    return {
      isValid: false,
      error: 'Malformed ticket list payload: expected an object.',
    };
  }

  if (!isOptionalString(raw.title)) {
    return {
      isValid: false,
      error: 'Invalid ticket list payload: title must be a string.',
    };
  }

  if (raw.total_count !== undefined && raw.total_count !== null && typeof raw.total_count !== 'number') {
    return {
      isValid: false,
      error: 'Invalid ticket list payload: total_count must be a number.',
    };
  }

  if (!Array.isArray(raw.tickets)) {
    return {
      isValid: false,
      error: 'Invalid ticket list payload: tickets must be an array.',
    };
  }

  const normalizedTickets: TicketRecord[] = [];

  for (let i = 0; i < raw.tickets.length; i++) {
    const item = raw.tickets[i];
    if (!isRecord(item)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: expected an object.`,
      };
    }

    // ticket_id: number or non-empty string
    const isNumId = typeof item.ticket_id === 'number' && !isNaN(item.ticket_id);
    const isStrId = isNonEmptyString(item.ticket_id);
    if (!isNumId && !isStrId) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: ticket_id is required and must be a number or non-empty string.`,
      };
    }

    if (!isNonEmptyString(item.title)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: title is required and must be a non-empty string.`,
      };
    }

    if (!isNonEmptyString(item.priority)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: priority is required and must be a non-empty string.`,
      };
    }

    if (!isNonEmptyString(item.status)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: status is required and must be a non-empty string.`,
      };
    }

    if (!isOptionalString(item.description)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: description must be a string.`,
      };
    }

    if (!isOptionalString(item.assigned_to)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: assigned_to must be a string.`,
      };
    }

    if (!isOptionalString(item.owner_id)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: owner_id must be a string.`,
      };
    }

    if (!isOptionalString(item.category)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: category must be a string.`,
      };
    }

    if (!isOptionalString(item.created_at)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: created_at must be a string.`,
      };
    }

    if (!isOptionalString(item.updated_at)) {
      return {
        isValid: false,
        error: `Invalid ticket item at index ${i}: updated_at must be a string.`,
      };
    }

    // Optional event history array
    let normalizedEvents: TicketEvent[] | undefined = undefined;
    if (item.events !== undefined && item.events !== null) {
      if (!Array.isArray(item.events)) {
        return {
          isValid: false,
          error: `Invalid ticket item at index ${i}: events must be an array.`,
        };
      }

      normalizedEvents = [];
      for (let j = 0; j < item.events.length; j++) {
        const ev = item.events[j];
        if (!isRecord(ev)) {
          return {
            isValid: false,
            error: `Invalid event at ticket index ${i}, event ${j}: expected an object.`,
          };
        }
        if (!isNonEmptyString(ev.timestamp)) {
          return {
            isValid: false,
            error: `Invalid event at ticket index ${i}, event ${j}: timestamp is required.`,
          };
        }
        if (!isNonEmptyString(ev.type)) {
          return {
            isValid: false,
            error: `Invalid event at ticket index ${i}, event ${j}: type is required.`,
          };
        }
        if (!isNonEmptyString(ev.description)) {
          return {
            isValid: false,
            error: `Invalid event at ticket index ${i}, event ${j}: description is required.`,
          };
        }

        normalizedEvents.push({
          id: isNonEmptyString(ev.id) ? ev.id.trim() : undefined,
          timestamp: ev.timestamp.trim(),
          type: ev.type.trim(),
          description: ev.description.trim(),
          actor: isNonEmptyString(ev.actor) ? ev.actor.trim() : undefined,
          old_value: isNonEmptyString(ev.old_value) ? ev.old_value.trim() : undefined,
          new_value: isNonEmptyString(ev.new_value) ? ev.new_value.trim() : undefined,
        });
      }
    }

    normalizedTickets.push({
      ticket_id: typeof item.ticket_id === 'number' ? item.ticket_id : (item.ticket_id as string).trim(),
      title: item.title.trim(),
      priority: item.priority.trim(),
      status: item.status.trim(),
      description: isNonEmptyString(item.description) ? item.description.trim() : undefined,
      assigned_to: isNonEmptyString(item.assigned_to) ? item.assigned_to.trim() : undefined,
      owner_id: isNonEmptyString(item.owner_id) ? item.owner_id.trim() : undefined,
      category: isNonEmptyString(item.category) ? item.category.trim() : undefined,
      created_at: isNonEmptyString(item.created_at) ? item.created_at.trim() : undefined,
      updated_at: isNonEmptyString(item.updated_at) ? item.updated_at.trim() : undefined,
      events: normalizedEvents,
    });
  }

  const normalizedPayload: TicketListPayload = {
    title: isNonEmptyString(raw.title) ? raw.title.trim() : undefined,
    total_count: typeof raw.total_count === 'number' ? raw.total_count : normalizedTickets.length,
    tickets: normalizedTickets,
  };

  return {
    isValid: true,
    data: normalizedPayload,
  };
}

/**
 * Fast TypeScript type guard for TicketListPayload.
 */
export function isTicketListPayload(raw: unknown): raw is TicketListPayload {
  return validateTicketListPayload(raw).isValid;
}

// ============================================================================
// 5. TEAM_METRIC_CHART Runtime Validator
// ============================================================================

/**
 * Validates that an arbitrary payload matches the TeamMetricChartPayload contract.
 *
 * Rules:
 * - Must be a non-null object.
 * - `chart_type` is required and must be 'BAR' or 'PIE'.
 * - `data` must be an array of data points with `label` (string) and finite `count` (number).
 * - Optional metadata: `metric_name`, `scope_description`, `team_id`, `time_range`, `kpis`.
 * - Rejects malformed protected payloads safely without leaking sensitive values.
 */
export function validateTeamMetricChartPayload(
  raw: unknown
): ValidationResult<TeamMetricChartPayload> {
  if (!isRecord(raw)) {
    return {
      isValid: false,
      error: 'Malformed chart payload: expected an object.',
    };
  }

  // Validate chart_type
  const rawType = typeof raw.chart_type === 'string' ? raw.chart_type.toUpperCase().trim() : '';
  if (rawType !== 'BAR' && rawType !== 'PIE' && rawType !== 'LINE' && rawType !== 'AREA') {
    return {
      isValid: false,
      error: 'Invalid chart payload: chart_type is unsupported.',
    };
  }

  // Validate data array
  if (!Array.isArray(raw.data) || raw.data.length > 100) {
    return {
      isValid: false,
      error: 'Invalid chart payload: data must be an array of data points.',
    };
  }

  const normalizedData: MetricDataPoint[] = [];
  for (let i = 0; i < raw.data.length; i++) {
    const pt = raw.data[i];
    if (!isRecord(pt)) {
      return {
        isValid: false,
        error: `Invalid chart data point at index ${i}: expected an object.`,
      };
    }

    // Accept label or name
    const rawLabel = isNonEmptyString(pt.label) ? pt.label : isNonEmptyString(pt.name) ? pt.name : null;
    if (!rawLabel) {
      return {
        isValid: false,
        error: `Invalid chart data point at index ${i}: label/name must be a non-empty string.`,
      };
    }

    // Accept count or value
    const rawCount = typeof pt.count === 'number' ? pt.count : typeof pt.value === 'number' ? pt.value : NaN;
    if (isNaN(rawCount) || !isFinite(rawCount) || rawCount < 0) {
      return {
        isValid: false,
        error: `Invalid chart data point at index ${i}: count/value must be a valid finite number.`,
      };
    }

    if (!isOptionalString(pt.priority)) {
      return {
        isValid: false,
        error: `Invalid chart data point at index ${i}: priority must be a string.`,
      };
    }

    if (!isOptionalString(pt.color)) {
      return {
        isValid: false,
        error: `Invalid chart data point at index ${i}: color must be a string.`,
      };
    }

    const cleanLabel = rawLabel.trim();
    normalizedData.push({
      label: cleanLabel,
      name: cleanLabel,
      count: rawCount,
      value: rawCount,
      priority: isNonEmptyString(pt.priority) ? pt.priority.trim() : undefined,
      color: isNonEmptyString(pt.color) ? pt.color.trim() : undefined,
    });
  }

  // Optional title and metric_name
  const rawTitle = isNonEmptyString(raw.title)
    ? raw.title.trim()
    : isNonEmptyString(raw.metric_name)
    ? raw.metric_name.trim()
    : undefined;

  // Optional string fields
  if (!isOptionalString(raw.metric_name) && !isOptionalString(raw.title)) {
    return { isValid: false, error: 'Invalid chart payload: metric_name / title must be a string.' };
  }
  if (!isOptionalString(raw.category)) {
    return { isValid: false, error: 'Invalid chart payload: category must be a string.' };
  }
  if (!isOptionalString(raw.unit)) {
    return { isValid: false, error: 'Invalid chart payload: unit must be a string.' };
  }
  if (!isOptionalString(raw.scope_description)) {
    return { isValid: false, error: 'Invalid chart payload: scope_description must be a string.' };
  }
  if (!isOptionalString(raw.team_id)) {
    return { isValid: false, error: 'Invalid chart payload: team_id must be a string.' };
  }
  if (!isOptionalString(raw.time_range)) {
    return { isValid: false, error: 'Invalid chart payload: time_range must be a string.' };
  }

  // Optional KPIs validation
  let normalizedKpis: MetricKpiSummary | undefined = undefined;
  if (raw.kpis !== undefined && raw.kpis !== null) {
    if (!isRecord(raw.kpis)) {
      return { isValid: false, error: 'Invalid chart payload: kpis must be an object.' };
    }
    const k = raw.kpis;
    const isFiniteNumOrUndef = (val: unknown) =>
      val === undefined || (typeof val === 'number' && isFinite(val));
    if (!isFiniteNumOrUndef(k.total_tickets)) {
      return { isValid: false, error: 'Invalid KPI: total_tickets must be a finite number.' };
    }
    if (!isFiniteNumOrUndef(k.open_tickets)) {
      return { isValid: false, error: 'Invalid KPI: open_tickets must be a finite number.' };
    }
    if (!isFiniteNumOrUndef(k.in_progress_tickets)) {
      return { isValid: false, error: 'Invalid KPI: in_progress_tickets must be a finite number.' };
    }
    if (!isFiniteNumOrUndef(k.resolved_tickets)) {
      return { isValid: false, error: 'Invalid KPI: resolved_tickets must be a finite number.' };
    }
    if (!isFiniteNumOrUndef(k.closed_tickets)) {
      return { isValid: false, error: 'Invalid KPI: closed_tickets must be a finite number.' };
    }

    const rawSla =
      typeof k.sla_compliance_rate === 'number'
        ? k.sla_compliance_rate
        : typeof k.sla_compliance_pct === 'number'
        ? k.sla_compliance_pct
        : undefined;

    if (rawSla !== undefined && (!isFinite(rawSla) || isNaN(rawSla))) {
      return { isValid: false, error: 'Invalid KPI: sla_compliance_rate must be a finite number.' };
    }

    // avg_resolution_time can be string or object { value, unit }
    let normalizedAvgTime: string | { value: number; unit: string } | undefined = undefined;
    if (typeof k.avg_resolution_time === 'string' && isNonEmptyString(k.avg_resolution_time)) {
      normalizedAvgTime = k.avg_resolution_time.trim();
    } else if (
      isRecord(k.avg_resolution_time) &&
      typeof k.avg_resolution_time.value === 'number' &&
      isFinite(k.avg_resolution_time.value)
    ) {
      normalizedAvgTime = {
        value: k.avg_resolution_time.value,
        unit: String(k.avg_resolution_time.unit || 'hours'),
      };
    }

    normalizedKpis = {
      total_tickets: typeof k.total_tickets === 'number' ? k.total_tickets : undefined,
      open_tickets: typeof k.open_tickets === 'number' ? k.open_tickets : undefined,
      in_progress_tickets:
        typeof k.in_progress_tickets === 'number' ? k.in_progress_tickets : undefined,
      resolved_tickets:
        typeof k.resolved_tickets === 'number' ? k.resolved_tickets : undefined,
      closed_tickets: typeof k.closed_tickets === 'number' ? k.closed_tickets : undefined,
      sla_compliance_rate: rawSla,
      sla_compliance_pct: rawSla,
      avg_resolution_time: normalizedAvgTime,
    };
  }

  const normalized: TeamMetricChartPayload = {
    chart_type: rawType as 'BAR' | 'PIE',
    metric_name: rawTitle,
    title: rawTitle,
    category: isNonEmptyString(raw.category) ? raw.category.trim() : undefined,
    unit: isNonEmptyString(raw.unit) ? raw.unit.trim() : undefined,
    scope_description: isNonEmptyString(raw.scope_description)
      ? raw.scope_description.trim()
      : undefined,
    team_id: isNonEmptyString(raw.team_id) ? raw.team_id.trim() : undefined,
    time_range: isNonEmptyString(raw.time_range) ? raw.time_range.trim() : undefined,
    kpis: normalizedKpis,
    data: normalizedData,
  };

  return {
    isValid: true,
    data: normalized,
  };
}

/**
 * Fast TypeScript type guard for TeamMetricChartPayload.
 */
export function isTeamMetricChartPayload(raw: unknown): raw is TeamMetricChartPayload {
  return validateTeamMetricChartPayload(raw).isValid;
}

// ============================================================================
// 6. TRUST_TRACE_GRAPH Runtime Validator
// ============================================================================

const SUPPORTED_TRACE_STATUSES = new Set([
  'PASS',
  'FAIL',
  'PENDING',
  'SKIPPED',
  'ABORTED',
  'DENIED',
  'SUCCESS',
]);

/**
 * Validates that an arbitrary payload matches the TrustTraceGraphPayload contract.
 *
 * Rules:
 * - Must be a non-null object.
 * - `nodes` must be an array.
 * - Each node must have a unique non-empty string `id`, non-empty `label`, valid `status`.
 * - Rejects duplicate node IDs.
 * - If `edges` are provided, each edge must reference existing node IDs (no dangling edges).
 * - Sanitizes and normalizes optional strings (detail, timestamp, reason, policy_decision, receipt_id, handshake metadata).
 * - Safe fallback with user-friendly error message; never leaks raw JSON.
 */
export function validateTrustTraceGraphPayload(
  raw: unknown
): ValidationResult<TrustTraceGraphPayload> {
  if (!isRecord(raw)) {
    return {
      isValid: false,
      error: 'Malformed trust trace payload: expected an object.',
    };
  }

  // Validate nodes array
  if (!Array.isArray(raw.nodes)) {
    return {
      isValid: false,
      error: 'Invalid trust trace payload: nodes must be an array.',
    };
  }

  const nodeIds = new Set<string>();
  const normalizedNodes: TrustTraceNode[] = [];

  for (let i = 0; i < raw.nodes.length; i++) {
    const node = raw.nodes[i];
    if (!isRecord(node)) {
      return {
        isValid: false,
        error: `Invalid trace node at index ${i}: expected an object.`,
      };
    }

    if (!isNonEmptyString(node.id)) {
      return {
        isValid: false,
        error: `Invalid trace node at index ${i}: id must be a non-empty string.`,
      };
    }

    const trimmedId = node.id.trim();
    if (nodeIds.has(trimmedId)) {
      return {
        isValid: false,
        error: `Duplicate node ID "${trimmedId}" detected in trust trace payload.`,
      };
    }
    nodeIds.add(trimmedId);

    if (!isNonEmptyString(node.label)) {
      return {
        isValid: false,
        error: `Invalid trace node "${trimmedId}": label must be a non-empty string.`,
      };
    }

    if (!isNonEmptyString(node.status)) {
      return {
        isValid: false,
        error: `Invalid trace node "${trimmedId}": status must be a non-empty string.`,
      };
    }

    const upperStatus = node.status.trim().toUpperCase();
    if (!SUPPORTED_TRACE_STATUSES.has(upperStatus)) {
      return {
        isValid: false,
        error: `Invalid trace node "${trimmedId}": status "${node.status}" is not a recognized verdict.`,
      };
    }

    const stageStr = isNonEmptyString(node.stage) ? node.stage.trim() : 'pipeline';

    normalizedNodes.push({
      id: trimmedId,
      label: node.label.trim(),
      stage: stageStr,
      status: upperStatus,
      detail: isNonEmptyString(node.detail) ? node.detail.trim() : undefined,
      timestamp: isNonEmptyString(node.timestamp) ? node.timestamp.trim() : undefined,
      reason: isNonEmptyString(node.reason) ? node.reason.trim() : undefined,
      policy_decision: isNonEmptyString(node.policy_decision) ? node.policy_decision.trim() : undefined,
      receipt_id: isNonEmptyString(node.receipt_id) ? node.receipt_id.trim() : undefined,
      turn_id: isNonEmptyString(node.turn_id) ? node.turn_id.trim() : undefined,
      requesting_agent: isNonEmptyString(node.requesting_agent) ? node.requesting_agent.trim() : undefined,
      receiving_agent: isNonEmptyString(node.receiving_agent) ? node.receiving_agent.trim() : undefined,
      requested_capability: isNonEmptyString(node.requested_capability) ? node.requested_capability.trim() : undefined,
      handshake_outcome: isNonEmptyString(node.handshake_outcome) ? node.handshake_outcome.trim() : undefined,
    });
  }

  // Validate edges array if provided
  const normalizedEdges: TrustTraceEdge[] = [];
  if (raw.edges !== undefined && raw.edges !== null) {
    if (!Array.isArray(raw.edges)) {
      return {
        isValid: false,
        error: 'Invalid trust trace payload: edges must be an array when provided.',
      };
    }

    for (let i = 0; i < raw.edges.length; i++) {
      const edge = raw.edges[i];
      if (!isRecord(edge)) {
        return {
          isValid: false,
          error: `Invalid trace edge at index ${i}: expected an object.`,
        };
      }

      if (!isNonEmptyString(edge.source) || !isNonEmptyString(edge.target)) {
        return {
          isValid: false,
          error: `Invalid trace edge at index ${i}: source and target must be non-empty strings.`,
        };
      }

      const sourceId = edge.source.trim();
      const targetId = edge.target.trim();

      // Dangling reference check
      if (!nodeIds.has(sourceId)) {
        return {
          isValid: false,
          error: `Invalid trace edge: source node "${sourceId}" does not exist in the graph.`,
        };
      }
      if (!nodeIds.has(targetId)) {
        return {
          isValid: false,
          error: `Invalid trace edge: target node "${targetId}" does not exist in the graph.`,
        };
      }

      const edgeId = isNonEmptyString(edge.id) ? edge.id.trim() : `e-${sourceId}-${targetId}`;

      normalizedEdges.push({
        id: edgeId,
        source: sourceId,
        target: targetId,
        label: isNonEmptyString(edge.label) ? edge.label.trim() : undefined,
        animated: edge.animated === true,
      });
    }
  }

  // Root optional fields
  if (!isOptionalString(raw.trace_id)) {
    return { isValid: false, error: 'Invalid trust trace payload: trace_id must be a string.' };
  }
  if (!isOptionalString(raw.turn_id)) {
    return { isValid: false, error: 'Invalid trust trace payload: turn_id must be a string.' };
  }
  if (!isOptionalString(raw.session_id)) {
    return { isValid: false, error: 'Invalid trust trace payload: session_id must be a string.' };
  }
  if (!isOptionalString(raw.summary)) {
    return { isValid: false, error: 'Invalid trust trace payload: summary must be a string.' };
  }
  if (!isOptionalString(raw.final_verdict)) {
    return { isValid: false, error: 'Invalid trust trace payload: final_verdict must be a string.' };
  }

  const normalized: TrustTraceGraphPayload = {
    trace_id: isNonEmptyString(raw.trace_id) ? raw.trace_id.trim() : undefined,
    turn_id: isNonEmptyString(raw.turn_id) ? raw.turn_id.trim() : undefined,
    session_id: isNonEmptyString(raw.session_id) ? raw.session_id.trim() : undefined,
    summary: isNonEmptyString(raw.summary) ? raw.summary.trim() : undefined,
    final_verdict: isNonEmptyString(raw.final_verdict) ? raw.final_verdict.trim().toUpperCase() : undefined,
    nodes: normalizedNodes,
    edges: normalizedEdges.length > 0 ? normalizedEdges : undefined,
  };

  return {
    isValid: true,
    data: normalized,
  };
}

/**
 * Fast TypeScript type guard for TrustTraceGraphPayload.
 */
export function isTrustTraceGraphPayload(raw: unknown): raw is TrustTraceGraphPayload {
  return validateTrustTraceGraphPayload(raw).isValid;
}

// ============================================================================
// 7. READBACK_CONFIRMATION Runtime Validator
// ============================================================================

/**
 * Validates that an arbitrary payload matches the ReadbackConfirmationPayload contract.
 *
 * Rules:
 * - Must be a non-null object.
 * - Must contain either `draft` object with `action` and `params`, OR root-level `action` and `params`.
 * - `action` must be a non-empty string (e.g. "create_ticket").
 * - `params` must be an object (key/value map).
 * - Optional fields: `target`, `summary_readback`, `expires_in_seconds`, `confirmation_id`, `status`, `expires_at`.
 * - Rejects malformed payloads safely with sanitized errors and zero raw JSON dumps.
 */
export function validateReadbackConfirmationPayload(
  raw: unknown
): ValidationResult<ReadbackConfirmationPayload> {
  if (!isRecord(raw)) {
    return {
      isValid: false,
      error: 'Malformed readback confirmation payload: expected an object.',
    };
  }

  // Support either nested draft object or flat fields
  let candidateAction: unknown;
  let candidateTarget: unknown;
  let candidateParams: unknown;
  let candidateSummary: unknown;
  let candidateExpiresInSec: unknown;

  if (isRecord(raw.draft)) {
    candidateAction = raw.draft.action;
    candidateTarget = raw.draft.target;
    candidateParams = raw.draft.params;
    candidateSummary = raw.draft.summary_readback;
    candidateExpiresInSec = raw.draft.expires_in_seconds;
  } else {
    candidateAction = raw.action;
    candidateTarget = raw.target;
    candidateParams = raw.params;
    candidateSummary = raw.summary_readback;
    candidateExpiresInSec = raw.expires_in_seconds;
  }

  // Validate required action
  if (!isNonEmptyString(candidateAction)) {
    return {
      isValid: false,
      error: 'Invalid readback confirmation payload: action verb must be a non-empty string.',
    };
  }

  // Validate required params object
  if (!isRecord(candidateParams)) {
    return {
      isValid: false,
      error: 'Invalid readback confirmation payload: params must be a key-value object.',
    };
  }

  // Validate optional numeric expiry
  if (
    candidateExpiresInSec !== undefined &&
    candidateExpiresInSec !== null &&
    (typeof candidateExpiresInSec !== 'number' || !isFinite(candidateExpiresInSec) || isNaN(candidateExpiresInSec))
  ) {
    return {
      isValid: false,
      error: 'Invalid readback confirmation payload: expires_in_seconds must be a finite number.',
    };
  }

  // Validate optional string fields
  if (!isOptionalString(candidateTarget)) {
    return { isValid: false, error: 'Invalid readback confirmation payload: target must be a string.' };
  }
  if (!isOptionalString(candidateSummary)) {
    return { isValid: false, error: 'Invalid readback confirmation payload: summary_readback must be a string.' };
  }
  if (!isOptionalString(raw.confirmation_id)) {
    return { isValid: false, error: 'Invalid readback confirmation payload: confirmation_id must be a string.' };
  }
  if (!isOptionalString(raw.status)) {
    return { isValid: false, error: 'Invalid readback confirmation payload: status must be a string.' };
  }
  if (!isOptionalString(raw.expires_at)) {
    return { isValid: false, error: 'Invalid readback confirmation payload: expires_at must be a string.' };
  }

  const normalizedDraft: ProposedActionDraft = {
    action: candidateAction.trim(),
    target: isNonEmptyString(candidateTarget) ? candidateTarget.trim() : undefined,
    params: candidateParams,
    summary_readback: isNonEmptyString(candidateSummary) ? candidateSummary.trim() : undefined,
    expires_in_seconds: typeof candidateExpiresInSec === 'number' ? candidateExpiresInSec : undefined,
  };

  const normalized: ReadbackConfirmationPayload = {
    draft: normalizedDraft,
    action: normalizedDraft.action,
    target: normalizedDraft.target,
    params: normalizedDraft.params,
    summary_readback: normalizedDraft.summary_readback,
    expires_in_seconds: normalizedDraft.expires_in_seconds,
    requires_voice_confirmation: raw.requires_voice_confirmation === true,
    confirmation_id: isNonEmptyString(raw.confirmation_id) ? raw.confirmation_id.trim() : undefined,
    status: isNonEmptyString(raw.status) ? raw.status.trim().toUpperCase() : 'PENDING',
    expires_at: isNonEmptyString(raw.expires_at) ? raw.expires_at.trim() : undefined,
  };

  return {
    isValid: true,
    data: normalized,
  };
}

/**
 * Fast TypeScript type guard for ReadbackConfirmationPayload.
 */
export function isReadbackConfirmationPayload(raw: unknown): raw is ReadbackConfirmationPayload {
  return validateReadbackConfirmationPayload(raw).isValid;
}

// ============================================================================
// 8. ACTION_RECEIPT Runtime Validator
// ============================================================================

/**
 * Validates that an arbitrary payload matches the ActionReceiptPayload contract.
 *
 * Rules:
 * - Must be a non-null object.
 * - Must contain either `receipt` object with `tx_id`, `actor`, `timestamp`, OR flat equivalent fields.
 * - `tx_id` must be a non-empty string.
 * - `actor` must be a non-empty string.
 * - `timestamp` must be a non-empty string.
 * - Optional fields: `req_id`, `action`, `resource_id`, `status`, `grant_hash_prefix`, `summary`.
 * - Status defaults to 'COMMITTED' if absent.
 */
export function validateActionReceiptPayload(
  raw: unknown
): ValidationResult<ActionReceiptPayload> {
  if (!isRecord(raw)) {
    return {
      isValid: false,
      error: 'Malformed action receipt payload: expected an object.',
    };
  }

  // Support either nested receipt object or flat fields
  let candidateTxId: unknown;
  let candidateActor: unknown;
  let candidateTimestamp: unknown;
  let candidateReqId: unknown;
  let candidateAction: unknown;
  let candidateResourceId: unknown;
  let candidateStatus: unknown;
  let candidateGrantHashPrefix: unknown;
  let candidateSummary: unknown;

  if (isRecord(raw.receipt)) {
    candidateTxId = raw.receipt.tx_id;
    candidateActor = raw.receipt.actor;
    candidateTimestamp = raw.receipt.timestamp;
    candidateReqId = raw.receipt.req_id;
    candidateAction = raw.receipt.action;
    candidateResourceId = raw.receipt.resource_id;
    candidateStatus = raw.receipt.status;
    candidateGrantHashPrefix = raw.receipt.grant_hash_prefix;
  } else {
    candidateTxId = raw.tx_id;
    candidateActor = raw.actor;
    candidateTimestamp = raw.timestamp;
    candidateReqId = raw.req_id;
    candidateAction = raw.action;
    candidateResourceId = raw.resource_id;
    candidateStatus = raw.status;
    candidateGrantHashPrefix = raw.grant_hash_prefix;
    candidateSummary = raw.summary;
  }

  // Validate required tx_id
  if (!isNonEmptyString(candidateTxId)) {
    return {
      isValid: false,
      error: 'Invalid action receipt payload: tx_id must be a non-empty string.',
    };
  }

  // Validate required actor
  if (!isNonEmptyString(candidateActor)) {
    return {
      isValid: false,
      error: 'Invalid action receipt payload: actor must be a non-empty string.',
    };
  }

  // Validate required timestamp
  if (!isNonEmptyString(candidateTimestamp)) {
    return {
      isValid: false,
      error: 'Invalid action receipt payload: timestamp must be a non-empty string.',
    };
  }

  // Validate optional resource_id (string or number)
  if (
    candidateResourceId !== undefined &&
    candidateResourceId !== null &&
    typeof candidateResourceId !== 'string' &&
    typeof candidateResourceId !== 'number'
  ) {
    return {
      isValid: false,
      error: 'Invalid action receipt payload: resource_id must be a string or number.',
    };
  }

  // Validate optional strings
  if (!isOptionalString(candidateReqId)) {
    return { isValid: false, error: 'Invalid action receipt payload: req_id must be a string.' };
  }
  if (!isOptionalString(candidateAction)) {
    return { isValid: false, error: 'Invalid action receipt payload: action must be a string.' };
  }
  if (!isOptionalString(candidateStatus)) {
    return { isValid: false, error: 'Invalid action receipt payload: status must be a string.' };
  }
  if (!isOptionalString(candidateGrantHashPrefix)) {
    return { isValid: false, error: 'Invalid action receipt payload: grant_hash_prefix must be a string.' };
  }

  const normalizedReceipt: ExecutionReceipt = {
    tx_id: candidateTxId.trim(),
    actor: candidateActor.trim(),
    timestamp: candidateTimestamp.trim(),
    req_id: isNonEmptyString(candidateReqId) ? candidateReqId.trim() : undefined,
    action: isNonEmptyString(candidateAction) ? candidateAction.trim() : undefined,
    resource_id: candidateResourceId !== undefined && candidateResourceId !== null ? candidateResourceId : undefined,
    status: isNonEmptyString(candidateStatus) ? candidateStatus.trim().toUpperCase() : 'COMMITTED',
    grant_hash_prefix: isNonEmptyString(candidateGrantHashPrefix) ? candidateGrantHashPrefix.trim() : undefined,
  };

  const normalized: ActionReceiptPayload = {
    receipt: normalizedReceipt,
    tx_id: normalizedReceipt.tx_id,
    actor: normalizedReceipt.actor,
    timestamp: normalizedReceipt.timestamp,
    req_id: normalizedReceipt.req_id,
    action: normalizedReceipt.action,
    resource_id: normalizedReceipt.resource_id,
    status: normalizedReceipt.status,
    grant_hash_prefix: normalizedReceipt.grant_hash_prefix,
    summary: isNonEmptyString(candidateSummary) ? candidateSummary.trim() : undefined,
  };

  return {
    isValid: true,
    data: normalized,
  };
}

/**
 * Fast TypeScript type guard for ActionReceiptPayload.
 */
export function isActionReceiptPayload(raw: unknown): raw is ActionReceiptPayload {
  return validateActionReceiptPayload(raw).isValid;
}



