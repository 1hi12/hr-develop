import { useState, useMemo, useRef, useEffect, Fragment } from 'react';
import { Search, Filter, ExternalLink, MoreVertical, UploadCloud, FolderOpen, ChevronDown, ChevronUp, FileText, Loader2 } from 'lucide-react';
import { useCandidates, useUpdateCandidateStatusMutation } from '../../lib/query/mutations';
import { CandidateStatus, CandidateStatusFilter, Candidate, CandidateGroup } from '../../types/candidates.types';
import { useDebounce } from '../../hooks/useDebounce';
import { useTranslation } from '@/contexts/LanguageContext';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../lib/query/queryKeys';
import { clearMatchingCache } from '../../lib/query/queryClient';
import { toast } from 'sonner';
import { Button } from '../ui/button';
import { CandidateDetailModal } from './CandidateDetailModal';
import { useNotificationStore } from '@/stores/notificationStore';

const STATUS_STYLES: Record<CandidateStatus, string> = {
  pending: 'bg-[#f3f4f6] text-[#6b7280]',
  interviewing: 'bg-[#e0e7ff] text-[#4f46e5]',
  hired: 'bg-[#d1fae5] text-[#059669]',
  rejected: 'bg-[#fee2e2] text-[#dc2626]',
};

const VALID_TYPES = new Set([
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);

export function CandidateList() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<CandidateStatusFilter>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const debouncedSearch = useDebounce(searchTerm, 300);
  const wsRef = useRef<WebSocket | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [processingCVs, setProcessingCVs] = useState<string[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const updateStatus = useUpdateCandidateStatusMutation();

  const deleteCandidate = async (candidateId: string, name: string) => {
    if (!confirm(`Supprimer le candidat "${name}" ? Cette action est irréversible.`)) return;
    setDeletingId(candidateId);
    try {
      const res = await fetch(`/api/v1/candidates/${candidateId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error();
      queryClient.invalidateQueries({ queryKey: queryKeys.candidates.all });
      toast.success(`Candidat supprimé`);
    } catch {
      toast.error('Erreur lors de la suppression');
    } finally {
      setDeletingId(null);
      setMenuOpenId(null);
    }
  };
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const addNotification = useNotificationStore((s) => s.addNotification);

  // ── Batched upload via the pipeline endpoint ──────────────────────────────
  // Uploading N files individually to /candidates/upload made N separate LLM
  // calls in parallel, all racing for the same small Orange proxy token quota
  // — with just 2 files this could already 429 one of them into an empty
  // "Unknown" extraction. /pipeline/upload groups files into dynamically
  // sized batches (~20 LLM calls total regardless of N) processed by a small
  // worker pool, so this is the only path used for any number of files.
  const uploadBatch = async (files: File[]) => {
    const filenames = files.map(f => f.name);
    setProcessingCVs(prev => [...prev, ...filenames]);

    // The backend may echo back a filename that includes a folder prefix
    // (e.g. from a directory upload) even though the browser's File.name is
    // just the base name — compare by basename so removal still matches.
    const basename = (p: string) => p.split(/[/\\]/).pop() || p;

    try {
      const formData = new FormData();
      files.forEach(f => formData.append('files', f));

      const response = await fetch('/api/v1/pipeline/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error(`Upload failed: ${response.statusText}`);

      const { job_id } = await response.json();

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${wsProtocol}//${window.location.host}/api/v1/pipeline/ws/${job_id}`);

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.event === 'cv_processed') {
            const filename: string | undefined = msg.data?.filename;
            setProcessingCVs(prev => filename ? prev.filter(n => basename(n) !== basename(filename)) : prev);
            queryClient.invalidateQueries({ queryKey: queryKeys.candidates.lists() });
            clearMatchingCache();
            const name = msg.data?.cv?.name || filename || 'Candidat';
            if (msg.data?.already_exists) {
              toast.warning(`CV doublon — ${name}`, { duration: 4000 });
            } else {
              toast.success(`${name} ajouté avec succès`, { duration: 3000 });
            }

          } else if (msg.event === 'cv_error') {
            const filename: string | undefined = msg.data?.filename;
            setProcessingCVs(prev => filename ? prev.filter(n => basename(n) !== basename(filename)) : prev);
            toast.error(`Erreur lors de l'upload de ${filename || 'un CV'}`);

          } else if (msg.event === 'done') {
            // Safety net: guarantee this batch's entries clear even if a
            // per-file 'cv_processed'/'cv_error' match was ever missed —
            // the job is fully finished at this point either way.
            setProcessingCVs(prev => prev.filter(n => !filenames.includes(n)));
            ws.close();
          }
        } catch (err) {
          console.error('[Pipeline WS] Failed to parse message:', err);
        }
      };

      ws.onerror = () => console.error('[Pipeline WS] WebSocket error');

    } catch (err) {
      toast.error('Erreur lors de l\'upload des CV');
      setProcessingCVs(prev => prev.filter(n => !filenames.includes(n)));
      // Fallback: refetch so the list is eventually consistent
      queryClient.invalidateQueries({ queryKey: queryKeys.candidates.lists() });
    }
  };

  // ── WebSocket — real-time updates from other clients / workers ────────────
  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let destroyed = false;

    function connect() {
      if (destroyed) return;
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/candidates`);
      wsRef.current = ws;

      ws.onopen = () => console.log('[WS] Connected to candidates channel');

      ws.onmessage = async (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.event === 'cv_processed' || msg.event === 'candidate_added') {
            setProcessingCVs(prev => prev.filter(cv => cv !== msg.data?.filename));
            // Same reasoning as uploadBatch: grouping by identity happens
            // server-side, so a refetch is the simplest correct way to reflect it.
            queryClient.invalidateQueries({ queryKey: queryKeys.candidates.lists() });
            clearMatchingCache();

          } else if (msg.event === 'cv_processing') {
            const filename: string = msg.data?.filename || 'CV';
            setProcessingCVs(prev => [...prev, filename]);
          }
        } catch (err) {
          console.error('[WS] Failed to parse message:', err);
        }
      };

      ws.onerror = () => console.error('[WS] WebSocket error');

      ws.onclose = () => {
        console.log('[WS] Disconnected — reconnecting in 3s');
        if (!destroyed) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };
    }

    connect();

    return () => {
      destroyed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [queryClient]);

  const { data: paginatedData, isLoading, error } = useCandidates({
    search: debouncedSearch || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
  });

  const groups: CandidateGroup[] = paginatedData?.items ?? [];
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const toggleGroup = (identityId: string) => {
    const next = new Set(expandedGroups);
    if (next.has(identityId)) next.delete(identityId); else next.add(identityId);
    setExpandedGroups(next);
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    const validFiles = Array.from(selectedFiles).filter(file => {
      if (!VALID_TYPES.has(file.type)) {
        toast.error(`${file.name} n'est pas un format valide (PDF, DOC, DOCX)`);
        return false;
      }
      return true;
    });

    event.target.value = '';
    setShowDropdown(false);

    if (validFiles.length > 0) {
      await uploadBatch(validFiles);
    }
  };

  const handleFolderSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    const validFiles = Array.from(selectedFiles).filter(file => {
      if (!VALID_TYPES.has(file.type)) {
        toast.error(`${file.name} n'est pas un format valide`);
        return false;
      }
      return true;
    });

    event.target.value = '';
    setShowDropdown(false);

    if (validFiles.length > 0) {
      await uploadBatch(validFiles);
    }
  };

  const statusCounts = useMemo(() => {
    const allCandidates = groups.flatMap((g) => g.candidates);
    const counts = {
      all: allCandidates.length,
      pending: 0,
      interviewing: 0,
      hired: 0,
      rejected: 0,
    };

    allCandidates.forEach((candidate: Candidate) => {
      const status = (candidate.status || 'pending') as CandidateStatus;
      if (status in counts) {
        counts[status]++;
      }
    });

    return counts;
  }, [groups]);

  const renderRowActions = (candidate: Candidate) => (
    <div className="flex items-center gap-2 justify-end">
      <button
        onClick={() => setSelectedCandidate(candidate)}
        className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
        title="Voir les détails"
      >
        <ExternalLink className="h-[18px] w-[18px] text-gray-500 dark:text-gray-400" />
      </button>
      <div className="relative">
        <button
          onClick={(e) => { e.stopPropagation(); setMenuOpenId(menuOpenId === candidate.candidate_id ? null : candidate.candidate_id); }}
          className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
        >
          <MoreVertical className="h-[18px] w-[18px] text-gray-500 dark:text-gray-400" />
        </button>
        {menuOpenId === candidate.candidate_id && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setMenuOpenId(null)} />
            <div className="absolute right-0 mt-1 w-44 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl z-50 overflow-hidden">
              <button
                onClick={() => { setMenuOpenId(null); setSelectedCandidate(candidate); }}
                className="w-full px-4 py-2.5 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"
              >
                <ExternalLink className="w-4 h-4" /> Voir les détails
              </button>
              <div className="border-t border-gray-100 dark:border-gray-700" />
              <button
                onClick={() => deleteCandidate(candidate.candidate_id, candidate.full_name || 'Inconnu')}
                disabled={deletingId === candidate.candidate_id}
                className="w-full px-4 py-2.5 text-left text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 flex items-center gap-2 disabled:opacity-50"
              >
                {deletingId === candidate.candidate_id ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <span className="w-4 h-4 flex items-center justify-center font-bold">✕</span>
                )}
                Supprimer
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-red-600 dark:text-red-400">
        Error loading candidates: {error instanceof Error ? error.message : 'Unknown error'}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-[28px] font-bold text-gray-900 dark:text-white mb-1">
              {t('candidates.title')}
            </h1>
            <p className="text-[14px] text-gray-500 dark:text-gray-400">
              {t('candidates.subtitle')}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 dark:text-gray-500" />
              <input
                type="text"
                placeholder={t('candidates.searchPlaceholder')}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-[280px] h-[40px] pl-11 pr-4 rounded-[20px] border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-gray-900 dark:focus:ring-gray-600"
              />
            </div>
            <button className="w-[40px] h-[40px] rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 flex items-center justify-center hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <Filter className="h-4 w-4 text-gray-600 dark:text-gray-400" />
            </button>

            <div className="relative">
              <Button
                onClick={() => setShowDropdown(!showDropdown)}
                className="h-[40px] px-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg flex items-center gap-2"
              >
                <UploadCloud className="h-4 w-4" />
                <span className="text-sm font-medium">Upload CVs</span>
                <ChevronDown className="h-4 w-4" />
              </Button>

              {showDropdown && (
                <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-2 z-50">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full px-4 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-3"
                  >
                    <FileText className="h-4 w-4" />
                    <span>CV individuel</span>
                  </button>
                  <button
                    onClick={() => folderInputRef.current?.click()}
                    className="w-full px-4 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-3"
                  >
                    <FolderOpen className="h-4 w-4" />
                    <span>Dossier de CVs</span>
                  </button>
                </div>
              )}

              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.doc,.docx"
                multiple
                onChange={handleFileSelect}
                className="hidden"
              />
              <input
                ref={folderInputRef}
                type="file"
                accept=".pdf,.doc,.docx"
                multiple
                {...({ webkitdirectory: "", directory: "" } as any)}
                onChange={handleFolderSelect}
                className="hidden"
              />
            </div>
          </div>
        </div>

        <div className="flex gap-2 mb-6">
          {(['all', 'pending', 'interviewing', 'hired', 'rejected'] as CandidateStatusFilter[]).map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`
                h-[36px] px-4 rounded-full text-sm font-medium transition-all
                ${statusFilter === status
                  ? 'bg-gray-900 dark:bg-gray-700 text-white'
                  : 'bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                }
              `}
            >
              {status === 'all' ? t('common.all') : t(`candidates.status.${status}`)}
            </button>
          ))}
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-[12px] shadow-[0_2px_8px_rgba(0,0,0,0.06)] dark:shadow-[0_2px_8px_rgba(0,0,0,0.3)] border border-gray-300 dark:border-gray-700 p-5 mx-5">
          {processingCVs.length > 0 && (
            <div className="mb-4 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <div className="flex items-center gap-3">
                <Loader2 className="h-5 w-5 text-blue-600 dark:text-blue-400 animate-spin" />
                <div>
                  <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                    Traitement en cours ({processingCVs.length} CV{processingCVs.length > 1 ? 's' : ''})
                  </p>
                  <p className="text-xs text-blue-700 dark:text-blue-300 mt-1">
                    {processingCVs.slice(0, 3).join(', ')}{processingCVs.length > 3 ? '...' : ''}
                  </p>
                </div>
              </div>
            </div>
          )}

          {isLoading ? (
            <div className="py-12 text-center text-gray-500 dark:text-gray-400">
              {t('common.loading')}
            </div>
          ) : groups.length === 0 && processingCVs.length === 0 ? (
            <div className="py-12 text-center text-gray-500 dark:text-gray-400">
              {t('candidates.noCandidates')}
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-300 dark:border-gray-700">
                  <th className="pb-3 text-left text-[12px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-[0.08em]">
                    {t('candidates.applicant').toUpperCase()}
                  </th>
                  <th className="pb-3 text-left text-[12px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-[0.08em]">
                    {t('candidates.experience').toUpperCase()}
                  </th>
                  <th className="pb-3 text-left text-[12px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-[0.08em]">
                    {t('candidates.expertise').toUpperCase()}
                  </th>
                  <th className="pb-3 text-left text-[12px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-[0.08em]">
                    {t('common.status').toUpperCase()}
                  </th>
                  <th className="pb-3"></th>
                </tr>
              </thead>

              <tbody>
                {groups.map((group: CandidateGroup) => {
                  const isMulti = group.cv_count > 1;
                  const isExpanded = expandedGroups.has(group.identity_id);
                  const representative = group.candidates[0];
                  // Collapsed (or singleton) groups show the most recent CV's data inline;
                  // expanded groups leave the header row blank and list every CV below it.
                  const showInlineDetails = !isMulti || !isExpanded;

                  return (
                    <Fragment key={group.identity_id}>
                      <tr
                        className="border-b border-gray-200 dark:border-gray-800 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                      >
                        <td className="py-5">
                          <div className="flex items-center gap-3">
                            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-semibold text-lg">
                              {group.full_name?.charAt(0).toUpperCase() || '?'}
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="text-[15px] font-bold text-gray-900 dark:text-white">
                                  {group.full_name || 'Unknown'}
                                </span>
                                {isMulti && (
                                  <button
                                    onClick={() => toggleGroup(group.identity_id)}
                                    className="flex items-center gap-1 px-2 py-[2px] rounded-full bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 text-[11px] font-bold hover:bg-indigo-200 dark:hover:bg-indigo-900/70 transition-colors"
                                  >
                                    {group.cv_count} CV
                                    {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                                  </button>
                                )}
                              </div>
                              {showInlineDetails && (
                                <div className="text-[13px] text-gray-600 dark:text-gray-400">
                                  {representative.seniority_level ? representative.seniority_level.charAt(0).toUpperCase() + representative.seniority_level.slice(1) : ''}
                                </div>
                              )}
                            </div>
                          </div>
                        </td>

                        <td className="py-5">
                          {showInlineDetails ? (
                            representative.total_years_experience ? (
                              <>
                                <div className="text-[15px] font-bold text-gray-900 dark:text-white">
                                  {representative.total_years_experience} {t('candidates.years')}
                                </div>
                                <div className="text-[12px] text-gray-500 dark:text-gray-400 italic">
                                  {representative.seniority_level ? representative.seniority_level.charAt(0).toUpperCase() + representative.seniority_level.slice(1) : ''}
                                </div>
                              </>
                            ) : (
                              <span className="text-[13px] text-gray-400 dark:text-gray-600 italic">—</span>
                            )
                          ) : null}
                        </td>

                        <td className="py-5">
                          {showInlineDetails && (
                            <div className="flex gap-1.5">
                              {representative.skills?.slice(0, 2).map((skill: string, idx: number) => (
                                <span
                                  key={idx}
                                  className="px-[10px] py-[4px] rounded-[6px] bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-[12px] font-medium"
                                >
                                  {skill}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>

                        <td className="py-5">
                          {showInlineDetails && (
                            <span
                              className={`
                                inline-block px-3 py-[4px] rounded-[20px] text-[11px] font-bold uppercase tracking-wide
                                ${STATUS_STYLES[(representative.status || 'pending') as Exclude<CandidateStatus, 'all'>]}
                              `}
                            >
                              {t(`candidates.status.${(representative.status || 'pending') as Exclude<CandidateStatus, 'all'>}`)}
                            </span>
                          )}
                        </td>

                        <td className="py-5">
                          {showInlineDetails && renderRowActions(representative)}
                        </td>
                      </tr>

                      {isMulti && isExpanded && (
                        <tr key={`${group.identity_id}-header`} className="bg-gray-50 dark:bg-gray-900/40">
                          <td colSpan={5} className="px-4 py-2 text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                            CV / Candidatures liées à ce candidat
                          </td>
                        </tr>
                      )}

                      {isMulti && isExpanded && group.candidates.map((candidate) => {
                        const candidateStatus = (candidate.status || 'pending') as Exclude<CandidateStatus, 'all'>;
                        return (
                          <tr
                            key={candidate.candidate_id}
                            className="border-b border-gray-200 dark:border-gray-800 last:border-0 bg-gray-50/60 dark:bg-gray-900/20 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                          >
                            <td className="py-4 pl-8">
                              <div className="text-[14px] font-medium text-gray-800 dark:text-gray-200">
                                {candidate.filename}
                              </div>
                            </td>
                            <td className="py-4">
                              {candidate.total_years_experience ? (
                                <>
                                  <div className="text-[14px] font-bold text-gray-900 dark:text-white">
                                    {candidate.total_years_experience} {t('candidates.years')}
                                  </div>
                                  <div className="text-[12px] text-gray-500 dark:text-gray-400 italic">
                                    {candidate.seniority_level ? candidate.seniority_level.charAt(0).toUpperCase() + candidate.seniority_level.slice(1) : ''}
                                  </div>
                                </>
                              ) : (
                                <span className="text-[13px] text-gray-400 dark:text-gray-600 italic">—</span>
                              )}
                            </td>
                            <td className="py-4">
                              <div className="flex gap-1.5">
                                {candidate.skills?.slice(0, 2).map((skill: string, idx: number) => (
                                  <span
                                    key={idx}
                                    className="px-[10px] py-[4px] rounded-[6px] bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-[12px] font-medium"
                                  >
                                    {skill}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td className="py-4">
                              <span
                                className={`
                                  inline-block px-3 py-[4px] rounded-[20px] text-[11px] font-bold uppercase tracking-wide
                                  ${STATUS_STYLES[candidateStatus]}
                                `}
                              >
                                {t(`candidates.status.${candidateStatus}`)}
                              </span>
                            </td>
                            <td className="py-4">{renderRowActions(candidate)}</td>
                          </tr>
                        );
                      })}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <CandidateDetailModal
        candidate={selectedCandidate}
        onClose={() => setSelectedCandidate(null)}
      />

    </div>
  );
}
