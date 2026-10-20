import { useCallback, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, Info, Folder } from 'lucide-react';
import { useUploadStore } from '../../stores/uploadStore';
import { toast } from 'sonner';
import { useTranslation } from '@/contexts/LanguageContext';

const MAX_FILE_SIZE = 5 * 1024 * 1024;
const ACCEPTED_FORMATS = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
};

export function UploadZone() {
  const { t } = useTranslation();
  const { addFiles } = useUploadStore();
  const folderInputRef = useRef<HTMLInputElement>(null);

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: any[]) => {
      rejectedFiles.forEach((rejected) => {
        const error = rejected.errors[0];
        if (error.code === 'file-too-large') {
          toast.error(`${rejected.file.name} ${t('upload.fileTooLarge')}`);
        } else if (error.code === 'file-invalid-type') {
          toast.error(`${rejected.file.name} ${t('upload.invalidFileType')}`);
        }
      });

      if (acceptedFiles.length > 0) {
        addFiles(acceptedFiles);
        toast.success(`${acceptedFiles.length} ${t('upload.filesAdded')}`);
      }
    },
    [addFiles, t]
  );

  const handleFolderUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const fileList = Array.from(files);
    const validFiles = fileList.filter(file => {
      const isValidType = file.type === 'application/pdf' || 
                          file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      const isValidSize = file.size <= MAX_FILE_SIZE;
      
      if (!isValidType) {
        toast.error(`${file.name} ${t('upload.invalidFileType')}`);
      }
      if (!isValidSize) {
        toast.error(`${file.name} ${t('upload.fileTooLarge')}`);
      }
      
      return isValidType && isValidSize;
    });

    if (validFiles.length > 0) {
      addFiles(validFiles);
      toast.success(`${validFiles.length} ${t('upload.filesAdded')}`);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_FORMATS,
    maxSize: MAX_FILE_SIZE,
    multiple: true,
  });

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={`
          relative rounded-2xl p-16 text-center cursor-pointer
          transition-all duration-300 ease-in-out
          bg-gradient-to-br from-blue-600 via-purple-600 to-purple-700
          hover:shadow-2xl hover:-translate-y-1
          ${isDragActive ? 'scale-105 ring-4 ring-blue-300' : ''}
        `}
      >
        <input {...getInputProps()} />
        
        <div className="max-w-md mx-auto">
          <div className="w-24 h-24 mx-auto mb-6 bg-white/20 backdrop-blur-sm rounded-2xl flex items-center justify-center shadow-xl">
            <Upload className="w-12 h-12 text-white" />
          </div>

          <h3 className="text-2xl font-semibold text-white mb-2">
            {isDragActive ? 'Drop the files here' : 'Drop your CV files here'}
          </h3>
          
          <p className="text-white/80 mb-6">
            or browse to upload
          </p>

          <div className="inline-flex items-center gap-2 px-4 py-2 bg-white/10 backdrop-blur-sm rounded-lg">
            <Info className="w-4 h-4 text-white/60" />
            <span className="text-white/80 text-sm">
              PDF, DOCX • Max 5MB per file
            </span>
          </div>
        </div>
      </div>

      {/* Folder Upload Button */}
      <div className="flex justify-center">
        <input
          ref={folderInputRef}
          type="file"
          className="hidden"
          /* @ts-ignore - webkitdirectory is not in the standard TypeScript types */
          webkitdirectory=""
          directory=""
          multiple
          onChange={handleFolderUpload}
          accept=".pdf,.docx"
        />
        <button
          onClick={() => folderInputRef.current?.click()}
          className="inline-flex items-center gap-2 px-6 py-3 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg shadow-md hover:shadow-lg transition-all font-medium border border-gray-300 dark:border-gray-700"
        >
          <Folder className="w-5 h-5" />
          Télécharger un dossier de CVs
        </button>
      </div>
    </div>
  );
}