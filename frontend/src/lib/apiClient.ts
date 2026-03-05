/**
 * Digestor Unified - FastAPI HTTP Client
 * Replaces Supabase client for all API calls.
 */

const API_BASE = import.meta.env.VITE_API_URL || '/api';

interface RequestOptions extends RequestInit {
  params?: Record<string, string>;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private getAuthToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private async request<T>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { params, ...fetchOptions } = options;

    // Build URL with query params
    let url = `${this.baseUrl}${endpoint}`;
    if (params) {
      const searchParams = new URLSearchParams(params);
      url += `?${searchParams.toString()}`;
    }

    // Add auth header
    const token = this.getAuthToken();
    const headers: Record<string, string> = {
      ...(fetchOptions.headers as Record<string, string>),
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    // Add Content-Type for JSON bodies
    if (fetchOptions.body && !(fetchOptions.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, {
      ...fetchOptions,
      headers,
    });

    // Handle 401 or 403 — try token refresh (skip for auth endpoints)
    // Auth endpoints (login, register, etc.) return 401/403 for their own reasons
    // (wrong password, unverified email) — don't intercept those.
    const isAuthEndpoint = endpoint.startsWith('/auth/login')
      || endpoint.startsWith('/auth/register')
      || endpoint.startsWith('/auth/reset-password')
      || endpoint.startsWith('/auth/confirm-reset')
      || endpoint.startsWith('/auth/respond-challenge');

    if ((response.status === 401 || response.status === 403) && !isAuthEndpoint) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${this.getAuthToken()}`;
        const retryResponse = await fetch(url, { ...fetchOptions, headers });
        if (!retryResponse.ok) {
          throw new ApiError(retryResponse.status, await retryResponse.text());
        }
        return retryResponse.json();
      }
      // Refresh failed — clear tokens and redirect to home (login form renders at /)
      localStorage.removeItem('access_token');
      localStorage.removeItem('id_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/';
      throw new ApiError(401, 'Session expired');
    }

    if (!response.ok) {
      const errorText = await response.text();
      let errorDetail: string;
      try {
        const errorJson = JSON.parse(errorText);
        errorDetail = errorJson.detail || errorText;
      } catch {
        // If the response is HTML (e.g. ALB 502/504 error page), extract a clean message
        if (errorText.includes('<html') || errorText.includes('<!DOCTYPE')) {
          const titleMatch = errorText.match(/<title>(.*?)<\/title>/i);
          errorDetail = titleMatch ? titleMatch[1] : `Server error (HTTP ${response.status})`;
        } else {
          errorDetail = errorText;
        }
      }
      throw new ApiError(response.status, errorDetail);
    }

    return response.json();
  }

  private async refreshToken(): Promise<boolean> {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) return false;

    try {
      const response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) return false;

      const data = await response.json();
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('id_token', data.id_token);
      return true;
    } catch {
      return false;
    }
  }

  // --- Auth ---
  async login(email: string, password: string) {
    return this.request<any>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async register(email: string, password: string, fullName: string, organization?: string) {
    return this.request<any>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        full_name: fullName,
        organization,
      }),
    });
  }

  async respondChallenge(session: string, email: string, newPassword: string) {
    return this.request<any>('/auth/respond-challenge', {
      method: 'POST',
      body: JSON.stringify({ session, email, new_password: newPassword }),
    });
  }

  async resetPassword(email: string) {
    return this.request<any>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  async confirmReset(email: string, code: string, newPassword: string) {
    return this.request<any>('/auth/confirm-reset', {
      method: 'POST',
      body: JSON.stringify({
        email,
        confirmation_code: code,
        new_password: newPassword,
      }),
    });
  }

  async getMe() {
    return this.request<any>('/auth/me');
  }

  async logout() {
    try {
      await this.request<any>('/auth/logout', { method: 'POST' });
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('id_token');
      localStorage.removeItem('refresh_token');
    }
  }

  // --- Projects ---
  async listProjects(filters?: string | {
    status?: string;
    approval_status?: string[];
    sort_by?: string;
    sort_order?: string;
    page?: number;
    per_page?: number;
  }, page = 1, perPage = 20) {
    const params: Record<string, string> = {};
    if (typeof filters === 'string') {
      // Legacy: simple status string
      params.status = filters;
      params.page = String(page);
      params.per_page = String(perPage);
    } else if (filters) {
      if (filters.status) params.status = filters.status;
      if (filters.approval_status) params.approval_status = filters.approval_status.join(',');
      if (filters.sort_by) params.sort_by = filters.sort_by;
      if (filters.sort_order) params.sort_order = filters.sort_order;
      params.page = String(filters.page || page);
      params.per_page = String(filters.per_page || perPage);
    } else {
      params.page = String(page);
      params.per_page = String(perPage);
    }
    return this.request<any>('/projects', { params });
  }

  async createProject(name: string, description?: string) {
    return this.request<any>('/projects', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    });
  }

  async getProject(projectId: string) {
    return this.request<any>(`/projects/${projectId}`);
  }

  async updateProject(projectId: string, data: Record<string, any>) {
    return this.request<any>(`/projects/${projectId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteProject(projectId: string) {
    return this.request<any>(`/projects/${projectId}`, {
      method: 'DELETE',
    });
  }

  async submitProject(projectId: string) {
    return this.request<any>('/submit-project', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId }),
    });
  }

