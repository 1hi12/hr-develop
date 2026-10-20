import { createFileRoute } from '@tanstack/react-router';
import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Send,
  Sparkles,
  User,
  Bot,
  Users,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  SquarePen,
  Trash2,
  History,
  Search,
  FileText,
  Briefcase,
  Clock,
  TrendingUp,
  Download,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import { generateJobOfferDocx } from '@/lib/generateJobOfferDocx';

export const Route = createFileRoute('/ai-assistant')({
  component: AIAssistantPage,
});

// ─── Types ───────────────────────────────────────────────────────────

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  response_type?: string;
  recommendations?: any;
  job_offer_data?: any;
}

interface Conversation {
  conversation_id: string;
  title: string;
  messages: Message[];
  created_at: string;
  updated_at: string;
}

// ─── Suggested prompts ───────────────────────────────────────────────

const CAPABILITIES = [
  {
    icon: Users,
    color: 'blue',
    title: 'Recommandation d\'équipe',
    description: 'Décrivez votre projet et obtenez les meilleurs candidats pour chaque tâche',
    prompt: 'J\'ai besoin d\'une équipe pour développer une application web e-commerce. Tâches : backend (Python, FastAPI, PostgreSQL), frontend React/TypeScript, intégration paiement Stripe. Budget 40 000 €, 4 personnes max.',
  },
  {
    icon: Search,
    color: 'violet',
    title: 'Recherche par spécialité',
    description: 'Trouvez les candidats les plus compétents dans un domaine spécifique',
    prompt: 'Quels sont les candidats les plus orientés DevOps dans notre base ?',
  },
  {
    icon: FileText,
    color: 'emerald',
    title: 'Profil candidat',
    description: 'Obtenez un résumé détaillé du profil d\'un candidat spécifique',
    prompt: 'Donne-moi le profil complet de ',
  },
  {
    icon: Briefcase,
    color: 'amber',
    title: 'Rédiger une offre',
    description: 'Générez une offre d\'emploi professionnelle pour n\'importe quel poste',
    prompt: 'Rédige une offre d\'emploi pour un développeur fullstack React/Node.js, niveau senior.',
  },
];

const COLOR_MAP: Record<string, { bg: string; icon: string; border: string; hover: string }> = {
  blue:   { bg: 'bg-blue-50 dark:bg-blue-950/30',    icon: 'text-blue-600 dark:text-blue-400',    border: 'border-blue-100 dark:border-blue-800/60',   hover: 'hover:border-blue-300 hover:bg-blue-50/80 dark:hover:border-blue-600' },
  violet: { bg: 'bg-violet-50 dark:bg-violet-950/30', icon: 'text-violet-600 dark:text-violet-400', border: 'border-violet-100 dark:border-violet-800/60', hover: 'hover:border-violet-300 hover:bg-violet-50/80 dark:hover:border-violet-600' },
  emerald:{ bg: 'bg-emerald-50 dark:bg-emerald-950/30',icon: 'text-emerald-600 dark:text-emerald-400',border: 'border-emerald-100 dark:border-emerald-800/60',hover: 'hover:border-emerald-300 hover:bg-emerald-50/80 dark:hover:border-emerald-600' },
  amber:  { bg: 'bg-amber-50 dark:bg-amber-950/30',   icon: 'text-amber-600 dark:text-amber-400',   border: 'border-amber-100 dark:border-amber-800/60',   hover: 'hover:border-amber-300 hover:bg-amber-50/80 dark:hover:border-amber-600' },
};

// ─── Markdown renderer ───────────────────────────────────────────────

