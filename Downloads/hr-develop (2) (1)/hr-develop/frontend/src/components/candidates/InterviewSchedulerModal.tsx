import { useState, useEffect } from 'react';
import { X, Calendar, Clock, Video, Building2, ChevronRight, ChevronLeft, Check, Loader2, Link, Users, Layers, MonitorPlay, PenLine, Tv2, Camera, Phone, Wrench } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import { Candidate } from '../../types/candidates.types';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface Room {
  room_id:   string;
  name:      string;
  floor:     string | null;
  building:  string | null;
  capacity:  number;
  equipment: string[];
  available: boolean;
}

interface InterviewSchedulerModalProps {
  candidate:     Candidate;
  jobPostingId?: string;
  onClose:       () => void;
  onScheduled:   () => void;
}

type Format   = 'online' | 'onsite';
type Platform = 'teams' | 'meet' | 'zoom';
type Step     = 1 | 2 | 3;

const DURATIONS   = [30, 45, 60] as const;
const DUR_LABELS  = { 30: '30 min', 45: '45 min', 60: '1 heure' } as const;
const TIME_SLOTS  = Array.from({ length: 21 }, (_, i) => {
  const h = Math.floor(i / 2) + 8;
  const m = i % 2 === 0 ? '00' : '30';
  return `${String(h).padStart(2, '0')}:${m}`;
});

const PLATFORMS: { id: Platform; label: string; color: string }[] = [
  { id: 'teams', label: 'Microsoft Teams', color: 'bg-blue-600'  },
  { id: 'meet',  label: 'Google Meet',     color: 'bg-green-600' },
  { id: 'zoom',  label: 'Zoom',            color: 'bg-sky-500'   },
];

