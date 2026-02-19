import { useRef, useEffect, useCallback } from 'react';

export interface PdfBroadcastMessage {
  type: 'NAVIGATE' | 'FILES_UPDATE' | 'POPOUT_READY' | 'POPOUT_CLOSED' | 'POPOUT_PING';
  projectId: string;
  payload: {
    fileIndex?: number;
    fileName?: string;
    page?: number;
    highlight?: {
      x: number;
      y: number;
      width: number;
      height: number;
    };
    files?: Array<{ name: string; url: string; path?: string; pageCount?: number }>;
  };
}

interface UsePdfBroadcastChannelOptions {
  projectId: string;
  onMessage?: (message: PdfBroadcastMessage) => void;
  enabled?: boolean;
}

export function usePdfBroadcastChannel({
  projectId,
  onMessage,
  enabled = true,
}: UsePdfBroadcastChannelOptions) {
  const channelRef = useRef<BroadcastChannel | null>(null);
  const channelName = `pdf-preview-${projectId}`;
  
  // Store onMessage in a ref to avoid stale closures and prevent channel recreation
  const onMessageRef = useRef(onMessage);
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  // Initialize channel - only recreate when projectId or enabled changes
  useEffect(() => {
    if (!enabled || !projectId) return;

    try {
      channelRef.current = new BroadcastChannel(channelName);
      
      channelRef.current.onmessage = (event: MessageEvent<PdfBroadcastMessage>) => {
        // Validate message belongs to this project
        if (event.data?.projectId === projectId) {
          onMessageRef.current?.(event.data);
        }
      };
    } catch (error) {
      console.warn('BroadcastChannel not supported, falling back to localStorage events');
    }

    return () => {
      channelRef.current?.close();
      channelRef.current = null;
    };
  }, [channelName, projectId, enabled]); // Removed onMessage from deps

  // Send a message
  const sendMessage = useCallback((message: Omit<PdfBroadcastMessage, 'projectId'>) => {
    const fullMessage: PdfBroadcastMessage = {
      ...message,
      projectId,
    };

    if (channelRef.current) {
      console.log('[BroadcastChannel] Posting message:', fullMessage.type, fullMessage.payload);
      channelRef.current.postMessage(fullMessage);
    } else {
      // Fallback: use localStorage for cross-window communication
      try {
        const key = `pdf-broadcast-${projectId}`;
        localStorage.setItem(key, JSON.stringify({ ...fullMessage, timestamp: Date.now() }));
        // Clean up immediately
        setTimeout(() => localStorage.removeItem(key), 100);
      } catch (error) {
        console.error('Failed to send message via localStorage fallback:', error);
      }
    }
  }, [projectId]);

  // Send navigation command
  const sendNavigate = useCallback((
    fileIndex: number,
    page: number,
    fileName?: string,
    highlight?: { x: number; y: number; width: number; height: number }
  ) => {
    sendMessage({
      type: 'NAVIGATE',
      payload: { fileIndex, page, fileName, highlight },
    });
  }, [sendMessage]);

  // Send files update
  const sendFilesUpdate = useCallback((
    files: Array<{ name: string; url: string; path?: string; pageCount?: number }>
  ) => {
    sendMessage({
      type: 'FILES_UPDATE',
      payload: { files },
    });
  }, [sendMessage]);

  // Send ready signal
  const sendReady = useCallback(() => {
    sendMessage({
      type: 'POPOUT_READY',
      payload: {},
    });
  }, [sendMessage]);

  // Send closed signal
  const sendClosed = useCallback(() => {
    sendMessage({
      type: 'POPOUT_CLOSED',
      payload: {},
    });
  }, [sendMessage]);

  // Send ping to check if popout is alive
  const sendPing = useCallback(() => {
    sendMessage({
      type: 'POPOUT_PING',
      payload: {},
    });
  }, [sendMessage]);

  return {
    sendMessage,
    sendNavigate,
    sendFilesUpdate,
    sendReady,
    sendClosed,
    sendPing,
  };
}
