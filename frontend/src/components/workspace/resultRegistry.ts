import React from 'react';
import type { GenericResultBlock, ResultBlockType, SelectedEntityContext } from '../../types';

export interface ResultRendererProps<T = Record<string, unknown>> {
  block: GenericResultBlock & { payload: T };
  onAction?: (actionVerb: string, parameters: Record<string, unknown>) => void;
  selectedEntity?: SelectedEntityContext | null;
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
 * Check if a custom renderer is registered for a specific ResultBlockType.
 */
export function hasResultRenderer(type: string): boolean {
  return Boolean(RENDERER_REGISTRY[type as ResultBlockType]);
}

/**
 * Get the registered custom renderer for a specific ResultBlockType.
 */
export function getResultRenderer(type: string): CustomRendererComponent | undefined {
  return RENDERER_REGISTRY[type as ResultBlockType];
}
