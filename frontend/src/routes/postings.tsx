import { createFileRoute } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { PostingList } from '../components/postings/PostingList';
import { queryKeys } from '../lib/query/queryKeys';
import { fetchJobPostings } from '../lib/api';
import { useTranslation } from '@/contexts/LanguageContext';

export const Route = createFileRoute('/postings')({
  component: PostingsPage,
});

function PostingsPage() {
  const { t } = useTranslation();
  const { data: postings = [], isLoading } = useQuery({
    queryKey: queryKeys.postings.list(),
    queryFn: () => fetchJobPostings(),
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-50 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950 p-8">
      {/* Page Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
              {t('postings.title')}
            </h1>
            <p className="text-gray-600 dark:text-gray-400">
              {t('postings.subtitle')}
            </p>
          </div>
          <div className="flex items-center gap-2 px-5 py-2.5 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-xl text-sm font-semibold border border-gray-200 dark:border-gray-700 shadow-sm">
            <div className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
            <span className="text-gray-500 dark:text-gray-400">{t('common.total')}:</span>
            <span className="text-gray-900 dark:text-white">{postings.length}</span>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto">
        <PostingList postings={postings} isLoading={isLoading} />
      </div>
    </div>
  );
}
