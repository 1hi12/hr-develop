import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import StatsCard from '@/components/dashboard/StatsCard'
import ApplicantTrends from '@/components/dashboard/ApplicantTrends'
import DepartmentsDonut from '@/components/dashboard/DepartmentsDonut'
import { TopSkills } from '@/components/dashboard/TopSkills'
import { RecentActivity } from '@/components/dashboard/RecentActivity'
import { AdvancedKPIs } from '@/components/dashboard/AdvancedKPIs'
import { InterviewCalendar } from '@/components/dashboard/InterviewCalendar'
import { StatusByMonthChart } from '@/components/dashboard/StatusByMonthChart'
import { User, FileText, CheckCircle, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { JobPostingDialog } from '@/components/postings/JobPostingDialog'
import { useDashboardStats } from '@/lib/query/mutations'
import { useTranslation } from '@/contexts/LanguageContext'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  const { t } = useTranslation();
  const { data: stats, isLoading, error } = useDashboardStats();
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  return (
    <div className="p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">{t('dashboard.title')}</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">{t('dashboard.subtitle')}</p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            onClick={() => setIsDialogOpen(true)}
            className="bg-black dark:bg-white text-white dark:text-black hover:bg-gray-800 dark:hover:bg-gray-100"
          >
            {t('dashboard.newJob')}
          </Button>
        </div>
      </div>

      <JobPostingDialog open={isDialogOpen} onOpenChange={setIsDialogOpen} />

      {isLoading ? (
        <div className="flex items-center justify-center h-64 text-gray-500">
          {t('common.loading')}
        </div>
      ) : error ? (
        <div className="flex items-center justify-center h-64 text-red-600">
          {t('dashboard.errorLoading')}: {error instanceof Error ? error.message : t('dashboard.unknownError')}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
            <StatsCard
              title={t('dashboard.activeCandidates').toUpperCase()}
              value={stats?.activeCandidates?.toLocaleString() || '0'}
              icon={<User className="w-5 h-5" />}
              iconBg="bg-blue-50 text-blue-600"
            />

            <StatsCard
              title={t('dashboard.cvsScreened').toUpperCase()}
              value={stats?.cvsScreened?.toLocaleString() || '0'}
              icon={<FileText className="w-5 h-5" />}
              iconBg="bg-indigo-50 text-indigo-600"
            />

            <StatsCard
              title={t('dashboard.hiredCandidates').toUpperCase()}
              value={stats?.hiredCandidates?.toLocaleString() || '0'}
              icon={<CheckCircle className="w-5 h-5" />}
              iconBg="bg-green-50 text-green-600"
            />

            <StatsCard
              title={t('dashboard.avgDaysToHire').toUpperCase()}
              value={stats?.avgDaysToHire || 0}
              icon={<Clock className="w-5 h-5" />}
              iconBg="bg-orange-50 text-orange-500"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <div className="lg:col-span-2">
              <ApplicantTrends />
            </div>
            <div className="lg:col-span-1">
              <DepartmentsDonut />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
            <TopSkills />
            <RecentActivity />
          </div>

          {/* ── Dashboard sections ── */}
          <div className="mt-6 space-y-6">

            {/* Row: Interview calendar + candidature-by-status chart */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
              <InterviewCalendar />
              <StatusByMonthChart />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