function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith('## ')) {
      elements.push(<h2 key={i} className="text-base font-bold mt-4 mb-1 text-gray-900 dark:text-white">{renderInline(line.slice(3))}</h2>);
    } else if (line.startsWith('# ')) {
      elements.push(<h1 key={i} className="text-lg font-bold mt-4 mb-2 text-gray-900 dark:text-white">{renderInline(line.slice(2))}</h1>);
    } else if (line.startsWith('### ')) {
      elements.push(<h3 key={i} className="text-sm font-semibold mt-3 mb-1 text-gray-800 dark:text-gray-200">{renderInline(line.slice(4))}</h3>);
    } else if (line.startsWith('---')) {
      elements.push(<hr key={i} className="my-3 border-gray-200 dark:border-gray-700" />);
    } else if (line.match(/^(\d+)\.\s/)) {
      elements.push(
        <div key={i} className="flex gap-2 text-sm py-0.5">
          <span className="text-gray-400 shrink-0 font-medium">{line.match(/^(\d+)/)![1]}.</span>
          <span>{renderInline(line.replace(/^\d+\.\s/, ''))}</span>
        </div>
      );
    } else if (line.startsWith('- ') || line.startsWith('• ')) {
      elements.push(
        <div key={i} className="flex gap-2 text-sm py-0.5">
          <span className="text-indigo-400 shrink-0 mt-0.5">•</span>
          <span>{renderInline(line.slice(2))}</span>
        </div>
      );
    } else if (line.trim() === '') {
      elements.push(<div key={i} className="h-2" />);
    } else {
      elements.push(<p key={i} className="text-sm leading-relaxed">{renderInline(line)}</p>);
    }
    i++;
  }
  return elements;
}

function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const regex = /\*\*(.+?)\*\*|\*(.+?)\*/g;
  let last = 0;
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    if (match[1]) parts.push(<strong key={match.index} className="font-semibold text-gray-900 dark:text-white">{match[1]}</strong>);
    else if (match[2]) parts.push(<em key={match.index} className="italic">{match[2]}</em>);
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length === 1 ? parts[0] : <>{parts}</>;
}

// ─── Score bar ───────────────────────────────────────────────────────

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(Math.max(score, 0), 100);
  const color = pct >= 75 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-semibold text-gray-600 dark:text-gray-300 w-10 text-right">{pct.toFixed(0)}%</span>
    </div>
  );
}

// ─── Recommendations card ─────────────────────────────────────────────

