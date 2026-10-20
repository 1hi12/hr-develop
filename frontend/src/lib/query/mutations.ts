import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { queryKeys } from './queryKeys';
import { createJobPosting, fetchCandidates } from '../api';
import { CreateJobPostingRequest, JobPosting } from '../../types/postings.types';
import { Candidate, CandidateStatus, PaginatedCandidates } from '../../types/candidates.types';
import { fetchDashboardStats, fetchDepartments, fetchTrends, fetchDashboardTeam, fetchStatusByMonth, fetchStatusByDay, fetchInterviews } from '../api';
import { MatchingResponse } from '../api';

const apiClient = {
  postJobPosting: async (data: CreateJobPostingRequest): Promise<JobPosting> => {
    // Use the centralized API client
    return createJobPosting(data);
  },

  updateJobPostingStatus: async (id: string, status: 'active' | 'draft' | 'closed'): Promise<JobPosting> => {
    const response = await fetch(`/api/v1/postings/${id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    if (!response.ok) {
      throw new Error('Failed to update job posting status');
    }
    return response.json();
  },

  updateCandidateStatus: async (id: string, status: CandidateStatus, jobPostingId?: string): Promise<Candidate> => {
    const response = await fetch(`/api/v1/candidates/${id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, ...(jobPostingId ? { job_posting_id: jobPostingId } : {}) }),
    });
    if (!response.ok) {
      throw new Error('Failed to update candidate status');
    }
    return response.json();
  },
};

export const useCreateJobPostingMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: apiClient.postJobPosting,
    onSuccess: () => {
      // Refresh postings list + job matching sidebar + dashboard departments donut
      queryClient.invalidateQueries({ queryKey: queryKeys.postings.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all });
    },
  });
};

export const useUpdateJobPostingStatusMutation = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: 'active' | 'draft' | 'closed' }) => {
      return apiClient.updateJobPostingStatus(id, status);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.postings.all });
    },
  });
};

export const useDeleteJobPostingMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const response = await fetch(`/api/v1/postings/${id}`, { method: 'DELETE' });
      if (!response.ok) throw new Error('Failed to delete job posting');
      return id;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.postings.all });
    },
  });
};

// ─────────────────────────────────────────────────────────────
// Candidates Query Hooks
// ─────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

export function useCandidates(params?: {
  search?: string;
  status?: CandidateStatus;
  page?: number;
  limit?: number;
}) {
  const page = params?.page ?? 1;
  const limit = params?.limit ?? PAGE_SIZE;
  const offset = (page - 1) * limit;

  return useQuery<PaginatedCandidates>({
    queryKey: queryKeys.candidates.list({ ...params, page }),
    queryFn: () => fetchCandidates({
      search: params?.search,
      status: params?.status,
      limit,
      offset,
    }),
  });
}

/**
 * Hook to update candidate status
 */
export const useUpdateCandidateStatusMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, status, jobPostingId }: { id: string; status: CandidateStatus; jobPostingId?: string }) => {
      return apiClient.updateCandidateStatus(id, status, jobPostingId) as Promise<Candidate & { email_sent?: boolean; email_error?: string }>;
    },
    onSuccess: (updatedCandidate: Candidate & { email_sent?: boolean; email_error?: string }, variables) => {
      // Show email notification
      if (variables.status === 'hired') {
        if (updatedCandidate.email_sent) {
          toast.success('Email d\'acceptation envoyé au candidat');
        } else if (updatedCandidate.email_error) {
          toast.warning(`Email non envoyé : ${updatedCandidate.email_error}`);
        }
      } else if (variables.status === 'rejected') {
        if (updatedCandidate.email_sent) {
          toast.success('Email de refus envoyé au candidat');
        } else if (updatedCandidate.email_error) {
          toast.warning(`Email non envoyé : ${updatedCandidate.email_error}`);
        }
      }
      // 1. Update the specific job matching cache directly
      if (variables.jobPostingId) {
        const jobKey = queryKeys.matching.forJob(variables.jobPostingId);
        const cached = queryClient.getQueryData<MatchingResponse>(jobKey);

        if (cached) {
          queryClient.setQueryData<MatchingResponse>(jobKey, {
            ...cached,
            matched_candidates: cached.matched_candidates.map((c) =>
              c.candidate_id === variables.id ? { ...c, status: variables.status } : c
            ),
          });
        }
      } else {
        // Fallback: update all matching caches (just this candidate's status)
        queryClient.getQueriesData({ queryKey: queryKeys.matching.all }).forEach(([key, data]) => {
          if (data && typeof data === 'object' && 'matched_candidates' in data) {
            const d = data as MatchingResponse;
            queryClient.setQueryData(key, {
              ...d,
              matched_candidates: d.matched_candidates.map((c) =>
                c.candidate_id === variables.id ? { ...c, status: variables.status } : c
              ),
            });
          }
        });
      }

      // 2. Update candidate list cache
      queryClient.getQueriesData({ queryKey: queryKeys.candidates.all }).forEach(([key, data]) => {
        if (Array.isArray(data)) {
          queryClient.setQueryData(
            key,
            data.map((c: any) =>
              c.candidate_id === variables.id ? { ...c, status: variables.status } : c
            )
          );
        }
      });

      // 3. Invalidate candidate list to sync with server
      queryClient.invalidateQueries({ queryKey: queryKeys.candidates.all, refetchType: 'none' });

      // Note: matching caches are NOT invalidated/refetched here on purpose.
      // Each job posting's matching pool/status is scoped per-posting on the
      // backend, so this decision cannot affect other postings' cached
      // results — and the specific job's cache was already patched precisely
      // above (step 1). Triggering a full pipeline refetch here used to race
      // with the auto-reject-on-quota-reached calls in job-matching.tsx,
      // sometimes overwriting fresh optimistic state with a stale/partial
      // recompute. A full recompute is available on demand via "Recalculer".
    },
    onError: (error) => {
      console.error('Failed to update candidate status:', error);
      // On error, refetch candidates only — matching cache is updated via setQueryData above
      queryClient.invalidateQueries({ queryKey: queryKeys.candidates.all });
    },
  });
};

// ─────────────────────────────────────────────────────────────
// Dashboard Query Hooks
// ─────────────────────────────────────────────────────────────


/**
 * Hook to fetch dashboard statistics
 */
export function useDashboardStats() {
  return useQuery({
    queryKey: queryKeys.dashboard.stats(),
    queryFn: fetchDashboardStats,
    staleTime: 30000, // 30 seconds
  });
}

/**
 * Hook to fetch department distribution
 */
export function useDepartments() {
  return useQuery({
    queryKey: queryKeys.dashboard.departments(),
    queryFn: fetchDepartments,
    staleTime: 60000, // 1 minute
  });
}

/**
 * Hook to fetch the RH team shown on the dashboard team widget
 */
export function useDashboardTeam() {
  return useQuery({
    queryKey: queryKeys.dashboard.team(),
    queryFn: fetchDashboardTeam,
    staleTime: 5 * 60000,
  });
}

/**
 * Hook to fetch scheduled interviews (dashboard calendar)
 */
export function useInterviews() {
  return useQuery({
    queryKey: queryKeys.dashboard.interviews(),
    queryFn: fetchInterviews,
    staleTime: 30000,
  });
}

/**
 * Hook to fetch candidature-by-status counts, per month of a given year
 */
export function useStatusByMonth(year: number) {
  return useQuery({
    queryKey: queryKeys.dashboard.statusByMonth(year),
    queryFn: () => fetchStatusByMonth(year),
    staleTime: 60000,
  });
}

/**
 * Hook to fetch candidature-by-status counts, per day of a given month
 */
export function useStatusByDay(year: number, month: number) {
  return useQuery({
    queryKey: queryKeys.dashboard.statusByDay(year, month),
    queryFn: () => fetchStatusByDay(year, month),
    staleTime: 60000,
  });
}

/**
 * Hook to fetch applicant trends
 */
export function useTrends(period?: string) {
  return useQuery({
    queryKey: queryKeys.dashboard.trends(period),
    queryFn: () => fetchTrends(period),
    staleTime: 60000, // 1 minute
  });
}


