import { createFileRoute } from '@tanstack/react-router';
import { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Shield, TrendingUp, ChevronDown, Target, Zap, ChevronRight, Check } from 'lucide-react';
import {
  fetchJobPostings,
  matchCandidatesForJobStream,
  recalculateMatchForJob,
  type JobPosting,
  type MatchingResponse,
  type CandidateMatch,
} from '@/lib/api';
import { queryKeys } from '@/lib/query/queryKeys';
import { useUpdateCandidateStatusMutation } from '@/lib/query/mutations';
import { CandidateStatus, Candidate } from '@/types/candidates.types';
import { useTranslation } from '@/contexts/LanguageContext';
import { toast } from 'sonner';
import { InterviewSchedulerModal } from '@/components/candidates/InterviewSchedulerModal';

const STATUS_STYLES: Record<Exclude<CandidateStatus, 'all'>, string> = {
  pending: 'bg-[#f3f4f6] text-[#6b7280]',
  interviewing: 'bg-[#e0e7ff] text-[#4f46e5]',
  hired: 'bg-[#d1fae5] text-[#059669]',
  rejected: 'bg-[#fee2e2] text-[#dc2626]',
};

// Renders "**bold**" markdown segments (used by the LLM to highlight the
// strongest/weakest points inline) as <strong>, everything else as plain text.
function renderBoldedText(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-bold text-gray-900">{part.slice(2, -2)}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

export const Route = createFileRoute('/job-matching')({
  component: JobMatchingPage,
});

function JobMatchingPage() {
  const { t, language } = useTranslation();
  const [selectedPosting, setSelectedPosting] = useState<JobPosting | null>(null);
  const [expandedId, setExpandedId]           = useState<string | null>(null);
  const [recalculating, setRecalculating]     = useState(false);
  const [statusDropdownOpen, setStatusDropdownOpen] = useState<string | null>(null);
  // Local status overrides — applied on top of server data for instant UI feedback
  const [statusOverrides, setStatusOverrides] = useState<Record<string, CandidateStatus>>({});
  // Interview scheduler modal
  const [schedulingCandidate, setSchedulingCandidate] = useState<Candidate | null>(null);
  // Inline quota editor
  const [editingQuota, setEditingQuota] = useState(false);
  const [quotaInput, setQuotaInput] = useState(1);

  const queryClient = useQueryClient();
  const updateStatusMutation = useUpdateCandidateStatusMutation();

  // Live postings list
  const { data: postings = [], isLoading: loadingPostings } = useQuery({
    queryKey: queryKeys.postings.list({ status: 'active' }),
    queryFn: () => fetchJobPostings('active'),
  });

  const ssKey    = (jobId: string) => `matching:${jobId}:${language}`;
  const ssKeyTs  = (jobId: string) => `matching:${jobId}:${language}:ts`;

  // Matching results for the selected posting — query key includes `language` so
  // toggling the language switch triggers a refetch with LLM analysis in the new language.
  const {
    data: matchingData,
    isLoading: loading,
    isError,
  } = useQuery<MatchingResponse>({
    queryKey: queryKeys.matching.forJob(selectedPosting?.job_id ?? '', language),
    queryFn: () => {
      const jobId = selectedPosting!.job_id;
      const jobKey = queryKeys.matching.forJob(jobId, language);
      // Progressive reveal: each candidate is pushed into the query cache as
      // soon as it's scored, so the table below re-renders incrementally
      // instead of waiting for the whole pool. The promise this returns
      // still resolves with the final sorted/trimmed list, which react-query
      // then writes as the authoritative cache value.
      return matchCandidatesForJobStream(
        jobId,
        { top_k: 10, min_score: 0.1, lang: language },
        (candidate: CandidateMatch) => {
          queryClient.setQueryData<MatchingResponse>(jobKey, (old) => {
            const base: MatchingResponse = old ?? {
              job_id: jobId,
              job_title: selectedPosting!.title,
              total_candidates: 0,
              matched_candidates: [],
              recruiter_advice: '',
              total_processing_time_s: 0,
            };
            const exists = base.matched_candidates.some(c => c.candidate_id === candidate.candidate_id);
            const matched_candidates = exists
              ? base.matched_candidates.map(c => c.candidate_id === candidate.candidate_id ? candidate : c)
              : [...base.matched_candidates, candidate];
            return { ...base, matched_candidates, total_candidates: matched_candidates.length };
          });
        },
      );
    },
    enabled: !!selectedPosting,
    staleTime: Infinity,
    gcTime: 24 * 60 * 60 * 1000,
    refetchOnMount: true,
    refetchOnWindowFocus: false,
  });

  // On posting change (or language switch): restore from sessionStorage into React Query cache before the API fires
  useEffect(() => {
    if (!selectedPosting) return;
    const jobKey = queryKeys.matching.forJob(selectedPosting.job_id, language);
    if (queryClient.getQueryData(jobKey)) return; // already in cache
    try {
      const raw = sessionStorage.getItem(ssKey(selectedPosting.job_id));
      if (raw) queryClient.setQueryData(jobKey, JSON.parse(raw));
    } catch {}
  }, [selectedPosting?.job_id, language]);

  // Save to sessionStorage whenever results change
  useEffect(() => {
    if (!matchingData || !selectedPosting) return;
    try {
      sessionStorage.setItem(ssKey(selectedPosting.job_id), JSON.stringify(matchingData));
      sessionStorage.setItem(ssKeyTs(selectedPosting.job_id), Date.now().toString());
    } catch {}
  }, [matchingData, selectedPosting?.job_id, language]);

  // Keep selectedPosting in sync with the latest postings data (nb_positions may change)
  useEffect(() => {
    if (postings.length === 0) return;
    if (!selectedPosting) {
      setSelectedPosting(postings[0]);
    } else {
      const fresh = postings.find(p => p.job_id === selectedPosting.job_id);
      if (fresh && fresh.nb_positions !== selectedPosting.nb_positions) {
        setSelectedPosting(fresh);
      }
    }
  }, [postings]);

  // Reset overrides when switching to a different job posting
  useEffect(() => {
    setStatusOverrides({});
  }, [selectedPosting?.job_id]);

  // Debug: log cache state when matchingData loads (to verify persistence after navigation)
  useEffect(() => {
    if (matchingData && selectedPosting) {
      const statuses = matchingData.matched_candidates.map(c => `${c.name}: ${c.status ?? 'pending'}`);
      console.log('[Cache Check] statuses from cache for job', selectedPosting.job_id, ':', statuses);
    }
  }, [matchingData?.matched_candidates, selectedPosting?.job_id]);


  // Patch the React Query cache AND sessionStorage immediately with the new status
  const patchCandidateStatus = (candidateId: string, newStatus: string) => {
    if (!selectedPosting) return;
    const jobKey = queryKeys.matching.forJob(selectedPosting.job_id, language);
    queryClient.setQueryData<MatchingResponse>(jobKey, (old) => {
      if (!old) return old;
      const updated = {
        ...old,
        matched_candidates: old.matched_candidates.map(c =>
          c.candidate_id === candidateId ? { ...c, status: newStatus } : c
        ),
      };
      // Save immediately — don't wait for useEffect
      try {
        sessionStorage.setItem(ssKey(selectedPosting.job_id), JSON.stringify(updated));
        sessionStorage.setItem(ssKeyTs(selectedPosting.job_id), Date.now().toString());
      } catch {}
      return updated;
    });
  };

  // Effective status: local override takes priority, then DB status, then default 'pending'
  const getEffectiveStatus = (candidateId: string, dbStatus: string | null): Exclude<CandidateStatus, 'all'> =>
    ((statusOverrides[candidateId] ?? dbStatus ?? 'pending') as Exclude<CandidateStatus, 'all'>);

  const hiredCount = matchingData?.matched_candidates.filter(
    (c) => getEffectiveStatus(c.candidate_id, c.status) === 'hired'
  ).length ?? 0;
  const quota = selectedPosting?.nb_positions ?? null;
  const quotaReached = quota !== null && hiredCount >= quota;

  const handleStatusChange = async (candidateId: string, newStatus: Exclude<CandidateStatus, 'all'>) => {
    setStatusDropdownOpen(null);

    // Open interview scheduler popup when moving to "interviewing"
    if (newStatus === 'interviewing') {
      const match = matchingData?.matched_candidates.find(c => c.candidate_id === candidateId);
      if (match) {
        setSchedulingCandidate({
          candidate_id: match.candidate_id,
          full_name: match.name,
          email: match.email,
          status: 'interviewing',
          seniority_level: '',
          total_years_experience: null,
          skills: match.matched_skills,
          created_at: '',
        } as unknown as Candidate);
      }
      // Also update the status in DB
      setStatusOverrides(prev => ({ ...prev, [candidateId]: 'interviewing' }));
      try {
        await updateStatusMutation.mutateAsync({ id: candidateId, status: 'interviewing', jobPostingId: selectedPosting?.job_id });
        patchCandidateStatus(candidateId, 'interviewing');
      } catch {
        setStatusOverrides(prev => { const n = { ...prev }; delete n[candidateId]; return n; });
      }
      return;
    }

    if (newStatus === 'hired') {
      // Find this candidate's current effective status to avoid double-counting
      const dbStatus = matchingData?.matched_candidates.find(c => c.candidate_id === candidateId)?.status ?? null;
      const wasAlreadyHired = getEffectiveStatus(candidateId, dbStatus) === 'hired';
      const nextHiredCount = hiredCount + (wasAlreadyHired ? 0 : 1);
      console.log('[Quota Debug] hired candidate:', candidateId, '| quota:', quota, '| hiredCount:', hiredCount, '| nextHiredCount:', nextHiredCount, '| nb_positions:', selectedPosting?.nb_positions);

      // Build overrides: hired candidate + auto-rejected ones (if quota reached)
      const overrides: Record<string, CandidateStatus> = { [candidateId]: 'hired' };
      const toAutoReject: string[] = [];

      if (quota !== null && nextHiredCount >= quota) {
        matchingData?.matched_candidates.forEach((c) => {
          const cur = getEffectiveStatus(c.candidate_id, c.status);
          if (c.candidate_id !== candidateId && cur !== 'hired' && cur !== 'rejected') {
            overrides[c.candidate_id] = 'rejected';
            toAutoReject.push(c.candidate_id);
          }
        });
      }

      // Instant UI feedback
      setStatusOverrides((prev) => ({ ...prev, ...overrides }));

      // Also update the React Query cache for the auto-rejected ones
      if (toAutoReject.length > 0 && selectedPosting) {
        const jobKey = queryKeys.matching.forJob(selectedPosting.job_id, language);
        const cached = queryClient.getQueryData<MatchingResponse>(jobKey);
        if (cached) {
          queryClient.setQueryData<MatchingResponse>(jobKey, {
            ...cached,
            matched_candidates: cached.matched_candidates.map((c) =>
              toAutoReject.includes(c.candidate_id) ? { ...c, status: 'rejected' } : c
            ),
          });
        }
      }

      try {
        // Save hired candidate to DB. The backend independently rejects all
        // other matched candidates for this job once the quota is actually
        // filled (see _send_rejection_emails_for_job in candidates.py) — the
        // frontend must NOT also fire those PATCH calls itself, that used to
        // race with the backend's own pass and cause inconsistent results.
        // The optimistic overrides set above already give instant UI feedback
        // predicting the same outcome.
        await updateStatusMutation.mutateAsync({
          id: candidateId,
          status: 'hired',
          jobPostingId: selectedPosting?.job_id,
        });
        patchCandidateStatus(candidateId, 'hired');
        if (toAutoReject.length > 0) {
          toast.success(`${toAutoReject.length} ${t('jobMatching.autoRejected')}`);
        }
      } catch (error) {
        setStatusOverrides((prev) => {
          const next = { ...prev };
          delete next[candidateId];
          return next;
        });
        console.error('Failed to update status:', error);
      }
    } else {
      setStatusOverrides((prev) => ({ ...prev, [candidateId]: newStatus }));
      try {
        await updateStatusMutation.mutateAsync({
          id: candidateId,
          status: newStatus,
          jobPostingId: selectedPosting?.job_id,
        });
        patchCandidateStatus(candidateId, newStatus);
      } catch (error) {
        setStatusOverrides((prev) => {
          const next = { ...prev };
          delete next[candidateId];
          return next;
        });
        console.error('Failed to update status:', error);
      }
    }
  };

  // Set nb_positions directly from the matching page
  const handleSetQuota = async () => {
    if (!selectedPosting) return;
    try {
      await fetch(`/api/v1/postings/${selectedPosting.job_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nb_positions: quotaInput }),
      });
      // Update the postings cache with the new nb_positions
      queryClient.setQueryData<JobPosting[]>(
        queryKeys.postings.list({ status: 'active' }),
        (old) => old?.map(p => p.job_id === selectedPosting.job_id ? { ...p, nb_positions: quotaInput } : p) ?? []
      );
      setSelectedPosting(prev => prev ? { ...prev, nb_positions: quotaInput } : prev);
      setEditingQuota(false);
      const positionLabel = quotaInput > 1 ? t('jobMatching.positionPlural') : t('jobMatching.positionSingular');
      toast.success(`${t('jobMatching.quotaSet')} ${quotaInput} ${positionLabel}`);
    } catch {
      toast.error(t('jobMatching.quotaSetError'));
    }
  };

  // Recalculate = call the dedicated endpoint, then update React Query cache
  const handleRecalculate = async () => {
    if (!selectedPosting || recalculating) return;
    setRecalculating(true);
    try {
      const fresh = await recalculateMatchForJob(selectedPosting.job_id, { top_k: 10, min_score: 0.3, lang: language });
      queryClient.setQueryData(
        queryKeys.matching.forJob(selectedPosting.job_id, language),
        fresh,
      );
    } catch (err) {
      console.error('[Recalculate] failed:', err);
    } finally {
      setRecalculating(false);
    }
  };


  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 p-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">{t('jobMatching.title')}</h1>
        <p className="text-gray-500 dark:text-gray-400">{t('jobMatching.subtitle')}</p>
      </div>

      <div className="flex gap-6">
        {/* Left Sidebar - Active Postings */}
        <div className="w-80">
          <h2 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">{t('jobMatching.activePostings').toUpperCase()}</h2>
          
          {loadingPostings ? (
            <div className="text-center py-8 text-gray-500">{t('jobMatching.loadingPostings')}</div>
          ) : postings.length === 0 ? (
            <div className="text-center py-8 text-gray-500">{t('jobMatching.noPostings')}</div>
          ) : (
            <div className="space-y-3">
              {postings.map((posting) => (
                <div key={posting.job_id} className="relative">
                  <Card
                    onClick={() => setSelectedPosting(posting)}
                    className="p-4 cursor-pointer transition-all bg-white border border-[#E5E7EB]"
                    style={{ 
                      borderRadius: '12px',
                      boxShadow: selectedPosting?.job_id === posting.job_id 
                        ? '0 2px 8px rgba(79, 110, 247, 0.2)' 
                        : 'none'
                    }}
                  >
                    {selectedPosting?.job_id === posting.job_id && (
                      <div 
                        className="absolute left-0 top-1/2 -translate-y-1/2 w-1 bg-[#4F6EF7]"
                        style={{ height: '50%', borderRadius: '0 2px 2px 0' }}
                      />
                    )}
                    <h3 className={`font-semibold text-base leading-tight mb-2 ${
                      selectedPosting?.job_id === posting.job_id 
                        ? 'text-[#4F6EF7]' 
                        : 'text-[#111111]'
                    }`}>
                      {posting.title}
                    </h3>
                    <div className="flex items-center justify-between">
                      <span 
                        className="font-medium text-[#9CA3AF] uppercase"
                        style={{ fontSize: '11px', letterSpacing: '0.05em' }}
                      >
                        {posting.department || ''}
                      </span>
                      <span 
                        className={`font-medium ${
                          selectedPosting?.job_id === posting.job_id
                            ? 'bg-[#EEF2FF] text-[#4F6EF7]'
                            : 'bg-[#F3F4F6] text-[#6B7280]'
                        }`}
                        style={{ 
                          fontSize: '12px', 
                          padding: '2px 8px', 
                          borderRadius: '9999px' 
                        }}
                      >
                        {selectedPosting?.job_id === posting.job_id && matchingData
                          ? matchingData.total_candidates
                          : selectedPosting?.job_id === posting.job_id && loading 
                          ? '...' 
                          : '0'}
                      </span>
                    </div>
                  </Card>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Main Content Container */}
        <div className="flex-1 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-8">
          {!selectedPosting ? (
            <div className="text-center py-16 text-gray-500">
              {t('jobMatching.selectPosting')}
            </div>
          ) : (
            <>
              {/* Selected Job Header */}
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="w-14 h-14 bg-[#EEF2FF] rounded-full flex items-center justify-center">
                    <Target className="w-7 h-7 text-[#4F6EF7]" />
                  </div>
                  <div>
                    <h2 className="text-[22px] font-bold text-[#111111]" style={{ fontWeight: 700 }}>{selectedPosting.title}</h2>
                    <div className="flex items-center gap-2 text-sm mt-1">
                      <span className="text-[#9CA3AF]">{selectedPosting.location || 'Remote'}</span>
                      <span className="text-[#9CA3AF]">•</span>
                      <span className="text-[#4F6EF7] font-medium">{selectedPosting.employment_type}</span>
                      {selectedPosting.nb_positions !== null && (
                        <>
                          <span className="text-[#9CA3AF]">•</span>
                          <span className="text-xs font-bold px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full">
                            {selectedPosting.nb_positions} {selectedPosting.nb_positions > 1 ? t('jobMatching.positionPlural') : t('jobMatching.positionSingular')}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <Button
                  onClick={handleRecalculate}
                  disabled={loading || recalculating}
                  className="bg-[#111111] text-white hover:bg-gray-800"
                  style={{ borderRadius: '8px' }}
                >
                  {recalculating ? t('jobMatching.recalculating') : loading ? t('jobMatching.calculating') : t('jobMatching.recalculate')}
                </Button>
              </div>

              {isError && (
                <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
                  <p className="text-red-600 dark:text-red-400">{t('jobMatching.failedToMatch')}</p>
                </div>
              )}

              {loading ? (
                <div className="text-center py-16 text-gray-500">{t('jobMatching.matchingCandidates')}</div>
              ) : matchingData && matchingData.matched_candidates.length > 0 ? (
                <>
                  {/* Score breakdown cards */}
                  <div className="grid grid-cols-3 gap-4 mb-8">
                    <Card className="bg-[#FFFBEB] border-0 p-6" style={{ borderRadius: '12px' }}>
                      <div className="flex items-center gap-3 mb-3">
                        <div className="w-10 h-10 bg-white rounded-lg flex items-center justify-center">
                          <Zap className="w-5 h-5 text-[#F97316]" />
                        </div>
                        <span className="text-[11px] font-semibold text-[#F97316] uppercase tracking-wide">{t('jobMatching.technicalFit').toUpperCase()}</span>
                      </div>
                      <div className="text-[28px] font-bold text-[#F97316]" style={{ fontWeight: 700 }}>
                        {Math.round(matchingData.matched_candidates.reduce((s, c) => s + c.skill_score, 0) / matchingData.matched_candidates.length)}%
                      </div>
                    </Card>

                    <Card className="bg-[#F0FDF4] border-0 p-6" style={{ borderRadius: '12px' }}>
                      <div className="flex items-center gap-3 mb-3">
                        <div className="w-10 h-10 bg-white rounded-lg flex items-center justify-center">
                          <Shield className="w-5 h-5 text-[#22C55E]" />
                        </div>
                        <span className="text-[11px] font-semibold text-[#22C55E] uppercase tracking-wide">{t('jobMatching.cultureFit').toUpperCase()}</span>
                      </div>
                      <div className="text-[28px] font-bold text-[#22C55E]" style={{ fontWeight: 700 }}>
                        {Math.round(matchingData.matched_candidates.reduce((s, c) => s + c.seniority_multiplier * 100, 0) / matchingData.matched_candidates.length)}%
                      </div>
                    </Card>

                    <Card className="bg-[#EEF2FF] border-0 p-6" style={{ borderRadius: '12px' }}>
                      <div className="flex items-center gap-3 mb-3">
                        <div className="w-10 h-10 bg-white rounded-lg flex items-center justify-center">
                          <TrendingUp className="w-5 h-5 text-[#4F6EF7]" />
                        </div>
                        <span className="text-[11px] font-semibold text-[#4F6EF7] uppercase tracking-wide">{t('jobMatching.growthFit').toUpperCase()}</span>
                      </div>
                      <div className="text-[28px] font-bold text-[#4F6EF7]" style={{ fontWeight: 700 }}>
                        {Math.round(matchingData.matched_candidates.reduce((s, c) => s + c.final_score, 0) / matchingData.matched_candidates.length)}%
                      </div>
                    </Card>
                  </div>

                  {/* ── Smart Quota Progress Bar / Setter ── */}
                  {quota === null && (
                    <div className="mb-6 p-4 rounded-2xl border-2 border-dashed border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-950/20">
                      {!editingQuota ? (
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-indigo-600 dark:text-indigo-400 font-medium">
                            {t('jobMatching.noQuotaDefined')}
                          </span>
                          <button
                            onClick={() => { setQuotaInput(1); setEditingQuota(true); }}
                            className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-lg transition-colors"
                          >
                            {t('jobMatching.defineQuota')}
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-3">
                          <span className="text-sm text-indigo-700 dark:text-indigo-300 font-medium whitespace-nowrap">
                            {t('jobMatching.numberOfPositions')}
                          </span>
                          <div className="flex gap-2">
                            {[1, 2, 3, 5].map(n => (
                              <button
                                key={n}
                                onClick={() => setQuotaInput(n)}
                                className={`w-9 h-9 rounded-lg text-sm font-bold border-2 transition-all ${
                                  quotaInput === n
                                    ? 'bg-indigo-600 text-white border-indigo-600'
                                    : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-indigo-400'
                                }`}
                              >{n}</button>
                            ))}
                            <input
                              type="number" min={1} max={100}
                              value={quotaInput}
                              onChange={e => setQuotaInput(Math.max(1, parseInt(e.target.value) || 1))}
                              className="w-16 h-9 text-center text-sm font-bold border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:border-indigo-500 outline-none dark:bg-gray-800"
                            />
                          </div>
                          <button
                            onClick={handleSetQuota}
                            className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-lg transition-colors"
                          >
                            {t('jobMatching.confirm')}
                          </button>
                          <button
                            onClick={() => setEditingQuota(false)}
                            className="px-3 py-1.5 text-gray-500 hover:text-gray-700 text-sm rounded-lg border border-gray-300 transition-colors"
                          >
                            {t('common.cancel')}
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                  {quota !== null && (
                    <div className={`mb-6 p-4 rounded-2xl border-2 transition-all ${
                      quotaReached
                        ? 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/20 dark:border-emerald-800'
                        : 'bg-[#EEF2FF] border-[#C7D2FE] dark:bg-indigo-950/20 dark:border-indigo-800'
                    }`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-bold uppercase tracking-wide ${quotaReached ? 'text-emerald-600' : 'text-[#4F6EF7]'}`}>
                            {quotaReached ? `🎉 ${t('jobMatching.recruitmentComplete')}` : t('jobMatching.recruitmentProgress')}
                          </span>
                        </div>
                        <span className={`text-sm font-bold ${quotaReached ? 'text-emerald-600' : 'text-[#4F6EF7]'}`}>
                          {hiredCount} / {quota} {t('jobMatching.positionsFilled')}
                        </span>
                      </div>
                      <div className="w-full bg-white dark:bg-gray-800 rounded-full h-3 overflow-hidden border border-gray-200 dark:border-gray-700">
                        <div
                          className={`h-3 rounded-full transition-all duration-500 ${quotaReached ? 'bg-emerald-500' : 'bg-[#4F6EF7]'}`}
                          style={{ width: `${Math.min(100, (hiredCount / quota) * 100)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Rankings */}
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-[11px] font-semibold text-[#9CA3AF] uppercase" style={{ letterSpacing: '0.05em' }}>
                        {t('jobMatching.rankings').toUpperCase()} ({matchingData.total_candidates} {t('jobMatching.candidates').toUpperCase()})
                      </h3>
                      {matchingData.total_processing_time_s > 0 && (
                        <p className="text-[10px] text-gray-400 mt-0.5">
                          ⏱ {t('jobMatching.processedIn')} {matchingData.total_processing_time_s.toFixed(2)}s
                        </p>
                      )}
                    </div>
                    <button className="text-[#4F6EF7] text-sm font-medium hover:underline">
                      {t('jobMatching.viewLogic')}
                    </button>
                  </div>

                  <div className="space-y-2">
                    {matchingData.matched_candidates.map((candidate, index) => {
                      const isExpanded = expandedId === candidate.candidate_id;
                      const effectiveStatus = getEffectiveStatus(candidate.candidate_id, candidate.status);
                      const scoreColor =
                        candidate.final_score >= 90 ? 'text-[#22C55E]' :
                        candidate.final_score >= 80 ? 'text-[#4F6EF7]' :
                        'text-[#F97316]';

                      return (
                        <div key={candidate.candidate_id}>
                          <div
                            className="flex items-center gap-4 p-4 cursor-pointer bg-[#F9FAFB] hover:bg-white hover:border-[#4F6EF7] border border-[#E5E7EB] transition-all group"
                            style={{ borderRadius: '8px' }}
                            onClick={() => setExpandedId(isExpanded ? null : candidate.candidate_id)}
                          >
                            {/* Avatar avec badge en overlap */}
                            <div className="relative flex-shrink-0">
                              {/* Badge numéro */}
                              <div 
                                className="absolute w-6 h-6 bg-[#111111] text-white rounded flex items-center justify-center text-xs font-semibold"
                                style={{ borderRadius: '6px', top: '-8px', left: '-8px' }}
                              >
                                {index + 1}
                              </div>

                              {/* Avatar */}
                              <div className="w-12 h-12 bg-gray-900 rounded-lg flex items-center justify-center">
                                <span className="text-white font-bold text-xl">
                                  {candidate.name.charAt(0).toUpperCase()}
                                </span>
                              </div>
                            </div>

                            {/* Info */}
                            <div className="flex-1 min-w-0">
                              <h4 className="font-bold text-[#111111] text-[15px] mb-1">
                                {candidate.name}
                              </h4>
                              <div className="flex items-center gap-2">
                                <span className="text-[12px] text-[#9CA3AF]">
                                  {candidate.experience}
                                </span>
                                {candidate.skill && candidate.skill !== 'N/A' && (
                                  <span
                                    className="bg-[#EEF2FF] text-[#4F6EF7] text-[11px] font-medium px-2 py-1 uppercase"
                                    style={{ borderRadius: '9999px' }}
                                  >
                                    #{candidate.skill}
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Score */}
                            <div className="flex items-center gap-3 flex-shrink-0">
                              {/* Status Selector */}
                              <div className="relative">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setStatusDropdownOpen(
                                      statusDropdownOpen === candidate.candidate_id ? null : candidate.candidate_id
                                    );
                                  }}
                                  className={`
                                    px-3 py-1.5 rounded-full text-[11px] font-bold uppercase tracking-wide
                                    ${STATUS_STYLES[effectiveStatus]}
                                    hover:opacity-80 transition-all flex items-center gap-1.5
                                    ${statusDropdownOpen === candidate.candidate_id ? 'ring-2 ring-[#4F6EF7] ring-offset-2' : ''}
                                  `}
                                >
                                  {t(`candidates.status.${effectiveStatus}`)}
                                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${
                                    statusDropdownOpen === candidate.candidate_id ? 'rotate-180' : ''
                                  }`} />
                                </button>

                                {statusDropdownOpen === candidate.candidate_id && (
                                  <>
                                    {/* Backdrop to close dropdown when clicking outside */}
                                    <div 
                                      className="fixed inset-0 z-40"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setStatusDropdownOpen(null);
                                      }}
                                    />
                                    
                                    <div 
                                      className="absolute right-0 mt-2 w-44 bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden z-50"
                                      style={{ boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15)' }}
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <div className="py-1">
                                        {(['pending', 'interviewing', 'hired', 'rejected'] as const).map((status) => {
                                          const isSelected = effectiveStatus === status;
                                          return (
                                            <button
                                              key={status}
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                handleStatusChange(candidate.candidate_id, status);
                                              }}
                                              className={`
                                                w-full px-4 py-2.5 text-left text-sm transition-all
                                                flex items-center justify-between group
                                                ${isSelected 
                                                  ? 'bg-[#EEF2FF] text-[#4F6EF7] font-semibold' 
                                                  : 'hover:bg-[#F9FAFB] dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                                                }
                                              `}
                                            >
                                              <span className="flex items-center gap-2">
                                                <span className={`w-2 h-2 rounded-full ${
                                                  status === 'pending' ? 'bg-gray-400' :
                                                  status === 'interviewing' ? 'bg-indigo-500' :
                                                  status === 'hired' ? 'bg-green-500' :
                                                  'bg-red-500'
                                                }`} />
                                                {t(`candidates.status.${status}`)}
                                              </span>
                                              {isSelected && (
                                                <Check className="w-4 h-4 text-[#4F6EF7]" strokeWidth={3} />
                                              )}
                                            </button>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  </>
                                )}
                              </div>

                              <div className="text-right">
                                <div className="text-[10px] text-[#9CA3AF] uppercase tracking-wide mb-1">{t('jobMatching.score').toUpperCase()}</div>
                                <div className={`text-[20px] font-bold ${scoreColor}`} style={{ fontWeight: 700 }}>
                                  {Math.round(candidate.final_score)}%
                                </div>
                              </div>

                              {/* Bouton flèche */}
                              <div className="w-8 h-8 bg-[#F3F4F6] group-hover:bg-[#EEF2FF] rounded-full flex items-center justify-center transition-colors">
                                <ChevronRight className="w-4 h-4 text-[#6B7280] group-hover:text-[#4F6EF7] transition-colors" />
                              </div>
                            </div>
                          </div>

                          {/* Expanded detail */}
                          {isExpanded && (
                            <div className="px-4 pb-4 border-t border-gray-200 pt-4 space-y-4">
                              {/* Score breakdown */}
                              <div className="grid grid-cols-3 gap-3">
                                <div className="bg-gray-50 rounded-lg p-3 text-center">
                                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">{t('jobMatching.semantic')}</div>
                                  <div className="text-xl font-bold text-orange-500">{candidate.skill_score.toFixed(0)}%</div>
                                  <div className="text-xs text-gray-400">× 70%</div>
                                </div>
                                <div className="bg-gray-50 rounded-lg p-3 text-center">
                                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">{t('jobMatching.seniorityScore')}</div>
                                  <div className="text-xl font-bold text-emerald-500">{(candidate.seniority_multiplier * 100).toFixed(0)}%</div>
                                  <div className="text-xs text-gray-400">× 30%</div>
                                </div>
                                <div className="bg-gray-50 rounded-lg p-3 text-center">
                                  <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">{t('jobMatching.finalScore')}</div>
                                  <div className={`text-xl font-bold ${scoreColor}`}>{candidate.final_score.toFixed(0)}/100</div>
                                </div>
                              </div>

                              {/* Skills */}
                              <div className="grid grid-cols-2 gap-3">
                                {candidate.matched_skills.length > 0 && (
                                  <div>
                                    <p className="text-xs font-semibold text-emerald-600 uppercase tracking-wide mb-2">✓ {t('jobMatching.presentSkills')}</p>
                                    <div className="flex flex-wrap gap-1">
                                      {candidate.matched_skills.map(s => (
                                        <span key={s} className="px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded text-xs">{s}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                {candidate.missing_skills.length > 0 && (
                                  <div>
                                    <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-2">✗ {t('jobMatching.missingSkills')}</p>
                                    <div className="flex flex-wrap gap-1">
                                      {candidate.missing_skills.map(s => (
                                        <span key={s} className="px-2 py-0.5 bg-red-50 text-red-600 rounded text-xs">{s}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>

                              {/* Strengths / Weaknesses */}
                              {(candidate.key_strengths.length > 0 || candidate.key_weaknesses.length > 0) && (
                                <div className="grid grid-cols-2 gap-3">
                                  {candidate.key_strengths.length > 0 && (
                                    <div>
                                      <p className="text-xs font-semibold text-emerald-600 uppercase tracking-wide mb-2">+ {t('jobMatching.strengths')}</p>
                                      <div className="flex flex-wrap gap-1">
                                        {candidate.key_strengths.map(s => (
                                          <span key={s} className="px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded text-xs">{s}</span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                  {candidate.key_weaknesses.length > 0 && (
                                    <div>
                                      <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-2">− {t('jobMatching.weaknesses')}</p>
                                      <div className="flex flex-wrap gap-1">
                                        {candidate.key_weaknesses.map(s => (
                                          <span key={s} className="px-2 py-0.5 bg-red-50 text-red-600 rounded text-xs">{s}</span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* AI description + recommendation — single shared box */}
                              {(candidate.ai_description || candidate.recommendation) && (
                                <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-4 space-y-3">
                                  {candidate.ai_description && (
                                    <div>
                                      <div className="flex items-center justify-between mb-2">
                                        <p className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">{t('jobMatching.analysis')}</p>
                                        {candidate.scoring_time_s > 0 && (
                                          <span className="text-[10px] text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                                            ⏱ {candidate.scoring_time_s.toFixed(2)}s
                                          </span>
                                        )}
                                      </div>
                                      <p className="text-sm text-gray-700 leading-relaxed">{renderBoldedText(candidate.ai_description)}</p>
                                    </div>
                                  )}
                                  {candidate.recommendation && (
                                    <div>
                                      <p className="text-xs font-semibold text-indigo-600 uppercase tracking-wide mb-2">{t('jobMatching.recommendationTitle')}</p>
                                      <p className="text-sm font-bold text-gray-800 leading-relaxed">{candidate.recommendation}</p>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="text-center py-16 text-gray-500">
                  {t('jobMatching.noCandidatesMatched')}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {schedulingCandidate && (
        <InterviewSchedulerModal
          candidate={schedulingCandidate}
          jobPostingId={selectedPosting?.job_id}
          onClose={() => setSchedulingCandidate(null)}
          onScheduled={() => {
            queryClient.invalidateQueries({ queryKey: queryKeys.candidates.all });
          }}
        />
      )}
    </div>
  );
}
