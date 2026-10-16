/**
 * IntentLock — Test Fixtures for Streaming Message Rendering
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Controlled fixtures for verifying incremental assistant text rendering,
 * partial state display, and finalized states without requiring live backend.
 */

import type { ConversationMessage } from '../../types';

export const streamingMessageInitialFixture: ConversationMessage = {
  id: 'fixture-stream-initial',
  sender: 'assistant',
  text: '',
  timestamp: '11:00 AM',
  isStreaming: true,
  status: 'streaming',
};

export const streamingMessagePartialFixture: ConversationMessage = {
  id: 'fixture-stream-partial',
  sender: 'assistant',
  text: 'Hardware requests for standard peripherals do not require manager approval.',
  timestamp: '11:01 AM',
  isStreaming: true,
  status: 'streaming',
};

export const streamingMessageFinalFixture: ConversationMessage = {
  id: 'fixture-stream-final',
  sender: 'assistant',
  text: 'Hardware requests for standard peripherals do not require manager approval. High-tier items such as development laptops or specialized monitors require biometric identity verification.',
  timestamp: '11:02 AM',
  isStreaming: false,
  status: 'complete',
};

export const streamingMessageErrorFixture: ConversationMessage = {
  id: 'fixture-stream-error',
  sender: 'assistant',
  text: 'Hardware policy information could not be retrieved completely.',
  timestamp: '11:03 AM',
  isStreaming: false,
  status: 'error',
  errorMessage: 'Inference response stream was interrupted.',
};
