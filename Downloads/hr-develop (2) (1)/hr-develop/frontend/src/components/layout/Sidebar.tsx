// Use plain anchors for now because the app's route types only include '/'.
// Using <a> avoids TypeScript errors from @tanstack/react-router's generated types.
import {
  LayoutDashboard,
  Users,
  Briefcase,
  Bot,
  Plus,
  LogOut,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { useTranslation } from '@/contexts/LanguageContext';

export function Sidebar() {
  const { t } = useTranslation();
  const [activePath, setActivePath] = useState(window.location.pathname);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const logout = useAuthStore((state) => state.logout);

  // Liste des liens de navigation
  const navItems = [
    { labelKey: 'nav.dashboard',    icon: LayoutDashboard, path: '/' },
    { labelKey: 'nav.candidates',   icon: Users,           path: '/candidates' },
    { labelKey: 'nav.jobMatching', icon: Briefcase,       path: '/job-matching' },
    { labelKey: 'nav.aiAssistant', icon: Bot,             path: '/ai-assistant' },
    { labelKey: 'nav.postings',     icon: Plus,            path: '/postings' },
  ];

  useEffect(() => {
    // Mettre à jour le chemin actif lorsque l'URL change
    const handleLocationChange = () => {
      setActivePath(window.location.pathname);
    };

    window.addEventListener('popstate', handleLocationChange);
    return () => window.removeEventListener('popstate', handleLocationChange);
  }, []);

  const handleSignOut = async () => {
    if (isSigningOut) return;

    try {
      setIsSigningOut(true);
      await logout();
      window.location.href = '/login';
    } finally {
      setIsSigningOut(false);
    }
  };

  return (
    <aside className="w-64 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col fixed left-0 top-0 bottom-0 z-40 transition-colors">
     {/* Logo Sofrecom */}
<div className="flex items-center justify-center px-6 py-6 border-b border-gray-100 dark:border-gray-800">
  <img
    src="/sofrecom-meta-logo-small-2025.webp"
    alt="Sofrecom Logo"
    className="h-14 w-auto object-contain"
  />
</div>

      {/* Navigation principale */}
      <nav className="flex-1 px-4 py-6 space-y-1">
        {navItems.map(({ labelKey, icon: Icon, path }) => {
          const isActive = activePath === path;
          const isPostings = path === '/postings';
          
          return (
            <a
              key={path}
              href={path}
              onClick={() => setActivePath(path)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-black dark:bg-white text-white dark:text-black'
                  : isPostings
                  ? 'text-indigo-600 dark:text-indigo-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              <Icon size={18} />
              {t(labelKey)}
            </a>
          );
        })}
      </nav>

      {/* Liens du bas (Sign Out) */}
      <div className="px-4 py-4 border-t border-gray-100 dark:border-gray-800 space-y-1">
        <button
          type="button"
          onClick={handleSignOut}
          disabled={isSigningOut}
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 w-full transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <LogOut size={18} />
          {isSigningOut ? t('nav.signingOut') : t('nav.signOut')}
        </button>
      </div>
    </aside>
  );
}