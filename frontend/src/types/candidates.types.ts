/**
 * Candidate-related types
 */

export type CandidateStatus = 'pending' | 'interviewing' | 'hired' | 'rejected';
export type CandidateStatusFilter = 'all' | CandidateStatus;
 
export interface Candidate {
  candidate_id: string;
  identity_id?: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  seniority_level: string;
  total_years_experience: number;
  extraction_confidence: number | null;
  skills: string[];
  filename: string;
  created_at: string;
  status?: CandidateStatus;
  summary?: string | null;
  linkedin?: string | null;
  github?: string | null;
  languages?: string[];
}

export interface CandidateListFilters {
  search?: string;
  status?: CandidateStatusFilter;
}

export interface CandidateGroup {
  identity_id: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  cv_count: number;
  candidates: Candidate[];
}

export interface PaginatedCandidates {
  items: CandidateGroup[];
  total: number;
  limit: number;
  offset: number;
}
