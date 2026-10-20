export interface Skill {
  id: string;
  name: string;
}

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

export interface Candidate {
  id: string;
  name: string;
  title: string;
  experience: string;
  skills: string[];
  matchScore: number;
  avatar: string;
  contact?: string;
}

export interface JobMatchingResult {
  postingId: string;
  candidates: Candidate[];
}
