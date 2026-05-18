/**
 * DeepFlow Frontend Configuration Defaults
 * All polling intervals configurable via config.json
 * Vite env vars as override: VITE_POLLING_*
 */

/// <reference types="vite/client" />

export const DEFAULT_POLLING = {
  health_ms: 5000,
  task_ms: 3000,
  report_delay_ms: 3000,
  active_task_ms: 5000,
} as const

/**
 * Read polling config from Vite env vars (injected at build time)
 * Falls back to defaults above
 */
export function getPollingConfig() {
  const env = (import.meta as any).env || {}
  return {
    health_ms: Number(env.VITE_POLLING_HEALTH || DEFAULT_POLLING.health_ms),
    task_ms: Number(env.VITE_POLLING_TASK || DEFAULT_POLLING.task_ms),
    report_delay_ms: Number(env.VITE_POLLING_REPORT_DELAY || DEFAULT_POLLING.report_delay_ms),
    active_task_ms: Number(env.VITE_POLLING_ACTIVE_TASK || DEFAULT_POLLING.active_task_ms),
  }
}
