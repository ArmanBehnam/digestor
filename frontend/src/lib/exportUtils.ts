import apiClient from "@/lib/apiClient";
import { exportAnswer } from "@/lib/displayUtils";

/**
 * Fetch fresh remarks for a project from the backend API
 * Grouped by row_id for efficient lookup
 */
export async function fetchProjectRemarks(projectHash: string): Promise<Map<string, any[]>> {
  try {
    const data = await apiClient.getProjectRemarks(projectHash);
    const remarks = data?.remarks || [];

    const remarksByRow = new Map<string, any[]>();
    remarks.forEach((remark: any) => {
      if (!remarksByRow.has(remark.row_id)) {
        remarksByRow.set(remark.row_id, []);
      }
      remarksByRow.get(remark.row_id)!.push(remark);
    });

    return remarksByRow;
  } catch (error) {
    console.error("Error fetching remarks:", error);
    return new Map();
  }
}

/**
 * Format a date and time for CSV remarks display (e.g., "Jan 15, 2024 - 10:30 AM")
 */
function formatRemarkDateTime(dateString: string): string {
  const date = new Date(dateString);
  const datePart = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
  const timePart = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });
  return `${datePart} - ${timePart}`;
}

/**
 * Format remarks for CSV export (single string with author and timestamp)
 */
export function formatRemarksForCSV(remarks: any[]): string {
  return remarks
    .map((r: any) => `[${r.created_by_full_name} - ${formatRemarkDateTime(r.created_at)}]: ${r.remark_text}`)
    .join(" | ");
}

/**
 * Format remarks for JSON export (array of structured objects)
 */
export function formatRemarksForJSON(remarks: any[]): any[] {
  return remarks.map((r: any) => ({
    author: r.created_by_full_name,
    text: r.remark_text,
    created_at: r.created_at,
  }));
}

/**
 * Escape a value for safe CSV inclusion
 */
export function escapeCSV(val: any): string {
  const strVal = String(val ?? "");
  if (strVal.includes(",") || strVal.includes('"') || strVal.includes("\n") || strVal.includes("\r")) {
    return `"${strVal.replace(/"/g, '""')}"`;
  }
  return strVal;
}

/**
 * Generate fresh CSV content with latest remarks from database
 */
export async function generateFreshCSV(
  projectHash: string,
  snapshotData: any[],
  options?: { includeHeaders?: boolean }
): Promise<string> {
  const remarksByRow = await fetchProjectRemarks(projectHash);
  const includeHeaders = options?.includeHeaders !== false;

  const headers = [
    "ID",
    "Category",
    "Question",
    "Extracted Answer",
    "Normalized Answer",
    "Unit",
    "Reference",
    "Confidence",
    "AI Extraction Accuracy",
    "Remarks"
  ];

  const rows = snapshotData
    .filter((row: any) => {
      if (row.is_not_applicable === true) return false;
      if (row.excluded || row.deleted) return false;

      const answersForQuestion = snapshotData.filter(
        (r: any) => r.question_id === row.question_id && !r.excluded && !r.deleted && !r.is_not_applicable
      );

      if (answersForQuestion.length === 1) return true;

      const hasExplicitSelection = answersForQuestion.some((r: any) => r.is_selected === true);

      if (hasExplicitSelection) {
        return row.is_selected === true;
      } else {
        const sortedAnswers = [...answersForQuestion].sort((a, b) => {
          const aIndex = parseInt(a.row_id?.split('-')[1] || '0');
          const bIndex = parseInt(b.row_id?.split('-')[1] || '0');
          return aIndex - bIndex;
        });
        return row.row_id === sortedAnswers[0]?.row_id;
      }
    })
    .map((row: any) => {
      const rowId = row.row_id || row.id || "";
      const rowRemarks = remarksByRow.get(rowId) || [];
      const remarksText = formatRemarksForCSV(rowRemarks);

      return [
        row.question_id || "",
        row.category || "",
        row.question || "",
        exportAnswer(row.extracted_answer) || "",
        exportAnswer(row.normalized_answer) || "",
        row.unit || "",
        exportAnswer(row.reference) || "",
        row.confidence ? `${(Number(row.confidence) * 100).toFixed(0)}%` : "",
        row.feedback || "",
        remarksText,
      ].map(escapeCSV).join(",");
    });

  return includeHeaders ? [headers.join(","), ...rows].join("\n") : rows.join("\n");
}

