import React, { useState, useRef, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  TooltipProps,
  CartesianGrid,
} from 'recharts'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { ChevronDown, X } from 'lucide-react'
import { useTrends } from '@/lib/query/mutations'
import { useTranslation } from '@/contexts/LanguageContext'

const periodMap: Record<string, '1d' | '1w' | '1m' | '3m' | '6m'> = {
  'daily': '1d',
  'weekly': '1w',
  'last1Month': '1m',
  'last3Months': '3m',
  'last6Months': '6m',
}

interface CandidateDetail {
  candidate_id: string
  full_name: string
  email: string | null
  phone: string | null
  location: string | null
  status: string
  seniority_level: string | null
  total_years_experience: number | null
  created_at: string | null
}

export function ApplicantTrends() {
  const { t } = useTranslation()
  const [period, setPeriod] = useState('last6Months')
  const [isOpen, setIsOpen] = useState(false)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [candidateDetails, setCandidateDetails] = useState<CandidateDetail[]>([])
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const periods = [
    { key: 'daily', label: t('dashboard.periods.daily') },
    { key: 'weekly', label: t('dashboard.periods.weekly') },
    { key: 'last1Month', label: t('dashboard.periods.last1Month') },
    { key: 'last3Months', label: t('dashboard.periods.last3Months') },
    { key: 'last6Months', label: t('dashboard.periods.last6Months') },
  ]

  const { data: trendsData, isLoading, error } = useTrends(periodMap[period])

  const chartData = trendsData?.map((item:any) => ({
    month: item.label,
    value: item.value,
    interviews: item.interviews ?? 0,
  })) || []

  const handleChartClick = async (data: any) => {
    if (!data || !data.activeLabel) return

    const dateLabel = data.activeLabel
    setSelectedDate(dateLabel)
    setLoadingDetails(true)
    setShowModal(true)

    try {
      const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const response = await fetch(
        `${API_BASE}/api/v1/dashboard/trends/details?date=${encodeURIComponent(dateLabel)}&period=${periodMap[period]}`
      )

      if (!response.ok) throw new Error('Failed to fetch candidate details')

      const details = await response.json()
      setCandidateDetails(details)
    } catch (error) {
      console.error('Error fetching candidate details:', error)
      setCandidateDetails([])
    } finally {
      setLoadingDetails(false)
    }
  }

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <Card className="border border-gray-200 dark:border-gray-700 shadow-sm bg-white dark:bg-gray-800">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('dashboard.applicantTrends')}</CardTitle>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('dashboard.monthlySubmissions')}</p>
          </div>
          <div className="relative" ref={dropdownRef}>
            <button 
              onClick={() => setIsOpen(!isOpen)}
              className="flex items-center gap-2 px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
            >
              {periods.find(p => p.key === period)?.label || t('dashboard.periods.last6Months')}
              <ChevronDown className="w-4 h-4" />
            </button>
            {isOpen && (
              <div className="absolute right-0 mt-1 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-10">
                {periods.map((p) => (
                  <button
                    key={p.key}
                    onClick={() => {
                      setPeriod(p.key)
                      setIsOpen(false)
                    }}
                    className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-700 first:rounded-t-lg last:rounded-b-lg ${
                      period === p.key ? 'bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white font-medium' : 'text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 mt-3">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: '#5b5ce2' }} />
            <span className="text-sm text-gray-600 dark:text-gray-300">{t('dashboard.cvsReceived')}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: '#10b981' }} />
            <span className="text-sm text-gray-600 dark:text-gray-300">{t('dashboard.interviews')}</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <div className="flex items-center justify-center h-[200px] text-gray-500">
            {t('dashboard.loadingTrends')}
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-[200px] text-red-500">
            {t('dashboard.errorLoadingTrends')}
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[200px] text-gray-400">
            {t('dashboard.noTrendData')}
          </div>
        ) : (
        <div style={{ width: '100%', height: 200 }}>
          <ResponsiveContainer>
            <LineChart
              data={chartData}
              margin={{ top: 24, right: 16, left: 0, bottom: 0 }}
              onClick={handleChartClick}
              style={{ cursor: 'pointer' }}
            >
              <defs>
                <linearGradient id="lineGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#5b5ce2" stopOpacity="0.1" />
                  <stop offset="100%" stopColor="#5b5ce2" stopOpacity="0" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
              <XAxis
                dataKey="month"
                stroke="transparent"
                tick={{ fill: '#9CA3AF', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                dy={10}
                interval={
                  periodMap[period] === '1m' ? 4 :
                  periodMap[period] === '1d' ? 0 :
                  0
                }
              />
              <YAxis
                stroke="#F3F4F6"
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#9CA3AF', fontSize: 11 }}
                domain={[0, (dataMax: number) => Math.max(dataMax + 1, 5)]}
                allowDecimals={false}
                width={30}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1f2937',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  color: '#fff',
                }}
                labelStyle={{ color: '#fff', fontWeight: 600 }}
                cursor={{ stroke: '#5b5ce2', strokeWidth: 2, strokeDasharray: '5 5' }}
              />
              <Line
                type="monotone"
                dataKey="value"
                name={t('dashboard.cvsReceived')}
                stroke="#5b5ce2"
                strokeWidth={2.5}
                dot={{ fill: '#5b5ce2', r: 4, strokeWidth: 2, stroke: '#fff' }}
                activeDot={{ r: 6, fill: '#5b5ce2', stroke: '#fff', strokeWidth: 2 }}
                fill="url(#lineGradient)"
                animationDuration={300}
              />
              <Line
                type="monotone"
                dataKey="interviews"
                name={t('dashboard.interviews')}
                stroke="#10b981"
                strokeWidth={2.5}
                dot={{ fill: '#10b981', r: 4, strokeWidth: 2, stroke: '#fff' }}
                activeDot={{ r: 6, fill: '#10b981', stroke: '#fff', strokeWidth: 2 }}
                animationDuration={300}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        )}
      </CardContent>

      {/* Modal for candidate details */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full max-h-[80vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
              <div>
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                  Candidates for {selectedDate}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {candidateDetails.length} candidate{candidateDetails.length !== 1 ? 's' : ''} found
                </p>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>

            {/* Content */}
            <div className="p-6 overflow-y-auto max-h-[calc(80vh-140px)]">
              {loadingDetails ? (
                <div className="flex items-center justify-center py-12 text-gray-500">
                  Loading candidate details...
                </div>
              ) : candidateDetails.length === 0 ? (
                <div className="flex items-center justify-center py-12 text-gray-400">
                  No candidates found for this period
                </div>
              ) : (
                <div className="space-y-3">
                  {candidateDetails.map((candidate) => (
                    <div
                      key={candidate.candidate_id}
                      className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-semibold">
                              {candidate.full_name.charAt(0).toUpperCase()}
                            </div>
                            <div>
                              <h3 className="font-semibold text-gray-900 dark:text-white">
                                {candidate.full_name}
                              </h3>
                              <p className="text-sm text-gray-500 dark:text-gray-400">
                                {candidate.seniority_level ?
                                  candidate.seniority_level.charAt(0).toUpperCase() + candidate.seniority_level.slice(1)
                                  : ''}
                              </p>
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            {candidate.email && (
                              <div className="text-gray-600 dark:text-gray-400">
                                📧 {candidate.email}
                              </div>
                            )}
                            {candidate.phone && (
                              <div className="text-gray-600 dark:text-gray-400">
                                📱 {candidate.phone}
                              </div>
                            )}
                            {candidate.location && (
                              <div className="text-gray-600 dark:text-gray-400">
                                📍 {candidate.location}
                              </div>
                            )}
                            {candidate.total_years_experience && (
                              <div className="text-gray-600 dark:text-gray-400">
                                💼 {candidate.total_years_experience} years
                              </div>
                            )}
                          </div>
                        </div>
                        <span className={`
                          px-3 py-1 rounded-full text-xs font-semibold uppercase
                          ${candidate.status === 'hired' ? 'bg-green-100 text-green-800' :
                            candidate.status === 'interviewing' ? 'bg-blue-100 text-blue-800' :
                            candidate.status === 'rejected' ? 'bg-red-100 text-red-800' :
                            'bg-gray-100 text-gray-800'}
                        `}>
                          {candidate.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}

export default ApplicantTrends
