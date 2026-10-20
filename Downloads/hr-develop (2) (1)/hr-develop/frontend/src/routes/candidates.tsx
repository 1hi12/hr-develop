import { createFileRoute } from '@tanstack/react-router';
import { CandidateList } from '../components/candidates/CandidateList';

export const Route = createFileRoute('/candidates')({
  component: CandidatesPage,
});

function CandidatesPage() {
  return (
    <div className="min-h-screen">
      <CandidateList />
    </div>
  );
}
