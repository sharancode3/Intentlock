/**
 * IntentLock — Result Renderers Barrel & Registry Bootstrap
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Bootstraps the custom result card renderers for Stage 1:
 * - Registers PUBLIC_FAQ -> PublicFaqCard
 * - Registers DENIAL_BANNER -> DenialBanner
 *
 * INVARIANT:
 * Unimplemented result types (EMPLOYEE_PROFILE, TICKET_LIST, TEAM_METRIC_CHART, etc.)
 * are deliberately NOT registered here so they retain the clean fallback UI
 * implemented in ResultHost.tsx and ConversationPanel.tsx.
 */

import { registerResultRenderer } from '../workspace/resultRegistry';
import { PublicFaqCard } from './PublicFaqCard';
import { DenialBanner } from './DenialBanner';

// Bootstrap registration strictly for the two Stage 1 renderers
registerResultRenderer('PUBLIC_FAQ', PublicFaqCard);
registerResultRenderer('DENIAL_BANNER', DenialBanner);

export { PublicFaqCard } from './PublicFaqCard';
export { DenialBanner } from './DenialBanner';
export { StreamingText } from './StreamingText';
export type { StreamingTextProps } from './StreamingText';
export {
  validatePublicFaqPayload,
  validateDenialBannerPayload,
  isPublicFaqPayload,
  isDenialBannerPayload,
} from './validation';
export * from './fixtures';
export * from './streamingFixtures';
