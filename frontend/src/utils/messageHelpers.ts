/**
 * IntentLock — Message Streaming & Update Utilities
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 *
 * Pure, immutable helper functions for incremental message updates,
 * streaming token concatenation, and message lifecycle state transitions.
 *
 * INVARIANTS:
 * - Preserves stable message IDs.
 * - Does not mutate input arrays or objects.
 * - Does not fabricate credentials or backend claims.
 */

import type { ConversationMessage, MessageSender, GenericResultBlock } from '../types';

/**
 * Creates a new streaming assistant message initialized with empty or partial text.
 */
export function createStreamingMessage(
  id: string,
  sender: MessageSender = 'assistant',
  initialText = '',
  turnId?: string,
  timestamp?: string
): ConversationMessage {
  return {
    id,
    sender,
    text: initialText,
    timestamp:
      timestamp ||
      new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    turnId,
    isStreaming: true,
    status: 'streaming',
  };
}

/**
 * Immutably appends an incremental text chunk to an existing message by ID.
 * Returns the updated messages array, preserving order and references for unchanged items.
 */
export function appendMessageChunk(
  messages: readonly ConversationMessage[],
  messageId: string,
  chunk: string
): ConversationMessage[] {
  return messages.map((msg) => {
    if (msg.id !== messageId) {
      return msg;
    }
    return {
      ...msg,
      text: msg.text + chunk,
      isStreaming: true,
      status: 'streaming',
    };
  });
}

/**
 * Immutably marks a message as finalized, updating its final text and optional attached result block.
 */
export function finalizeMessage(
  messages: readonly ConversationMessage[],
  messageId: string,
  finalText?: string,
  resultBlock?: GenericResultBlock
): ConversationMessage[] {
  return messages.map((msg) => {
    if (msg.id !== messageId) {
      return msg;
    }
    return {
      ...msg,
      text: finalText !== undefined ? finalText : msg.text,
      isStreaming: false,
      status: 'complete',
      resultBlock: resultBlock !== undefined ? resultBlock : msg.resultBlock,
    };
  });
}

/**
 * Immutably marks a message with an error state, terminating streaming.
 */
export function setMessageError(
  messages: readonly ConversationMessage[],
  messageId: string,
  errorMessage: string
): ConversationMessage[] {
  return messages.map((msg) => {
    if (msg.id !== messageId) {
      return msg;
    }
    return {
      ...msg,
      isStreaming: false,
      status: 'error',
      errorMessage,
    };
  });
}
