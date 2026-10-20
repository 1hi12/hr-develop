import { createRootRouteWithContext, Outlet, useLocation } from '@tanstack/react-router'
import type { QueryClient } from '@tanstack/react-query'
import { MainLayout } from '@/components/layout/MainLayout'
import { useAuthStore } from '@/stores/authStore'
import { useProtectedRoute } from '@/hooks/useProtectedRoute'
import { useEffect } from 'react'

interface RouterContext {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootComponent,
})

function RootComponent() {
  const { checkAuth } = useAuthStore()
  const location = useLocation()

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  // Routes without layout (public routes)
  const publicRoutes = ['/login', '/sso-callback']
  const isPublicRoute = publicRoutes.some(route => location.pathname.startsWith(route))

  useProtectedRoute(!isPublicRoute)

  if (isPublicRoute) {
    return <Outlet />
  }

  return (
    <MainLayout>
      <Outlet />
    </MainLayout>
  )
}
