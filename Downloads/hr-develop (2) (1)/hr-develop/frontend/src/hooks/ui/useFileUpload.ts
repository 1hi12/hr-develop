import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../lib/query/queryKeys';
import { useUploadStore, UploadState } from '../../stores/uploadStore';
import { UploadResponse } from '../../types/upload.types';

export interface UseFileUploadOptions {
  onUpload?: (response: UploadResponse) => void;
  onError?: (error: Error, fileId: string) => void;
  maxFiles?: number;
  maxSize?: number;
  accept?: Record<string, string[]>;
}

export interface UseFileUploadReturn {
  getRootProps: ReturnType<typeof useDropzone>['getRootProps'];
  getInputProps: ReturnType<typeof useDropzone>['getInputProps'];
  isDragActive: boolean;
  files: UploadState['files'];
  removeFile: UploadState['removeFile'];
  clearFiles: UploadState['clearFiles'];
  uploadFile: (fileId: string) => Promise<void>;
  uploadAllFiles: () => Promise<void>;
}

export function useFileUpload(options: UseFileUploadOptions = {}): UseFileUploadReturn {
  const {
    onUpload,
    onError,
    maxFiles = 10,
    maxSize = 10 * 1024 * 1024, // 10MB
    accept = {
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    },
  } = options;

  const queryClient = useQueryClient();
  const { files, addFiles, updateFileProgress, updateFileStatus, setFileResponse, removeFile, clearFiles, incrementDuplicateCount } = useUploadStore();

  const uploadFile = useCallback(async (fileId: string) => {
    // Get the latest files from store to avoid stale closure
    const currentFiles = useUploadStore.getState().files;
    const file = currentFiles.find((f) => f.id === fileId);
    if (!file) return;

    try {
      updateFileStatus(fileId, 'uploading');
      
      // Create FormData for upload
      const formData = new FormData();
      formData.append('file', file.file);

      // Make the actual upload request
      const response = await fetch('/api/v1/candidates/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      const raw = await response.json();
      const data: UploadResponse = { ...raw, uploadedAt: new Date().toISOString() };

      updateFileProgress(fileId, 100);
      setFileResponse(fileId, data);

      if (data.status === 'already_exists') {
        const name = data.full_name ?? data.candidate?.full_name ?? data.filename ?? file.file.name;
        toast.warning(`CV doublon — ${name}`, { duration: 4000 });
        incrementDuplicateCount();
        updateFileStatus(fileId, 'duplicate');
      } else {
        updateFileStatus(fileId, 'success');
        // Show success notification
        const candidateName = data.full_name ?? data.candidate?.full_name ?? file.file.name;
        toast.success(`✅ ${candidateName} ajouté avec succès`, { duration: 3000 });
        // Refresh candidates list
        queryClient.invalidateQueries({ queryKey: queryKeys.candidates.lists() });
        onUpload?.(data);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Upload failed';
      updateFileStatus(fileId, 'error', errorMessage);
      onError?.(error instanceof Error ? error : new Error(errorMessage), fileId);
    }
  }, [updateFileProgress, updateFileStatus, setFileResponse, queryClient, onUpload, onError, incrementDuplicateCount]);

  const uploadAllFiles = useCallback(async () => {
    const currentFiles = useUploadStore.getState().files;
    const pendingFiles = currentFiles.filter((f) => f.status === 'pending' || f.status === 'error');
    await Promise.all(pendingFiles.map((f) => uploadFile(f.id)));
  }, [uploadFile]);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    addFiles(acceptedFiles);
  }, [addFiles]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxFiles,
    maxSize,
    accept,
  });

  return {
    getRootProps,
    getInputProps,
    isDragActive,
    files,
    removeFile,
    clearFiles,
    uploadFile,
    uploadAllFiles,
  };
}
