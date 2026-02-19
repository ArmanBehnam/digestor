import { useState, useCallback, useEffect, useRef } from "react";

export type DirtyAction =
  | "normalized_answer_edited"
  | "feedback_changed"
  | "remark_added"
  | "remark_edited"
  | "exclusion_changed"
  | "deletion_changed"
  | "selection_changed"
  | "note_added"
  | "note_edited"
  | "restore_answer"
  | "question_applicability_changed";

interface DirtyChange {
  action: DirtyAction;
  timestamp: number;
  details?: Record<string, any>;
}

interface ReviewDirtyState {
  isDirty: boolean;
  dirtyActions: DirtyChange[];
  changesCount: number;
  lastAction: DirtyAction | null;
  markDirty: (action: DirtyAction, details?: Record<string, any>) => void;
  markClean: () => void;
  reset: () => void;
}

export function useReviewDirtyState(initialDirty = false): ReviewDirtyState {
  const [isDirty, setIsDirty] = useState(initialDirty);
  const [dirtyActions, setDirtyActions] = useState<DirtyChange[]>([]);
  const [changesCount, setChangesCount] = useState(0);
  const [lastAction, setLastAction] = useState<DirtyAction | null>(null);
  
  // Use ref to prevent stale closures in event handlers
  const isDirtyRef = useRef(isDirty);
  useEffect(() => {
    isDirtyRef.current = isDirty;
  }, [isDirty]);

  const markDirty = useCallback((action: DirtyAction, details?: Record<string, any>) => {
    const change: DirtyChange = {
      action,
      timestamp: Date.now(),
      details,
    };
    
    setDirtyActions(prev => [...prev, change]);
    setChangesCount(prev => prev + 1);
    setLastAction(action);
    setIsDirty(true);
    
    console.log(`[ReviewDirtyState] Marked dirty: ${action}`, details || "");
  }, []);

  const markClean = useCallback(() => {
    setIsDirty(false);
    console.log("[ReviewDirtyState] Marked clean");
  }, []);

  const reset = useCallback(() => {
    setIsDirty(false);
    setDirtyActions([]);
    setChangesCount(0);
    setLastAction(null);
    console.log("[ReviewDirtyState] Reset");
  }, []);

  return {
    isDirty,
    dirtyActions,
    changesCount,
    lastAction,
    markDirty,
    markClean,
    reset,
  };
}

/**
 * Hook to handle beforeunload browser events for external navigation only
 * (tab close, refresh, typing new URL).
 * 
 * IMPORTANT: This only triggers for actual browser unload events, NOT for
 * internal SPA navigation.
 */
export function useBeforeUnloadWarning(isDirty: boolean, message?: string) {
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        // Modern browsers ignore custom messages, but we still need to set returnValue
        e.preventDefault();
        e.returnValue = ""; // Required for Chrome
        return ""; // For older browsers
      }
    };

    // Only add listener when dirty to minimize overhead
    if (isDirty) {
      window.addEventListener("beforeunload", handleBeforeUnload);
    }
    
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [isDirty, message]);
}

/**
 * Hook that triggers autosave when tab becomes hidden (user switches tabs/closes).
 * This provides a safety net against data loss on tab close/refresh.
 */
export function useAutosaveOnVisibilityChange(
  isDirty: boolean, 
  saveDraftFn: (() => Promise<void>) | null
) {
  const lastAutoSaveRef = useRef<number>(0);
  const AUTOSAVE_DEBOUNCE = 5000; // 5 seconds minimum between autosaves
  
  useEffect(() => {
    if (!saveDraftFn) return;
    
    const handleVisibilityChange = async () => {
      if (document.hidden && isDirty) {
        const now = Date.now();
        if (now - lastAutoSaveRef.current > AUTOSAVE_DEBOUNCE) {
          lastAutoSaveRef.current = now;
          console.log('[Autosave] Visibility hidden, saving draft...');
          try {
            await saveDraftFn();
            console.log('[Autosave] Draft saved successfully');
          } catch (e) {
            console.error('[Autosave] Failed:', e);
          }
        }
      }
    };
    
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [isDirty, saveDraftFn]);
}

/**
 * Combined hook that manages both internal navigation blocking and external 
 * browser unload warnings. Use this as the primary hook for unsaved changes protection.
 * 
 * This implementation does NOT use useBlocker (which requires a data router).
 * Instead, it:
 * - Uses beforeunload for external navigation (refresh, tab close)
 * - Provides a triggerNavigationBlock callback for intercepting internal navigation
 * - Parent components must call triggerNavigationBlock before navigating
 */
export function useUnsavedChangesProtection(initialDirty = false) {
  const dirtyState = useReviewDirtyState(initialDirty);
  
  // Store pending navigation callback for when user chooses to proceed
  const pendingNavigationRef = useRef<(() => void) | null>(null);
  const [showDialog, setShowDialog] = useState(false);
  
  // Handle beforeunload for external navigation (tab close, refresh)
  useBeforeUnloadWarning(dirtyState.isDirty);
  
  // Proceed with navigation (after save or discard)
  const handleProceed = useCallback(() => {
    setShowDialog(false);
    
    // Execute pending callback if exists
    if (pendingNavigationRef.current) {
      pendingNavigationRef.current();
      pendingNavigationRef.current = null;
    }
  }, []);
  
  // Stay on page (cancel navigation)
  const handleStay = useCallback(() => {
    setShowDialog(false);
    pendingNavigationRef.current = null;
  }, []);
  
  /**
   * Trigger dialog for navigation attempts.
   * Call this before any navigation action when there are unsaved changes.
   * 
   * @param callback - The navigation function to execute if user proceeds
   * @returns true if navigation was blocked (dialog shown), false if not dirty
   */
  const triggerNavigationBlock = useCallback((callback: () => void) => {
    if (dirtyState.isDirty) {
      pendingNavigationRef.current = callback;
      setShowDialog(true);
      return true; // Navigation was blocked
    }
    return false; // Navigation was not blocked, proceed immediately
  }, [dirtyState.isDirty]);
  
  /**
   * Create a wrapped navigate function that checks dirty state first.
   * Use this to wrap navigation calls throughout the component.
   */
  const createGuardedNavigate = useCallback((navigateFn: () => void) => {
    return () => {
      const blocked = triggerNavigationBlock(navigateFn);
      if (!blocked) {
        navigateFn();
      }
    };
  }, [triggerNavigationBlock]);
  
  return {
    ...dirtyState,
    showDialog,
    setShowDialog,
    pendingNavigationRef,
    handleProceed,
    handleStay,
    triggerNavigationBlock,
    createGuardedNavigate,
  };
}
