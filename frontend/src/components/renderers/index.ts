/**
 * IntentLock — Result Renderers Barrel & Registry Bootstrap
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Bootstraps the custom result card renderers through Stage 7:
 * - Registers PUBLIC_FAQ -> PublicFaqCard (Stage 1)
 * - Registers DENIAL_BANNER -> DenialBanner (Stage 1)
 * - Registers EMPLOYEE_PROFILE -> EmployeeProfileCard (Stage 3)
 * - Registers TICKET_LIST -> TicketListCard (Stage 4)
 * - Registers TEAM_METRIC_CHART -> TeamMetricChartCard (Stage 5)
 * - Registers TRUST_TRACE_GRAPH -> TrustTraceGraphCard (Stage 6)
 * - Registers READBACK_CONFIRMATION -> ReadbackConfirmationCard (Stage 7)
 * - Registers ACTION_RECEIPT -> ActionReceiptCard (Stage 7)
 */

import { registerResultRenderer } from '../workspace/resultRegistry';
import { PublicFaqCard } from './PublicFaqCard';
import { DenialBanner } from './DenialBanner';
import { EmployeeProfileCard } from './EmployeeProfileCard';
import { TicketListCard } from './TicketListCard';
import { TeamMetricChartCard } from './TeamMetricChartCard';
import { TrustTraceGraphCard } from './TrustTraceGraphCard';
import { ReadbackConfirmationCard } from './ReadbackConfirmationCard';
import { ActionReceiptCard } from './ActionReceiptCard';

// Bootstrap registration for custom result card renderers
registerResultRenderer('PUBLIC_FAQ', PublicFaqCard);
registerResultRenderer('DENIAL_BANNER', DenialBanner);
registerResultRenderer('EMPLOYEE_PROFILE', EmployeeProfileCard);
registerResultRenderer('TICKET_LIST', TicketListCard);
registerResultRenderer('TEAM_METRIC_CHART', TeamMetricChartCard);
registerResultRenderer('TRUST_TRACE_GRAPH', TrustTraceGraphCard);
registerResultRenderer('READBACK_CONFIRMATION', ReadbackConfirmationCard);
registerResultRenderer('ACTION_RECEIPT', ActionReceiptCard);

export { PublicFaqCard } from './PublicFaqCard';
export { DenialBanner } from './DenialBanner';
export { EmployeeProfileCard } from './EmployeeProfileCard';
export { TicketListCard } from './TicketListCard';
export { TeamMetricChartCard } from './TeamMetricChartCard';
export { TrustTraceGraphCard } from './TrustTraceGraphCard';
export { TrustTraceNode } from './TrustTraceNode';
export { TrustTraceDetails } from './TrustTraceDetails';
export { ReadbackConfirmationCard } from './ReadbackConfirmationCard';
export { ActionReceiptCard } from './ActionReceiptCard';
export { MetricSummaryCards } from './MetricSummaryCards';
export { MetricBarChart } from './MetricBarChart';
export { MetricPieChart } from './MetricPieChart';
export { TicketDetails, getPriorityBadgeClass, getStatusBadgeClass } from './TicketDetails';
export type { TicketDetailsProps } from './TicketDetails';
export { TicketTimeline } from './TicketTimeline';
export type { TicketTimelineProps } from './TicketTimeline';
export { StreamingText } from './StreamingText';
export type { StreamingTextProps } from './StreamingText';
export {
  validatePublicFaqPayload,
  validateDenialBannerPayload,
  validateEmployeeProfilePayload,
  validateTicketListPayload,
  validateTeamMetricChartPayload,
  validateTrustTraceGraphPayload,
  validateReadbackConfirmationPayload,
  validateActionReceiptPayload,
  isPublicFaqPayload,
  isDenialBannerPayload,
  isEmployeeProfilePayload,
  isTicketListPayload,
  isTeamMetricChartPayload,
  isTrustTraceGraphPayload,
  isReadbackConfirmationPayload,
  isActionReceiptPayload,
} from './validation';
export * from './fixtures';
export * from './streamingFixtures';
