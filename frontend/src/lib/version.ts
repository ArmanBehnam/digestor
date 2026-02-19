// Application version - Update this value for each release
export const APP_VERSION = "2.2";

// Version timestamp in mm-dd-yyyy-hh:mm format
// Updated each time the codebase is saved/bookmarked
export const VERSION_TIMESTAMP = "01-22-2026-14:30";

// Short version for display: vx.x
export const VERSION_DISPLAY = `v${APP_VERSION}`;

// Tooltip message for last updated
export const VERSION_TOOLTIP = `Last Updated on ${VERSION_TIMESTAMP}`;

// Version history - Admin only (newest first)
export interface VersionEntry {
  version: string;
  timestamp: string;
  note?: string;
}

export const VERSION_HISTORY: VersionEntry[] = [
  { version: "2.2", timestamp: "01-22-2026-14:30", note: "Added version history tooltip for admins" },
  { version: "2.1", timestamp: "01-12-2026-19:30", note: "Initial release" },
];
