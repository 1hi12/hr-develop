import type { ReactNode } from 'react'
import { useRouterState } from '@tanstack/react-router'
import { Topbar } from './Topbar'
import { Sidebar } from './Sidebar'

interface MainLayoutProps {
  children: ReactNode
}

// Pages qui occupent tout l'espace disponible sans padding
const FULL_PAGE_ROUTES = ['/ai-assistant']

export function MainLayout({ children }: MainLayoutProps) {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const isFullPage = FULL_PAGE_ROUTES.includes(pathname)

  return (
    <div className={isFullPage ? 'h-screen overflow-hidden bg-white dark:bg-gray-950' : 'min-h-screen bg-gray-50 dark:bg-gray-950 transition-colors'}>
      <Topbar />
      <Sidebar />
      <main
        className={
          isFullPage
            ? 'ml-64 mt-16 h-[calc(100vh-4rem)] flex flex-col overflow-hidden'
            : 'ml-64 mt-16 flex-1 p-6'
        }
      >
        {children}
      </main>
    </div>
  )
}