const EQUIP_MAP: Record<string, { icon: React.ReactNode; label: string; cls: string }> = {
  projector:  { icon: <MonitorPlay className="h-3 w-3" />, label: 'Projecteur', cls: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800' },
  whiteboard: { icon: <PenLine     className="h-3 w-3" />, label: 'Tableau',    cls: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-800' },
  tv:         { icon: <Tv2         className="h-3 w-3" />, label: 'TV',         cls: 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/20 dark:text-purple-300 dark:border-purple-800' },
  webcam:     { icon: <Camera      className="h-3 w-3" />, label: 'Webcam',     cls: 'bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/20 dark:text-orange-300 dark:border-orange-800' },
  phone:      { icon: <Phone       className="h-3 w-3" />, label: 'Téléphone',  cls: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/20 dark:text-rose-300 dark:border-rose-800' },
};
const EQUIP_DEFAULT = { icon: <Wrench className="h-3 w-3" />, label: '', cls: 'bg-gray-50 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700' };

function parseEquipment(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw as string[];
  if (typeof raw === 'string') {
    try { return JSON.parse(raw); } catch { return []; }
  }
  return [];
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatDateFR(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso + 'T12:00:00');
  return d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}

function buildCalendarDays(year: number, month: number): (number | null)[] {
  const first   = new Date(year, month, 1).getDay(); // 0=Sun
  const offset  = (first + 6) % 7;                  // Mon=0
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = Array(offset).fill(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  return cells;
}

const MONTH_NAMES_FR = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
];
const DAY_NAMES_FR = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];

// ─────────────────────────────────────────────────────────────────────────────
// Mini calendar component
// ─────────────────────────────────────────────────────────────────────────────

function MiniCalendar({
  selected, onSelect,
}: {
  selected: string;
  onSelect: (d: string) => void;
}) {
  const now     = new Date();
  const [year,  setYear]  = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());

  const cells   = buildCalendarDays(year, month);
  const todayIso = today();

  function toISO(day: number) {
    return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  }

  function prevMonth() {
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
  }

  function nextMonth() {
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
  }

  return (
    <div className="w-full select-none">
      <div className="flex items-center justify-between mb-3">
        <button onClick={prevMonth} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
          <ChevronLeft className="h-4 w-4 text-gray-600 dark:text-gray-400" />
        </button>
        <span className="text-sm font-semibold text-gray-900 dark:text-white">
          {MONTH_NAMES_FR[month]} {year}
        </span>
        <button onClick={nextMonth} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
          <ChevronRight className="h-4 w-4 text-gray-600 dark:text-gray-400" />
        </button>
      </div>

      <div className="grid grid-cols-7 mb-1">
        {DAY_NAMES_FR.map(d => (
          <div key={d} className="text-center text-[11px] font-medium text-gray-400 dark:text-gray-500 py-1">{d}</div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-y-1">
        {cells.map((day, i) => {
          if (!day) return <div key={i} />;
          const iso      = toISO(day);
          const isPast   = iso < todayIso;
          const isToday  = iso === todayIso;
          const isSelected = iso === selected;
          const isWeekend = [5, 6].includes((new Date(iso).getDay() + 6) % 7); // Sat/Sun in Mon-first

          return (
            <button
              key={i}
              disabled={isPast || isWeekend}
              onClick={() => onSelect(iso)}
              className={`
                h-8 w-8 mx-auto rounded-full text-sm transition-all
                ${isPast || isWeekend ? 'text-gray-300 dark:text-gray-700 cursor-not-allowed' : 'cursor-pointer'}
                ${isSelected ? 'bg-indigo-600 text-white font-semibold shadow-md' : ''}
                ${isToday && !isSelected ? 'ring-2 ring-indigo-400 text-indigo-600 dark:text-indigo-400 font-semibold' : ''}
                ${!isSelected && !isPast && !isWeekend ? 'hover:bg-indigo-50 dark:hover:bg-indigo-900/30 text-gray-900 dark:text-white' : ''}
              `}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Step indicator
// ─────────────────────────────────────────────────────────────────────────────

function StepBar({ current }: { current: Step }) {
  const steps = [
    { n: 1, label: 'Date & Heure' },
    { n: 2, label: 'Format'       },
    { n: 3, label: 'Confirmer'    },
  ];
  return (
    <div className="flex items-center gap-0 mb-6">
      {steps.map((s, i) => (
        <div key={s.n} className="flex items-center flex-1 last:flex-none">
          <div className="flex flex-col items-center gap-1">
            <div className={`
              w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all
              ${current > s.n
                ? 'bg-indigo-600 text-white'
                : current === s.n
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200 dark:shadow-indigo-900/30 scale-110'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-600'}
            `}>
              {current > s.n ? <Check className="h-4 w-4" /> : s.n}
            </div>
            <span className={`text-[11px] font-medium whitespace-nowrap ${current === s.n ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-400 dark:text-gray-600'}`}>
              {s.label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div className={`flex-1 h-0.5 mx-2 mb-5 rounded transition-all ${current > s.n ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-700'}`} />
          )}
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main modal
// ─────────────────────────────────────────────────────────────────────────────

export function InterviewSchedulerModal({
  candidate, jobPostingId, onClose, onScheduled,
}: InterviewSchedulerModalProps) {

  const [step, setStep]               = useState<Step>(1);
  const [date, setDate]               = useState<string>(today());
  const [time, setTime]               = useState<string>('');
  const [duration, setDuration]       = useState<30 | 45 | 60>(45);
  const [format, setFormat]           = useState<Format>('online');
  const [platform, setPlatform]       = useState<Platform>('teams');
  const [meetingLink, setMeetingLink] = useState<string>('');
  const [rooms, setRooms]             = useState<Room[]>([]);
  const [roomsLoading, setRoomsLoading] = useState(false);
  const [selectedRoom, setSelectedRoom] = useState<string>('');
  const [submitting, setSubmitting]   = useState(false);
  const [resolvedEmail, setResolvedEmail] = useState<string | null>(candidate.email ?? null);

  // Fetch candidate email from DB if not provided
  useEffect(() => {
    if (!candidate.email && candidate.candidate_id) {
      fetch(`/api/v1/candidates/${candidate.candidate_id}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data?.email) setResolvedEmail(data.email); })
        .catch(() => {});
    }
  }, [candidate.candidate_id, candidate.email]);

  // Load available rooms when switching to onsite or step 2
  useEffect(() => {
    if (format === 'onsite' && date && time) {
      setRoomsLoading(true);
      fetch(`/api/v1/rooms/available?date=${date}&time=${time}&duration_min=${duration}`)
        .then(r => r.json())
        .then(data => { setRooms(data); setRoomsLoading(false); })
        .catch(() => setRoomsLoading(false));
    }
  }, [format, date, time, duration]);

  const canGoStep2 = !!date && !!time;
  const canGoStep3 =
    format === 'online'
      ? true
      : !!selectedRoom;

  async function handleConfirm() {
    setSubmitting(true);
    try {
      const body = {
        candidate_id:    candidate.candidate_id,
        job_posting_id:  jobPostingId ?? null,
        interview_date:  date,
        interview_time:  time,
        duration_min:    duration,
        format,
        platform:        format === 'online' ? platform : null,
        meeting_link:    format === 'online' && meetingLink ? meetingLink : null,
        room_id:         format === 'onsite' ? selectedRoom || null : null,
        candidate_email: resolvedEmail,
        candidate_name:  candidate.full_name,
      };

      const res = await fetch('/api/v1/interviews', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 409) {
          toast.warning(`⚠️ ${err.detail}`, { duration: 7000 });
          return;
        }
        throw new Error(err.detail || 'Erreur lors de la planification');
      }

      const data = await res.json();
      toast.success(
        data.email_sent
          ? `Entretien planifié — email de convocation envoyé avec succès`
          : `Entretien planifié (vérifiez la configuration SMTP)`,
        { duration: 5000 }
      );
      onScheduled();
      onClose();
    } catch (err: any) {
      toast.error(err.message || 'Erreur lors de la planification');
    } finally {
      setSubmitting(false);
    }
  }

  const slideVariants = {
    enter:  (dir: number) => ({ x: dir * 40, opacity: 0 }),
    center: { x: 0, opacity: 1 },
    exit:   (dir: number) => ({ x: dir * -40, opacity: 0 }),
  };

  const [dir, setDir] = useState(1);

  function goNext() { setDir(1); setStep(s => (s + 1) as Step); }
  function goPrev() { setDir(-1); setStep(s => (s - 1) as Step); }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 16 }}
        transition={{ duration: 0.18 }}
        className="relative w-full max-w-xl bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">
              Planifier un entretien
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {candidate.full_name}
              {resolvedEmail && <span className="ml-2 text-gray-400 dark:text-gray-500">· {resolvedEmail}</span>}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          >
            <X className="h-4 w-4 text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 pt-5 pb-6">
          <StepBar current={step} />

          <div className="overflow-hidden" style={{ minHeight: 320 }}>
            <AnimatePresence mode="wait" custom={dir}>
              {step === 1 && (
                <motion.div
                  key="step1"
                  custom={dir}
                  variants={slideVariants}
                  initial="enter"
                  animate="center"
                  exit="exit"
                  transition={{ duration: 0.2 }}
                >
                  <Step1
                    date={date} onDateChange={setDate}
                    time={time} onTimeChange={setTime}
                    duration={duration} onDurationChange={setDuration}
                  />
                </motion.div>
              )}
              {step === 2 && (
                <motion.div
                  key="step2"
                  custom={dir}
                  variants={slideVariants}
                  initial="enter"
                  animate="center"
                  exit="exit"
                  transition={{ duration: 0.2 }}
                >
                  <Step2
                    format={format} onFormatChange={f => { setFormat(f); setSelectedRoom(''); }}
                    platform={platform} onPlatformChange={setPlatform}
                    meetingLink={meetingLink} onMeetingLinkChange={setMeetingLink}
                    rooms={rooms} roomsLoading={roomsLoading}
                    selectedRoom={selectedRoom} onRoomChange={setSelectedRoom}
                  />
                </motion.div>
              )}
              {step === 3 && (
                <motion.div
                  key="step3"
                  custom={dir}
                  variants={slideVariants}
                  initial="enter"
                  animate="center"
                  exit="exit"
                  transition={{ duration: 0.2 }}
                >
                  <Step3
                    candidate={candidate}
                    resolvedEmail={resolvedEmail}
                    date={date} time={time} duration={duration}
                    format={format} platform={platform}
                    meetingLink={meetingLink}
                    rooms={rooms} selectedRoom={selectedRoom}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={goPrev}
              disabled={step === 1}
              className="flex items-center gap-1.5 px-4 h-9 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
              Retour
            </button>

            {step < 3 ? (
              <button
                onClick={goNext}
                disabled={step === 1 ? !canGoStep2 : !canGoStep3}
                className="flex items-center gap-1.5 px-5 h-9 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
              >
                Suivant
                <ChevronRight className="h-4 w-4" />
              </button>
            ) : (
              <button
                onClick={handleConfirm}
                disabled={submitting}
                className="flex items-center gap-2 px-5 h-9 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-60 transition-colors shadow-sm"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                {submitting ? 'Planification...' : 'Confirmer l\'entretien'}
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Step 1 — Date, time, duration
// ─────────────────────────────────────────────────────────────────────────────

function Step1({
  date, onDateChange,
  time, onTimeChange,
  duration, onDurationChange,
}: {
  date: string; onDateChange: (d: string) => void;
  time: string; onTimeChange: (t: string) => void;
  duration: 30 | 45 | 60; onDurationChange: (d: 30 | 45 | 60) => void;
}) {
  return (
    <div className="space-y-5">
      {/* Calendar */}
      <div>
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <Calendar className="h-3.5 w-3.5" /> Choisir la date
        </p>
        <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700">
          <MiniCalendar selected={date} onSelect={onDateChange} />
        </div>
        {date && (
          <p className="mt-2 text-xs text-indigo-600 dark:text-indigo-400 font-medium">
            {formatDateFR(date)}
          </p>
        )}
      </div>

      {/* Time slots */}
      <div>
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" /> Choisir l'heure
        </p>
        <div className="grid grid-cols-7 gap-1.5">
          {TIME_SLOTS.map(slot => (
            <button
              key={slot}
              onClick={() => onTimeChange(slot)}
              className={`
                h-8 rounded-lg text-xs font-medium transition-all
                ${time === slot
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 hover:text-indigo-700 dark:hover:text-indigo-300 border border-gray-200 dark:border-gray-700'}
              `}
            >
              {slot}
            </button>
          ))}
        </div>
      </div>

      {/* Duration */}
      <div>
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" /> Durée estimée
        </p>
        <div className="flex gap-2">
          {DURATIONS.map(d => (
            <button
              key={d}
              onClick={() => onDurationChange(d)}
              className={`
                flex-1 h-10 rounded-xl text-sm font-semibold border transition-all
                ${duration === d
                  ? 'bg-indigo-600 border-indigo-600 text-white shadow-sm'
                  : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-400'}
              `}
            >
              {DUR_LABELS[d]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Step 2 — Format (online / onsite)
// ─────────────────────────────────────────────────────────────────────────────

function Step2({
  format, onFormatChange,
  platform, onPlatformChange,
  meetingLink, onMeetingLinkChange,
  rooms, roomsLoading,
  selectedRoom, onRoomChange,
}: {
  format: Format; onFormatChange: (f: Format) => void;
  platform: Platform; onPlatformChange: (p: Platform) => void;
  meetingLink: string; onMeetingLinkChange: (l: string) => void;
  rooms: Room[]; roomsLoading: boolean;
  selectedRoom: string; onRoomChange: (id: string) => void;
}) {
  return (
    <div className="space-y-5">
      {/* Toggle */}
      <div>
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
          Format de l'entretien
        </p>
        <div className="flex rounded-xl overflow-hidden border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 p-1 gap-1">
          <button
            onClick={() => onFormatChange('online')}
            className={`
              flex-1 flex items-center justify-center gap-2 h-11 rounded-lg text-sm font-semibold transition-all
              ${format === 'online'
                ? 'bg-white dark:bg-gray-900 text-indigo-600 dark:text-indigo-400 shadow-sm border border-gray-200 dark:border-gray-700'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}
            `}
          >
            <Video className="h-4 w-4" /> En ligne
          </button>
          <button
            onClick={() => onFormatChange('onsite')}
            className={`
              flex-1 flex items-center justify-center gap-2 h-11 rounded-lg text-sm font-semibold transition-all
              ${format === 'onsite'
                ? 'bg-white dark:bg-gray-900 text-indigo-600 dark:text-indigo-400 shadow-sm border border-gray-200 dark:border-gray-700'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}
            `}
          >
            <Building2 className="h-4 w-4" /> Présentiel
          </button>
        </div>
      </div>

      {/* Online section */}
      {format === 'online' && (
        <div className="space-y-4">
          <div>
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
              Plateforme
            </p>
            <div className="space-y-2">
              {PLATFORMS.map(p => (
                <button
                  key={p.id}
                  onClick={() => onPlatformChange(p.id)}
                  className={`
                    w-full flex items-center gap-3 px-4 h-12 rounded-xl border text-sm font-medium transition-all text-left
                    ${platform === p.id
                      ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-300'
                      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'}
                  `}
                >
                  <span className={`w-2.5 h-2.5 rounded-full ${p.color} flex-shrink-0`} />
                  {p.label}
                  {platform === p.id && <Check className="h-4 w-4 text-indigo-500 ml-auto" />}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2 flex items-center gap-1.5">
              <Link className="h-3.5 w-3.5" /> Lien de réunion (optionnel)
            </label>
            <input
              type="url"
              value={meetingLink}
              onChange={e => onMeetingLinkChange(e.target.value)}
              placeholder={`https://${platform === 'teams' ? 'teams.microsoft.com/l/meetup-join/...' : platform === 'meet' ? 'meet.google.com/...' : 'zoom.us/j/...'}`}
              className="w-full h-10 px-3 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>
      )}

      {/* Onsite section */}
      {format === 'onsite' && (
        <div>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-1.5">
            <Building2 className="h-3.5 w-3.5" /> Salles disponibles
          </p>

          {roomsLoading ? (
            <div className="flex items-center justify-center h-24 text-gray-400 dark:text-gray-600">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              <span className="text-sm">Vérification des disponibilités...</span>
            </div>
          ) : rooms.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-6">
              Aucune salle disponible pour ce créneau.
            </p>
          ) : (
            <div className="space-y-2 max-h-56 overflow-y-auto pr-0.5">
              {rooms.map(room => {
                const equip   = parseEquipment(room.equipment);
                const selected = selectedRoom === room.room_id;
                return (
                  <button
                    key={room.room_id}
                    disabled={!room.available}
                    onClick={() => onRoomChange(room.room_id)}
                    className={[
                      'w-full flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-all duration-150',
                      !room.available
                        ? 'opacity-40 cursor-not-allowed bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700'
                        : selected
                          ? 'bg-indigo-50 dark:bg-indigo-950/40 border-indigo-400 dark:border-indigo-600 shadow-sm'
                          : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-600 hover:shadow-sm',
                    ].join(' ')}
                  >
                    {/* Icon */}
                    <div className={[
                      'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0',
                      selected
                        ? 'bg-indigo-100 dark:bg-indigo-900/50'
                        : 'bg-gray-100 dark:bg-gray-700',
                    ].join(' ')}>
                      <Layers className={`h-4 w-4 ${selected ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-500 dark:text-gray-400'}`} />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className={`text-sm font-semibold truncate ${selected ? 'text-indigo-700 dark:text-indigo-300' : 'text-gray-900 dark:text-white'}`}>
                          {room.name}
                        </span>
                        {!room.available && (
                          <span className="text-[10px] font-semibold text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-400 px-2 py-0.5 rounded-full border border-red-200 dark:border-red-800 flex-shrink-0">
                            Occupée
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-3 mb-1.5">
                        {room.floor && (
                          <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                            <Layers className="h-3 w-3" /> Étage {room.floor}
                          </span>
                        )}
                        <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                          <Users className="h-3 w-3" /> {room.capacity} pers.
                        </span>
                        {room.building && (
                          <span className="text-xs text-gray-400 dark:text-gray-500">{room.building}</span>
                        )}
                      </div>

                      {equip.length > 0 && (
                        <div className="flex gap-1 flex-wrap">
                          {equip.map(eq => {
                            const e = EQUIP_MAP[eq] ?? { ...EQUIP_DEFAULT, label: eq };
                            return (
                              <span
                                key={eq}
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] font-medium ${e.cls}`}
                              >
                                {e.icon}
                                {e.label || eq}
                              </span>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {selected && room.available && (
                      <div className="w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center flex-shrink-0">
                        <Check className="h-3 w-3 text-white" />
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Step 3 — Confirmation summary
// ─────────────────────────────────────────────────────────────────────────────

function Step3({
  candidate, resolvedEmail, date, time, duration,
  format, platform, meetingLink,
  rooms, selectedRoom,
}: {
  candidate: Candidate;
  resolvedEmail: string | null;
  date: string; time: string; duration: 30 | 45 | 60;
  format: Format; platform: Platform; meetingLink: string;
  rooms: Room[]; selectedRoom: string;
}) {
  const room = rooms.find(r => r.room_id === selectedRoom);
  const platformLabels: Record<Platform, string> = {
    teams: 'Microsoft Teams',
    meet:  'Google Meet',
    zoom:  'Zoom',
  };

  const rows: { label: string; value: string; icon: React.ReactNode }[] = [
    {
      label: 'Candidat',
      value: candidate.full_name || 'N/A',
      icon: <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold">{candidate.full_name?.charAt(0) || '?'}</div>,
    },
    {
      label: 'Date',
      value: formatDateFR(date),
      icon: <Calendar className="h-4 w-4 text-indigo-500" />,
    },
    {
      label: 'Heure',
      value: `${time} (${DUR_LABELS[duration]})`,
      icon: <Clock className="h-4 w-4 text-indigo-500" />,
    },
    {
      label: 'Format',
      value: format === 'online' ? `En ligne — ${platformLabels[platform]}` : `Présentiel${room ? ` — ${room.name}` : ''}`,
      icon: format === 'online' ? <Video className="h-4 w-4 text-indigo-500" /> : <Building2 className="h-4 w-4 text-indigo-500" />,
    },
    ...(format === 'online' && meetingLink ? [{
      label: 'Lien',
      value: meetingLink,
      icon: <Link className="h-4 w-4 text-indigo-500" />,
    }] : []),
  ];

  return (
    <div className="space-y-4">
      <div className="bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        {rows.map((row, i) => (
          <div
            key={i}
            className={`flex items-center gap-3 px-4 py-3 ${i < rows.length - 1 ? 'border-b border-gray-200 dark:border-gray-700' : ''}`}
          >
            <div className="flex-shrink-0">{row.icon}</div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] text-gray-400 dark:text-gray-500 uppercase tracking-wide font-medium">{row.label}</p>
              <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{row.value}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-950/30 px-4 py-3 space-y-1.5">
        <p className="text-xs font-semibold text-indigo-700 dark:text-indigo-400 uppercase tracking-wide">
          Actions automatiques
        </p>
        {[
          resolvedEmail ? `Email de confirmation envoyé à ${resolvedEmail}` : 'Aucun email (adresse non renseignée)',
          'Rappel automatique la veille de l\'entretien',
          format === 'onsite' && room ? `Salle « ${room.name} » réservée instantanément` : null,
        ].filter(Boolean).map((action, i) => (
          <p key={i} className="text-xs text-indigo-600 dark:text-indigo-300 flex items-center gap-2">
            <Check className="h-3 w-3 flex-shrink-0" /> {action}
          </p>
        ))}
      </div>
    </div>
  );
}
