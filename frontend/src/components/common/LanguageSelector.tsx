import { Globe } from 'lucide-react';
import { useTranslation } from '@/contexts/LanguageContext';

export function LanguageSelector() {
  const { language, setLanguage } = useTranslation();

  return (
    <div className="relative inline-block">
      <button
        onClick={() => setLanguage(language === 'fr' ? 'en' : 'fr')}
        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        title={language === 'fr' ? 'Switch to English' : 'Passer en français'}
      >
        <Globe className="w-4 h-4 text-gray-600 dark:text-gray-400" />
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 uppercase">
          {language}
        </span>
      </button>
    </div>
  );
}
