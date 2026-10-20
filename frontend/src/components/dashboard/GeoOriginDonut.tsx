import { useRef, useState } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { useGeoOrigins } from '@/lib/query/mutations'
import { useTranslation } from '@/contexts/LanguageContext'
import { exportElementToPdf } from '@/lib/exportPdf'

const COLORS = ['#6b62d6', '#AFA9EC', '#EEEDFE']

export function GeoOriginDonut() {
  const { t } = useTranslation()
  const { data, isLoading } = useGeoOrigins()
  const cardRef = useRef<HTMLDivElement>(null)
  const [exporting, setExporting] = useState(false)

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const handleExport = async () => {
    if (!cardRef.current || exporting) return
    setExporting(true)
    try {
      await exportElementToPdf(cardRef.current, 'provenance-geographique.pdf')
    } finally {
      setExporting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4 sm:p-5 animate-pulse h-64" />
    )
  }

  return (
    <div ref={cardRef} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <p className="font-medium text-sm text-gray-900 dark:text-white">{t('dashboard.geoOrigins.title')}</p>
        <button
          onClick={handleExport}
          disabled={exporting}
          className="text-xs px-2.5 py-1 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white disabled:opacity-50"
        >
          {exporting ? '…' : t('dashboard.geoOrigins.export')}
        </button>
      </div>

      {items.length === 0 ? (
        <div className="flex items-center justify-center h-[160px] text-gray-400 text-sm">
          {t('dashboard.geoOrigins.noData')}
        </div>
      ) : (
        <>
          <div className="relative mx-auto" style={{ width: 160, height: 160 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  key={items.map((i) => i.label).join('|')}
                  data={items}
                  dataKey="count"
                  nameKey="label"
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={78}
                  paddingAngle={0}
                  startAngle={90}
                  endAngle={450}
                  isAnimationActive={false}
                >
                  {items.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} stroke="none" />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span className="text-2xl font-semibold text-gray-900 dark:text-white">{total}</span>
              <span className="text-[11px] text-gray-500 dark:text-gray-400">{t('dashboard.geoOrigins.candidates')}</span>
            </div>
          </div>

          <ul className="mt-4 space-y-1.5 max-w-[220px] mx-auto">
            {items.map((item, i) => (
              <li key={item.label} className="flex items-center justify-between px-3 py-1.5 rounded-full bg-gray-50 dark:bg-gray-800">
                <div className="flex items-center gap-2.5">
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {item.label === 'Autre / distance' ? t('dashboard.geoOrigins.other') : item.label}
                  </span>
                </div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">{item.value}%</div>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-3 text-center">{t('dashboard.geoOrigins.subtitle')}</p>
    </div>
  )
}

export default GeoOriginDonut
