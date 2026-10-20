import { CheckCircle, AlertCircle, Loader2, FileText, X, CopyX } from 'lucide-react';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { Progress } from '../ui/progress';
import { Badge } from '../ui/badge';
import { UploadFile } from '../../types/upload.types';
import { useTranslation } from '@/contexts/LanguageContext';

interface FileCardProps {
  file: UploadFile;
  onRemove: (id: string) => void;
}

export function FileCard({ file, onRemove }: FileCardProps) {
  const { t } = useTranslation();
  const { file: fileObj, progress, status, error } = file;

  const getStatusIcon = () => {
    switch (status) {
      case 'uploading':
        return <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />;
      case 'success':
        return <CheckCircle className="w-5 h-5 text-green-600" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-600" />;
      case 'duplicate':
        return <CopyX className="w-5 h-5 text-amber-600" />;
      default:
        return <FileText className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusBadge = () => {
    switch (status) {
      case 'uploading':
        return <Badge className="bg-blue-100 text-blue-700">{t('upload.uploading')} {progress}%</Badge>;
      case 'success':
        return <Badge className="bg-green-100 text-green-700">{t('upload.success')}</Badge>;
      case 'error':
        return <Badge className="bg-red-100 text-red-700">{t('upload.failed')}</Badge>;
      case 'duplicate':
        return <Badge className="bg-amber-100 text-amber-700">CV en double</Badge>;
      default:
        return <Badge className="bg-gray-100 text-gray-700">{t('common.status')}</Badge>;
    }
  };

  const getFileSize = () => {
    const sizeInMB = fileObj.size / (1024 * 1024);
    return sizeInMB > 1 
      ? `${sizeInMB.toFixed(2)} MB` 
      : `${(fileObj.size / 1024).toFixed(0)} KB`;
  };

  const bgColor = {
    uploading:  'bg-blue-50/50 border-blue-200',
    success:    'bg-green-50/50 border-green-200',
    error:      'bg-red-50/50 border-red-200',
    duplicate:  'bg-amber-50/50 border-amber-200',
    pending:    'bg-white border-gray-200',
  }[status] ?? 'bg-white border-gray-200';

  return (
    <Card className={`p-4 transition-all hover:shadow-md ${bgColor}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-4 flex-1">
          <div className="flex-shrink-0">
            {getStatusIcon()}
          </div>

          <div className="flex-1 min-w-0">
            <p className="font-medium text-gray-900 truncate text-sm">
              {fileObj.name}
            </p>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-xs text-gray-500">{getFileSize()}</span>
              {file.response?.uploadedAt && status === 'success' && (
                <>
                  <span className="text-xs text-gray-400">•</span>
                  <span className="text-xs text-gray-500">
                    {new Date(file.response.uploadedAt).toLocaleTimeString()}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {getStatusBadge()}
          
          {status !== 'uploading' && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onRemove(file.id)}
              className="h-8 w-8 p-0"
            >
              <X className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>

      {status === 'uploading' && (
        <Progress value={progress} className="h-1.5" />
      )}

      {status === 'error' && error && (
        <p className="text-xs text-red-600 mt-2">{error}</p>
      )}

      {status === 'duplicate' && (
        <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 space-y-1">
          <div className="flex items-center gap-1.5">
            <CopyX className="w-3.5 h-3.5 text-amber-600 shrink-0" />
            <span className="text-xs font-semibold text-amber-800">CV déjà enregistré</span>
          </div>
          {file.response?.full_name && (
            <p className="text-xs text-amber-700">
              Appartient à <strong>{file.response.full_name}</strong>
              {file.response.seniority && file.response.seniority !== 'unknown' && (
                <> · {file.response.seniority}</>
              )}
            </p>
          )}
          <p className="text-xs text-amber-600">Aucune donnée écrasée ni dupliquée.</p>
        </div>
      )}
    </Card>
  );
}