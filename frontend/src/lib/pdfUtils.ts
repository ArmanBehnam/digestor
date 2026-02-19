import apiClient from "@/lib/apiClient";
import * as pdfjsLib from "pdfjs-dist";

// Configure PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;

export interface FileMetadata {
  name: string;
  file_name?: string;
  path?: string;
  file_path?: string;
  size?: number;
  type?: string;
  signedUrl?: string;
  urlExpiresAt?: string;
  pageCount?: number;
}

export interface SignedUrlResult {
  fileName: string;
  signedUrl: string;
  expiresAt: string;
  pageCount?: number;
}

// Cache for page counts to avoid refetching
const pageCountCache = new Map<string, number>();

/**
 * Gets the page count of a PDF from its URL using pdf.js
 * Uses minimal fetch to only load the document header
 */
async function getPdfPageCount(url: string): Promise<number | undefined> {
  // Check cache first
  if (pageCountCache.has(url)) {
    return pageCountCache.get(url);
  }

  try {
    const loadingTask = pdfjsLib.getDocument({
      url,
      // Only load metadata, not full pages
      disableAutoFetch: true,
      disableStream: true,
    });

    const pdf = await loadingTask.promise;
    const numPages = pdf.numPages;

    // Cache the result
    pageCountCache.set(url, numPages);

    // Clean up
    await pdf.destroy();

    return numPages;
  } catch (error) {
    console.error("Error getting PDF page count:", error);
    return undefined;
  }
}

/**
 * Generates fresh signed URLs for PDF files via S3 presigned URLs
 * Signed URLs expire after 1 hour by default
 * Also detects page counts using pdf.js if not already available
 */
export async function generateSignedUrls(
  filesMetadata: FileMetadata[]
): Promise<SignedUrlResult[]> {
  if (!filesMetadata || filesMetadata.length === 0) {
    return [];
  }

  const pdfFiles = filesMetadata.filter((f) =>
    (f.name || f.file_name || "").toLowerCase().endsWith(".pdf")
  );

  const signedUrlPromises = pdfFiles.map(async (file) => {
    const filePath = file.path || file.file_path;

    if (!filePath) {
      console.error("No file path for:", file);
      return null;
    }

    try {
      // Generate S3 presigned URL via backend
      const data = await apiClient.getPresignedUrl(filePath);

      if (!data?.signed_url) {
        console.error("No signed URL returned for", filePath);
        return null;
      }

      const expiresAt = data.expires_at || new Date(Date.now() + 3600 * 1000).toISOString();

      // Get page count - use existing if available, otherwise detect
      let pageCount = file.pageCount;
      if (!pageCount) {
        pageCount = await getPdfPageCount(data.signed_url);
      }

      return {
        fileName: file.name || file.file_name || "unknown.pdf",
        signedUrl: data.signed_url,
        expiresAt,
        pageCount,
      };
    } catch (err) {
      console.error("Exception generating signed URL for", filePath, err);
      return null;
    }
  });

  const results = await Promise.all(signedUrlPromises);
  return results.filter((r) => r !== null) as SignedUrlResult[];
}

/**
 * Checks if a signed URL has expired
 */
export function isSignedUrlExpired(expiresAt?: string): boolean {
  if (!expiresAt) return true;
  return new Date(expiresAt) <= new Date();
}

/**
 * Gets or refreshes signed URLs, checking expiration
 */
export async function getRefreshedSignedUrls(
  filesMetadata: FileMetadata[]
): Promise<SignedUrlResult[]> {
  // Check if existing URLs are expired
  const needsRefresh = filesMetadata.some(
    (f) => !f.signedUrl || isSignedUrlExpired(f.urlExpiresAt)
  );

  if (needsRefresh) {
    console.log("Signed URLs expired or missing, regenerating...");
    return await generateSignedUrls(filesMetadata);
  }

  // Return existing signed URLs if still valid
  const validUrls: SignedUrlResult[] = filesMetadata
    .filter(
      (f) =>
        (f.name || f.file_name || "").toLowerCase().endsWith(".pdf") &&
        f.signedUrl
    )
    .map((f) => ({
      fileName: f.name || f.file_name || "unknown.pdf",
      signedUrl: f.signedUrl!,
      expiresAt: f.urlExpiresAt || "",
      pageCount: f.pageCount,
    }));

  return validUrls;
}