  async approveProject(projectId: string, approved: boolean, remarks?: string) {
    return this.request<any>('/approve-project', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, approved, remarks }),
    });
  }

  // --- Upload ---
  async uploadDocument(file: File, metadata: string | {
    projectHash?: string;
    projectName?: string;
    filesMetadata?: any[];
    project_id?: string;
  }) {
    const formData = new FormData();
    formData.append('file', file);
    if (typeof metadata === 'string') {
      formData.append('project_id', metadata);
    } else {
      if (metadata.project_id) formData.append('project_id', metadata.project_id);
      if (metadata.projectHash) formData.append('project_hash', metadata.projectHash);
      // Always send a project_name — generate a default if empty
      const projectName = metadata.projectName || `Project_${Date.now()}`;
      formData.append('project_name', projectName);
      if (metadata.filesMetadata) formData.append('files_metadata', JSON.stringify(metadata.filesMetadata));
    }
    return this.request<any>('/upload-document', {
      method: 'POST',
      body: formData,
    });
  }

  // --- Processing ---
  async processDocument(
    documentIdOrData: string | {
      document_id: string;
      extracted_text?: string;
      text_positions?: any[];
      processing_mode?: string;
      page_count?: number;
    },
    extractedText?: string,
  ) {
    let data: Record<string, any>;
    if (typeof documentIdOrData === 'string') {
      // Called as processDocument(documentId, extractedText)
      data = {
        document_id: documentIdOrData,
        extracted_text: extractedText || null,
      };
    } else {
      // Called as processDocument({ document_id, ... })
      data = documentIdOrData;
    }
    return this.request<any>('/process-document', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async processAws(documentId: string) {
    return this.request<any>('/process-aws', {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId }),
    });
  }

  // --- Combined Project Processing ---
  async processProject(data: {
    project_id: string;
    documents: Array<{ document_id: string; extracted_text: string }>;
    processing_mode?: string;
  }) {
    return this.request<any>('/process-project', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getProjectResults(projectId: string) {
    return this.request<any>(`/results/project/${projectId}`);
  }

  // --- Results ---
  async getResults(documentId: string) {
    return this.request<any>(`/results/${documentId}`);
  }

  async submitFeedback(data: {
    document_id: string;
    question_key: string;
    feedback_type: string;
    corrected_value?: string;
    remarks?: string;
  }) {
    return this.request<any>('/results/feedback', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateResult(data: {
    document_id: string;
    question_key: string;
    new_value: string;
    remarks?: string;
  }) {
    return this.request<any>('/results/update', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // --- Chat ---
  async chatWithDocument(documentId: string, message: string, history?: any[]) {
    return this.request<any>('/chat', {
      method: 'POST',
      body: JSON.stringify({
        document_id: documentId,
        message,
        conversation_history: history,
      }),
    });
  }

  // --- Profile ---
  async updateProfile(data: { full_name?: string }) {
    return this.request<any>('/auth/profile', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async changePassword(newPassword: string) {
    return this.request<any>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    });
  }

  async deleteAccount() {
    return this.request<any>('/auth/delete-account', {
      method: 'POST',
    });
  }

  // --- Tickets ---
  async createTicket(data: {
    title: string;
    description: string;
    type?: string;
    priority?: string;
    project_reference?: string;
    screenshot?: File;
  }) {
    const formData = new FormData();
    formData.append('title', data.title);
    formData.append('description', data.description);
    if (data.type) formData.append('type', data.type);
    if (data.priority) formData.append('priority', data.priority);
    if (data.project_reference) formData.append('project_reference', data.project_reference);
    if (data.screenshot) formData.append('screenshot', data.screenshot);
    return this.request<any>('/tickets', {
      method: 'POST',
      body: formData,
    });
  }

  async listTickets(status?: string) {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    return this.request<any>('/tickets', { params });
  }

  async listMyTickets() {
    return this.request<any>('/tickets/mine');
  }

  async updateTicket(ticketId: string, data: Record<string, any>) {
    return this.request<any>(`/tickets/${ticketId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // --- Feedback Surveys ---
  async getFeedbackSurvey() {
    return this.request<any>('/feedback/survey');
  }

  async saveFeedbackSurvey(data: Record<string, any>) {
    return this.request<any>('/feedback/survey', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async submitFeedbackSurvey(data: Record<string, any>) {
    return this.request<any>('/feedback/survey/submit', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // --- Notes ---
  async getProjectNotes(projectId: string) {
    return this.request<any>(`/projects/${projectId}/notes`);
  }

  async addProjectNote(projectId: string, text: string) {
    return this.request<any>(`/projects/${projectId}/notes`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  }

  async updateProjectNote(projectId: string, noteId: string, text: string) {
    return this.request<any>(`/projects/${projectId}/notes/${noteId}`, {
      method: 'PUT',
      body: JSON.stringify({ text }),
    });
  }

  async deleteProjectNote(projectId: string, noteId: string) {
    return this.request<any>(`/projects/${projectId}/notes/${noteId}`, {
      method: 'DELETE',
    });
  }

  // --- Remarks ---
  async getProjectRemarks(projectHash: string) {
    return this.request<any>(`/projects/remarks/${projectHash}`);
  }

  async createRemark(data: {
    project_hash: string;
    row_id: string;
    remark_text: string;
    created_by_user_id: string;
    created_by_full_name: string;
  }) {
    return this.request<any>('/projects/remarks', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateRemark(remarkId: string, data: { remark_text: string }) {
    return this.request<any>(`/projects/remarks/${remarkId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteRemark(remarkId: string) {
    return this.request<any>(`/projects/remarks/${remarkId}`, {
      method: 'DELETE',
    });
  }

  // --- Edit Notes / Result Edits (by row) ---
  async getEditNotes(projectHash: string, rowId: string) {
    return this.request<any>(`/projects/by-hash/${projectHash}/edits`, {
      params: { row_id: rowId, notes_only: 'true' },
    });
  }

  async getEditNotesPreview(projectHash: string, rowId: string) {
    return this.request<any>(`/projects/by-hash/${projectHash}/edits`, {
      params: { row_id: rowId, notes_only: 'true', preview: 'true' },
    });
  }

  // --- Document Text ---
  async getDocumentText(recordId: string) {
    return this.request<any>(`/projects/records/${recordId}/text`);
  }

  // --- Processing Metrics ---
  async getProcessingMetrics(recordId: string) {
    return this.request<any>(`/projects/records/${recordId}/metrics`);
  }

  // --- File URLs (S3 presigned) ---
  async getPresignedUrl(filePath: string) {
    return this.request<any>('/files/presigned-url', {
      params: { path: filePath },
    });
  }

  async getPresignedUrls(filePaths: string[]) {
    return this.request<any>('/files/presigned-urls', {
      method: 'POST',
      body: JSON.stringify({ paths: filePaths }),
    });
  }

  // --- Analytics ---
  async getAnalyticsOverview(days = 30) {
    return this.request<any>('/analytics/overview', {
      params: { days: String(days) },
    });
  }

  async getAnalyticsTrends(days = 30) {
    return this.request<any>('/analytics/trends', {
      params: { days: String(days) },
    });
  }

  // --- Admin ---
  async listUsers() {
    return this.request<any>('/admin/users');
  }

  async updateUserRole(userId: string, role: string) {
    return this.request<any>(`/admin/users/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role }),
    });
  }

  async getAdminSettings() {
    return this.request<any>('/admin/settings');
  }

  async updateAdminSettings(data: Record<string, any>) {
    return this.request<any>('/admin/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async listAllFeedback(status?: string) {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    return this.request<any>('/admin/feedback', { params });
  }

  async getEditAnalytics(params?: Record<string, string>) {
    return this.request<any>('/analytics/edits', { params });
  }

  // --- Project by Hash (for review workflows) ---
  async getProjectByHash(projectHash: string) {
    return this.request<any>(`/projects/by-hash/${projectHash}`);
  }

  async getProjectRecordsByHash(projectHash: string) {
    return this.request<any>(`/projects/by-hash/${projectHash}/records`);
  }

  async updateProjectById(recordId: string, data: Record<string, any>) {
    return this.request<any>(`/projects/records/${recordId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async updateProjectByHash(projectHash: string, data: Record<string, any>) {
    return this.request<any>(`/projects/by-hash/${projectHash}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteProjectById(recordId: string) {
    return this.request<any>(`/projects/records/${recordId}`, {
      method: 'DELETE',
    });
  }

  // --- Pending Projects (Waiting for Approval) ---
  async listPendingProjects() {
    return this.request<any>('/projects/pending');
  }

  // --- Edit History / Result Edits ---
  async getEditHistory(projectHash: string) {
    return this.request<any>(`/projects/by-hash/${projectHash}/edits`);
  }

  async createResultEdit(data: Record<string, any>) {
    return this.request<any>('/projects/result-edits', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // --- Users for Assignment ---
  async getUsersForAssignment() {
    return this.request<any>('/admin/users/for-assignment');
  }

  // --- Finalized Project (replaces edge functions) ---
  async getFinalizedProject(projectKey: string, version?: number) {
    const params: Record<string, string> = { project_key: projectKey };
    if (version) params.version = String(version);
    return this.request<any>('/projects/finalized', { params });
  }

  async repairProject(projectHash: string, version?: number) {
    return this.request<any>('/projects/repair', {
      method: 'POST',
      body: JSON.stringify({ projectHash, version }),
    });
  }

  async updateApprovedProject(projectHash: string, snapshotJson: any[], version: number) {
    return this.request<any>('/projects/update-approved', {
      method: 'POST',
      body: JSON.stringify({ projectHash, snapshotJson, version }),
    });
  }

  // --- Submit Project (full payload, replaces edge function) ---
  async submitProjectForApproval(data: Record<string, any>) {
    return this.request<any>('/submit-project', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

// Singleton instance
const apiClient = new ApiClient(API_BASE);
export default apiClient;
