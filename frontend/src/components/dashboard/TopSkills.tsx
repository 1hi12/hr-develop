import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from '@/contexts/LanguageContext';
import { TrendingUp } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

interface TopSkill {
  skill: string;
  count: number;
  jobs: number;
}

const RANK_STYLES = [
  {
    badge: 'bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-700',
    bar: 'from-amber-400 to-orange-400',
    glow: 'shadow-amber-200 dark:shadow-amber-900',
  },
  {
    badge: 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700',
    bar: 'from-indigo-500 to-violet-500',
    glow: '',
  },
  {
    badge: 'bg-orange-50 dark:bg-orange-900/30 text-orange-500 dark:text-orange-400 border border-orange-200 dark:border-orange-700',
    bar: 'from-teal-500 to-cyan-400',
    glow: '',
  },
  {
    badge: 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700',
    bar: 'from-blue-500 to-sky-400',
    glow: '',
  },
  {
    badge: 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700',
    bar: 'from-pink-500 to-rose-400',
    glow: '',
  },
];

const RANK_LABELS = ['🥇', '🥈', '🥉', '4', '5'];

function AnimatedBar({ pct, colorClass }: { pct: number; colorClass: string }) {
  const [width, setWidth] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          requestAnimationFrame(() => setWidth(pct));
          observer.disconnect();
        }
      },
      { threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [pct]);

  return (
    <div ref={ref} className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
      <div
        className={`h-full bg-gradient-to-r ${colorClass} rounded-full transition-all duration-700 ease-out`}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

export function TopSkills() {
  const { t } = useTranslation();

  const { data: skills, isLoading } = useQuery<TopSkill[]>({
    queryKey: ['dashboard', 'top-skills'],
    queryFn: async () => {
      const response = await fetch('/api/v1/dashboard/top-skills?limit=5');
      if (!response.ok) throw new Error('Failed to fetch top skills');
      return response.json();
    },
  });

  const maxCount = skills && skills.length > 0 ? Math.max(...skills.map((s) => s.count)) : 1;

  return (
    <Card className="border border-gray-200 dark:border-gray-700 shadow-sm bg-white dark:bg-gray-800 h-full flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-teal-50 dark:bg-teal-900/30 rounded-lg shrink-0">
            <TrendingUp className="h-4.5 w-4.5 text-teal-600 dark:text-teal-400" />
          </div>
          <div className="min-w-0">
            <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white leading-tight">
              {t('dashboard.topSkills') || 'Compétences les plus recherchées'}
            </CardTitle>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
              Top 5 des compétences dans les offres actives
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0 flex-1 flex flex-col">
        {isLoading ? (
          <div className="flex-1 space-y-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-gray-200 dark:bg-gray-700 shrink-0" />
                  <div className="flex-1">
                    <div className="h-3.5 bg-gray-200 dark:bg-gray-700 rounded w-2/3 mb-1.5" />
                    <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full" />
                  </div>
                  <div className="w-12 h-5 bg-gray-200 dark:bg-gray-700 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        ) : !skills || skills.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center py-8">
            <div className="w-14 h-14 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center mb-3">
              <TrendingUp className="w-7 h-7 text-gray-400" />
            </div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Aucune compétence pour le moment</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Ajoutez des offres d'emploi pour voir les tendances</p>
          </div>
        ) : (
          <div className="flex-1 space-y-4">
            {skills.map((skill, index) => {
              const style = RANK_STYLES[index] ?? RANK_STYLES[RANK_STYLES.length - 1];
              const pct = Math.round((skill.count / maxCount) * 100);

              return (
                <div key={index} className="group">
                  <div className="flex items-center gap-3 mb-1.5">
                    {/* Rank badge */}
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold shrink-0 ${style.badge} ${index === 0 ? `shadow-md ${style.glow}` : ''}`}
                    >
                      {RANK_LABELS[index]}
                    </div>

                    {/* Skill name */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span
                          className={`text-sm font-semibold truncate capitalize ${
                            index === 0
                              ? 'text-gray-900 dark:text-white'
                              : 'text-gray-700 dark:text-gray-300'
                          }`}
                        >
                          {skill.skill}
                        </span>
                        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-full whitespace-nowrap shrink-0">
                          {skill.count}×
                        </span>
                      </div>
                      <AnimatedBar pct={pct} colorClass={style.bar} />
                    </div>
                  </div>

                  {/* Jobs count for top skill */}
                  {index === 0 && skill.jobs > 0 && (
                    <div className="ml-11 mt-0.5">
                      <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">
                        🔥 Présente dans {skill.jobs} offre{skill.jobs > 1 ? 's' : ''}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Footer */}
        {skills && skills.length > 0 && (
          <div className="mt-5 pt-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between">
            <span className="text-xs text-gray-400 dark:text-gray-500">Basé sur {skills.reduce((a, s) => a + s.count, 0)} mentions</span>
            <span className="text-xs font-medium text-teal-600 dark:text-teal-400">
              Top compétence : {skills[0]?.skill}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
