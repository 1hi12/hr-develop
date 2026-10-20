import React from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useDepartments } from '@/lib/query/mutations'
import { useTranslation } from '@/contexts/LanguageContext'

const COLORS = ['#5b5ce2', '#7c7ff0', '#a5b4fc', '#d1d5db']

export function DepartmentsDonut() {
  const { t } = useTranslation()
  const { data: departmentsData, isLoading, error } = useDepartments()
  
  const chartData = departmentsData?.map((dept, index) => ({
    id: `dept-${index}`,
    name: dept.label,
    value: dept.value
  })) || []
  
  return (
    <Card className="border border-gray-200 dark:border-gray-700 shadow-sm bg-white dark:bg-gray-800">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{t('dashboard.departments')}</CardTitle>
        <p className="text-sm text-gray-500 dark:text-gray-400">{t('dashboard.hiringDistribution')}</p>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <div className="flex items-center justify-center h-[160px] text-gray-500">
            {t('dashboard.loadingDepartments')}
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-[160px] text-red-500">
            {t('dashboard.errorLoadingDepartments')}
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[160px] text-gray-400">
            {t('dashboard.noDepartmentData')}
          </div>
        ) : (
        <>
        <div style={{ width: '100%', height: 160 }} className="flex items-center justify-center">
          <ResponsiveContainer>
            <PieChart>
              <Pie 
                data={chartData} 
                dataKey="value" 
                nameKey="name" 
                cx="50%" 
                cy="50%" 
                innerRadius={50} 
                outerRadius={70}
                paddingAngle={0}
                startAngle={90}
                endAngle={450}
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} stroke="none" />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>

        <ul className="mt-2 space-y-1.5">
          {chartData.map((d, i) => (
            <li key={d.id} className="flex items-center justify-between px-3 py-1.5 rounded-full bg-gray-50 dark:bg-gray-700">
              <div className="flex items-center gap-2.5">
                <span 
                  className="w-2 h-2 rounded-full flex-shrink-0" 
                  style={{ backgroundColor: COLORS[i % COLORS.length] }}
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">{d.name}</span>
              </div>
              <div className="text-sm font-semibold text-gray-900 dark:text-white">{d.value}%</div>
            </li>
          ))}
        </ul>
        </>
        )}
      </CardContent>
    </Card>
  )
}

export default DepartmentsDonut
