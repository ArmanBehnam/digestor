/**
 * WebSocket hook for real-time processing progress.
 * Replaces Supabase Realtime subscriptions.
 */

import { useState, useEffect, useCallback } from 'react';
import wsManager, { type ProgressMessage } from '@/lib/websocket';

interface UseWebSocketReturn {
  progress: number;
  message: string;
  stage: string;
  isComplete: boolean;
  isError: boolean;
  errorMessage: string | null;
  connect: (jobId: string) => void;
  disconnect: () => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [stage, setStage] = useState('');
  const [isComplete, setIsComplete] = useState(false);
  const [isError, setIsError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleMessage = useCallback((msg: ProgressMessage) => {
    switch (msg.type) {
      case 'progress':
        setProgress(msg.progress || 0);
        setMessage(msg.message || '');
        setStage(msg.stage || '');
        break;
      case 'log':
        setMessage(msg.message || '');
        break;
      case 'status':
        setMessage(msg.message || '');
        setStage(msg.stage || '');
        break;
      case 'complete':
        setProgress(100);
        setIsComplete(true);
        setMessage(msg.message || 'Processing complete');
        setStage('complete');
        break;
      case 'error':
        setIsError(true);
        setErrorMessage(msg.message || 'Processing failed');
        break;
    }
  }, []);

  const connect = useCallback((jobId: string) => {
    // Reset state
    setProgress(0);
    setMessage('Connecting...');
    setStage('');
    setIsComplete(false);
    setIsError(false);
    setErrorMessage(null);

    wsManager.connect(jobId, handleMessage);
  }, [handleMessage]);

  const disconnect = useCallback(() => {
    wsManager.disconnect();
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsManager.disconnect();
    };
  }, []);

  return {
    progress,
    message,
    stage,
    isComplete,
    isError,
    errorMessage,
    connect,
    disconnect,
  };
}
