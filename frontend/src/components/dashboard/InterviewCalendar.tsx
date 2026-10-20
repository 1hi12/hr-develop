import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useInterviews, useCandidates } from '@/lib/query/mutations'
import { queryKeys } from '@/lib/query/queryKeys'
import { useTranslation } from '@/contexts/LanguageContext'
import { InterviewSchedulerModal } from '@/components/candidates/InterviewSchedulerModal'
import type { Candidate } from '@/types/candidates.types'

const DAY_LABELS = ['Lun.', 'Mar.', 'Mer.', 'Jeu.', 'Ven.']

function startOfWeek(date: Date): Date {
  const d = new Date(date)
  const day = d.getDay() // 0 = Sunday
  const diff = day === 0 ? -6 : 1 - day
  d.setDate(d.getDate() + diff)
  d.setHours(0, 0, 0, 0)
  return d
}

function toDateKey(d: Date): string {
  return d.toISOString().slice(0, 10)
}

const FORMAT_STYLES: Record<string, string> = {
  online: 'bg-brand-50 border-brand-200 text-brand-600',
  onsite: 'bg-amber-50 border-amber-400/30 text-amber-400',
}

export function InterviewCalendar() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [weekOffset, setWeekOffset] = useState(0)
  const [schedulingCandidate, setSchedulingCandidate] = useState<Candidate | null>(null)

  const { data: interviews = [], isLoading } = useInterviews()
  const { data: pendingCandidates } = useCandidates({ status: 'pending', limit: 100 })

  const weekStart = useMemo(() => {
    const base = new Date()
    base.setDate(base.getDate() + weekOffset * 7)
    return startOfWeek(base)
  }, [weekOffset])

  const days = useMemo(
    () => Array.from({ length: 5 }, (_, i) => {
      const d = new Date(weekStart)
      d.setDate(d.getDate() + i)
      return d
    }),
    [weekStart]
  )

  const todayKey = toDateKey(new Date())

  const interviewsByDay = useMemo(() => {
    const map = new Map<string, typeof interviews>()
    for (const iv of interviews) {
      if (iv.status !== 'scheduled') continue
      const list = map.get(iv.interview_date) ?? []
      list.push(iv)
      map.set(iv.interview_date, list)
    }
    for (const list of map.values()) list.sort((a, b) => a.interview_time.localeCompare(b.interview_time))
    return map
  }, [interviews])

  const scheduledCandidateIds = useMemo(
    () => new Set(interviews.filter((iv) => iv.status === 'scheduled').map((iv) => iv.candidate_id)),
    [interviews]
  )

  const toSchedule = (pendingCandidates?.items ?? [])
    .flatMap((g) => g.candidates)
    .filter((c) => !scheduledCandidateIds.has(c.candidate_id))

  const weekRangeLabel = `${weekStart.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' })} — ${days[4].toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })}`

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium text-sm text-gray-900 dark:text-white">{t('dashboard.calendar.title')}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {t('dashboard.calendar.weekOf')} {weekRangeLabel}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setWeekOffset((w) => w - 1)}
            className="w-8 h-8 rounded-lg border border-gray-200 dark:border-gray-700 flex items-center justify-center text-gray-500 hover:text-gray-900 dark:hover:text-white"
          >
            ‹
          </button>
          <button
            onClick={() => setWeekOffset(0)}
            className="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300"
          >
            {t('dashboard.calendar.thisWeek')}
          </button>
          <button
            onClick={() => setWeekOffset((w) => w + 1)}
            className="w-8 h-8 rounded-lg border border-gray-200 dark:border-gray-700 flex items-center justify-center text-gray-500 hover:text-gray-900 dark:hover:text-white"
          >
            ›
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3 grid grid-cols-1 sm:grid-cols-5 gap-3">
          {days.map((day, i) => {
            const key = toDateKey(day)
            const isToday = key === todayKey
            const dayInterviews = interviewsByDay.get(key) ?? []
            return (
              <div
                key={key}
                className={`bg-white dark:bg-gray-900 rounded-xl border p-3 h-[280px] overflow-y-auto ${isToday ? 'border-brand-400/50' : 'border-gray-100 dark:border-gray-800'}`}
              >
                <p className={`text-xs mb-2 ${isToday ? 'text-brand-600 font-medium' : 'text-gray-500 dark:text-gray-400'}`}>
                  {DAY_LABELS[i]} {day.getDate()}
                  {isToday && ` · ${t('dashboard.calendar.today')}`}
                </p>
                {isLoading ? (
                  <div className="h-16 rounded-lg bg-gray-50 dark:bg-gray-800 animate-pulse" />
                ) : dayInterviews.length === 0 ? (
                  <p className="text-[11px] text-gray-300 dark:text-gray-600 mt-6 text-center">
                    {t('dashboard.calendar.noInterview')}
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {dayInterviews.map((iv) => (
                      <div
                        key={iv.interview_id}
                        className={`border rounded-lg p-2 ${FORMAT_STYLES[iv.format] ?? FORMAT_STYLES.online}`}
                      >
                        <p className="text-[11px] font-medium">{iv.interview_time}</p>
                        <p className="text-xs mt-0.5 text-gray-900 dark:text-gray-100">{iv.candidate_name ?? '—'}</p>
                        <p className="text-[10px] text-gray-500 dark:text-gray-400">
                          {[iv.job_title, iv.platform ?? (iv.format === 'onsite' ? iv.room_name : null), `${iv.duration_min} min`]
                            .filter(Boolean)
                            .join(' · ')}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4 h-[280px] flex flex-col">
          <p className="font-medium text-sm text-gray-900 dark:text-white mb-1">{t('dashboard.calendar.toSchedule')}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{t('dashboard.calendar.toScheduleSubtitle')}</p>
          <div className="space-y-2.5 overflow-y-auto pr-1 flex-1 min-h-0">
            {toSchedule.length === 0 && (
              <p className="text-xs text-gray-400">{t('dashboard.calendar.noneToSchedule')}</p>
            )}
            {toSchedule.map((c) => (
              <div
                key={c.candidate_id}
                className="flex items-center justify-between gap-2 bg-gray-50 dark:bg-gray-800 rounded-lg p-2.5"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-7 h-7 rounded-full bg-brand-100 text-brand-600 flex items-center justify-center text-[11px] font-semibold shrink-0">
                    {(c.full_name ?? '?').split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-medium truncate text-gray-900 dark:text-gray-100">{c.full_name}</p>
                    <p className="text-[10px] text-gray-500 dark:text-gray-400">{c.seniority_level}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSchedulingCandidate(c)}
                  className="text-[11px] px-2 py-1 rounded-md bg-brand-50 text-brand-600 shrink-0 hover:bg-brand-100"
                >
                  {t('dashboard.calendar.schedule')}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {schedulingCandidate && (
        <InterviewSchedulerModal
          candidate={schedulingCandidate}
          onClose={() => setSchedulingCandidate(null)}
          onScheduled={() => {
            setSchedulingCandidate(null)
            queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.interviews() })
            queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all })
          }}
        />
      )}
    </div>
  )
}

export default InterviewCalendar
