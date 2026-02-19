import { useRef, useCallback, useEffect } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

// Configure PDF.js worker using bundled worker
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

// Global cache shared across all components
const globalPdfCache = new Map<string, pdfjsLib.PDFDocumentProxy>();
const loadingPromises = new Map<string, Promise<pdfjsLib.PDFDocumentProxy>>();

// Cache for pre-rendered first page canvases
interface PrerenderedPage {
  canvas: HTMLCanvasElement;
  scale: number;
  rotation: number;
}
const prerenderedFirstPages = new Map<string, PrerenderedPage>();

export const usePdfPreloader = () => {
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const preloadPdf = useCallback(async (url: string): Promise<pdfjsLib.PDFDocumentProxy | null> => {
    if (!url) return null;

    // Return cached document immediately
    if (globalPdfCache.has(url)) {
      console.log('usePdfPreloader: Using cached PDF document for', url);
      return globalPdfCache.get(url)!;
    }

    // If already loading, return existing promise
    if (loadingPromises.has(url)) {
      console.log('usePdfPreloader: Waiting for existing load promise for', url);
      return loadingPromises.get(url)!;
    }

    // Start loading with progressive streaming
    console.log('usePdfPreloader: Starting PDF preload with progressive streaming for', url);
    
    const loadPromise = (async () => {
      try {
        const loadingTask = pdfjsLib.getDocument({
          url,
          rangeChunkSize: 65536, // 64KB chunks for progressive loading
          disableAutoFetch: true, // Don't fetch entire document upfront
          disableStream: false, // Enable streaming
        });

        const pdfDoc = await loadingTask.promise;
        
        // Cache the loaded document
        globalPdfCache.set(url, pdfDoc);
        console.log('usePdfPreloader: PDF loaded and cached:', url);
        
        // Pre-render first page immediately for INSTANT display
        if (pdfDoc.numPages > 0 && !prerenderedFirstPages.has(url)) {
          try {
            console.log('usePdfPreloader: Pre-rendering first page for instant display');
            const page = await pdfDoc.getPage(1);
            
            // Use low scale for fast rendering - will be scaled up in viewer
            const pageRotation = page.rotate || 0;
            const viewport = page.getViewport({ scale: 0.8, rotation: pageRotation });
            
            // Create off-screen canvas
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d', { willReadFrequently: true });
            
            if (context) {
              canvas.width = viewport.width;
              canvas.height = viewport.height;
              
              // Render page to canvas
              await page.render({
                canvasContext: context,
                viewport: viewport,
              } as any).promise;
              
              // Cache the pre-rendered canvas
              prerenderedFirstPages.set(url, {
                canvas,
                scale: 0.8,
                rotation: pageRotation,
              });
              
              console.log('usePdfPreloader: First page pre-rendered and cached');
            }
          } catch (err) {
            console.warn('Failed to pre-render first page (non-critical):', err);
          }
        }
        
        return pdfDoc;
      } catch (error) {
        console.error('usePdfPreloader: Failed to load PDF:', error);
        throw error;
      } finally {
        loadingPromises.delete(url);
      }
    })();

    loadingPromises.set(url, loadPromise);
    return loadPromise;
  }, []);

  const preloadMultiplePdfs = useCallback(async (urls: string[]): Promise<void> => {
    console.log('usePdfPreloader: Preloading multiple PDFs in parallel:', urls.length);
    
    // Load all PDFs in parallel
    const promises = urls.map(url => preloadPdf(url).catch(err => {
      console.error('Failed to preload PDF (non-critical):', url, err);
      return null;
    }));
    
    await Promise.all(promises);
    console.log('usePdfPreloader: All PDFs preloaded');
  }, [preloadPdf]);

  const getCachedPdf = useCallback((url: string): pdfjsLib.PDFDocumentProxy | null => {
    return globalPdfCache.get(url) || null;
  }, []);

  const getPrerenderedFirstPage = useCallback((url: string): HTMLCanvasElement | null => {
    return prerenderedFirstPages.get(url)?.canvas || null;
  }, []);

  const clearCache = useCallback(() => {
    console.log('usePdfPreloader: Clearing PDF cache');
    globalPdfCache.forEach(pdf => {
      try {
        pdf.destroy();
      } catch (err) {
        console.warn('Error destroying PDF:', err);
      }
    });
    globalPdfCache.clear();
    loadingPromises.clear();
    prerenderedFirstPages.clear();
  }, []);

  return {
    preloadPdf,
    preloadMultiplePdfs,
    getCachedPdf,
    getPrerenderedFirstPage,
    clearCache,
  };
};
