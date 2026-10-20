import { CheckCircle, XCircle, Copy, Clock, Cpu } from 'lucide-react';
import { Progress } from '../ui/progress';
import { Badge } from '../ui/badge';
import type { BulkCV, BulkProgress } from '../../hooks/ui/useBulkUpload';

const SENIORITY_COLORS: Record<string, string> = {
  intern:    'bg-gray-100 text-gray-700',
  junior:    'bg-blue-100 text-blue-700',
  mid:       'bg-green-100 text-green-700',
  senior:    'bg-purple-100 text-purple-700',
  lead:      'bg-orange-100 text-orange-700',
  executive: 'bg-red-100 text-red-700',
};

function CVCard({ cv }: { cv: BulkCV }) {
  const isError = cv.status === 'error';
  const isDuplicate = cv.status === 'duplicate';

  return (
    <div
      className={`rounded-xl border p-4 space-y-2 text-sm transition-all animate-in fade-in slide-in-from-bottom-2 duration-300 ${
        isError
          ? 'border-red-200 bg-red-50 dark:bg-red-950/20'
          : isDuplicate
          ? 'border-yellow-200 bg-yellow-50 dark:bg-yellow-950/20'
          : 'border-gray-200 bg-white dark:bg-gray-900'
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-gray-900 dark:text-gray-100 truncate">
            {cv.name ?? cv.filename}
          </p>
          {cv.email && (
            <p className="text-xs text-gray-500 truncate">{cv.email}</p>
          )}
        </div>
        <div className="shrink-0 mt-0.5">
          {isError ? (
            <XCircle className="w-4 h-4 text-red-500" />
          ) : isDuplicate ? (
            <Copy className="w-4 h-4 text-yellow-500" />
          ) : (
            <CheckCircle className="w-4 h-4 text-green-500" />
          )}
        </div>
      </div>

      {/* Error message */}
      {isError && cv.error && (
        <p className="text-xs text-red-600 dark:text-red-400 line-clamp-2">{cv.error}</p>
      )}

      {/* Tags */}
      {!isError && (
        <div className="flex flex-wrap gap-1.5">
          {cv.seniority && cv.seniority !== 'unknown' && (
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                SENIORITY_COLORS[cv.seniority] ?? 'bg-gray-100 text-gray-700'
              }`}
            >
              {cv.seniority}
            </span>
          )}
          {cv.skills_count > 0 && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300 font-medium">
              {cv.skills_count} skills
            </span>
          )}
          {isDuplicate && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700 font-medium">
              déjà existant
            </span>
          )}
        </div>
      )}

      {/* Footer */}
      {!isError && (
        <div className="flex items-center gap-3 text-xs text-gray-400 pt-1">
          {cv.processing_time_ms > 0 && (
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {(cv.processing_time_ms / 1000).toFixed(1)}s
            </span>
          )}
          {cv.model_used && cv.model_used !== 'dedup_cache' && cv.model_used !== 'cache' && (
            <span className="flex items-center gap-1">
              <Cpu className="w-3 h-3" />
              {cv.model_used}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

type Props = {
  progress: BulkProgress;
  cvs: BulkCV[];
  isDone: boolean;
  errors: number;
};

export function BulkProgressPanel({ progress, cvs, isDone, errors }: Props) {
  const successCount = cvs.filter((c) => c.status === 'done').length;
  const duplicateCount = cvs.filter((c) => c.status === 'duplicate').length;
  const errorCount = cvs.filter((c) => c.status === 'error').length;

  return (
    <div className="space-y-6">
      {/* Progress header */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {isDone ? 'Traitement terminé' : 'Traitement en cours…'}
            </h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {progress.done} / {progress.total} CVs traités
            </p>
          </div>
          <span className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            {Math.round(progress.percent)}%
          </span>
        </div>

        <Progress value={progress.percent} className="h-3" />

        {/* Stats row */}
        <div className="flex gap-4 text-sm">
          <span className="flex items-center gap-1.5 text-green-600">
            <CheckCircle className="w-4 h-4" />
            {successCount} ajoutés
          </span>
          {duplicateCount > 0 && (
            <span className="flex items-center gap-1.5 text-yellow-600">
              <Copy className="w-4 h-4" />
              {duplicateCount} doublons
            </span>
          )}
          {errorCount > 0 && (
            <span className="flex items-center gap-1.5 text-red-600">
              <XCircle className="w-4 h-4" />
              {errorCount} erreurs
            </span>
          )}
        </div>
      </div>

      {/* CV cards grid */}
      {cvs.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {cvs.map((cv, i) => (
            <CVCard key={cv.candidate_id || `${cv.filename}-${i}`} cv={cv} />
          ))}
        </div>
      )}

      {/* Empty state while waiting */}
      {cvs.length === 0 && !isDone && (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400">
          <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-4" />
          <p className="text-sm">Analyse des CVs en cours…</p>
        </div>
      )}
    </div>
  );
}
