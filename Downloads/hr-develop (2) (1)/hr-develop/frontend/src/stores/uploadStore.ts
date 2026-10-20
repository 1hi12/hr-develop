import { create } from 'zustand';
import { UploadFile, UploadResponse } from '../types/upload.types';

export interface UploadState {
  files: UploadFile[];
  addFiles: (files: File[]) => void;
  updateFileProgress: (id: string, progress: number) => void;
  updateFileStatus: (id: string, status: UploadFile['status'], error?: string) => void;
  setFileResponse: (id: string, response: UploadResponse) => void;
  removeFile: (id: string) => void;
  clearFiles: () => void;
  duplicateCount: number;
  incrementDuplicateCount: () => void;
  resetDuplicateCount: () => void;
}

export const useUploadStore = create<UploadState>((set) => ({
  files: [],
  duplicateCount: 0,

  incrementDuplicateCount: () => set((state) => ({ duplicateCount: state.duplicateCount + 1 })),
  resetDuplicateCount: () => set({ duplicateCount: 0 }),

  addFiles: (newFiles: File[]) => set((state) => ({
    files: [
      ...state.files,
      ...newFiles.map((file) => ({
        id: crypto.randomUUID(),
        file,
        progress: 0,
        status: 'pending' as const,
      })),
    ],
  })),
  
  updateFileProgress: (id: string, progress: number) => set((state) => ({
    files: state.files.map((f) =>
      f.id === id ? { ...f, progress } : f
    ),
  })),
  
  updateFileStatus: (id: string, status: UploadFile['status'], error?: string) => set((state) => ({
    files: state.files.map((f) =>
      f.id === id ? { ...f, status, error } : f
    ),
  })),
  
  setFileResponse: (id: string, response: UploadResponse) => set((state) => ({
    files: state.files.map((f) =>
      f.id === id ? { ...f, response } : f
    ),
  })),
  
  removeFile: (id: string) => set((state) => ({
    files: state.files.filter((f) => f.id !== id),
  })),
  
  clearFiles: () => set({ files: [] }),
}));
