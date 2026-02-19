/**
 * Global registry for PDF pop-out window handles.
 * Provides direct window.postMessage as a fallback to BroadcastChannel.
 */

// Map of projectId -> Window handle
const popoutWindows = new Map<string, Window>();

/**
 * Register a pop-out window for a project
 */
export function registerPopoutWindow(projectId: string, windowHandle: Window): void {
  popoutWindows.set(projectId, windowHandle);
  console.log('[PopoutRegistry] Registered window for project:', projectId);
}

/**
 * Unregister a pop-out window for a project
 */
export function unregisterPopoutWindow(projectId: string): void {
  popoutWindows.delete(projectId);
  console.log('[PopoutRegistry] Unregistered window for project:', projectId);
}

/**
 * Get the pop-out window for a project (returns null if not available or closed)
 */
export function getPopoutWindow(projectId: string): Window | null {
  const win = popoutWindows.get(projectId);
  if (!win || win.closed) {
    // Clean up if window is closed
    if (win) {
      popoutWindows.delete(projectId);
    }
    return null;
  }
  return win;
}

/**
 * Check if a pop-out window is open for a project
 */
export function isPopoutWindowOpen(projectId: string): boolean {
  return getPopoutWindow(projectId) !== null;
}

/**
 * Send a message directly to the pop-out window via postMessage
 */
export function sendDirectMessage(
  projectId: string, 
  message: { type: string; payload: unknown }
): boolean {
  const win = getPopoutWindow(projectId);
  if (!win) {
    return false;
  }
  
  try {
    const fullMessage = { ...message, projectId };
    console.log('[PopoutRegistry] Sending direct postMessage:', fullMessage.type);
    win.postMessage(fullMessage, window.location.origin);
    return true;
  } catch (error) {
    console.error('[PopoutRegistry] Failed to send postMessage:', error);
    return false;
  }
}
