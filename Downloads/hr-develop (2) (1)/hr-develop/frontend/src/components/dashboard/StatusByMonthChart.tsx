import { useState } from 'react'
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useStatusByMonth, useStatusByDay } from '@/lib/query/mutations'
import { useTranslation } from '@/contexts/LanguageContext'
import type { CandidateStatus } from '@/types/candidates.types'

const NOW = new Date()
const CURRENT_YEAR = NOW.getFullYear()
const CURRENT_MONTH = NOW.getMonth() + 1

const MONTH_NAMES = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
]

type ViewMode = 'year' | 'day'

interface Props {
  onStatusClick?: (status: CandidateStatus) => void
}

const SERIES: { key: 'received' | 'interview' | 'hired'; status: CandidateStatus; color: string; labelKey: string }[] = [
  { key: 'received', status: 'pending', color: '#6b62d6', labelKey: 'dashboard.statusByMonth.received' },
  { key: 'interview', status: 'interviewing', color: '#BA7517', labelKey: 'dashboard.statusByMonth.interview' },
  { key: 'hired', status: 'hired', color: '#1D9E75', labelKey: 'dashboard.statusByMonth.hired' },
]

export function StatusByMonthChart({ onStatusClick }: Props) {
  const { t } = useTranslation()
  const [viewMode, setViewMode] = useState<ViewMode>('year')
  const [year, setYear] = useState(CURRENT_YEAR)
  const [month, setMonth] = useState(CURRENT_MONTH)

  const yearQuery = useStatusByMonth(year)
  const dayQuery = useStatusByDay(year, month)
  const { data, isLoading } = viewMode === 'year' ? yearQuery : dayQuery

  const chartData = data?.labels.map((label, i) => ({
    label,
    received: data.received[i],
    interview: data.interview[i],
    hired: data.hired[i],
  })) ?? []

  const isAtLatest = viewMode === 'year'
    ? year >= CURRENT_YEAR
    : year > CURRENT_YEAR || (year === CURRENT_YEAR && month >= CURRENT_MONTH)

  const goPrev = () => {
    if (viewMode === 'year') {
      setYear((y) => y - 1)
      return
    }
    if (month === 1) {
      setMonth(12)
      setYear((y) => y - 1)
    } else {
      setMonth((m) => m - 1)
    }
  }

  const goNext = () => {
    if (isAtLatest) return
    if (viewMode === 'year') {
      setYear((y) => y + 1)
      return
    }
    if (month === 12) {
      setMonth(1)
      setYear((y) => y + 1)
    } else {
      setMonth((m) => m + 1)
    }
  }

  const toggleMode = () => {
    setViewMode((mode) => (mode === 'year' ? 'day' : 'year'))
  }

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4 animate-pulse h-full min-h-[280px]" />
    )
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4 sm:p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-1">
        <p className="font-medium text-sm text-gray-900 dark:text-white">{t('dashboard.statusByMonth.title')}</p>
        <div className="flex items-center gap-1 bg-[#0f1c3f] rounded-full pl-1 pr-2 py-1">
          <button
            type="button"
            onClick={goPrev}
            aria-label="Précédent"
            className="w-6 h-6 rounded-full flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="text-xs font-semibold text-white text-center whitespace-nowrap px-1">
            {viewMode === 'year' ? year : `${MONTH_NAMES[month - 1]} ${year}`}
          </span>
          <button
            type="button"
            onClick={goNext}
            disabled={isAtLatest}
            aria-label="Suivant"
            className="w-6 h-6 rounded-full flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-transparent"
          >
            <ChevronRight size={14} />
          </button>
          <button
            type="button"
            onClick={toggleMode}
            aria-label={viewMode === 'year' ? 'Voir par jour' : 'Voir par année'}
            title={viewMode === 'year' ? 'Voir par jour' : 'Voir par année'}
            className="w-6 h-6 rounded-full flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 ml-1"
          >
            <Calendar size={13} />
          </button>
        </div>
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        {viewMode === 'year' ? t('dashboard.statusByMonth.subtitle') : t('dashboard.statusByMonth.subtitleDaily')}
      </p>

      <div className="flex-1 min-h-[200px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 4, right: 8, left: -28, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} dy={4} interval={viewMode === 'day' ? 2 : 0} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} allowDecimals={false} width={24} />
            <Tooltip
              contentStyle={{ borderRadius: 8, border: 'none', boxShadow: '0 4px 16px rgba(0,0,0,0.1)', fontSize: 11, padding: '6px 10px' }}
              labelStyle={{ fontWeight: 700, marginBottom: 2, fontSize: 11 }}
              itemStyle={{ padding: '1px 0' }}
            />
            {SERIES.map((s) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={t(s.labelKey)}
                stackId="status"
                fill={s.color}
                radius={s.key === 'hired' ? [3, 3, 0, 0] : undefined}
                cursor="pointer"
                onClick={() => onStatusClick?.(s.status)}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-wrap gap-4 text-[11px] mt-3">
        {SERIES.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => onStatusClick?.(s.status)}
            className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          >
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
            {t(s.labelKey)}
          </button>
        ))}
      </div>
    </div>
  )
}

export default StatusByMonthChart
