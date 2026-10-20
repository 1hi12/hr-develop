import { create } from 'zustand';
import { JobPosting } from '../types/postings.types';

export interface PostingState {
  postings: JobPosting[];
  setPostings: (postings: JobPosting[]) => void;
  addPosting: (posting: JobPosting) => void;
  removePosting: (id: string) => void;
}

export const usePostingStore = create<PostingState>((set) => ({
  postings: [],
  
  setPostings: (postings: JobPosting[]) => set({ postings }),
  
  addPosting: (posting: JobPosting) => set((state) => ({
    postings: [posting, ...state.postings],
  })),
  
  removePosting: (id: string) => set((state) => ({
    postings: state.postings.filter((p) => p.job_id !== id),
  })),
}));
