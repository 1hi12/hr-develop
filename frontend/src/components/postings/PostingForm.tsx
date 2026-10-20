import { useState } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import { Badge } from '../ui/badge';
import { X, Plus, Upload, FileText, Users } from 'lucide-react';
import { toast } from 'sonner';
import { useCreateJobPostingMutation } from '../../lib/query/mutations';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../lib/query/queryKeys';
import { useTranslation } from '@/contexts/LanguageContext';

interface PostingFormProps {
  onSuccess?: () => void;
}

export function PostingForm({ onSuccess }: PostingFormProps) {
  const { t } = useTranslation();
  const [uploadMode, setUploadMode] = useState<'form' | 'pdf'>('form');
  const [isUploadingPDF, setIsUploadingPDF] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [skillInput, setSkillInput] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [nbPositions, setNbPositions] = useState<number>(1);
  const [errors, setErrors] = useState<Record<string, string>>({});
  // Popup after PDF upload when nb_positions not found in PDF
  const [showQuotaPopup, setShowQuotaPopup] = useState(false);
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);
  const [popupNbPositions, setPopupNbPositions] = useState<number>(1);
  
  const queryClient = useQueryClient();

  const mutation = useCreateJobPostingMutation();

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!title.trim()) {
      newErrors.title = t('postingForm.titleRequired');
    }

    if (!description.trim()) {
      newErrors.description = t('postingForm.descriptionRequired');
    }

    if (skills.length === 0) {
      newErrors.skills = t('postingForm.skillsRequired');
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleAddSkill = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const skill = skillInput.trim();

      if (skill && !skills.includes(skill)) {
        setSkills([...skills, skill]);
        setSkillInput('');
        setErrors({ ...errors, skills: '' });
      }
    }
  };

  const handleRemoveSkill = (skill: string) => {
    setSkills(skills.filter((s) => s !== skill));
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      processFile(file);
    }
  };

  const processFile = async (file: File) => {
    if (file.type !== 'application/pdf') {
      toast.error(t('postingForm.selectPDF'));
      return;
    }

    setIsUploadingPDF(true);

    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await fetch('/api/v1/postings/upload-pdf', {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
        if (response.status === 409) {
          const detail = errorBody.detail;
          const msg = typeof detail === 'object' ? detail.message : detail;
          toast.warning(msg || 'Cette offre d\'emploi existe déjà.', { duration: 6000 });
          return;
        }
        throw new Error(
          typeof errorBody.detail === 'object' ? errorBody.detail.message : errorBody.detail || t('postingForm.pdfFailed')
        );
      }
      
      const jobPosting = await response.json();
      console.log('[PDF Upload] job created:', jobPosting);
      console.log('[PDF Upload] nb_positions value:', jobPosting.nb_positions, typeof jobPosting.nb_positions);

      // Refresh the postings list
      queryClient.invalidateQueries({ queryKey: queryKeys.postings.list() });

      if (jobPosting.nb_positions === null || jobPosting.nb_positions === undefined) {
        // nb_positions not found in PDF → show popup
        setPendingJobId(jobPosting.job_id);
        setPopupNbPositions(1);
        setShowQuotaPopup(true);
        toast.success(`"${jobPosting.title}" créé — précisez le nombre de postes à pourvoir`);
      } else {
        toast.success(`"${jobPosting.title}" créé — ${jobPosting.nb_positions} poste(s) à pourvoir (extrait du PDF ✓)`);
        if (onSuccess) onSuccess();
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('postingForm.pdfFailed'));
    } finally {
      setIsUploadingPDF(false);
    }
  };

  const handleQuotaConfirm = async () => {
    if (!pendingJobId) return;
    try {
      await fetch(`/api/v1/postings/${pendingJobId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nb_positions: popupNbPositions }),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.postings.list() });
      toast.success(`${popupNbPositions} poste(s) à pourvoir enregistré(s)`);
    } catch {
      toast.error('Erreur lors de la mise à jour du quota');
    } finally {
      setShowQuotaPopup(false);
      setPendingJobId(null);
      if (onSuccess) onSuccess();
    }
  };

  const handlePDFUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset form
    e.target.value = '';
    
    processFile(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      toast.error(t('postingForm.fixErrors'));
      return;
    }

    try {
      await mutation.mutateAsync({
        title: title.trim(),
        description: description.trim(),
        required_skills: skills,
        employment_type: 'full-time',
        nb_positions: nbPositions,
      });

      setTitle('');
      setDescription('');
      setSkills([]);
      setSkillInput('');
      setErrors({});

      toast.success(t('postingForm.created'));
      
      if (onSuccess) {
        onSuccess();
      }
    } catch (error: unknown) {
      // Check if it's a 409 duplicate job posting error
      const err = error as Error & { status?: number; detail?: unknown };
      if (err?.status === 409) {
        const detail = err.detail;
        const msg = typeof detail === 'object' && detail !== null
          ? (detail as { message?: string }).message
          : typeof detail === 'string' ? detail : undefined;
        toast.warning(msg || "Cette offre d'emploi existe déjà.", { duration: 6000 });
      } else {
        toast.error(t('postingForm.failed'));
        console.error(error);
      }
    }
  };

  return (
    <div className="bg-transparent">
      {/* Quota popup — nested Radix Dialog so focus/events work correctly inside outer Dialog */}
      <DialogPrimitive.Root open={showQuotaPopup}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm" style={{ zIndex: 100000 }} />
          <DialogPrimitive.Content
            style={{ zIndex: 100001, maxWidth: 420, width: 'calc(100vw - 32px)' }}
            className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-gray-900 rounded-2xl shadow-2xl p-8 border border-gray-200 dark:border-gray-700 outline-none"
            onInteractOutside={(e) => e.preventDefault()}
            onEscapeKeyDown={(e) => e.preventDefault()}
            onOpenAutoFocus={(e) => e.preventDefault()}
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-indigo-100 dark:bg-indigo-900/40 rounded-xl flex items-center justify-center flex-shrink-0">
                <Users className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
              </div>
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">Postes à pourvoir</h3>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
              Le nombre de postes n'a pas été détecté dans le PDF.<br />
              Combien de candidats souhaitez-vous recruter ?
            </p>

            {/* Quick presets */}
            <div className="flex gap-2 mb-4">
              {[1, 2, 3, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setPopupNbPositions(n)}
                  style={{ flex: 1 }}
                  className={`py-3 rounded-xl text-sm font-bold border-2 transition-all ${
                    popupNbPositions === n
                      ? 'bg-indigo-600 text-white border-indigo-600 shadow-md'
                      : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-indigo-400'
                  }`}
                >
                  {n} poste{n > 1 ? 's' : ''}
                </button>
              ))}
            </div>

            {/* Custom number */}
            <div className="flex items-center gap-3 mb-6">
              <span className="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap font-medium">Autre :</span>
              <Input
                type="number"
                min={1}
                max={100}
                value={popupNbPositions}
                onChange={(e) => setPopupNbPositions(Math.max(1, parseInt(e.target.value) || 1))}
                className="w-24 h-10 text-center font-bold text-lg border-2 border-gray-200 dark:border-gray-700 focus-visible:border-indigo-500"
              />
            </div>

            <Button
              type="button"
              onClick={handleQuotaConfirm}
              className="w-full h-12 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl text-base"
            >
              Confirmer — {popupNbPositions} poste{popupNbPositions > 1 ? 's' : ''} à pourvoir
            </Button>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
      <form onSubmit={handleSubmit} className="space-y-6">

        {/* Mode Toggle */}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => setUploadMode('form')}
            className={`flex-1 py-3 px-5 rounded-lg text-sm font-semibold transition-all duration-200 ${
              uploadMode === 'form'
                ? 'bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-400 border-2 border-indigo-500 dark:border-indigo-500 shadow-md'
                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-700 hover:bg-gray-50 dark:hover:bg-gray-900'
            }`}
          >
            <FileText className="w-4 h-4 inline mr-2" />
            {t('postingForm.manualForm')}
          </button>
          <button
            type="button"
            onClick={() => setUploadMode('pdf')}
            className={`flex-1 py-3 px-5 rounded-lg text-sm font-semibold transition-all duration-200 ${
              uploadMode === 'pdf'
                ? 'bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-400 border-2 border-indigo-500 dark:border-indigo-500 shadow-md'
                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-700 hover:bg-gray-50 dark:hover:bg-gray-900'
            }`}
          >
            <Upload className="w-4 h-4 inline mr-2" />
            {t('postingForm.pdfUpload')}
          </button>
        </div>

        {uploadMode === 'pdf' ? (
          /* PDF Upload Section */
          <div className="space-y-4">
            {!showQuotaPopup ? (
              <div
                className={`border-2 border-dashed rounded-2xl p-16 text-center transition-all duration-300 ${
                  isDragging
                    ? 'border-indigo-500 bg-gradient-to-br from-indigo-50 to-indigo-100 dark:from-indigo-950/30 dark:to-indigo-900/30 scale-[1.02] shadow-lg'
                    : 'border-gray-300 dark:border-gray-700 hover:border-indigo-400 dark:hover:border-indigo-600 hover:bg-gray-50 dark:hover:bg-gray-900/50'
                }`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                {isUploadingPDF ? (
                  <>
                    <div className="relative w-20 h-20 mx-auto mb-6">
                      <div className="absolute inset-0 border-4 border-gray-200 dark:border-gray-700 border-t-indigo-600 dark:border-t-indigo-400 rounded-full animate-spin" />
                      <div className="absolute inset-2 border-4 border-transparent border-b-indigo-400 dark:border-b-indigo-500 rounded-full animate-spin" style={{animationDuration: '1.5s', animationDirection: 'reverse'}} />
                    </div>
                    <p className="text-base font-semibold text-gray-800 dark:text-gray-200">
                      {t('postingForm.creatingFromPDF')}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                      {t('postingForm.extractingText')}
                    </p>
                  </>
                ) : (
                  <>
                    <div className="w-20 h-20 mx-auto mb-6 bg-gradient-to-br from-indigo-100 to-indigo-200 dark:from-indigo-900/30 dark:to-indigo-800/30 rounded-2xl flex items-center justify-center shadow-lg">
                      <Upload className="w-10 h-10 text-indigo-600 dark:text-indigo-400" />
                    </div>
                    <label htmlFor="pdf-upload" className="cursor-pointer block">
                      <span className="text-lg font-bold text-gray-800 dark:text-gray-200 block mb-3">
                        {isDragging ? t('postingForm.dropPDF') : t('postingForm.dragDropPDF')}
                      </span>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                        {t('postingForm.pdfConversion')}
                      </p>
                      <div className="inline-flex items-center gap-2 mt-4 px-5 py-2.5 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-400 rounded-lg border border-indigo-200 dark:border-indigo-800">
                        <FileText className="w-4 h-4" />
                        <span className="text-xs font-semibold">{t('postingForm.maxFileSize')}</span>
                      </div>
                      <input
                        id="pdf-upload"
                        type="file"
                        accept=".pdf"
                        onChange={handlePDFUpload}
                        className="hidden"
                        disabled={isUploadingPDF}
                      />
                    </label>
                  </>
                )}
              </div>
            ) : null}
          </div>
        ) : (
          /* Manual Form Section */
          <>
          {/* Title */}
          <div className="space-y-2">
            <label className="block text-sm font-bold text-gray-800 dark:text-gray-200 mb-3">
              {t('postingForm.jobTitle')} <span className="text-red-500">*</span>
            </label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('postingForm.jobTitlePlaceholder')}
              className={`h-12 text-base bg-white dark:bg-gray-900 border-2 ${
                errors.title
                  ? 'border-red-500 focus-visible:ring-red-500'
                  : 'border-gray-200 dark:border-gray-800 focus-visible:border-indigo-500 focus-visible:ring-indigo-500/20'
              } transition-all duration-200`}
            />
            {errors.title && (
              <p className="text-sm text-red-500 mt-2 font-medium flex items-center gap-1">
                <span className="inline-block w-1 h-1 bg-red-500 rounded-full"></span>
                {errors.title}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-2">
            <label className="block text-sm font-bold text-gray-800 dark:text-gray-200 mb-3">
              {t('postingForm.jobDescription')} <span className="text-red-500">*</span>
            </label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('postingForm.jobDescriptionPlaceholder')}
              rows={10}
              className={`text-sm bg-white dark:bg-gray-900 border-2 resize-none ${
                errors.description
                  ? 'border-red-500 focus-visible:ring-red-500'
                  : 'border-gray-200 dark:border-gray-800 focus-visible:border-indigo-500 focus-visible:ring-indigo-500/20'
              } transition-all duration-200`}
            />
            {errors.description && (
              <p className="text-sm text-red-500 mt-2 font-medium flex items-center gap-1">
                <span className="inline-block w-1 h-1 bg-red-500 rounded-full"></span>
                {errors.description}
              </p>
            )}
          </div>

          {/* Skills */}
          <div className="space-y-2">
            <label className="block text-sm font-bold text-gray-800 dark:text-gray-200 mb-3">
              {t('postingForm.requiredSkills')} <span className="text-red-500">*</span>
            </label>
            <Input
              value={skillInput}
              onChange={(e) => setSkillInput(e.target.value)}
              onKeyDown={handleAddSkill}
              placeholder={t('postingForm.skillsPlaceholder')}
              className={`h-12 text-base bg-white dark:bg-gray-900 border-2 ${
                errors.skills
                  ? 'border-red-500 focus-visible:ring-red-500'
                  : 'border-gray-200 dark:border-gray-800 focus-visible:border-indigo-500 focus-visible:ring-indigo-500/20'
              } transition-all duration-200`}
            />
            {errors.skills && (
              <p className="text-sm text-red-500 mt-2 font-medium flex items-center gap-1">
                <span className="inline-block w-1 h-1 bg-red-500 rounded-full"></span>
                {errors.skills}
              </p>
            )}

            {/* Skills Tags */}
            {skills.length > 0 && (
              <div className="mt-4 p-4 bg-gradient-to-br from-indigo-50 to-indigo-50 dark:from-indigo-950/20 dark:to-indigo-950/20 rounded-xl border border-indigo-100 dark:border-indigo-900/30">
                <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-3 uppercase tracking-wide">
                  {skills.length} {skills.length === 1 ? 'compétence ajoutée' : 'compétences ajoutées'}
                </p>
                <div className="flex flex-wrap gap-2">
                  {skills.map((skill) => (
                    <Badge
                      key={skill}
                      variant="secondary"
                      className="bg-white dark:bg-gray-900 text-indigo-700 dark:text-indigo-400 border-2 border-indigo-200 dark:border-indigo-800 hover:border-indigo-300 dark:hover:border-indigo-700 hover:shadow-md px-4 py-2 h-auto text-sm font-semibold rounded-lg transition-all duration-200"
                    >
                      {skill}
                      <button
                        type="button"
                        onClick={() => handleRemoveSkill(skill)}
                        className="ml-2 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Nb Positions */}
          <div className="space-y-2">
            <label className="block text-sm font-bold text-gray-800 dark:text-gray-200 mb-3 flex items-center gap-2">
              <Users className="w-4 h-4 text-indigo-500" />
              Nombre de postes à pourvoir
            </label>
            <div className="flex gap-2">
              {[1, 2, 3, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setNbPositions(n)}
                  className={`flex-1 py-2.5 rounded-xl text-sm font-bold border-2 transition-all ${
                    nbPositions === n
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-indigo-400'
                  }`}
                >
                  {n}
                </button>
              ))}
              <Input
                type="number"
                min={1}
                max={100}
                value={nbPositions}
                onChange={(e) => setNbPositions(Math.max(1, parseInt(e.target.value) || 1))}
                className="w-20 h-11 text-center font-bold border-2 border-gray-200 dark:border-gray-700 focus-visible:border-indigo-500"
                placeholder="N"
              />
            </div>
          </div>

          {/* Submit Button */}
          <Button
            type="submit"
            disabled={mutation.isPending}
            className="w-full h-14 bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-400 border-2 border-indigo-500 dark:border-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/50 font-bold text-base rounded-xl shadow-md hover:shadow-lg transition-all duration-200"
          >
            {mutation.isPending ? (
              <span className="flex items-center gap-3">
                <span className="w-5 h-5 border-3 border-indigo-300 dark:border-indigo-600 border-t-indigo-600 dark:border-t-indigo-400 rounded-full animate-spin" />
                {t('postingForm.creating')}
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Plus className="w-5 h-5" />
                {t('postingForm.createJobPosting')}
              </span>
            )}
          </Button>
          </>
        )}
      </form>
    </div>
  );
}
