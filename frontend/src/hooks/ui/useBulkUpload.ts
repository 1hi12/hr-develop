import { useState, useRef, useCallback } from 'react';
import { toast } from 'sonner';

export type BulkCV = {
  filename: string;
  candidate_id: string;
  name: string | null;
  email: string | null;
  seniority: string | null;
  skills_count: number;
  chunks_count: number;
  model_used: string;
  processing_time_ms: number;
  already_exists: boolean;
  created_at?: string | null;
  error?: string;
  status: 'done' | 'error' | 'duplicate';
};

export type BulkProgress = {
  done: number;
  total: number;
  percent: number;
};

export type BulkState =
  | { phase: 'idle' }
  | { phase: 'uploading' }
  | { phase: 'processing'; jobId: string; progress: BulkProgress; cvs: BulkCV[] }
  | { phase: 'done'; progress: BulkProgress; cvs: BulkCV[]; errors: number };

export function useBulkUpload() {
  const [state, setState] = useState<BulkState>({ phase: 'idle' });
  const wsRef = useRef<WebSocket | null>(null);

  const start = useCallback(async (files: File[]) => {
    if (!files.length) return;

    setState({ phase: 'uploading' });

    const formData = new FormData();
    for (const f of files) {
      formData.append('files', f);
    }

    let jobId: string;
    let total: number;
    try {
      const res = await fetch('/api/v1/pipeline/upload', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
      const data = await res.json();
      jobId = data.job_id;
      total = data.total;
    } catch (err) {
      setState({ phase: 'idle' });
      throw err;
    }

    setState({
      phase: 'processing',
      jobId,
      progress: { done: 0, total, percent: 0 },
      cvs: [],
    });

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/api/v1/pipeline/ws/${jobId}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      let msg: { event: string; data?: any };
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }

      if (msg.event === 'ping') return;

      if (msg.event === 'cv_processed') {
        const d = msg.data;
        const isDuplicate = d.already_exists ?? false;

        if (isDuplicate) {
          toast.warning('Duplicate CV', { duration: 4000 });
        }

        const cv: BulkCV = {
          filename: d.filename,
          candidate_id: d.candidate_id,
          name: d.cv?.name ?? null,
          email: d.cv?.email ?? null,
          seniority: d.seniority ?? null,
          skills_count: d.skills_count ?? 0,
          chunks_count: d.chunks_count ?? 0,
          model_used: d.model_used ?? '',
          processing_time_ms: d.processing_time_ms ?? 0,
          already_exists: isDuplicate,
          status: isDuplicate ? 'duplicate' : 'done',
        };
        setState((prev) => {
          if (prev.phase !== 'processing') return prev;
          return { ...prev, cvs: [...prev.cvs, cv] };
        });
      }

      if (msg.event === 'progress') {
        const d = msg.data;
        setState((prev) => {
          if (prev.phase !== 'processing') return prev;
          return { ...prev, progress: { done: d.done, total: d.total, percent: d.percent } };
        });
      }

      if (msg.event === 'cv_error') {
        const cv: BulkCV = {
          filename: msg.data.filename,
          candidate_id: '',
          name: null,
          email: null,
          seniority: null,
          skills_count: 0,
          chunks_count: 0,
          model_used: 'error',
          processing_time_ms: 0,
          error: msg.data.error,
          already_exists: false,
          status: 'error',
        };
        setState((prev) => {
          if (prev.phase !== 'processing') return prev;
          return { ...prev, cvs: [...prev.cvs, cv] };
        });
      }

      if (msg.event === 'done') {
        const d = msg.data;
        setState((prev) => {
          if (prev.phase !== 'processing') return prev;
          return {
            phase: 'done',
            progress: { done: d.done, total: d.total, percent: 100 },
            cvs: prev.cvs,
            errors: d.errors,
          };
        });
        ws.close();
      }
    };

    ws.onerror = () => {
      setState((prev) => {
        if (prev.phase === 'processing') {
          return { phase: 'done', progress: prev.progress, cvs: prev.cvs, errors: 0 };
        }
        return { phase: 'idle' };
      });
    };
  }, []);

  const reset = useCallback(() => {
    wsRef.current?.close();
    setState({ phase: 'idle' });
  }, []);

  return { state, start, reset };
}
