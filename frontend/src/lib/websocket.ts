/**
 * Digestor Unified - WebSocket Manager
 * Replaces Supabase Realtime for processing progress updates.
 */

export interface ProgressMessage {
  type: 'progress' | 'log' | 'status' | 'complete' | 'error' | 'pong' | 'close';
  progress?: number;
  message?: string;
  stage?: 'ocr' | 'llm' | 'validation' | 'complete';
  data?: any;
}

type ProgressCallback = (message: ProgressMessage) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private callbacks: Map<string, ProgressCallback> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private jobId: string | null = null;

  private getWsUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.VITE_WS_HOST || window.location.host;
    return `${protocol}//${host}/ws`;
  }

  connect(jobId: string, onMessage: ProgressCallback): void {
    this.jobId = jobId;
    this.callbacks.set(jobId, onMessage);

    const url = `${this.getWsUrl()}/progress/${jobId}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log(`[WS] Connected to job ${jobId}`);
      this.reconnectAttempts = 0;
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      try {
        const message: ProgressMessage = JSON.parse(event.data);
        const callback = this.callbacks.get(jobId);
        if (callback) {
          callback(message);
        }

        // Auto-disconnect on completion
        if (message.type === 'close' || message.type === 'complete') {
          this.disconnect();
        }
      } catch (e) {
        console.warn('[WS] Failed to parse message:', event.data);
      }
    };

    this.ws.onerror = (error) => {
      console.error('[WS] Error:', error);
    };

    this.ws.onclose = (event) => {
      console.log(`[WS] Disconnected (code: ${event.code})`);
      this.stopHeartbeat();

      // Auto-reconnect on unexpected close
      if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        setTimeout(() => {
          if (this.jobId && this.callbacks.has(this.jobId)) {
            this.connect(this.jobId, this.callbacks.get(this.jobId)!);
          }
        }, delay);
      }
    };
  }

  disconnect(): void {
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    if (this.jobId) {
      this.callbacks.delete(this.jobId);
      this.jobId = null;
    }
  }

  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 30000); // Every 30 seconds
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Singleton
const wsManager = new WebSocketManager();
export default wsManager;
