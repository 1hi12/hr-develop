import { useRef, useState } from 'react'
import { useCandidates, useUpdateCandidateStatusMutation } from '@/lib/query/mutations'
import { useTranslation } from '@/contexts/LanguageContext'
import { CandidateDetailModal } from '@/components/candidates/CandidateDetailModal'
import type { Candidate, CandidateStatus } from '@/types/candidates.types'

interface Props {
  highlightStatus?: CandidateStatus
}

const COLUMNS: { status: CandidateStatus; labelKey: string; avatarClass: string }[] = [
  { status: 'pending', labelKey: 'dashboard.kanban.received', avatarClass: 'bg-brand-100 text-brand-600' },
  { status: 'interviewing', labelKey: 'dashboard.kanban.interviewing', avatarClass: 'bg-amber-50 text-amber-400' },
  { status: 'hired', labelKey: 'dashboard.kanban.hired', avatarClass: 'bg-teal-50 text-teal-600' },
]

function initials(name: string | null): string {
  if (!name) return '?'
  return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()
}

function KanbanColumn({
  status,
  labelKey,
  avatarClass,
  highlighted,
  onDropCandidate,
  onCardClick,
}: {
  status: CandidateStatus
  labelKey: string
  avatarClass: string
  highlighted: boolean
  onDropCandidate: (candidateId: string, fromStatus: CandidateStatus) => void
  onCardClick: (c: Candidate) => void
}) {
  const { t } = useTranslation()
  const [dragOver, setDragOver] = useState(false)
  const { data, isLoading } = useCandidates({ status, limit: 100 })
  const candidates = (data?.items ?? []).flatMap((g) => g.candidates)

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        const candidateId = e.dataTransfer.getData('candidateId')
        const fromStatus = e.dataTransfer.getData('fromStatus') as CandidateStatus
        if (candidateId && fromStatus !== status) onDropCandidate(candidateId, fromStatus)
      }}
      className={`rounded-xl border p-3 transition-colors ${
        dragOver
          ? 'bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/40'
          : highlighted
            ? 'bg-gray-50 dark:bg-gray-800/60 border-brand-300 dark:border-brand-500/30'
            : 'bg-gray-50 dark:bg-gray-800/60 border-gray-100 dark:border-gray-800'
      }`}
    >
      <div className="flex items-center justify-between mb-3 px-1">
        <span className="text-sm font-medium text-gray-900 dark:text-white">{t(labelKey)}</span>
        <span className="text-xs bg-black/5 dark:bg-white/10 rounded-full px-2 py-0.5 text-gray-600 dark:text-gray-300">
          {data?.total ?? candidates.length}
        </span>
      </div>
      <div className="space-y-2 min-h-[80px]">
        {isLoading && <div className="h-16 rounded-lg bg-white dark:bg-gray-900 animate-pulse" />}
        {candidates.map((c) => (
          <div
            key={c.candidate_id}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('candidateId', c.candidate_id)
              e.dataTransfer.setData('fromStatus', status)
            }}
            onClick={() => onCardClick(c)}
            className="bg-white dark:bg-gray-900 rounded-lg border border-gray-100 dark:border-gray-800 p-3 shadow-sm cursor-grab active:cursor-grabbing hover:border-brand-300 dark:hover:border-brand-500/40"
          >
            <div className="flex items-center gap-2 mb-1.5">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold shrink-0 ${avatarClass}`}>
                {initials(c.full_name)}
              </div>
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{c.full_name}</span>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">{c.seniority_level}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export function RecruitmentKanban({ highlightStatus }: Props) {
  const { t } = useTranslation()
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)
  const updateStatus = useUpdateCandidateStatusMutation()
  const { data: rejectedData } = useCandidates({ status: 'rejected', limit: 1 })
  const draggingRef = useRef(false)

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="font-medium text-sm text-gray-900 dark:text-white">{t('dashboard.kanban.title')}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{t('dashboard.kanban.subtitle')}</p>
        </div>
        <span className="text-xs px-2.5 py-1 rounded-full bg-coral-50 text-coral-600">
          {rejectedData?.total ?? 0} {t('dashboard.kanban.rejectedHidden')}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {COLUMNS.map((col) => (
          <KanbanColumn
            key={col.status}
            status={col.status}
            labelKey={col.labelKey}
            avatarClass={col.avatarClass}
            highlighted={highlightStatus === col.status}
            onCardClick={setSelectedCandidate}
            onDropCandidate={(candidateId, fromStatus) => {
              void fromStatus
              if (draggingRef.current) return
              draggingRef.current = true
              updateStatus.mutate(
                { id: candidateId, status: col.status },
                { onSettled: () => { draggingRef.current = false } }
              )
            }}
          />
        ))}
      </div>

      <CandidateDetailModal candidate={selectedCandidate} onClose={() => setSelectedCandidate(null)} />
    </div>
  )
}

export default RecruitmentKanban
