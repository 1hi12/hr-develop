import { useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useAuthStore } from '@/stores/authStore'

export function useProtectedRoute(enabled = true) {
  const navigate = useNavigate()
  const { isAuthenticated, isLoading } = useAuthStore()

  useEffect(() => {
    if (enabled && !isLoading && !isAuthenticated) {
      navigate({ to: '/login' })
    }
  }, [enabled, isAuthenticated, isLoading, navigate])

  return { isAuthenticated, isLoading }
}
