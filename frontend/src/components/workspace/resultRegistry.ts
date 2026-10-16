import React from 'react';
import type { GenericResultBlock, ResultBlockType } from '../../types';

export interface ResultRendererProps<T = Record<string, unknown>> {
  block: GenericResultBlock & { payload: T };
  onAction?: (actionVerb: string, parameters: Record<string, unknown>) => void;
}

export type CustomRendererComponent = React.ComponentType<ResultRendererProps>;

const RENDERER_REGISTRY: Partial<Record<ResultBlockType, CustomRendererComponent>> = {};

/**
 * Register a custom renderer for a specific ResultBlockType.
 * Teammates can call this to mount their cards:
 * registerResultRenderer('PUBLIC_FAQ', PublicFaqCard);
 */
export function registerResultRenderer(type: ResultBlockType, component: CustomRendererComponent): void {
  RENDERER_REGISTRY[type] = component;
}

/**
 * Get the registered custom renderer for a specific ResultBlockType.
 */
export function getResultRenderer(type: ResultBlockType): CustomRendererComponent | undefined {
  return RENDERER_REGISTRY[type];
}