function RecommendationsDisplay({ recommendations }: { recommendations: any }) {
  if (!recommendations) return null;
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="mt-4 space-y-4 w-full">
      <div className="grid grid-cols-3 gap-3">
        {[
          { value: recommendations.team_members?.length ?? 0, label: 'Membres', color: 'text-indigo-600 dark:text-indigo-400' },
          { value: recommendations.assignments?.length ?? 0, label: 'Tâches', color: 'text-violet-600 dark:text-violet-400' },
          {
            value: `${recommendations.assignments?.length > 0 ? Math.round(recommendations.assignments.reduce((s: number, a: any) => s + (a.confidence_score ?? 0), 0) / recommendations.assignments.length * 100) : 0}%`,
            label: 'Conf. moy.', color: 'text-emerald-600 dark:text-emerald-400'
          },
        ].map((stat, i) => (
          <div key={i} className="bg-gray-50 dark:bg-gray-800/60 border border-gray-100 dark:border-gray-700/60 rounded-xl p-3 text-center">
            <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
            <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{stat.label}</div>
          </div>
        ))}
      </div>

      {recommendations.warnings?.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-800/40 rounded-xl p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
            <div className="space-y-1">
              {recommendations.warnings.map((w: string, i: number) => (
                <p key={i} className="text-xs text-amber-700 dark:text-amber-300">{w}</p>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          <Users className="w-3.5 h-3.5" /> Candidats recommandés
        </div>
        {recommendations.team_members?.map((member: any) => {
          const memberAssignments = recommendations.assignments?.filter((a: any) => a.candidate_id === member.candidate_id) ?? [];
          const avgScore = memberAssignments.length > 0
            ? memberAssignments.reduce((s: number, a: any) => s + (a.confidence_score ?? 0), 0) / memberAssignments.length * 100 : 0;
          return (
            <div key={member.candidate_id} className="bg-white dark:bg-gray-800/80 border border-gray-100 dark:border-gray-700/60 rounded-xl p-4 hover:shadow-sm transition-shadow">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold text-sm shadow-sm">
                    {member.candidate_name?.charAt(0)?.toUpperCase() ?? '?'}
                  </div>
                  <div>
                    <div className="font-semibold text-gray-900 dark:text-white text-sm">{member.candidate_name}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <Clock className="w-3 h-3 text-gray-400" />
                      <span className="text-xs text-gray-400">{member.years_experience} ans d'exp.</span>
                      {member.total_workload_days > 0 && (
                        <><span className="text-gray-200 dark:text-gray-600">·</span><span className="text-xs text-gray-400">{member.total_workload_days}j estimés</span></>
                      )}
                    </div>
                  </div>
                </div>
                <div className="shrink-0 w-28"><ScoreBar score={avgScore} /></div>
              </div>
              {member.skills?.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {member.skills.slice(0, 7).map((skill: string, i: number) => (
                    <span key={i} className="px-2 py-0.5 rounded-md bg-gray-100 dark:bg-gray-700/80 text-gray-600 dark:text-gray-300 text-xs">{skill}</span>
                  ))}
                </div>
              )}
              {memberAssignments.length > 0 && (
                <div className="border-t border-gray-100 dark:border-gray-700/50 pt-3 space-y-2">
                  <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Tâches assignées</div>
                  {memberAssignments.map((assignment: any, idx: number) => (
                    <div key={idx} className="bg-indigo-50/50 dark:bg-indigo-950/20 rounded-lg p-2.5">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-medium text-gray-800 dark:text-gray-200">{assignment.task_title}</span>
                        <span className="text-[10px] text-gray-400 shrink-0">{((assignment.matching_score || assignment.confidence_score * 100) ?? 0).toFixed(0)}%</span>
                      </div>
                      {assignment.reasoning && <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{assignment.reasoning}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {recommendations.overall_recommendation && (
        <div className="bg-gradient-to-br from-indigo-50 to-violet-50 dark:from-indigo-950/20 dark:to-violet-950/20 border border-indigo-100 dark:border-indigo-800/40 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <TrendingUp className="w-4 h-4 text-indigo-500 mt-0.5 shrink-0" />
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-1">Analyse globale</div>
              <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{recommendations.overall_recommendation}</p>
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
}

// ─── Main component ───────────────────────────────────────────────────

function AIAssistantPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [loadingLabel, setLoadingLabel] = useState('Analyse en cours...');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { loadConversations(); }, []);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) { ta.style.height = 'auto'; ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`; }
  }, [inputValue]);

  const loadConversations = async () => {
    try {
      const res = await fetch('/api/conversations/', { credentials: 'include' });
      if (res.ok) { const data = await res.json(); setConversations(data.conversations ?? []); }
    } catch (e) { console.error('Failed to load conversations:', e); }
  };

  const createNewConversation = async () => {
    try {
      const res = await fetch('/api/conversations/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ title: `Conversation — ${new Date().toLocaleDateString('fr-FR')}` }),
      });
      if (res.ok) {
        const conv = await res.json();
        setConversations(prev => [conv, ...prev]);
        setCurrentConversationId(conv.conversation_id);
        setMessages([]);
      }
    } catch (e) { toast.error('Erreur lors de la création'); }
  };

  const loadConversation = async (id: string) => {
    try {
      const res = await fetch(`/api/conversations/${id}`, { credentials: 'include' });
      if (res.ok) {
        const conv = await res.json();
        setCurrentConversationId(conv.conversation_id);
        setMessages(conv.messages.map((m: any) => ({ ...m, timestamp: new Date(m.timestamp) })));
      }
    } catch (e) { toast.error('Erreur lors du chargement'); }
  };

  const deleteConversation = async (id: string) => {
    try {
      const res = await fetch(`/api/conversations/${id}`, { method: 'DELETE', credentials: 'include' });
      if (res.ok) {
        setConversations(prev => prev.filter(c => c.conversation_id !== id));
        if (currentConversationId === id) { setCurrentConversationId(null); setMessages([]); }
        toast.success('Conversation supprimée');
      }
    } catch (e) { toast.error('Erreur lors de la suppression'); }
  };

  const saveMessage = async (message: Message, convId?: string): Promise<string | null> => {
    const target = convId ?? currentConversationId;
    try {
      if (!target) {
        const createRes = await fetch('/api/conversations/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ title: message.content.slice(0, 60) + (message.content.length > 60 ? '…' : '') }),
        });
        if (!createRes.ok) throw new Error(`Erreur création: ${createRes.status}`);
        const newConv = await createRes.json();
        const newId = newConv.conversation_id;
        await fetch(`/api/conversations/${newId}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ message }),
        });
        setCurrentConversationId(newId);
        setConversations(prev => [newConv, ...prev]);
        return newId;
      } else {
        await fetch(`/api/conversations/${target}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ message }),
        });
        return target;
      }
    } catch (e: any) {
      console.error('[saveMessage]', e);
      return null;
    }
  };

  const detectLoadingLabel = (text: string) => {
    const t = text.toLowerCase();
    if (/(offre|fiche de poste|annonce)/.test(t)) return 'Rédaction de l\'offre…';
    if (/(résumé|profil|cv de|qui est|parle moi)/.test(t)) return 'Analyse du profil…';
    if (/(spécialisé|orienté|expert|meilleur|frontend|backend|devops|fullstack)/.test(t)) return 'Recherche en cours…';
    if (/(comment|quel|qu\'est|conseil|explique)/.test(t)) return 'Réflexion en cours…';
    return 'Analyse en cours…';
  };

  const handleSendMessage = async (content: string) => {
    if (!content.trim() || isLoading) return;

    const userMessage: Message = { id: Date.now().toString(), role: 'user', content: content.trim(), timestamp: new Date() };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setLoadingLabel(detectLoadingLabel(content));
    setIsLoading(true);

    const convId = await saveMessage(userMessage);
    if (!convId) {
      setMessages(prev => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: '❌ Impossible de créer la conversation. Veuillez réessayer.', timestamp: new Date() }]);
      setIsLoading(false);
      return;
    }

    try {
      const res = await fetch('/api/projects/analyze-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ text: content.trim(), conversation_id: convId }),
      });
      if (!res.ok) throw new Error('Erreur lors de l\'analyse');
      const data = await res.json();
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.message ?? 'Analyse terminée',
        timestamp: new Date(),
        response_type: data.response_type,
        recommendations: data.recommendations,
        job_offer_data: data.job_offer_data,
      };
      setMessages(prev => [...prev, assistantMessage]);
      await saveMessage(assistantMessage, convId);
      loadConversations();
    } catch (e: any) {
      const errMsg: Message = { id: (Date.now() + 1).toString(), role: 'assistant', content: `❌ Erreur: ${e.message}`, timestamp: new Date() };
      setMessages(prev => [...prev, errMsg]);
      await saveMessage(errMsg, convId);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendMessage(inputValue); }
  };

  const getResponseTypeBadge = (type?: string) => {
    const map: Record<string, { label: string; color: string }> = {
      project:           { label: 'Recommandation',      color: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-400' },
      candidate_profile: { label: 'Profil candidat',     color: 'bg-violet-50 text-violet-600 dark:bg-violet-950/40 dark:text-violet-400' },
      specialty_search:  { label: 'Spécialité',          color: 'bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400' },
      job_offer:         { label: 'Offre d\'emploi',     color: 'bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-400' },
      general:           { label: 'Conseil RH',          color: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400' },
    };
    if (!type || !map[type]) return null;
    const { label, color } = map[type];
    return <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${color}`}>{label}</span>;
  };

  const currentConversation = conversations.find(c => c.conversation_id === currentConversationId);

  // ─── Render ─────────────────────────────────────────────────────────

  return (
    <div className="h-full flex bg-white dark:bg-gray-950">

      {/* ── Sidebar ── */}
      <AnimatePresence initial={false}>
        {isSidebarOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 260, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 320, damping: 32 }}
            className="overflow-hidden border-r border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/60 flex flex-col shrink-0"
          >
            {/* Sidebar top */}
            <div className="px-3 pt-4 pb-3">
              <button
                onClick={createNewConversation}
                className="w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-600 hover:shadow-sm transition-all text-sm font-medium text-gray-700 dark:text-gray-200 group"
              >
                <span className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-indigo-500" />
                  Nouvelle conversation
                </span>
                <SquarePen className="w-3.5 h-3.5 text-gray-400 group-hover:text-indigo-500 transition-colors" />
              </button>
            </div>

            {/* History */}
            <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-0.5">
              {conversations.length === 0 ? (
                <div className="text-center py-12 text-gray-400 dark:text-gray-600">
                  <History className="w-7 h-7 mx-auto mb-2 opacity-30" />
                  <p className="text-xs">Aucune conversation</p>
                </div>
              ) : (
                <>
                  <p className="text-[10px] font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider px-2 py-2">Historique</p>
                  {conversations.map((conv) => (
                    <div
                      key={conv.conversation_id}
                      className={`group relative rounded-lg px-2.5 py-2 cursor-pointer transition-colors ${
                        currentConversationId === conv.conversation_id
                          ? 'bg-indigo-50 dark:bg-indigo-950/40'
                          : 'hover:bg-gray-100/80 dark:hover:bg-gray-800/50'
                      }`}
                      onClick={() => loadConversation(conv.conversation_id)}
                    >
                      <div className="flex items-center gap-2">
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs font-medium truncate leading-snug ${currentConversationId === conv.conversation_id ? 'text-indigo-700 dark:text-indigo-300' : 'text-gray-700 dark:text-gray-300'}`}>
                            {conv.title}
                          </p>
                          <p className="text-[10px] text-gray-400 dark:text-gray-600 mt-0.5">
                            {new Date(conv.updated_at).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
                          </p>
                        </div>
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteConversation(conv.conversation_id); }}
                          className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-md transition-all shrink-0"
                        >
                          <Trash2 className="w-3 h-3 text-red-400" />
                        </button>
                      </div>
                    </div>
                  ))}
                </>
              )}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* ── Main ── */}
      <div className="flex-1 flex flex-col min-w-0">


        {/* Messages area */}
        <div className="flex-1 overflow-y-auto px-5 py-6">
          {messages.length === 0 ? (

            /* Empty state */
            <div className="max-w-2xl mx-auto h-full flex flex-col justify-center">
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
                <div className="inline-flex w-14 h-14 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-2xl items-center justify-center shadow-md mb-5">
                  <Sparkles className="w-7 h-7 text-white" />
                </div>
                <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-2">
                  Que puis-je faire pour vous ?
                </h2>
                <p className="text-sm text-gray-400 dark:text-gray-500">
                  Posez une question, décrivez un projet ou demandez une offre
                </p>
              </motion.div>

              <div className="grid grid-cols-2 gap-2.5">
                {CAPABILITIES.map((cap, i) => {
                  const c = COLOR_MAP[cap.color];
                  return (
                    <motion.button
                      key={i}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.06 }}
                      onClick={() => { setInputValue(cap.prompt); textareaRef.current?.focus(); }}
                      className={`text-left p-4 rounded-xl border ${c.border} bg-white dark:bg-gray-900 ${c.hover} transition-all group cursor-pointer`}
                    >
                      <div className={`w-8 h-8 rounded-lg ${c.bg} flex items-center justify-center mb-3`}>
                        <cap.icon className={`w-4 h-4 ${c.icon}`} />
                      </div>
                      <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">{cap.title}</div>
                      <p className="text-xs text-gray-400 dark:text-gray-500 leading-relaxed">{cap.description}</p>
                    </motion.button>
                  );
                })}
              </div>
            </div>

          ) : (

            /* Messages list */
            <div className="max-w-2xl mx-auto space-y-6">
              <AnimatePresence>
                {messages.map((msg) => (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    {msg.role === 'assistant' && (
                      <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-sm shrink-0 mt-1">
                        <Sparkles className="w-3.5 h-3.5 text-white" />
                      </div>
                    )}

                    <div className={`max-w-[88%] ${msg.role === 'user' ? 'flex flex-col items-end' : 'flex flex-col items-start'}`}>
                      {msg.role === 'assistant' && msg.response_type && msg.response_type !== 'project' && (
                        <div className="mb-1.5">{getResponseTypeBadge(msg.response_type)}</div>
                      )}

                      <div className={`rounded-2xl px-4 py-3 ${
                        msg.role === 'user'
                          ? 'bg-indigo-600 text-white rounded-tr-md'
                          : 'bg-gray-50 dark:bg-gray-800/80 border border-gray-100 dark:border-gray-700/60 text-gray-900 dark:text-white rounded-tl-md'
                      }`}>
                        {msg.role === 'user' ? (
                          <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                        ) : (
                          <div className="text-sm text-gray-700 dark:text-gray-200 space-y-0.5">
                            {renderMarkdown(msg.content)}
                          </div>
                        )}
                        <p className={`text-[10px] mt-2 ${msg.role === 'user' ? 'text-indigo-300' : 'text-gray-400 dark:text-gray-500'}`}>
                          {(msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp))
                            .toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                        </p>
                      </div>

                      {msg.role === 'assistant' && msg.recommendations && (
                        <div className="w-full mt-2">
                          {getResponseTypeBadge('project')}
                          <RecommendationsDisplay recommendations={msg.recommendations} />
                        </div>
                      )}

                      {msg.role === 'assistant' && msg.response_type === 'job_offer' && msg.job_offer_data && (
                        <div className="w-full mt-3">
                          <div className="flex items-center gap-3 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3">
                            {/* Icône fichier */}
                            <div className="w-10 h-10 rounded-lg bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 flex items-center justify-center shrink-0 shadow-sm">
                              <FileText className="w-5 h-5 text-indigo-500" />
                            </div>
                            {/* Infos fichier */}
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                                {msg.job_offer_data.title || 'Offre d\'emploi'}
                              </p>
                              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Document · DOCX</p>
                            </div>
                            {/* Bouton télécharger */}
                            <button
                              onClick={async () => {
                                try {
                                  await generateJobOfferDocx(msg.job_offer_data);
                                  toast.success('Offre téléchargée');
                                } catch {
                                  toast.error('Erreur lors de la génération');
                                }
                              }}
                              className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg transition-colors shrink-0"
                            >
                              <Download className="w-3.5 h-3.5" />
                              Télécharger
                            </button>
                          </div>
                        </div>
                      )}
                    </div>

                    {msg.role === 'user' && (
                      <div className="w-7 h-7 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center shrink-0 mt-1">
                        <User className="w-3.5 h-3.5 text-gray-500 dark:text-gray-300" />
                      </div>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>

              {isLoading && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                  <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-sm shrink-0 mt-1">
                    <Sparkles className="w-3.5 h-3.5 text-white" />
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800/80 border border-gray-100 dark:border-gray-700/60 rounded-2xl rounded-tl-md px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex gap-1">
                        {[0, 0.15, 0.3].map((delay, i) => (
                          <motion.div
                            key={i}
                            className="w-1.5 h-1.5 bg-indigo-400 rounded-full"
                            animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }}
                            transition={{ duration: 0.9, delay, repeat: Infinity }}
                          />
                        ))}
                      </div>
                      <span className="text-xs text-gray-400">{loadingLabel}</span>
                    </div>
                  </div>
                </motion.div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-950 px-5 py-3 shrink-0">
          <div className="max-w-2xl mx-auto">
            <div className="flex gap-2 items-end bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700 rounded-2xl px-4 py-3 focus-within:border-indigo-300 dark:focus-within:border-indigo-600 focus-within:ring-2 focus-within:ring-indigo-100 dark:focus-within:ring-indigo-900/30 transition-all">
              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Posez votre question…"
                rows={1}
                disabled={isLoading}
                className="flex-1 resize-none bg-transparent text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 outline-none disabled:opacity-50"
                style={{ minHeight: 24, maxHeight: 160 }}
              />
              <button
                onClick={() => handleSendMessage(inputValue)}
                disabled={!inputValue.trim() || isLoading}
                className="w-8 h-8 flex items-center justify-center rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
