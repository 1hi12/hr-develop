import { useQuery } from '@tanstack/react-query';
import { TrendingUp, TrendingDown, Minus, Calendar, Users, Briefcase, Award } from 'lucide-react';

interface KPIData {
  conversion_rate:      number;
  conv_this_week:       number;
  conv_prev_week:       number;
  interviews_this_week: number;
  interviews_prev_week: number;
  candidates_this_week: number;
  candidates_prev_week: number;
  active_postings:      number;
  hired_this_week:      number;
  avg_days_to_hire:     number;
  total_candidates:     number;
  total_interviews:     number;
}

function Trend({ current, previous, unit = '' }: { current: number; previous: number; unit?: string }) {
  if (previous === 0 && current === 0) return <span className="text-gray-400 text-xs flex items-center gap-1"><Minus size={12} /> Stable</span>;
  if (previous === 0) return <span className="text-emerald-500 text-xs flex items-center gap-1"><TrendingUp size={12} /> Nouveau</span>;
  const pct = Math.round(((current - previous) / previous) * 100);
  if (pct > 0) return <span className="text-emerald-500 text-xs flex items-center gap-1"><TrendingUp size={12} /> +{pct}%{unit} vs sem. préc.</span>;
  if (pct < 0) return <span className="text-red-500 text-xs flex items-center gap-1"><TrendingDown size={12} /> {pct}%{unit} vs sem. préc.</span>;
  return <span className="text-gray-400 text-xs flex items-center gap-1"><Minus size={12} /> Stable</span>;
}

interface KPICardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  color: string;
  trend?: React.ReactNode;
  subtitle?: string;
}

function KPICard({ title, value, icon, color, trend, subtitle }: KPICardProps) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">{title}</span>
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${color}`}>{icon}</div>
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
        {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
      </div>
      {trend && <div>{trend}</div>}
    </div>
  );
}

export function AdvancedKPIs() {
  const { data, isLoading } = useQuery<KPIData>({
    queryKey: ['dashboard-kpis'],
    queryFn: async () => {
      const r = await fetch('/api/v1/dashboard/kpis');
      if (!r.ok) throw new Error('KPIs unavailable');
      return r.json();
    },
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 animate-pulse h-32" />
        ))}
      </div>
    );
  }

  if (!data) return null;

  const convRate = Math.min(data.conversion_rate, 100);

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
        KPIs — Semaine en cours
      </h2>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Taux de conversion"
          value={`${convRate}%`}
          subtitle="CV → Entretien (global)"
          icon={<TrendingUp size={16} className="text-white" />}
          color="bg-blue-500"
          trend={<Trend current={data.conv_this_week} previous={data.conv_prev_week} unit="%" />}
        />
        <KPICard
          title="Entretiens cette semaine"
          value={data.interviews_this_week}
          subtitle={`${data.total_interviews} au total`}
          icon={<Calendar size={16} className="text-white" />}
          color="bg-violet-500"
          trend={<Trend current={data.interviews_this_week} previous={data.interviews_prev_week} />}
        />
        <KPICard
          title="Nouveaux CVs"
          value={data.candidates_this_week}
          subtitle={`${data.total_candidates} candidats au total`}
          icon={<Users size={16} className="text-white" />}
          color="bg-emerald-500"
          trend={<Trend current={data.candidates_this_week} previous={data.candidates_prev_week} />}
        />
        <KPICard
          title="Postes actifs"
          value={data.active_postings}
          subtitle={data.avg_days_to_hire > 0 ? `Moy. ${data.avg_days_to_hire}j pour embaucher` : 'Aucune embauche encore'}
          icon={<Briefcase size={16} className="text-white" />}
          color="bg-amber-500"
        />
      </div>
    </div>
  );
}
