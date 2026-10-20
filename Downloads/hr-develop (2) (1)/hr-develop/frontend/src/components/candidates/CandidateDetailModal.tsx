import { X, Mail, Phone, MapPin, User, Briefcase } from 'lucide-react';
import { Candidate } from '../../types/candidates.types';

interface CandidateDetailModalProps {
  candidate: Candidate | null;
  onClose: () => void;
}

export function CandidateDetailModal({ candidate, onClose }: CandidateDetailModalProps) {
  if (!candidate) return null;

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200"
      onClick={handleBackdropClick}
    >
      <div className="relative w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Thin accent line */}
        <div className="h-1 bg-gradient-to-r from-indigo-500 to-blue-500" />

        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-5 pb-4">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-white dark:bg-gray-800 ring-2 ring-indigo-100 dark:ring-indigo-900/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400 font-bold text-2xl flex-shrink-0">
              {candidate.full_name?.charAt(0).toUpperCase() || '?'}
            </div>
            <div>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {candidate.full_name || 'Nom inconnu'}
              </p>
              <div className="flex flex-wrap items-center gap-2 mt-1.5">
                {candidate.seniority_level && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 capitalize">
                    <Briefcase className="h-3 w-3" />
                    {candidate.seniority_level}
                  </span>
                )}
                {candidate.total_years_experience ? (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                    {candidate.total_years_experience} ans d'expérience
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex-shrink-0"
          >
            <X className="h-5 w-5 text-gray-400 dark:text-gray-500" />
          </button>
        </div>

        <div className="px-6 pb-6">
          {/* Info grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Email */}
            <div className="flex items-center gap-3 rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-gray-100 dark:border-gray-800 p-3">
              <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
                <Mail className="h-4 w-4 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] text-gray-400 dark:text-gray-500 uppercase tracking-wide font-medium">
                  Email
                </p>
                {candidate.email ? (
                  <a
                    href={`mailto:${candidate.email}`}
                    className="text-sm text-blue-600 dark:text-blue-400 hover:underline truncate block"
                  >
                    {candidate.email}
                  </a>
                ) : (
                  <p className="text-sm text-gray-400 dark:text-gray-500 italic">Non renseigné</p>
                )}
              </div>
            </div>

            {/* Phone */}
            <div className="flex items-center gap-3 rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-gray-100 dark:border-gray-800 p-3">
              <div className="w-9 h-9 rounded-lg bg-green-50 dark:bg-green-900/30 flex items-center justify-center flex-shrink-0">
                <Phone className="h-4 w-4 text-green-600 dark:text-green-400" />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] text-gray-400 dark:text-gray-500 uppercase tracking-wide font-medium">
                  Contact
                </p>
                {candidate.phone ? (
                  <a
                    href={`tel:${candidate.phone}`}
                    className="text-sm text-gray-900 dark:text-white hover:underline truncate block"
                  >
                    {candidate.phone}
                  </a>
                ) : (
                  <p className="text-sm text-gray-400 dark:text-gray-500 italic">Non renseigné</p>
                )}
              </div>
            </div>

            {/* Location */}
            {candidate.location && (
              <div className="flex items-center gap-3 rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-gray-100 dark:border-gray-800 p-3 sm:col-span-2">
                <div className="w-9 h-9 rounded-lg bg-orange-50 dark:bg-orange-900/30 flex items-center justify-center flex-shrink-0">
                  <MapPin className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] text-gray-400 dark:text-gray-500 uppercase tracking-wide font-medium">
                    Localisation
                  </p>
                  <p className="text-sm text-gray-900 dark:text-white truncate">{candidate.location}</p>
                </div>
              </div>
            )}
          </div>

          {/* Summary */}
          {candidate.summary && (
            <div className="rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-gray-100 dark:border-gray-800 p-4 mt-3">
              <div className="flex items-center gap-2 mb-2">
                <User className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Résumé
                </p>
              </div>
              <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                {candidate.summary}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
