import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PDFViewerWithAnnotations, PDFHighlight } from '@/components/PDFViewerWithAnnotations';
import { PDFSourceCarousel } from '@/components/PDFSourceCarousel';
import { Card } from '@/components/ui/card';
import { Loader2 } from 'lucide-react';
import { usePdfBroadcastChannel, PdfBroadcastMessage } from '@/hooks/usePdfBroadcastChannel';
import { generateSignedUrls, SignedUrlResult } from '@/lib/pdfUtils';

interface FileData {
  name: string;
  path: string;
  size?: number;
}

export default function PdfPopoutPage() {
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get('projectId') || '';
  const encodedFilesData = searchParams.get('filesData');
  const initialSelectedIndex = parseInt(searchParams.get('selectedIndex') || '0', 10);

  const [filesData, setFilesData] = useState<FileData[]>([]);
  const [pdfUrls, setPdfUrls] = useState<SignedUrlResult[]>([]);
  const [selectedPdfIndex, setSelectedPdfIndex] = useState(initialSelectedIndex);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfHighlights, setPdfHighlights] = useState<PDFHighlight[]>([]);
  
  const pendingNavigationRef = useRef<{ page: number; highlight?: PDFHighlight } | null>(null);
  
  // Use ref to track current selectedPdfIndex to avoid stale closure in handleMessage
  const selectedPdfIndexRef = useRef(selectedPdfIndex);
  useEffect(() => {
    selectedPdfIndexRef.current = selectedPdfIndex;
  }, [selectedPdfIndex]);

  // Ref for broadcast channel callback to avoid stale closures
  const broadcastCallbackRef = useRef<((msg: PdfBroadcastMessage) => void) | null>(null);
  
  // Ref for sendReady to avoid stale closure in handleMessage
  const sendReadyRef = useRef<() => void>(() => {});

  // Initialize broadcast channel FIRST with a ref-based callback
  const { sendReady, sendClosed } = usePdfBroadcastChannel({
    projectId,
    onMessage: (msg) => broadcastCallbackRef.current?.(msg),
    enabled: !!projectId,
  });
  
  // Store sendReady in ref for stable access
  useEffect(() => {
    sendReadyRef.current = sendReady;
  }, [sendReady]);

  // Parse files data from URL
  useEffect(() => {
    if (encodedFilesData) {
      try {
        const decoded = JSON.parse(atob(decodeURIComponent(encodedFilesData)));
        setFilesData(decoded);
      } catch (e) {
        console.error('Failed to parse files data:', e);
        setError('Failed to parse file data from URL');
      }
    }
  }, [encodedFilesData]);

  // Generate signed URLs for PDFs
  useEffect(() => {
    const loadPdfs = async () => {
      if (filesData.length === 0) return;

      setLoading(true);
      try {
        const filesMetadata = filesData.map(f => ({
          name: f.name,
          path: f.path,
          size: f.size || 0,
          type: 'application/pdf',
        }));

        const signedUrls = await generateSignedUrls(filesMetadata);
        setPdfUrls(signedUrls);
      } catch (e) {
        console.error('Failed to generate signed URLs:', e);
        setError('Failed to load PDF files');
      } finally {
        setLoading(false);
      }
    };

    loadPdfs();
  }, [filesData]);

  // Execute navigation to a specific page - uses event-based ready detection
  const executeNavigation = useCallback((page: number, highlight?: PDFHighlight) => {
    const maxWaitTime = 5000;
    const checkInterval = 50;
    let waited = 0;
    let cleanedUp = false;

    const attemptNavigation = () => {
      if (cleanedUp) return false;
      if (typeof (window as any).jumpToPdfLocation === 'function') {
        const location = highlight || { page, x: 0, y: 0, width: 0, height: 0 };
        (window as any).jumpToPdfLocation(location);
        console.log('[PopOut] Navigation executed successfully:', { page, highlight });
        return true;
      }
      return false;
    };

    // Try immediately
    if (attemptNavigation()) return;

    // Listen for ready event
    const handleReady = () => {
      if (attemptNavigation()) {
        window.removeEventListener('pdf-viewer-ready', handleReady);
        cleanedUp = true;
      }
    };
    window.addEventListener('pdf-viewer-ready', handleReady);

    // Fallback polling
    const pollForReady = async () => {
      while (waited < maxWaitTime && !cleanedUp) {
        if (attemptNavigation()) {
          window.removeEventListener('pdf-viewer-ready', handleReady);
          cleanedUp = true;
          return;
        }
        await new Promise(resolve => setTimeout(resolve, checkInterval));
        waited += checkInterval;
      }
      
      if (!cleanedUp) {
        window.removeEventListener('pdf-viewer-ready', handleReady);
        console.warn('[PopOut] PDF viewer not ready for navigation after timeout');
      }
    };

    pollForReady();
  }, []);

  // Set up the broadcast message handler using refs to avoid stale closures
  useEffect(() => {
    broadcastCallbackRef.current = (message: PdfBroadcastMessage) => {
      console.log('[PopOut] Received broadcast message:', message.type, message.payload);
      
      if (message.type === 'NAVIGATE') {
        const { fileIndex, page, highlight } = message.payload;
        console.log('[PopOut] Processing NAVIGATE:', { fileIndex, page, highlight });
        
        // Use ref for current index comparison to avoid stale closure
        const currentIndex = selectedPdfIndexRef.current;
        const needsFileSwitch = fileIndex !== undefined && fileIndex !== currentIndex;
        
        if (needsFileSwitch) {
          setSelectedPdfIndex(fileIndex!);
        }
        
        if (page !== undefined) {
          // Store the navigation request - will be executed after PDF switch
          const highlightData: PDFHighlight | undefined = highlight ? {
            page,
            x: highlight.x,
            y: highlight.y,
            width: highlight.width,
            height: highlight.height,
          } : undefined;
          
          if (highlightData) {
            setPdfHighlights([highlightData]);
          }
          
          pendingNavigationRef.current = { page, highlight: highlightData };
          
          // If we're already on the correct file, navigate immediately
          if (!needsFileSwitch) {
            executeNavigation(page, highlightData);
          }
        }
      } else if (message.type === 'FILES_UPDATE') {
        // Update files if main window sends new data
        if (message.payload.files) {
          const newFilesData = message.payload.files.map(f => ({
            name: f.name,
            path: f.path || '',
            size: 0,
          }));
          setFilesData(newFilesData);
        }
      } else if (message.type === 'POPOUT_PING') {
        // Respond to ping with ready signal using ref
        sendReadyRef.current();
      }
    };
  }, [executeNavigation]);

  // Also listen for direct postMessage events (fallback mechanism)
  useEffect(() => {
    const handlePostMessage = (event: MessageEvent) => {
      // Validate origin and message structure
      if (event.origin !== window.location.origin) return;
      if (!event.data || typeof event.data !== 'object') return;
      if (event.data.projectId !== projectId) return;
      
      console.log('[PopOut] Received postMessage:', event.data.type, event.data.payload);
      
      if (event.data.type === 'NAVIGATE') {
        const { fileIndex, page, highlight } = event.data.payload || {};
        console.log('[PopOut] Processing postMessage NAVIGATE:', { fileIndex, page, highlight });
        
        const currentIndex = selectedPdfIndexRef.current;
        const needsFileSwitch = fileIndex !== undefined && fileIndex !== currentIndex;
        
        if (needsFileSwitch) {
          setSelectedPdfIndex(fileIndex);
        }
        
        if (page !== undefined) {
          const highlightData: PDFHighlight | undefined = highlight ? {
            page,
            x: highlight.x,
            y: highlight.y,
            width: highlight.width,
            height: highlight.height,
          } : undefined;
          
          if (highlightData) {
            setPdfHighlights([highlightData]);
          }
          
          pendingNavigationRef.current = { page, highlight: highlightData };
          
          if (!needsFileSwitch) {
            executeNavigation(page, highlightData);
          }
        }
      }
    };
    
    window.addEventListener('message', handlePostMessage);
    return () => window.removeEventListener('message', handlePostMessage);
  }, [projectId, executeNavigation]);

  // Handle PDF switching - execute pending navigation after switch using event-based detection
  useEffect(() => {
    if (pdfUrls.length > 0 && pendingNavigationRef.current) {
      const { page, highlight } = pendingNavigationRef.current;
      pendingNavigationRef.current = null;
      
      // Use executeNavigation which waits for pdf-viewer-ready event
      executeNavigation(page, highlight);
    }
  }, [selectedPdfIndex, pdfUrls, executeNavigation]);

  // Send ready signal when loaded
  useEffect(() => {
    if (!loading && pdfUrls.length > 0 && projectId) {
      sendReady();
    }
  }, [loading, pdfUrls.length, projectId, sendReady]);

  // Send closed signal on unmount
  useEffect(() => {
    const handleBeforeUnload = () => {
      sendClosed();
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      sendClosed();
    };
  }, [sendClosed]);

  // Set page title
  useEffect(() => {
    document.title = `PDF Preview - ${projectId}`;
  }, [projectId]);

  if (error) {
    return (
      <div className="min-h-screen bg-background p-4 flex items-center justify-center">
        <Card className="p-6 text-center">
          <p className="text-destructive">{error}</p>
          <p className="text-muted-foreground mt-2 text-sm">
            Please close this window and try again.
          </p>
        </Card>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background p-4 flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
          <p className="text-muted-foreground">Loading PDF preview...</p>
        </div>
      </div>
    );
  }

  if (pdfUrls.length === 0) {
    return (
      <div className="min-h-screen bg-background p-4 flex items-center justify-center">
        <Card className="p-6 text-center">
          <p className="text-muted-foreground">No PDFs available</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background p-4 flex flex-col">
      {/* PDF Source Tabs */}
      <div className="mb-4">
        <PDFSourceCarousel
          sources={pdfUrls.map(pdf => ({
            name: pdf.fileName,
            url: pdf.signedUrl,
            pageCount: pdf.pageCount,
          }))}
          selectedIndex={selectedPdfIndex}
          onSelect={setSelectedPdfIndex}
        />
      </div>

      {/* PDF Viewer */}
      <div className="flex-1 min-h-0">
        <PDFViewerWithAnnotations
          fileUrl={pdfUrls[selectedPdfIndex].signedUrl}
          fileName={pdfUrls[selectedPdfIndex].fileName}
          highlights={pdfHighlights}
        />
      </div>
    </div>
  );
}
