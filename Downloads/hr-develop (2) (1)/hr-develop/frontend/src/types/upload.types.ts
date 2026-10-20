export interface UploadFile {
  id: string;
  file: File;
  progress: number;
  status: 'pending' | 'uploading' | 'success' | 'error' | 'duplicate';
  error?: string;
  response?: UploadResponse;
}

export interface UploadResponse {
  success: boolean;
  candidate_id: string;
  job_id: string | null;
  status: string;
  message?: string;
  filename?: string;
  full_name?: string;
  seniority?: string;
  skills_count?: number;
  chunks_count?: number;
  uploadedAt: string; // set client-side on upload completion
  candidate?: {
    candidate_id: string;
    full_name: string | null;
    email: string | null;
    seniority_level: string | null;
    created_at: string | null;
    skills: string[];
    status: string;
  };
}

export interface UploadState {
  files: UploadFile[];
  addFiles: (files: File[]) => void;
  updateFileProgress: (id: string, progress: number) => void;
  updateFileStatus: (id: string, status: UploadFile['status'], error?: string) => void;
  setFileResponse: (id: string, response: UploadResponse) => void;
  removeFile: (id: string) => void;
  clearFiles: () => void;
}
