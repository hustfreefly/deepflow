/**
 * React Hook for DeepFlow Task Management
 * 
 * Provides state management for task creation, status polling, and report retrieval.
 * Automatically uses v2 API with fallback to v1.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import {
  createTask,
  getTask,
  getStatus,
  getReport,
  pollTaskStatus,
  TaskRequest,
  TaskResponse,
  TaskDetail,
  TaskStatus,
  ReportData,
} from '../api/client';

export interface UseTaskState {
  // Task info
  sessionId: string | null;
  task: TaskDetail | null;
  status: TaskStatus | null;
  report: ReportData | null;
  
  // Loading states
  isCreating: boolean;
  isLoading: boolean;
  isPolling: boolean;
  
  // Error
  error: Error | null;
  
  // Actions
  createNewTask: (request: TaskRequest) => Promise<void>;
  refreshTask: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  loadReport: () => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
}

export function useTask(): UseTaskState {
  // State
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [status, setStatus] = useState<TaskStatus | null>(null);
  const [report, setReport] = useState<ReportData | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  
  // Refs
  const stopPollingRef = useRef<(() => void) | null>(null);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (stopPollingRef.current) {
        stopPollingRef.current();
      }
    };
  }, []);
  
  /**
   * Create a new task
   */
  const createNewTask = useCallback(async (request: TaskRequest) => {
    setIsCreating(true);
    setError(null);
    
    try {
      const response = await createTask(request);
      setSessionId(response.session_id);
      
      // Load initial task details
      const taskDetail = await getTask(response.session_id);
      setTask(taskDetail);
      
      // Start polling automatically
      startPolling();
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      throw error;
    } finally {
      setIsCreating(false);
    }
  }, []);
  
  /**
   * Refresh task details
   */
  const refreshTask = useCallback(async () => {
    if (!sessionId) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      const taskDetail = await getTask(sessionId);
      setTask(taskDetail);
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);
  
  /**
   * Refresh status
   */
  const refreshStatus = useCallback(async () => {
    if (!sessionId) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      const taskStatus = await getStatus(sessionId);
      setStatus(taskStatus);
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);
  
  /**
   * Load report
   */
  const loadReport = useCallback(async () => {
    if (!sessionId) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      const reportData = await getReport(sessionId);
      setReport(reportData);
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);
  
  /**
   * Start polling for status updates
   */
  const startPolling = useCallback(() => {
    if (!sessionId || isPolling) return;
    
    setIsPolling(true);
    
    stopPollingRef.current = pollTaskStatus(
      sessionId,
      (newStatus) => {
        setStatus(newStatus);
        
        // Auto-load report when completed
        if (newStatus.status === 'completed' && !report) {
          loadReport();
        }
      },
      (err) => {
        console.error('[useTask] Polling error:', err);
        // Don't set error state for polling errors
      },
      3000 // 3 second interval
    );
  }, [sessionId, isPolling, report, loadReport]);
  
  /**
   * Stop polling
   */
  const stopPolling = useCallback(() => {
    if (stopPollingRef.current) {
      stopPollingRef.current();
      stopPollingRef.current = null;
    }
    setIsPolling(false);
  }, []);
  
  return {
    sessionId,
    task,
    status,
    report,
    isCreating,
    isLoading,
    isPolling,
    error,
    createNewTask,
    refreshTask,
    refreshStatus,
    loadReport,
    startPolling,
    stopPolling,
  };
}

/**
 * React Hook for task list
 */
export interface UseTaskListState {
  tasks: TaskResponse[];
  isLoading: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
}

export function useTaskList(): UseTaskListState {
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  
  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      // Import dynamically to avoid circular dependency
      const { listTasksV2 } = await import('../api/client');
      const taskList = await listTasksV2();
      setTasks(taskList);
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  // Auto-refresh on mount
  useEffect(() => {
    refresh();
  }, [refresh]);
  
  return { tasks, isLoading, error, refresh };
}