/**
 * Generate fresh JSON content with latest remarks from database
 */
export async function generateFreshJSON(
  projectHash: string,
  snapshotData: any[],
  projectMeta: {
    project_name?: string;
    project_id?: string;
    finalized_at?: string;
    files_metadata?: any[];
  }
): Promise<string> {
  const remarksByRow = await fetchProjectRemarks(projectHash);

  const results = snapshotData
    .filter((row: any) => {
      if (row.is_not_applicable === true) return false;
      if (row.excluded || row.deleted) return false;

      const answersForQuestion = snapshotData.filter(
        (r: any) => r.question_id === row.question_id && !r.excluded && !r.deleted && !r.is_not_applicable
      );

      if (answersForQuestion.length === 1) return true;

      const hasExplicitSelection = answersForQuestion.some((r: any) => r.is_selected === true);

      if (hasExplicitSelection) {
        return row.is_selected === true;
      } else {
        const sortedAnswers = [...answersForQuestion].sort((a, b) => {
          const aIndex = parseInt(a.row_id?.split('-')[1] || '0');
          const bIndex = parseInt(b.row_id?.split('-')[1] || '0');
          return aIndex - bIndex;
        });
        return row.row_id === sortedAnswers[0]?.row_id;
      }
    })
    .map((row: any) => {
      const rowId = row.row_id || row.id || "";
      const rowRemarks = remarksByRow.get(rowId) || [];

      return {
        id: row.question_id || null,
        category: row.category || "",
        question: row.question || "",
        extracted_answer: exportAnswer(row.extracted_answer) || "",
        normalized_answer: exportAnswer(row.normalized_answer) || "",
        unit: row.unit || "",
        reference: exportAnswer(row.reference) || "",
        confidence: row.confidence ? Number(row.confidence) * 100 : null,
        feedback: row.feedback || null,
        row_id: rowId,
        is_edited: row.is_edited || false,
        remarks: formatRemarksForJSON(rowRemarks),
      };
    });

  return JSON.stringify({
    project_id: projectMeta.project_id,
    project_name: projectMeta.project_name,
    project_hash: projectHash,
    finalized_at: projectMeta.finalized_at,
    files: projectMeta.files_metadata || [],
    results,
  }, null, 2);
}

/**
 * Download content as a file
 */
export function downloadContent(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Generate and download fresh CSV with latest remarks
 */
export async function downloadFreshCSV(
  projectHash: string,
  snapshotData: any[],
  filename: string
): Promise<void> {
  const csvContent = await generateFreshCSV(projectHash, snapshotData);
  downloadContent(csvContent, filename, "text/csv;charset=utf-8");
}

/**
 * Generate and download fresh JSON with latest remarks
 */
export async function downloadFreshJSON(
  projectHash: string,
  snapshotData: any[],
  projectMeta: {
    project_name?: string;
    project_id?: string;
    finalized_at?: string;
    files_metadata?: any[];
  },
  filename: string
): Promise<void> {
  const jsonContent = await generateFreshJSON(projectHash, snapshotData, projectMeta);
  downloadContent(jsonContent, filename, "application/json;charset=utf-8");
}

/**
 * Export project results with fresh remarks (for ProjectsHistory fallback)
 */
export async function exportProjectResultsWithRemarks(
  projectHash: string,
  projectName: string,
  processedAt: string,
  filesMetadata: any,
  results: any[]
): Promise<void> {
  const remarksByRow = await fetchProjectRemarks(projectHash);

  const transformedResults = results.map((result: any) => {
    const rowId = result.row_id || result.id || "";
    const rowRemarks = remarksByRow.get(rowId) || [];

    return {
      ...result,
      answer: exportAnswer(result.answer),
      normalizedAnswer: exportAnswer(result.normalizedAnswer || result.answer),
      reference: exportAnswer(result.reference),
      remarks: formatRemarksForJSON(rowRemarks),
    };
  });

  const dataStr = JSON.stringify({
    project_name: projectName,
    project_hash: projectHash,
    processed_at: processedAt,
    files: filesMetadata,
    results: transformedResults,
  }, null, 2);

  downloadContent(dataStr, `${projectName.replace(/[^a-z0-9]/gi, "_")}_results.json`, "application/json;charset=utf-8");
}
