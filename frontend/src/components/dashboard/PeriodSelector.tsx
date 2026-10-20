import React from 'react'
import { Period } from '@/stores/dashboardStore'

interface PeriodSelectorProps {
  period: Period
  onChange: (period: Period) => void
}

export function PeriodSelector({ period, onChange }: PeriodSelectorProps) {
  const periods: { label: string; value: Period }[] = [
    { label: '1 Month', value: '1M' },
    { label: '3 Months', value: '3M' },
    { label: '6 Months', value: '6M' },
  ]

  return (
    <div className="inline-flex items-center gap-1 rounded-lg bg-muted p-1">
      {periods.map((p) => (
        <button
          key={p.value}
          onClick={() => onChange(p.value)}
          className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${
            period === p.value
              ? 'bg-white text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {p.label}
        </button>
      ))}
    </div>
  )
}

export default PeriodSelector
