import { useState, useEffect, useRef, useCallback } from 'react';
import { ExternalLink, Focus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { usePdfBroadcastChannel, PdfBroadcastMessage } from '@/hooks/usePdfBroadcastChannel';
import { registerPopoutWindow, unregisterPopoutWindow } from '@/lib/pdfPopoutRegistry';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface PdfPopoutButtonProps {
  projectId: string;
  filesMetadata: Array<{ name: string; path: string; size?: number; type?: string }>;
  selectedIndex: number;
  onPopoutStateChange?: (isActive: boolean) => void;
}

export function PdfPopoutButton({
  projectId,
  filesMetadata,
  selectedIndex,
  onPopoutStateChange,
}: PdfPopoutButtonProps) {
  const [isPopoutActive, setIsPopoutActive] = useState(false);
  const popoutWindowRef = useRef<Window | null>(null);
  const checkIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Handle incoming messages from popout
  const handleMessage = useCallback((message: PdfBroadcastMessage) => {
    if (message.type === 'POPOUT_READY') {
      // Confirmation that popout is loaded and ready - ensure state is active
      if (!isPopoutActive) {
        setIsPopoutActive(true);
        onPopoutStateChange?.(true);
      }
    } else if (message.type === 'POPOUT_CLOSED') {
      setIsPopoutActive(false);
      onPopoutStateChange?.(false);
      popoutWindowRef.current = null;
    }
  }, [isPopoutActive, onPopoutStateChange]);

  const { sendFilesUpdate } = usePdfBroadcastChannel({
    projectId,
    onMessage: handleMessage,
    enabled: true,
  });

  // Check if popout window is still open
  useEffect(() => {
    if (isPopoutActive) {
      checkIntervalRef.current = setInterval(() => {
        if (popoutWindowRef.current?.closed) {
          // Unregister from global registry when window closes
          unregisterPopoutWindow(projectId);
          setIsPopoutActive(false);
          onPopoutStateChange?.(false);
          popoutWindowRef.current = null;
          if (checkIntervalRef.current) {
            clearInterval(checkIntervalRef.current);
          }
        }
      }, 500);
    }

    return () => {
      if (checkIntervalRef.current) {
        clearInterval(checkIntervalRef.current);
      }
    };
  }, [isPopoutActive, onPopoutStateChange]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (checkIntervalRef.current) {
        clearInterval(checkIntervalRef.current);
      }
    };
  }, []);

  const handlePopout = () => {
    if (isPopoutActive && popoutWindowRef.current && !popoutWindowRef.current.closed) {
      // Focus existing window
      popoutWindowRef.current.focus();
      return;
    }

    // Prepare data to pass via URL (only paths, not signed URLs for security)
    const filesData = filesMetadata.map(f => ({
      name: f.name,
      path: f.path,
      size: f.size,
    }));
    
    const encodedData = encodeURIComponent(btoa(JSON.stringify(filesData)));
    const url = `/pdf-preview?projectId=${encodeURIComponent(projectId)}&filesData=${encodedData}&selectedIndex=${selectedIndex}`;
    
    // Window features for a proper pop-up
    const width = Math.min(1200, window.screen.availWidth * 0.7);
    const height = Math.min(900, window.screen.availHeight * 0.8);
    const left = (window.screen.availWidth - width) / 2;
    const top = (window.screen.availHeight - height) / 2;
    
    const features = `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes,status=no,toolbar=no,menubar=no,location=no`;
    
    const popout = window.open(url, `pdf-preview-${projectId}`, features);
    
    if (!popout || popout.closed || typeof popout.closed === 'undefined') {
      toast.error('Popup blocked - please allow popups for this site', {
        description: 'Click the popup blocker icon in your browser address bar to allow popups.',
        duration: 5000,
      });
      return;
    }
    
    popoutWindowRef.current = popout;
    
    // Register the window handle in the global registry for direct postMessage
    registerPopoutWindow(projectId, popout);
    
    // Set active immediately on successful window.open() instead of waiting for POPOUT_READY message
    // This ensures isPopoutActive is true right away for reference navigation
    setIsPopoutActive(true);
    onPopoutStateChange?.(true);
  };

  const handleFocusPopout = () => {
    if (popoutWindowRef.current && !popoutWindowRef.current.closed) {
      popoutWindowRef.current.focus();
    }
  };

  const handleClosePopout = () => {
    if (popoutWindowRef.current && !popoutWindowRef.current.closed) {
      popoutWindowRef.current.close();
    }
    // Unregister from global registry
    unregisterPopoutWindow(projectId);
    setIsPopoutActive(false);
    onPopoutStateChange?.(false);
    popoutWindowRef.current = null;
  };

  if (isPopoutActive) {
    return (
      <div className="flex items-center gap-1">
        <Badge variant="secondary" className="text-xs bg-primary/10 text-primary border-primary/20">
          Pop-out Active
        </Badge>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleFocusPopout}
                className="h-7 w-7 p-0"
              >
                <Focus className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Focus pop-out window</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClosePopout}
                className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Close pop-out window</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            onClick={handlePopout}
            className="h-8 w-8 p-0"
          >
            <ExternalLink className="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>Open in separate window</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// Export a ref-based accessor for sending navigation commands
export function usePopoutNavigation(projectId: string) {
  const { sendNavigate } = usePdfBroadcastChannel({
    projectId,
    enabled: true,
  });

  return { sendNavigate };
}
