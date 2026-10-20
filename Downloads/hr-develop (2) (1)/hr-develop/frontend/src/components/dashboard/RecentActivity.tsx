import { useQuery } from '@tanstack/react-query';
import { useTranslation } from '@/contexts/LanguageContext';
import { Activity, UserPlus, Briefcase } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

interface RecentActivityItem {
  id: string;
  type: 'candidate_added' | 'job_posted';
  title: string;
  timestamp: string;
}

const TYPE_STYLES = {
  candidate_added: {
    icon: UserPlus,
    bg: 'bg-indigo-50 dark:bg-indigo-900/30',
    text: 'text-indigo-600 dark:text-indigo-400',
    ring: 'ring-indigo-100 dark:ring-indigo-900/50',
  },
  job_posted: {
    icon: Briefcase,
    bg: 'bg-teal-50 dark:bg-teal-900/30',
    text: 'text-teal-600 dark:text-teal-400',
    ring: 'ring-teal-100 dark:ring-teal-900/50',
  },
} as const;

export function RecentActivity() {
  const { t } = useTranslation();

  const { data: activities, isLoading } = useQuery<RecentActivityItem[]>({
    queryKey: ['dashboard', 'recent-activity'],
    queryFn: async () => {
      const response = await fetch('/api/v1/dashboard/recent-activity?limit=5');
      if (!response.ok) throw new Error('Failed to fetch recent activity');
      return response.json();
    },
  });

  const getActivityDescription = (activity: RecentActivityItem) => {
    if (activity.type === 'job_posted') {
      return (
        <>
          <span className="font-semibold">{activity.title}</span> publiée
        </>
      );
    }
    return (
      <>
        <span className="font-semibold">{activity.title}</span> ajouté
      </>
    );
  };

  const getTimeAgo = (timestamp: string) => {
    const now = new Date();
    const date = new Date(timestamp);
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'À l\'instant';
    if (diffMins < 60) return `Il y a ${diffMins} min`;
    if (diffHours < 24) return `Il y a ${diffHours}h`;
    if (diffDays === 1) return 'Hier';
    return `Il y a ${diffDays} jour${diffDays > 1 ? 's' : ''}`;
  };

  return (
    <Card className="border border-gray-200 dark:border-gray-700 shadow-sm bg-white dark:bg-gray-800 h-full flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-50 dark:bg-indigo-900/30 rounded-lg shrink-0">
            <Activity className="h-4.5 w-4.5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div className="min-w-0">
            <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white leading-tight">
              {t('dashboard.recentActivity') || 'Activité récente'}
            </CardTitle>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
              Derniers mouvements sur la plateforme
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0 flex-1">
        {isLoading ? (
          <div className="space-y-5">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex items-center gap-3 animate-pulse">
                <div className="w-9 h-9 rounded-full bg-gray-200 dark:bg-gray-700 shrink-0" />
                <div className="flex-1">
                  <div className="h-3.5 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-1.5" />
                  <div className="h-2.5 bg-gray-100 dark:bg-gray-800 rounded w-1/4" />
                </div>
              </div>
            ))}
          </div>
        ) : !activities || activities.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8">
            <div className="w-14 h-14 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center mb-3">
              <Activity className="w-7 h-7 text-gray-400" />
            </div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Aucune activité récente</p>
          </div>
        ) : (
          <div className="relative">
            {/* Timeline connector */}
            <div className="absolute left-[17px] top-2 bottom-2 w-px bg-gray-100 dark:bg-gray-800" />

            <div className="space-y-5">
              {activities.map((activity) => {
                const style = TYPE_STYLES[activity.type] ?? TYPE_STYLES.candidate_added;
                const Icon = style.icon;
                return (
                  <div key={activity.id} className="relative flex items-start gap-3 group">
                    <div
                      className={`relative z-10 flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center ring-4 ring-white dark:ring-gray-800 ${style.bg} ${style.text} transition-transform group-hover:scale-105`}
                    >
                      <Icon className="w-4 h-4" />
                    </div>

                    <div className="flex-1 min-w-0 pt-1.5">
                      <p className="text-sm text-gray-700 dark:text-gray-200 leading-snug">
                        {getActivityDescription(activity)}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {getTimeAgo(activity.timestamp)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
