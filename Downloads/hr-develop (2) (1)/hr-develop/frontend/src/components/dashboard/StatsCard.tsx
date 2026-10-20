import React from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { TrendingUp } from 'lucide-react'

interface Props {
  title: string
  value: string | number
  change?: string
  icon?: React.ReactNode
  iconBg?: string
}

export function StatsCard({ title, value, change, icon, iconBg }: Props) {
  const isPositive = change?.startsWith('+') || change?.startsWith('-')
  
  return (
    <Card className="border border-gray-200 dark:border-gray-700 shadow-sm bg-white dark:bg-gray-800">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-2">
          <div className={`flex items-center justify-center w-8 h-8 rounded-lg ${iconBg ?? 'bg-blue-50 text-blue-600'}`}>
            {icon}
          </div>
          {change && (
            <div className="flex items-center gap-1 text-green-600 dark:text-green-400 text-sm font-medium">
              <TrendingUp className="w-3 h-3" />
              <span>{change}</span>
            </div>
          )}
        </div>
        
        <div>
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">{title}</div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">{value}</div>
        </div>
      </CardContent>
    </Card>
  )
}

export default StatsCard
