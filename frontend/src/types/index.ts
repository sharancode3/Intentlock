/**
 * IntentLock — Frontend Foundation Contracts & Seams
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 * 
 * IMPORTANT ARCHITECTURAL INVARIANT:
 * The frontend UI is an untrusted presentation layer. It NEVER computes
 * authorization, NEVER fabricates verification checks, and NEVER alters server session states.
 * 
 * Every verified identity, role, ticket row, biometric verdict, action grant,
 * and trust receipt MUST originate strictly from the trusted FastAPI backend.
 */

// ============================================================================
// 1. Session & Actor Display Types
// ============================================================================

/**
 * Status of the kiosk session.
 * 
 * SECURITY INVARIANT:
 * 'VERIFIED' is ONLY set when the backend returns a validated session token with
 * dual DetectifAI checks ('PASS' + 'MATCH'). Stating a name or selecting a persona
 * NEVER transitions the session to 'VERIFIED'.
 */
export type SessionState = 'ANONYMOUS' | 'VERIFYING' | 'VERIFIED' | 'EXPIRED';

export interface VerifiedActorSummary {
  /** Server-authenticated employee ID, e.g. "EMP-1001" */
  employeeId: string;
  /** Display name from authoritative database, e.g. "Charlie Davis" */
  fullName: string;
  /** Enforced role: 'employee' | 'manager' | 'helpdesk' | 'executive' */
  role: 'employee' | 'manager' | 'helpdesk' | 'executive';
  /** Assigned department or team ID, e.g. "team_eng_a" */
  teamId?: string;
  /** Remaining session validity in seconds (sliding 90s window) */
  expiresInSeconds: number;
}

export interface SessionInfo {
  state: SessionState;
  /** Present ONLY when state === 'VERIFIED' */
  actor?: VerifiedActorSummary;
  /** Ingress session token issued by server (sess_<uuid4>), null when anonymous */
  sessionId: string | null;
}

// ============================================================================
// 2. UI Turn & Recording Lifecycle States
// ============================================================================

/**
 * Visual lifecycle state for the current conversational turn.
 * These are purely presentation states; they do NOT represent locally verified security claims.
 */
export type TurnStatusType =
  | 'idle'
  | 'listening'
  | 'silence'
  | 'transcribing'
  | 'reasoning'
  | 'verifying'
  | 'clarification'
  | 'result_ready'
  | 'denial'
  | 'error';

export interface TurnStatusNotice {
  type: TurnStatusType;
  /** Optional human-readable guidance or coaching message */
  message?: string;
  /** Time remaining before turn or session expires */
  countdownSeconds?: number;
}

// ============================================================================
// 3. Conversation & Message Types
// ============================================================================

export type MessageSender = 'user' | 'assistant' | 'system';

/**
 * Message lifecycle status for streaming and asynchronous dispatch.
 */
export type MessageStatus = 'pending' | 'streaming' | 'complete' | 'error';

export interface ConversationMessage {
  id: string;
  sender: MessageSender;
  text: string;
  timestamp: string; // ISO 8601 string or formatted time
  turnId?: string;
  /** Optional reference to an attached contextual result block */
  resultBlockId?: string;
  /** Optional rich contextual result block rendered inline in the conversation stream */
  resultBlock?: GenericResultBlock;
  /** Whether this message is currently receiving incremental text chunks */
  isStreaming?: boolean;
  /** Optional lifecycle status of the message */
  status?: MessageStatus;
  /** Optional error message if generation failed */
  errorMessage?: string;
}

// ============================================================================
// 4. Contextual Result Block Types (Future Renderers Interface)
// ============================================================================

/**
 * Discriminator enum matching the card types specified across PRD & UI_UX.md.
 * Teammate B will plug in concrete card renderers for each of these in ResultRendererRegistry.
 */
export type ResultBlockType =
  | 'PUBLIC_FAQ'
  | 'EMPLOYEE_PROFILE'
  | 'TICKET_LIST'
  | 'TEAM_METRIC_CHART'
  | 'READBACK_CONFIRMATION'
  | 'DENIAL_BANNER'
  | 'ACTION_RECEIPT'
  | 'TRUST_TRACE_GRAPH'
  | 'PROTECTED_DOCUMENT_PREVIEW';

/**
 * Base envelope for any contextual result block returned by the server.
 * All properties originate strictly from the backend.
 */
export interface BaseResultBlock {
  id: string;
  type: ResultBlockType;
  title: string;
  timestamp: string;
  /** Whether the data inside this block requires an active verified session */
  isSensitive: boolean;
}

/**
 * Generic container allowing teammate to provide rich typed payloads.
 * If an unrecognized block type is encountered, ResultHost safely renders
 * a clean fallback notice without dumping raw JSON or sensitive fields.
 */
export interface GenericResultBlock extends BaseResultBlock {
  payload: Record<string, unknown>;
}

// ============================================================================
// 5. Settings & UI Preferences
// ============================================================================

export type ThemeMode = 'light' | 'dark' | 'system';
export type TextSize = 'sm' | 'md' | 'lg';
export type ViewMode = 'split' | 'feed';

export interface WorkspaceSettings {
  theme: ThemeMode;
  textSize: TextSize;
  reducedMotion: boolean;
  /** Voice audio playback enabled preference (purely UI audio preference; does NOT dictate backend TTS) */
  voicePlaybackEnabled: boolean;
  /** Playback volume from 0.0 to 1.0 */
  voiceVolume: number;
  /** Workspace layout mode: 'split' (dual-pane) or 'feed' (unified chat stream) */
  viewMode: ViewMode;
}

// ============================================================================
// 6. Callback Seams & Component Props
// ============================================================================

export interface WorkspaceCallbacks {
  /** Called when the browser microphone captures a complete audio turn (WAV Blob) */
  onAudioCaptured: (audioBlob: Blob, durationMs: number) => void;
  /** Called when user explicitly clicks "End Session" or session expires */
  onEndSession: () => void;
  /** Called when settings are updated */
  onUpdateSettings: (newSettings: Partial<WorkspaceSettings>) => void;
  /** Future hook: called when a user interacts with a result action (e.g. readback confirm) */
  onResultAction?: (actionVerb: string, parameters: Record<string, unknown>) => void;
}

// ============================================================================
// 7. Typed Result Payloads (Stage 1 Contracts)
// ============================================================================
export * from './payloads';
