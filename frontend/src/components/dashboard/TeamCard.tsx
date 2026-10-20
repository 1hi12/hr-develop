import { useState, useRef, useEffect } from 'react'
import { ChevronDown } from 'lucide-react'
import { useDashboardTeam } from '@/lib/query/mutations'
import { useTranslation } from '@/contexts/LanguageContext'

const AVATAR_COLORS = [
  'bg-brand-100 text-brand-600',
  'bg-amber-50 text-amber-400',
  'bg-teal-50 text-teal-600',
  'bg-coral-50 text-coral-600',
]

export function TeamCard() {
  const { t } = useTranslation()
  const { data: team = [] } = useDashboardTeam()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('click', onClickOutside)
    return () => document.removeEventListener('click', onClickOutside)
  }, [])

  return (
    <div
      ref={ref}
      className="relative bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-sm rounded-lg p-4 cursor-pointer hover:border-brand-400/40 transition-colors"
      onClick={() => setOpen((o) => !o)}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          {t('dashboard.team')}
        </span>
        <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
      </div>
      <div className="flex items-center gap-2 mt-1">
        <p className="text-2xl font-bold text-gray-900 dark:text-white">{team.length}</p>
        <div className="flex -space-x-2">
          {team.slice(0, 4).map((m, i) => (
            <span
              key={m.id}
              className={`w-6 h-6 rounded-full border-2 border-white dark:border-gray-800 flex items-center justify-center text-[10px] font-semibold ${AVATAR_COLORS[i % AVATAR_COLORS.length]}`}
              title={m.full_name}
            >
              {m.initials}
            </span>
          ))}
        </div>
      </div>

      {open && (
        <div
          className="absolute right-0 top-full mt-2 w-72 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl p-3 z-50 text-left cursor-default"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
            {t('dashboard.teamMembers')}
          </p>
          <div className="space-y-2.5">
            {team.map((m, i) => (
              <div key={m.id} className="flex items-center gap-2.5">
                <span
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-semibold shrink-0 ${AVATAR_COLORS[i % AVATAR_COLORS.length]}`}
                >
                  {m.initials}
                </span>
                <div className="min-w-0">
                  <p className="text-sm truncate text-gray-900 dark:text-gray-100">
                    {m.full_name}
                    {m.role === 'lead' && (
                      <span className="text-[10px] text-brand-600 border border-brand-200 rounded px-1 ml-1">
                        Lead
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{m.email}</p>
                </div>
              </div>
            ))}
            {team.length === 0 && <p className="text-xs text-gray-400">{t('common.loading')}</p>}
          </div>
        </div>
      )}
    </div>
  )
}

export default TeamCard
