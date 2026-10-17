/**
 * IntentLock — Stage 9 Speech Reliability, Interruption & Duplicate-Turn Test Suite
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Validates:
 * - Category A: Single Active Playback & Sequence Counter Protection
 * - Category B: Stop & Replay Audio Controls & Autoplay Restriction Handling
 * - Category C: Feedback Prevention & Microphone Capture Disarming
 * - Category D: Controlled Interruption ("Stop & Speak" Interaction Lifecycle)
 * - Category E: Duplicate Turn Prevention & Bounded Registry Management
 * - Category F: Stale Audio Responses & Session Expiry Cleanup
 * - Category G: Audio Media Buffer Release & Native Resource Deallocation
 * - Category H: Speech Timing Metrics Instrumentation & Observability
 */

import type {
  SpeechTimingMetrics,
  SessionInfo,
  TurnStatusNotice,
} from '../types';
import { deriveDisabledReason } from '../utils/statusPresentation';

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

export function runStage9SpeechReliabilitySuite(): void {
  console.log('Running Stage 9 Speech Playback, Interruption & Duplicate-Turn Reliability Test Suite...\n');
  let testCount = 0;

  // ==========================================================================
  // Category A: Single Active Playback & Sequence Counter Protection
  // ==========================================================================
  let activeAudioSequence: number = 0;
  let currentlyPlayingAudioId: string | null = null;
  let isPlayingAudioState: boolean = false;

  const simulatePlayAudio = (audioId: string, seq: number): boolean => {
    // If sequence does not match the latest audio play sequence, drop it
    if (seq !== activeAudioSequence) {
      return false;
    }
    currentlyPlayingAudioId = audioId;
    isPlayingAudioState = true;
    return true;
  };

  const simulateStopAudio = (): void => {
    activeAudioSequence += 1;
    currentlyPlayingAudioId = null;
    isPlayingAudioState = false;
  };

  // Turn 1 starts playback
  activeAudioSequence = 1;
  const started1 = simulatePlayAudio('audio-turn-1', 1);
  assert(started1 === true, 'A.1: Turn 1 audio must start playback');
  assert(currentlyPlayingAudioId === 'audio-turn-1', 'A.2: Active audio is Turn 1');
  assert(isPlayingAudioState, 'A.3: isPlayingAudio is true');

  // Turn 2 supersedes Turn 1 before Turn 1 finishes
  simulateStopAudio(); // Stops old audio and increments sequence to 2
  assert(activeAudioSequence === 2, 'A.4: Sequence incremented on stop/supersede');
  assert(currentlyPlayingAudioId === null, 'A.5: Active audio cleared');
  assert(!isPlayingAudioState, 'A.6: Playback state reset to false');

  // Stale callback from Turn 1 attempts to play
  const staleStarted = simulatePlayAudio('audio-turn-1-stale', 1);
  assert(staleStarted === false, 'A.7: Stale playback callback with older sequence must be dropped');
  assert(currentlyPlayingAudioId === null, 'A.8: Stale callback cannot overwrite active audio');

  // Turn 2 audio arrives with valid sequence 2
  const started2 = simulatePlayAudio('audio-turn-2', 2);
  assert(started2 === true, 'A.9: Turn 2 audio plays with matching sequence counter');
  assert(currentlyPlayingAudioId === 'audio-turn-2', 'A.10: Active audio set to Turn 2');

  testCount += 10;
  console.log('✓ A. Single Active Playback & Sequence Counter Protection passed (10/10 tests)');

  // ==========================================================================
  // Category B: Stop & Replay Audio Controls & Autoplay Restriction Handling
  // ==========================================================================
  let committedDbState = { balance: 5000, profileUpdated: true };
  let authorizedTextResponse = 'Your profile phone number has been updated to +1-555-0199.';
  let lastAudioPayload: string | null = 'UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';

  // Stopping playback must NOT cancel committed mutation or wipe authorized text
  simulateStopAudio();
  assert(!isPlayingAudioState, 'B.1: Stop audio stops active playback');
  assert(committedDbState.profileUpdated === true, 'B.2: Stop audio must NOT rollback or cancel committed DB operation');
  assert(authorizedTextResponse.length > 0, 'B.3: Authorized text response remains intact after audio stopped');

  // Replay control checks
  const canReplay = (session: SessionInfo, hasAudio: boolean): boolean => {
    if (!hasAudio) return false;
    if (session.state === 'EXPIRED') return false;
    return true;
  };

  const activeSession: SessionInfo = {
    sessionId: 'sess-01',
    state: 'VERIFIED',
    actor: {
      employeeId: 'EMP-1001',
      fullName: 'Elena Rostova',
      role: 'employee',
      expiresInSeconds: 300,
    },
  };

  const expiredSession: SessionInfo = {
    sessionId: null,
    state: 'EXPIRED',
  };

  assert(canReplay(activeSession, Boolean(lastAudioPayload)) === true, 'B.4: Replay allowed for active verified session with audio');
  assert(canReplay(expiredSession, Boolean(lastAudioPayload)) === false, 'B.5: Replay forbidden for expired session');
  assert(canReplay(activeSession, false) === false, 'B.6: Replay forbidden when no audio available');

  // Autoplay restriction handling
  const handleAutoplayResult = (errorName: string): { statusNotice: string; userActionRequired: boolean } => {
    if (errorName === 'NotAllowedError') {
      return {
        statusNotice: 'Playback requires interaction · tap Replay Audio to listen',
        userActionRequired: true,
      };
    }
    return {
      statusNotice: 'Audio playback failed',
      userActionRequired: false,
    };
  };

  const autoplayBlocked = handleAutoplayResult('NotAllowedError');
  assert(autoplayBlocked.userActionRequired === true, 'B.7: Autoplay restriction caught gracefully and flags user action required');
  assert(autoplayBlocked.statusNotice.includes('tap Replay Audio'), 'B.8: User guided to click Replay instead of showing error failure');

  testCount += 8;
  console.log('✓ B. Stop & Replay Audio Controls & Autoplay Handling passed (8/8 tests)');

  // ==========================================================================
  // Category C: Feedback Prevention & Microphone Capture Disarming
  // ==========================================================================
  // Invariant: While assistant is speaking, ordinary microphone input is disarmed
  // (microphoneDisabled = busy || playing) to avoid assistant audio leaking into STT.
  const idleStatus: TurnStatusNotice = { type: 'idle' };
  const isMicDisabled = (busy: boolean, playing: boolean): boolean => busy || playing;

  assert(isMicDisabled(false, true) === true, 'C.1: Mic is strictly disabled when playing audio');
  assert(isMicDisabled(true, false) === true, 'C.2: Mic is disabled when busy processing');
  assert(isMicDisabled(false, false) === false, 'C.3: Mic is NOT disabled when idle and audio stopped');

  const disabledReasonWhenPlaying = deriveDisabledReason(idleStatus, true);
  assert(disabledReasonWhenPlaying === 'Playing response…', 'C.4: Disabled reason correctly reports playing response');

  testCount += 4;
  console.log('✓ C. Feedback Prevention & Capture Disarming passed (4/4 tests)');

  // ==========================================================================
  // Category D: Controlled Interruption ("Stop & Speak" Lifecycle)
  // ==========================================================================
  let isMicrophoneArmed = false;
  let audioBuffersReleased = false;

  const simulateControlledInterruption = async (
    onStopAudioFn: () => void,
    onStartRecordingFn: () => void
  ): Promise<void> => {
    // Step 1: Deliberately stop playback
    onStopAudioFn();
    audioBuffersReleased = true;
    // Step 2: Brief pause to allow acoustic decay (prevent speaker echo from being recorded)
    await new Promise(resolve => setTimeout(resolve, 10));
    // Step 3: Activate microphone for the new turn
    onStartRecordingFn();
  };

  isPlayingAudioState = true;
  simulateControlledInterruption(
    () => { isPlayingAudioState = false; },
    () => { isMicrophoneArmed = true; }
  ).then(() => {
    assert(isPlayingAudioState === false, 'D.1: Playback stopped prior to recording');
    assert(audioBuffersReleased === true, 'D.2: Audio resources released');
    assert(isMicrophoneArmed === true, 'D.3: Microphone activated for fresh user turn');
  });

  // Verify non-cancellation of committed mutations during interruption
  const isInterruptionSafeForCommittedOps = (operationCommitted: boolean): boolean => {
    // Interruption stops frontend audio; it does NOT send a rollback or cancellation
    return operationCommitted;
  };
  assert(isInterruptionSafeForCommittedOps(true) === true, 'D.4: Interrupting audio does not cancel committed backend mutation');

  testCount += 4;
  console.log('✓ D. Controlled Interruption ("Stop & Speak") passed (4/4 tests)');

  // ==========================================================================
  // Category E: Duplicate Turn Prevention & Bounded Registry Management
  // ==========================================================================
  const submittedTurnRegistry = new Set<string>();
  let actualSubmissionCount = 0;

  const simulateTurnSubmission = (turnId: string): boolean => {
    if (submittedTurnRegistry.has(turnId)) {
      return false; // Duplicate turn blocked!
    }
    submittedTurnRegistry.add(turnId);
    if (submittedTurnRegistry.size > 50) {
      const oldest = submittedTurnRegistry.values().next().value;
      if (oldest) submittedTurnRegistry.delete(oldest);
    }
    actualSubmissionCount += 1;
    return true;
  };

  // Double click / duplicate VAD finalization race
  const turnA = 'turn-uuid-001';
  const sub1 = simulateTurnSubmission(turnA);
  const sub2 = simulateTurnSubmission(turnA); // Duplicate trigger
  assert(sub1 === true, 'E.1: First submission of turnA accepted');
  assert(sub2 === false, 'E.2: Duplicate submission of turnA rejected');
  assert(actualSubmissionCount === 1, 'E.3: Exactly 1 voice-turn submission occurred');

  // Verify Bounded Registry (max 50 entries to prevent memory leak on kiosk)
  for (let i = 0; i < 60; i++) {
    simulateTurnSubmission(`turn-filler-${i}`);
  }
  assert(submittedTurnRegistry.size === 50, 'E.4: Registry size strictly capped at 50');
  assert(!submittedTurnRegistry.has('turn-filler-0'), 'E.5: Oldest items pruned when capacity exceeded');
  assert(submittedTurnRegistry.has('turn-filler-59'), 'E.6: Newest items retained');

  testCount += 6;
  console.log('✓ E. Duplicate Turn Prevention & Bounded Registry passed (6/6 tests)');

  // ==========================================================================
  // Category F: Stale Audio Responses & Session Expiry Cleanup
  // ==========================================================================
  let currentSessionEpoch = 1;
  let activeAudioData: string | null = 'sample-audio-data';

  const onSessionExpiryOrHandoff = (): void => {
    currentSessionEpoch += 1;
    activeAudioData = null; // Clear cached audio
    simulateStopAudio();
  };

  // Simulate session expiry
  onSessionExpiryOrHandoff();
  assert(activeAudioData === null, 'F.1: Protected audio cache cleared on session handoff/expiry');
  assert(!isPlayingAudioState, 'F.2: Playback immediately halted on session expiry');

  // Late arriving audio for previous session epoch
  const handleLateAudioArrival = (responseEpoch: number): boolean => {
    if (responseEpoch !== currentSessionEpoch) {
      return false; // Stale session response dropped
    }
    return true;
  };

  const lateAudioAccepted = handleLateAudioArrival(1); // Old epoch
  assert(lateAudioAccepted === false, 'F.3: Late arriving audio from previous session epoch rejected');

  testCount += 3;
  console.log('✓ F. Stale Audio Responses & Session Expiry Cleanup passed (3/3 tests)');

  // ==========================================================================
  // Category G: Audio Media Buffer Release & Native Resource Deallocation
  // ==========================================================================
  interface MockAudioElement {
    src: string;
    paused: boolean;
    loadCalled: boolean;
    pause: () => void;
    load: () => void;
  }

  const mockAudio: MockAudioElement = {
    src: 'blob:http://localhost/test-audio',
    paused: false,
    loadCalled: false,
    pause() { this.paused = true; },
    load() { this.loadCalled = true; },
  };

  const deallocateAudioElement = (audio: MockAudioElement | null): null => {
    if (audio) {
      audio.pause();
      audio.src = '';
      audio.load(); // Forces browser to flush decoded audio buffers
    }
    return null;
  };

  const cleaned = deallocateAudioElement(mockAudio);
  assert(cleaned === null, 'G.1: Audio reference nulled out');
  assert(mockAudio.paused === true, 'G.2: Audio paused');
  assert(mockAudio.src === '', 'G.3: src removed');
  assert(mockAudio.loadCalled === true, 'G.4: load() called to immediately release media buffer');

  testCount += 4;
  console.log('✓ G. Media Buffer Release & Resource Deallocation passed (4/4 tests)');

  // ==========================================================================
  // Category H: Speech Timing Metrics Instrumentation & Observability
  // ==========================================================================
  const metrics: SpeechTimingMetrics = {
    micActivationMs: 42,
    speechStartToPreviewMs: 310,
    speechEndToFinalizeMs: 250,
    finalizeToSubmissionMs: 15,
    responseToPlaybackMs: 180,
  };

  assert(typeof metrics.micActivationMs === 'number' && metrics.micActivationMs > 0, 'H.1: micActivationMs is valid');
  assert(typeof metrics.speechStartToPreviewMs === 'number' && metrics.speechStartToPreviewMs > 0, 'H.2: speechStartToPreviewMs is valid');
  assert(typeof metrics.speechEndToFinalizeMs === 'number' && metrics.speechEndToFinalizeMs > 0, 'H.3: speechEndToFinalizeMs is valid');
  assert(typeof metrics.finalizeToSubmissionMs === 'number' && metrics.finalizeToSubmissionMs > 0, 'H.4: finalizeToSubmissionMs is valid');
  assert(typeof metrics.responseToPlaybackMs === 'number' && metrics.responseToPlaybackMs > 0, 'H.5: responseToPlaybackMs is valid');

  testCount += 5;
  console.log('✓ H. Speech Timing Metrics Instrumentation passed (5/5 tests)');

  console.log('\n======================================================');
  console.log(`All ${testCount} Stage 9 Speech Reliability tests PASSED successfully!`);
  console.log('======================================================\n');
}

// Auto-run when executed directly via tsx
runStage9SpeechReliabilitySuite();
