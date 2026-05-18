/**
 * DeepFlow Frontend API Client v2.0
 * 
 * Supports both v1 (legacy) and v2 (Webhook) APIs.
 * Automatically falls back to v1 if v2 is unavailable.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:17789';

// API Versions
export type ApiVersion = 'v1' | 'v2';

// Current default version
let DEFAULT_API_VERSION: ApiVersion = 'v2';

/**
 * Set default API version
 */
export function setApiVersion(version: ApiVersion): void {
  DEFAULT_API_VERSION = version;
}

/**
 * Get current API version
 */
export function getApiVersion(): ApiVersion {
  return DEFAULT_API_VERSION;
}

// Task Types
export interface TaskRequest {
  domain: 'solution' | 'investment' | string;
  session_prefix?: string;
  // Solution domain
  topic?: string;
  solution_type?: 'architecture' | 'design' | 'code';
  constraints?: string[];
  stakeholders?: string[];
  // Investment domain
  code?: string;
  name?: string;
  analysis_type?: 'value' | 'growth' | 'technical';
}

export interface TaskResponse {
  session_id: string;
  status: string;
  domain: string;
  created_at: string;
  webhook_sent: boolean;
  webhook_retries: number;
}

export interface TaskDetail extends TaskResponse {
  parameters: Record<string, any>;
  updated_at: string;
  error?: string;
}

// Status Types
export interface PipelineStage {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  started_at?: string;
  completed_at?: string;
}

export interface HarnessQuality {
  completeness: number;
  necessity: number;
  goal_alignment: number;
  overall: number;
}

export interface TaskStatus {
  session_id: string;
  domain: string;
  status: string;
  progress: number;
  current_stage?: string;
  stages: PipelineStage[];
  harness_quality?: HarnessQuality;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

export interface ReportData {
  session_id: string;
  domain: string;
  content: string;
  created_at: string;
}

// API Error
export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public response?: Response
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Generic API request handler
 */
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  version: ApiVersion = DEFAULT_API_VERSION
): Promise<T> {
  const url = `${API_BASE_URL}/api${version === 'v2' ? '/v2' : ''}${endpoint}`;
  
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    throw new ApiError(
      `API Error: ${response.status} - ${errorText}`,
      response.status,
      response
    );
  }
  
  // Handle empty responses
  if (response.status === 204) {
    return undefined as T;
  }
  
  return response.json();
}

// ==================== Task API v2 ====================

/**
 * Create a new task (v2 - with webhook)
 */
export async function createTaskV2(request: TaskRequest): Promise<TaskResponse> {
  return apiRequest<TaskResponse>('/tasks', {
    method: 'POST',
    body: JSON.stringify(request),
  }, 'v2');
}

/**
 * Get task details (v2)
 */
export async function getTaskV2(sessionId: string): Promise<TaskDetail> {
  return apiRequest<TaskDetail>(`/tasks/${sessionId}`, {}, 'v2');
}

/**
 * List all tasks (v2)
 */
export async function listTasksV2(): Promise<TaskResponse[]> {
  return apiRequest<TaskResponse[]>('/tasks', {}, 'v2');
}

// ==================== Status API v2 ====================

/**
 * Get task status from Blackboard (v2)
 */
export async function getStatusV2(sessionId: string): Promise<TaskStatus> {
  return apiRequest<TaskStatus>(`/status/${sessionId}`, {}, 'v2');
}

/**
 * Get task report from Blackboard (v2)
 */
export async function getReportV2(sessionId: string): Promise<ReportData> {
  return apiRequest<ReportData>(`/report/${sessionId}`, {}, 'v2');
}

// ==================== Legacy v1 API ====================

/**
 * Create a new task (v1 - file queue)
 */
export async function createTaskV1(request: TaskRequest): Promise<TaskResponse> {
  return apiRequest<TaskResponse>('/tasks', {
    method: 'POST',
    body: JSON.stringify(request),
  }, 'v1');
}

/**
 * Get task details (v1)
 */
export async function getTaskV1(sessionId: string): Promise<TaskDetail> {
  return apiRequest<TaskDetail>(`/tasks/${sessionId}`, {}, 'v1');
}

/**
 * Get task status (v1)
 */
export async function getStatusV1(sessionId: string): Promise<TaskStatus> {
  return apiRequest<TaskStatus>(`/status/${sessionId}`, {}, 'v1');
}

/**
 * Get task report (v1)
 */
export async function getReportV1(sessionId: string): Promise<ReportData> {
  return apiRequest<ReportData>(`/reports/${sessionId}`, {}, 'v1');
}

// ==================== Unified API (auto fallback) ====================

/**
 * Create a new task (auto v2 with v1 fallback)
 */
export async function createTask(request: TaskRequest): Promise<TaskResponse> {
  try {
    return await createTaskV2(request);
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 404) {
      console.warn('[API] v2 not available, falling back to v1');
      return createTaskV1(request);
    }
    throw error;
  }
}

/**
 * Get task details (auto v2 with v1 fallback)
 */
export async function getTask(sessionId: string): Promise<TaskDetail> {
  try {
    return await getTaskV2(sessionId);
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 404) {
      return getTaskV1(sessionId);
    }
    throw error;
  }
}

/**
 * Get task status (auto v2 with v1 fallback)
 */
export async function getStatus(sessionId: string): Promise<TaskStatus> {
  try {
    return await getStatusV2(sessionId);
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 404) {
      return getStatusV1(sessionId);
    }
    throw error;
  }
}

/**
 * Get task report (auto v2 with v1 fallback)
 */
export async function getReport(sessionId: string): Promise<ReportData> {
  try {
    return await getReportV2(sessionId);
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 404) {
      return getReportV1(sessionId);
    }
    throw error;
  }
}

// ==================== Health Check ====================

export interface HealthStatus {
  status: string;
  version: string;
  timestamp: string;
  openclaw?: {
    status: string;
    version?: string;
  };
}

/**
 * Check API health
 */
export async function checkHealth(): Promise<HealthStatus> {
  return apiRequest<HealthStatus>('/health', {}, 'v1');
}

// ==================== Real-time Updates (Polling) ====================

export type StatusCallback = (status: TaskStatus) => void;
export type ErrorCallback = (error: Error) => void;

/**
 * Poll task status until completion
 */
export function pollTaskStatus(
  sessionId: string,
  onUpdate: StatusCallback,
  onError?: ErrorCallback,
  intervalMs: number = 3000
): () => void {
  let isActive = true;
  let timeoutId: number | null = null;
  
  const poll = async () => {
    if (!isActive) return;
    
    try {
      const status = await getStatus(sessionId);
      onUpdate(status);
      
      // Continue polling if not complete
      if (status.status !== 'completed' && status.status !== 'failed') {
        timeoutId = window.setTimeout(poll, intervalMs);
      }
    } catch (error) {
      if (onError && error instanceof Error) {
        onError(error);
      }
      // Continue polling on error
      timeoutId = window.setTimeout(poll, intervalMs);
    }
  };
  
  // Start polling
  poll();
  
  // Return cleanup function
  return () => {
    isActive = false;
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
  };
}

// Default exports
export default {
  // Version
  setApiVersion,
  getApiVersion,
  
  // v2 API
  createTaskV2,
  getTaskV2,
  listTasksV2,
  getStatusV2,
  getReportV2,
  
  // v1 API
  createTaskV1,
  getTaskV1,
  getStatusV1,
  getReportV1,
  
  // Unified API
  createTask,
  getTask,
  getStatus,
  getReport,
  
  // Health
  checkHealth,
  
  // Polling
  pollTaskStatus,
};
