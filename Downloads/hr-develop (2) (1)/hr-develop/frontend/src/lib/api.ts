import { Candidate, CandidateStatus, PaginatedCandidates } from '../types/candidates.types';

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export interface JobPosting {
  job_id: string;
  title: string;
  description: string | null;
  department: string | null;
  location: string | null;
  employment_type: string;
  required_skills: string[];
  preferred_skills: string[];
  min_years_experience: number | null;
  max_years_experience: number | null;
  seniority_level: string | null;
  nb_positions: number | null;
  status: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CandidateMatch {
  candidate_id:         string;
  name:                 string;
  email:                string | null;
  experience:           string;
  skill:                string;
  status:               string;
  score:                number;
  skill_score:          number;
  seniority_multiplier: number;
  final_score:          number;
  seniority_gap:        number;
  matched_skills:       string[];
  missing_skills:       string[];
  ai_description:       string;
  key_strengths:        string[];
  key_weaknesses:       string[];
  recommendation:       string;
  scoring_time_s:       number;
}

export interface MatchingResponse {
  job_id:                  string;
  job_title:               string;
  total_candidates:        number;
  matched_candidates:      CandidateMatch[];
  recruiter_advice:        string;
  total_processing_time_s: number;
}

export interface CreateJobPostingRequest {
  title: string;
  description?: string;
  department?: string;
  location?: string;
  employment_type?: string;
  required_skills?: string[];
  preferred_skills?: string[];
  min_years_experience?: number;
  max_years_experience?: number;
  seniority_level?: string;
  created_by?: string;
  nb_positions?: number;
}

// ─────────────────────────────────────────────────────────────
// Job Postings API
// ─────────────────────────────────────────────────────────────

export async function fetchJobPostings(status?: string): Promise<JobPosting[]> {
  const url = new URL('/api/v1/postings', window.location.origin);
  if (status) {
    url.searchParams.set('status', status);
  }
  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`Failed to fetch job postings: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchJobPosting(jobId: string): Promise<JobPosting> {
  const response = await fetch(`/api/v1/postings/${jobId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch job posting: ${response.statusText}`);
  }
  return response.json();
}

export async function createJobPosting(data: CreateJobPostingRequest): Promise<JobPosting> {
  const response = await fetch('/api/v1/postings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const err: Error & { status?: number; detail?: unknown } = new Error(
      (typeof body?.detail === 'object' ? body.detail?.message : body?.detail) ||
        `Failed to create job posting: ${response.statusText}`
    );
    err.status = response.status;
    err.detail = body?.detail;
    throw err;
  }
  return response.json();
}

export async function matchCandidatesForJob(
  jobId: string,
  options?: { top_k?: number; min_score?: number; lang?: string }
): Promise<MatchingResponse> {
  const url = new URL(`/api/v1/postings/${jobId}/match`, window.location.origin);
  if (options?.top_k) {
    url.searchParams.set('top_k', options.top_k.toString());
  }
  if (options?.min_score !== undefined) {
    url.searchParams.set('min_score', options.min_score.toString());
  }
  if (options?.lang) {
    url.searchParams.set('lang', options.lang);
  }
  const response = await fetch(url.toString());
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to match candidates: ${response.statusText}`);
  }
  return response.json();
}

// Streamed counterpart: same pipeline as matchCandidatesForJob, but pushes
// each candidate over a WebSocket as soon as it's scored — onCandidate is
// called progressively, and the returned promise resolves with the final
// sorted/trimmed MatchingResponse once the server sends 'done'.
export function matchCandidatesForJobStream(
  jobId: string,
  options: { top_k?: number; min_score?: number; lang?: string } | undefined,
  onCandidate: (candidate: CandidateMatch) => void,
): Promise<MatchingResponse> {
  return new Promise((resolve, reject) => {
    const url = new URL(`/api/v1/postings/${jobId}/match/ws`, window.location.origin);
    if (options?.top_k) url.searchParams.set('top_k', options.top_k.toString());
    if (options?.min_score !== undefined) url.searchParams.set('min_score', options.min_score.toString());
    if (options?.lang) url.searchParams.set('lang', options.lang);

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}${url.pathname}${url.search}`);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === 'candidate_scored') {
          onCandidate(msg.data as CandidateMatch);
        } else if (msg.event === 'done') {
          resolve(msg.data as MatchingResponse);
          ws.close();
        } else if (msg.event === 'error') {
          reject(new Error(msg.data?.message || 'Matching failed'));
          ws.close();
        }
      } catch (err) {
        reject(err as Error);
      }
    };

    ws.onerror = () => reject(new Error('WebSocket error during matching'));
  });
}

export async function recalculateMatchForJob(
  jobId: string,
  options?: { top_k?: number; min_score?: number; lang?: string }
): Promise<MatchingResponse> {
  const url = new URL(`/api/v1/postings/${jobId}/recalculate`, window.location.origin);
  if (options?.top_k) {
    url.searchParams.set('top_k', options.top_k.toString());
  }
  if (options?.min_score !== undefined) {
    url.searchParams.set('min_score', options.min_score.toString());
  }
  if (options?.lang) {
    url.searchParams.set('lang', options.lang);
  }
  const response = await fetch(url.toString(), { method: 'POST' });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to recalculate: ${response.statusText}`);
  }
  return response.json();
}

