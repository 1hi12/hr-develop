import { create } from 'zustand'

export type Period = '1M' | '3M' | '6M'

interface DashboardStore {
  period: Period
  setPeriod: (period: Period) => void
}

export const useDashboardStore = create<DashboardStore>((set) => ({
  period: '6M',
  setPeriod: (period) => set({ period }),
}))
