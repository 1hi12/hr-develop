import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { PostingForm } from './PostingForm';
import { useTranslation } from '@/contexts/LanguageContext';

interface JobPostingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function JobPostingDialog({ open, onOpenChange }: JobPostingDialogProps) {
  const { t } = useTranslation();
  
  const handleSuccess = () => {
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto p-0 gap-0 bg-gradient-to-br from-white via-gray-50 to-white dark:from-gray-900 dark:via-gray-950 dark:to-gray-900">
        <DialogHeader className="px-8 pt-8 pb-4 border-b border-gray-200 dark:border-gray-800">
          <DialogTitle className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            {t('jobPostingDialog.title')}
          </DialogTitle>
          <DialogDescription className="text-gray-600 dark:text-gray-400 mt-2">
            {t('jobPostingDialog.description')}
          </DialogDescription>
        </DialogHeader>
        <div className="px-8 py-6">
          <PostingForm onSuccess={handleSuccess} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