export async function updateJobStatus(jobId: string, status: string): Promise<JobPosting> {
  const response = await fetch(`/api/v1/postings/${jobId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) {
    throw new Error(`Failed to update job status: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteJobPosting(jobId: string): Promise<void> {
  const response = await fetch(`/api/v1/postings/${jobId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(`Failed to delete job posting: ${response.statusText}`);
  }
}

// ─────────────────────────────────────────────────────────────
// Candidates API
// ─────────────────────────────────────────────────────────────

export async function fetchCandidates(params?: {
  search?: string;
  status?: CandidateStatus;
  limit?: number;
  offset?: number;
}): Promise<PaginatedCandidates> {
  const url = new URL('/api/v1/candidates', window.location.origin);
  if (params?.search) url.searchParams.set('search', params.search);
  if (params?.status) url.searchParams.set('status', params.status);
  if (params?.limit !== undefined) url.searchParams.set('limit', params.limit.toString());
  if (params?.offset !== undefined) url.searchParams.set('offset', params.offset.toString());
  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`Failed to fetch candidates: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchCandidate(candidateId: string): Promise<Candidate> {
  const response = await fetch(`/api/v1/candidates/${candidateId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch candidate: ${response.statusText}`);
  }
  return response.json();
}

// ─────────────────────────────────────────────────────────────
// Dashboard API
// ─────────────────────────────────────────────────────────────

export interface DashboardStats {
  activeCandidates: number;
  cvsScreened: number;
  hiredCandidates: number;
  avgDaysToHire: number;
}

export interface DepartmentData {
  label: string;
  value: number;
}

export interface TrendData {
  label: string;
  value: number;
  interviews: number;
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const response = await fetch('/api/v1/dashboard/stats');
  if (!response.ok) {
    throw new Error(`Failed to fetch dashboard stats: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchDepartments(): Promise<DepartmentData[]> {
  const response = await fetch('/api/v1/dashboard/departments');
  if (!response.ok) {
    throw new Error(`Failed to fetch departments: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchTrends(period?: string): Promise<TrendData[]> {
  const url = new URL('/api/v1/dashboard/trends', window.location.origin);
  if (period) {
    url.searchParams.set('period', period);
  }
  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`Failed to fetch trends: ${response.statusText}`);
  }
  return response.json();
}

export interface TeamMember {
  id: number;
  full_name: string;
  email: string;
  role: string;
  initials: string;
}

export async function fetchDashboardTeam(): Promise<TeamMember[]> {
  const response = await fetch('/api/v1/dashboard/team');
  if (!response.ok) {
    throw new Error(`Failed to fetch team: ${response.statusText}`);
  }
  return response.json();
}

export interface StatusSeries {
  labels: string[];
  received: number[];
  interview: number[];
  hired: number[];
}

export async function fetchStatusByMonth(year: number): Promise<StatusSeries> {
  const response = await fetch(`/api/v1/dashboard/status-by-month?year=${year}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch status by month: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchStatusByDay(year: number, month: number): Promise<StatusSeries> {
  const response = await fetch(`/api/v1/dashboard/status-by-day?year=${year}&month=${month}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch status by day: ${response.statusText}`);
  }
  return response.json();
}

export interface InterviewItem {
  interview_id: string;
  candidate_id: string;
  job_posting_id: string | null;
  interview_date: string;
  interview_time: string;
  duration_min: number;
  format: string;
  platform: string | null;
  meeting_link: string | null;
  room_id: string | null;
  room_name: string | null;
  status: string;
  interviewer_name: string | null;
  notes: string | null;
  candidate_name: string | null;
  job_title: string | null;
}

export async function fetchInterviews(): Promise<InterviewItem[]> {
  const response = await fetch('/api/v1/interviews');
  if (!response.ok) {
    throw new Error(`Failed to fetch interviews: ${response.statusText}`);
  }
  return response.json();
}
