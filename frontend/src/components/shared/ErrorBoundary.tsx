import { useState, useEffect, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

export function ErrorBoundary({ children, fallback }: ErrorBoundaryProps) {
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    const handleError = (event: ErrorEvent) => {
      setError(event.error)
    }

    window.addEventListener('error', handleError)
    return () => window.removeEventListener('error', handleError)
  }, [])

  if (error) {
    return (
      fallback ?? (
        <div className="p-4 text-destructive">
          <h2 className="font-semibold">Something went wrong</h2>
          <p className="text-sm">{error.message}</p>
          <button
            onClick={() => setError(null)}
            className="mt-2 text-sm underline"
          >
            Try again
          </button>
        </div>
      )
    )
  }

  return children
}
