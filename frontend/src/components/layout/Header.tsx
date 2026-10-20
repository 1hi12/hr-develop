import { ThemeToggle } from '@/components/shared/ThemeToggle'

export function Header() {
  return (
    <header className="border-b bg-background">
      <div className="container flex h-14 items-center justify-between">
        <span className="font-semibold">HR Assistant</span>
        <ThemeToggle />
      </div>
    </header>
  )
}
