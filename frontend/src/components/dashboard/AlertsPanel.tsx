import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, AlertCircle, Info, Clock } from 'lucide-react';

interface Alert {
  posting_id:      string;
  posting_title:   string;
  days_open:       number;
  interview_count: number;
  severity:        'critical' | 'warning' | 'info';
  message:         string;
}

const SEVERITY_CONFIG = {
  critical: {
    icon:       <AlertCircle size={16} />,
    bg:         'bg-red-50 dark:bg-red-950/40',
    border:     'border-red-200 dark:border-red-800',
    iconColor:  'text-red-500',
    badge:      'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
    label:      'Critique',
  },
  warning: {
    icon:       <AlertTriangle size={16} />,
    bg:         'bg-amber-50 dark:bg-amber-950/40',
    border:     'border-amber-200 dark:border-amber-800',
    iconColor:  'text-amber-500',
    badge:      'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',
    label:      'Attention',
  },
  info: {
    icon:       <Info size={16} />,
    bg:         'bg-blue-50 dark:bg-blue-950/40',
    border:     'border-blue-200 dark:border-blue-800',
    iconColor:  'text-blue-500',
    badge:      'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
    label:      'Info',
  },
};

export function AlertsPanel() {
  const { data: alerts = [], isLoading } = useQuery<Alert[]>({
    queryKey: ['dashboard-alerts'],
    queryFn: async () => {
      const r = await fetch('/api/v1/dashboard/alerts');
      if (!r.ok) throw new Error('Alerts unavailable');
      return r.json();
    },
    refetchInterval: 120_000,
  });

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 animate-pulse h-40" />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          Alertes postes en souffrance
        </h2>
        {alerts.length > 0 && (
          <span className="text-xs bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300 px-2 py-0.5 rounded-full font-medium">
            {alerts.length} alerte{alerts.length > 1 ? 's' : ''}
          </span>
        )}
      </div>

      {alerts.length === 0 ? (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-6 text-center">
          <div className="w-10 h-10 bg-emerald-100 dark:bg-emerald-900/40 rounded-full flex items-center justify-center mx-auto mb-3">
            <AlertCircle size={20} className="text-emerald-500" />
          </div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Tous les postes sont en bonne santé</p>
          <p className="text-xs text-gray-400 mt-1">Aucun poste en souffrance détecté</p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert) => {
            const cfg = SEVERITY_CONFIG[alert.severity];
            return (
              <div
                key={alert.posting_id}
                className={`rounded-xl border p-4 flex items-start gap-3 ${cfg.bg} ${cfg.border}`}
              >
                <div className={`mt-0.5 flex-shrink-0 ${cfg.iconColor}`}>{cfg.icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm text-gray-900 dark:text-white truncate">
                      {alert.posting_title}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${cfg.badge}`}>
                      {cfg.label}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{alert.message}</p>
                </div>
                <div className="flex-shrink-0 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                  <Clock size={12} />
                  {alert.days_open}j
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
