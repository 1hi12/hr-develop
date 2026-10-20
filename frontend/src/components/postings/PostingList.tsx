import { Card } from '../ui/card';
import { Badge } from '../ui/badge';
import { JobPosting } from '../../types/postings.types';
import { useUpdateJobPostingStatusMutation, useDeleteJobPostingMutation } from '../../lib/query/mutations';
import { CheckCircle2, FileEdit, XCircle, MoreVertical, Trash2, MapPin, Briefcase, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import { useTranslation } from '@/contexts/LanguageContext';

interface PostingListProps {
  postings: JobPosting[];
  isLoading: boolean;
}

export function PostingList({ postings, isLoading }: PostingListProps) {
  const { t } = useTranslation();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedDescriptions, setExpandedDescriptions] = useState<Set<string>>(new Set());
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const updateStatusMutation = useUpdateJobPostingStatusMutation();
  const deleteJobMutation = useDeleteJobPostingMutation();

  const toggleDescription = (jobId: string) => {
    const newSet = new Set(expandedDescriptions);
    if (newSet.has(jobId)) {
      newSet.delete(jobId);
    } else {
      newSet.add(jobId);
    }
    setExpandedDescriptions(newSet);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'active':
      case 'open':
        return <CheckCircle2 className="w-5 h-5 text-green-500" />;
      case 'paused':
      case 'draft':
      case 'inactive':
        return <FileEdit className="w-5 h-5 text-slate-500" />;
      case 'closed':
      case 'archived':
        return <XCircle className="w-5 h-5 text-red-500" />;
      default:
        return null;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
      case 'open':
        return 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-200 border-green-200 dark:border-green-800';
      case 'paused':
      case 'draft':
      case 'inactive':
        return 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600';
      case 'closed':
      case 'archived':
        return 'bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-200 border-red-200 dark:border-red-800';
      default:
        return 'bg-gray-50 dark:bg-gray-900 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700';
    }
  };

  const handleStatusChange = async (id: string, newStatus: 'active' | 'draft' | 'closed') => {
    try {
      await updateStatusMutation.mutateAsync({ id, status: newStatus });
      toast.success(`${t('postings.statusUpdated')} ${t(`common.${newStatus}`)}`);
      setExpandedId(null);
    } catch (error) {
      toast.error(t('postings.failedUpdate'));
      console.error(error);
    }
  };

  const handleDelete = async (id: string, title: string) => {
    // Show confirmation
    if (!window.confirm(`${t('postings.deleteConfirm')} "${title}"? ${t('postings.deleteWarning')}`)) {
      return;
    }

    try {
      await deleteJobMutation.mutateAsync(id);
      toast.success(t('postings.deleted'));
      setDeletingId(null);
    } catch (error) {
      toast.error(t('postings.failedDelete'));
      console.error(error);
    }
  };

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Card
            key={i}
            className="p-5 bg-white dark:bg-slate-950 animate-pulse border-gray-200 dark:border-gray-800"
          >
            <div className="flex justify-between items-start mb-3">
              <div className="flex-1">
                <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-2" />
                <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/2" />
              </div>
              <div className="h-6 w-16 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            </div>
            <div className="space-y-2 my-4">
              <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full" />
              <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-5/6" />
              <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-4/6" />
            </div>
            <div className="flex gap-2 mt-4">
              <div className="h-5 w-16 bg-gray-200 dark:bg-gray-700 rounded" />
              <div className="h-5 w-20 bg-gray-200 dark:bg-gray-700 rounded" />
              <div className="h-5 w-14 bg-gray-200 dark:bg-gray-700 rounded" />
            </div>
          </Card>
        ))}
      </div>
    );
  }

  if (postings.length === 0) {
    return (
      <Card className="p-16 bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 text-center border-gray-200 dark:border-gray-800">
        <div className="h-16 w-16 rounded-2xl bg-gray-200 dark:bg-gray-700 mx-auto mb-4 flex items-center justify-center">
          <Briefcase className="w-8 h-8 text-gray-400" />
        </div>
        <p className="text-gray-900 dark:text-gray-100 font-semibold text-lg mb-1">
          {t('postings.noPostings')}
        </p>
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          {t('postings.createFirst')}
        </p>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
      {postings.map((posting) => {
        const isDescriptionExpanded = expandedDescriptions.has(posting.job_id);
        const descriptionPreview = posting.description?.slice(0, 150) || '';
        const shouldShowReadMore = (posting.description?.length || 0) > 150;

        return (
          <Card
            key={posting.job_id}
            className="bg-white dark:bg-slate-950 border border-gray-200 dark:border-gray-800 hover:shadow-xl hover:border-gray-300 dark:hover:border-gray-700 transition-all duration-300 group relative"
          >
            {/* Header Section */}
            <div className="p-5 pb-4 border-b border-gray-100 dark:border-gray-800">
              <div className="flex justify-between items-start gap-3 mb-3">
                <h3 className="text-base font-bold text-gray-900 dark:text-white leading-tight flex-1 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                  {posting.title}
                </h3>
                
                {/* Compact Status Badge */}
                <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold ${getStatusColor(posting.status)}`}>
                  {getStatusIcon(posting.status)}
                  <span className="capitalize">
                    {posting.status === 'paused' || posting.status === 'inactive'
                      ? t('common.draft')
                      : posting.status === 'active'
                      ? t('common.active')
                      : posting.status === 'closed'
                      ? t('common.closed')
                      : posting.status}
                  </span>
                </div>
              </div>

              {/* Metadata Row */}
              <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                <div className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{formatDate(posting.created_at)}</span>
                </div>
                {posting.department && (
                  <div className="flex items-center gap-1.5">
                    <Briefcase className="w-3.5 h-3.5" />
                    <span>{posting.department}</span>
                  </div>
                )}
                {posting.location && (
                  <div className="flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5" />
                    <span>{posting.location}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Description Section */}
            <div className="p-5 pt-4">
              <div className={`text-sm text-gray-600 dark:text-gray-400 leading-relaxed ${isDescriptionExpanded ? '' : 'line-clamp-3'}`}>
                <ReactMarkdown
                  components={{
                    p: ({ node, ...props }) => <p className="mb-2" {...props} />,
                    ul: ({ node, ...props }) => <ul className="list-disc list-inside mb-2 space-y-0.5" {...props} />,
                    ol: ({ node, ...props }) => <ol className="list-decimal list-inside mb-2 space-y-0.5" {...props} />,
                    h1: ({ node, ...props }) => <h1 className="text-base font-bold mb-1.5 mt-2" {...props} />,
                    h2: ({ node, ...props }) => <h2 className="text-sm font-bold mb-1.5 mt-1.5" {...props} />,
                    h3: ({ node, ...props }) => <h3 className="text-sm font-semibold mb-1 mt-1.5" {...props} />,
                    strong: ({ node, ...props }) => <strong className="font-semibold text-gray-900 dark:text-gray-100" {...props} />,
                    li: ({ node, ...props }) => <li className="text-sm" {...props} />,
                  }}
                >
                  {isDescriptionExpanded ? posting.description : descriptionPreview + (shouldShowReadMore ? '...' : '')}
                </ReactMarkdown>
              </div>

              {shouldShowReadMore && (
                <button
                  onClick={() => toggleDescription(posting.job_id)}
                  className="mt-2 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 flex items-center gap-1 transition-colors"
                >
                  {isDescriptionExpanded ? (
                    <>
                      <ChevronUp className="w-3.5 h-3.5" />
                      {t('common.showLess')}
                    </>
                  ) : (
                    <>
                      <ChevronDown className="w-3.5 h-3.5" />
                      {t('common.readMore')}
                    </>
                  )}
                </button>
              )}
            </div>

            {/* Skills Section */}
            {posting.required_skills.length > 0 && (
              <div className="px-5 pb-4">
                <div className="flex flex-wrap gap-1.5">
                  {posting.required_skills.slice(0, 6).map((skill, index) => (
                    <Badge
                      key={index}
                      variant="secondary"
                      className="text-xs font-medium px-2.5 py-0.5 bg-indigo-50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-300 border-0 rounded-md"
                    >
                      {skill}
                    </Badge>
                  ))}
                  {posting.required_skills.length > 6 && (
                    <Badge
                      variant="secondary"
                      className="text-xs font-medium px-2.5 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-0 rounded-md"
                    >
                      +{posting.required_skills.length - 6} {t('common.moreItems')}
                    </Badge>
                  )}
                </div>
              </div>
            )}

            {/* Actions Footer */}
            <div className="px-5 py-3 bg-gray-50 dark:bg-gray-900/50 border-t border-gray-100 dark:border-gray-800 flex justify-between items-center">
              <div className="flex gap-2">
                {expandedId === posting.job_id ? (
                  <>
                    <button
                      onClick={() => handleStatusChange(posting.job_id, 'active')}
                      disabled={updateStatusMutation.isPending}
                      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                        posting.status === 'active'
                          ? 'bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-400'
                          : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                      } ${updateStatusMutation.isPending ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      {t('common.active')}
                    </button>
                    <button
                      onClick={() => handleStatusChange(posting.job_id, 'draft')}
                      disabled={updateStatusMutation.isPending}
                      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                        posting.status === 'draft' || posting.status === 'paused'
                          ? 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                          : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                      } ${updateStatusMutation.isPending ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      {t('common.draft')}
                    </button>
                    <button
                      onClick={() => handleStatusChange(posting.job_id, 'closed')}
                      disabled={updateStatusMutation.isPending}
                      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                        posting.status === 'closed'
                          ? 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-400'
                          : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                      } ${updateStatusMutation.isPending ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      {t('common.closed')}
                    </button>
                    <button
                      onClick={() => setExpandedId(null)}
                      className="px-3 py-1.5 text-xs font-medium rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-all"
                    >
                      ✕
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => setExpandedId(posting.job_id)}
                      className="px-3 py-1.5 text-xs font-medium rounded-lg bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-50 dark:hover:bg-indigo-950/50 transition-all"
                    >
                      {t('postings.changeStatus')}
                    </button>
                    <button
                      onClick={() => handleDelete(posting.job_id, posting.title)}
                      disabled={deleteJobMutation.isPending && deletingId === posting.job_id}
                      className={`px-3 py-1.5 text-xs font-medium rounded-lg bg-white dark:bg-gray-800 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/50 transition-all flex items-center gap-1.5 ${
                        deleteJobMutation.isPending && deletingId === posting.job_id ? 'opacity-50 cursor-not-allowed' : ''
                      }`}
                    >
                      <Trash2 className="w-3 h-3" />
                      {t('postings.delete')}
                    </button>
                  </>
                )}
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
