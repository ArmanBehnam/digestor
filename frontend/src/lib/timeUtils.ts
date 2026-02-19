/**
 * Formats decimal minutes to "X min Y sec" format
 * @param decimalMinutes - Time in decimal minutes (e.g., 2.81)
 * @returns Formatted string (e.g., "2 min 49 sec")
 */
export function formatProcessedTime(decimalMinutes: number): string {
  const minutes = Math.floor(decimalMinutes);
  const seconds = Math.round((decimalMinutes - minutes) * 60);
  return `${minutes} min ${seconds} sec`;
}
