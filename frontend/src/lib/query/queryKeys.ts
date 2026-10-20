export const queryKeys = {
  system: {
    all: ['system'] as const,
    status: () => [...queryKeys.system.all, 'status'] as const,
  },
  postings: {
    all: ['postings'] as const,
    lists: () => [...queryKeys.postings.all, 'list'] as const,
    list: (filters?: Record<string, any>) => [...queryKeys.postings.lists(), { filters }] as const,
    detail: (id: string) => [...queryKeys.postings.all, 'detail', id] as const,
  },
  candidates: {
    all: ['candidates'] as const,
    lists: () => [...queryKeys.candidates.all, 'list'] as const,
    list: (filters?: Record<string, any>) => [...queryKeys.candidates.lists(), { filters }] as const,
    detail: (id: string) => [...queryKeys.candidates.all, 'detail', id] as const,
  },
  dashboard: {
    all: ['dashboard'] as const,
    stats: () => [...queryKeys.dashboard.all, 'stats'] as const,
    departments: () => [...queryKeys.dashboard.all, 'departments'] as const,
    trends: (period?: string) => [...queryKeys.dashboard.all, 'trends', { period }] as const,
    team: () => [...queryKeys.dashboard.all, 'team'] as const,
    interviews: () => [...queryKeys.dashboard.all, 'interviews'] as const,
    statusByMonth: (year: number) => [...queryKeys.dashboard.all, 'status-by-month', year] as const,
    statusByDay: (year: number, month: number) => [...queryKeys.dashboard.all, 'status-by-day', year, month] as const,
  },
  matching: {
    all: ['matching'] as const,
    forJob: (jobId: string, lang: string = 'fr') => [...queryKeys.matching.all, jobId, lang] as const,
  },
} as const
