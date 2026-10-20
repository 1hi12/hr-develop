import { useEffect, useRef, useState } from 'react';
import { Bell, ChevronDown, Moon, Sun } from 'lucide-react';
import { useTheme } from '@/hooks/ui/useTheme';
import { useAuthStore } from '@/stores/authStore';
import { LanguageSelector } from '../common/LanguageSelector';
import { AlertsPanel } from '../dashboard/AlertsPanel';

export function Topbar() {
  const { theme, toggleTheme } = useTheme();
  const user = useAuthStore((state) => state.user);
  const displayName = user?.name || 'Sofrecom Admin';
  const displayEmail = user?.email || 'Head of HR';
  const initials = displayName
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  const [isAlertsOpen, setIsAlertsOpen] = useState(false);
  const alertsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (alertsRef.current && !alertsRef.current.contains(event.target as Node)) {
        setIsAlertsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="h-16 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex items-center justify-end px-6 fixed top-0 left-64 right-0 z-30 transition-colors">
      {/* Section droite : Theme Toggle + Language + Notifications + Profil utilisateur */}
      <div className="flex items-center gap-4">
        {/* Theme Toggle */}
        <button 
          onClick={toggleTheme}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? (
            <Sun size={20} className="text-gray-600 dark:text-gray-400" />
          ) : (
            <Moon size={20} className="text-gray-600 dark:text-gray-400" />
          )}
        </button>

        {/* Language Selector */}
        <LanguageSelector />

        {/* Cloche de notification */}
        <div className="relative" ref={alertsRef}>
          <button
            onClick={() => setIsAlertsOpen((prev) => !prev)}
            className="relative p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            aria-label="Notifications"
          >
            <Bell size={20} className="text-gray-600 dark:text-gray-400" />
            {/* Point rouge pour indiquer des notifications */}
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full"></span>
          </button>

          {isAlertsOpen && (
            <div className="absolute right-0 top-full mt-2 w-96 max-h-[28rem] overflow-y-auto bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-lg p-4 z-40">
              <AlertsPanel />
            </div>
          )}
        </div>

        {/* Profil utilisateur */}
        <div className="flex items-center gap-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 px-3 py-2 rounded-lg transition-colors">
          {/* Avatar avec initiales */}
          <div className="w-8 h-8 bg-orange-400 dark:bg-orange-500 rounded-full flex items-center justify-center">
            <span className="text-white text-xs font-bold">{initials || 'SA'}</span>
          </div>
          {/* Nom et rôle */}
          <div className="text-left">
            <p className="text-sm font-medium text-gray-800 dark:text-gray-200">{displayName}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">{displayEmail}</p>
          </div>
          {/* Flèche déroulante */}
          <ChevronDown size={14} className="text-gray-400 dark:text-gray-500" />
        </div>
      </div>
    </header>
  );
}
