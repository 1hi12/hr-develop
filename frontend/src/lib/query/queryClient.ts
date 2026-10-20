import { QueryClient } from '@tanstack/react-query'

const MATCHING_CACHE_KEY = 'hr_matching_cache_v2'

// Remove old cache versions automatically
localStorage.removeItem('hr_matching_cache_v1')

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      gcTime: 1000 * 60 * 30, // 30 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
})

// ── Restore matching cache from localStorage on startup ───────────────────────
try {
  const saved = localStorage.getItem(MATCHING_CACHE_KEY)
  if (saved) {
    const entries: Record<string, any> = JSON.parse(saved)
    Object.entries(entries).forEach(([jobId, data]) => {
      // Skip empty results — forces a fresh API call instead of showing "No candidates"
      if (!jobId || !data) return
      if (!Array.isArray(data.matched_candidates) || data.matched_candidates.length === 0) return
      const restored = {
        ...data,
        matched_candidates: data.matched_candidates.map((c: any) => ({
          ...c,
          status: 'pending',
        })),
      }
      queryClient.setQueryData(['matching', jobId], restored)
    })
  }
} catch {
  // corrupted cache — ignore, will be rebuilt on next fetch
  localStorage.removeItem(MATCHING_CACHE_KEY)
}

// ── Clear matching cache when new CVs are added ───────────────────────────────
export function clearMatchingCache() {
  localStorage.removeItem(MATCHING_CACHE_KEY)
  queryClient.removeQueries({ queryKey: ['matching'] })
}

// ── Persist matching cache to localStorage on every update ────────────────────
queryClient.getQueryCache().subscribe((event) => {
  if (
    event.type === 'updated' &&
    Array.isArray(event.query.queryKey) &&
    event.query.queryKey[0] === 'matching' &&
    event.query.queryKey[1]
  ) {
    try {
      const snapshot: Record<string, unknown> = {}
      queryClient
        .getQueriesData<any>({ queryKey: ['matching'] })
        .forEach(([key, data]) => {
          const jobId = key[1] as string
          if (jobId && data) {
            // Strip candidate statuses — on refresh they should show as pending
            // Scores/rankings are expensive (AI), statuses are cheap (DB)
            snapshot[jobId] = {
              ...data,
              matched_candidates: (data.matched_candidates ?? []).map((c: any) => ({
                ...c,
                status: 'pending',
              })),
            }
          }
        })
      localStorage.setItem(MATCHING_CACHE_KEY, JSON.stringify(snapshot))
    } catch {
      // localStorage full or unavailable — skip silently
    }
  }
})
