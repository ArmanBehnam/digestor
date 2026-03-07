/**
 * Centralized Reference Navigation Utilities
 * 
 * This module provides structured reference data handling and navigation
 * to eliminate brittle string parsing and ensure reliable PDF navigation.
 */

export interface StructuredReference {
  fileIndex: number;
  fileName: string;
  page: number;
  bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

export interface PDFFile {
  name: string;
  url?: string;
  path?: string;
  pageCount?: number;
}

/**
 * Parse reference string to extract page number
 * Handles formats: "Page 9", "Pages 1-8" (returns first page)
 */
export function parseReferencePage(referenceText: string): number | null {
  if (!referenceText) return null;
  
  // Try "Page X" format first
  const singlePageMatch = referenceText.match(/Page\s+(\d+)/i);
  if (singlePageMatch) {
    return parseInt(singlePageMatch[1], 10);
  }
  
  // Try "Pages X-Y" format - use first page
  const pagesMatch = referenceText.match(/Pages?\s+(\d+)/i);
  if (pagesMatch) {
    return parseInt(pagesMatch[1], 10);
  }
  
  return null;
}

/**
 * Parse filename from reference string
 * Handles format: "filename.pdf, Page 9"
 */
export function parseReferenceFilename(referenceText: string): string | null {
  if (!referenceText) return null;
  
  // Match everything before ", Page" or end of string that ends with .pdf
  const match = referenceText.match(/^([^,]+\.pdf)/i);
  return match ? match[1].trim() : null;
}

/**
 * Flexible file matching - finds the index of a file in the array
 * Uses multiple strategies: exact match, partial match, normalized match
 */
export function findFileIndex(
  fileName: string,
  files: PDFFile[]
): number {
  if (!fileName || !files || files.length === 0) return -1;
  
  const normalizedTarget = fileName.toLowerCase().trim();
  
  // Strategy 1: Exact match
  let index = files.findIndex(f => 
    f.name.toLowerCase().trim() === normalizedTarget
  );
  if (index !== -1) return index;
  
  // Strategy 2: Target contains file name or vice versa
  index = files.findIndex(f => {
    const normalizedName = f.name.toLowerCase().trim();
    return normalizedName.includes(normalizedTarget) || 
           normalizedTarget.includes(normalizedName);
  });
  if (index !== -1) return index;
  
  // Strategy 3: Match by removing common prefixes/suffixes
  const cleanTarget = normalizedTarget.replace(/^\d+[-_]\s*/, '').replace(/\s*\(\d+\)$/, '');
  index = files.findIndex(f => {
    const cleanName = f.name.toLowerCase().trim().replace(/^\d+[-_]\s*/, '').replace(/\s*\(\d+\)$/, '');
    return cleanName.includes(cleanTarget) || cleanTarget.includes(cleanName);
  });
  
  return index;
}

/**
 * Build a structured reference from pair data and file list
 * Uses structured bbox if available, falls back to parsing reference string
 */
export function buildStructuredReference(
  pair: {
    reference: string;
    bbox?: { x: number; y: number; width: number; height: number };
  },
  files: PDFFile[],
  defaultFileIndex?: number
): StructuredReference | null {
  if (!pair.reference || pair.reference === 'Not Found' || pair.reference === 'Not Available') {
    return null;
  }

  const page = parseReferencePage(pair.reference);
  if (!page) return null;

  const fileName = parseReferenceFilename(pair.reference);
  if (fileName) {
    const fileIndex = findFileIndex(fileName, files);
    if (fileIndex === -1) return null;
    return {
      fileIndex,
      fileName: files[fileIndex].name,
      page,
      bbox: pair.bbox,
    };
  }

  // No filename in reference (e.g. "Page 3") — use default file index
  const fallbackIndex = files.length === 1 ? 0 : (defaultFileIndex ?? 0);
  if (fallbackIndex >= 0 && fallbackIndex < files.length) {
    return {
      fileIndex: fallbackIndex,
      fileName: files[fallbackIndex].name,
      page,
      bbox: pair.bbox,
    };
  }
  return null;
}

/**
 * Build a structured reference from a row in the snapshot (approved projects)
 */
export function buildStructuredReferenceFromRow(
  row: {
    reference: string;
    reference_metadata?: { x: number; y: number; width: number; height: number };
  },
  files: PDFFile[],
  defaultFileIndex?: number
): StructuredReference | null {
  if (!row.reference || row.reference === 'Not Found' || row.reference === 'Not Available') {
    return null;
  }

  const page = parseReferencePage(row.reference);
  if (!page) return null;

  const fileName = parseReferenceFilename(row.reference);
  if (fileName) {
    const fileIndex = findFileIndex(fileName, files);
    if (fileIndex === -1) return null;
    return {
      fileIndex,
      fileName: files[fileIndex].name,
      page,
      bbox: row.reference_metadata,
    };
  }

  // No filename in reference — use default file index
  const fallbackIndex = files.length === 1 ? 0 : (defaultFileIndex ?? 0);
  if (fallbackIndex >= 0 && fallbackIndex < files.length) {
    return {
      fileIndex: fallbackIndex,
      fileName: files[fallbackIndex].name,
      page,
      bbox: row.reference_metadata,
    };
  }
  return null;
}

/**
 * Wait for PDF viewer to be ready and execute navigation
 * Uses event-based approach with fallback polling
 */
export async function waitForPdfReady(
  timeoutMs: number = 5000,
  checkIntervalMs: number = 50
): Promise<boolean> {
  return new Promise((resolve) => {
    // Check if already ready
    if (typeof (window as any).jumpToPdfLocation === 'function') {
      resolve(true);
      return;
    }
    
    let waited = 0;
    
    // Listen for ready event
    const handleReady = () => {
      window.removeEventListener('pdf-viewer-ready', handleReady);
      resolve(true);
    };
    window.addEventListener('pdf-viewer-ready', handleReady);
    
    // Fallback polling
    const pollInterval = setInterval(() => {
      waited += checkIntervalMs;
      
      if (typeof (window as any).jumpToPdfLocation === 'function') {
        clearInterval(pollInterval);
        window.removeEventListener('pdf-viewer-ready', handleReady);
        resolve(true);
        return;
      }
      
      if (waited >= timeoutMs) {
        clearInterval(pollInterval);
        window.removeEventListener('pdf-viewer-ready', handleReady);
        resolve(false);
      }
    }, checkIntervalMs);
  });
}

/**
 * Execute navigation to a PDF location
 */
export function jumpToPdfLocation(
  page: number,
  bbox?: { x: number; y: number; width: number; height: number }
): void {
  if (typeof (window as any).jumpToPdfLocation === 'function') {
    const location = {
      page,
      x: bbox?.x ?? 0,
      y: bbox?.y ?? 0,
      width: bbox?.width ?? 0,
      height: bbox?.height ?? 0,
    };
    (window as any).jumpToPdfLocation(location);
  }
}
