"use client";

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Check, Ban, Link2, Plus, RefreshCw, ExternalLink,
  Search, Loader2, AlertCircle, FileCode, Info, CheckCircle2,
  MessageSquare, LayoutList, Tag, BookOpen, Network, ArrowLeft, Cpu, FolderKanban, Percent, Sparkles,
} from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { API_URL } from '@/app/services/api';
import { LinkChatView } from './LinkChatView';
import { TopicsPanel } from './TopicsPanel';
import { useLanguage } from '@/lib/i18n/LanguageContext';

// ── Types ─────────────────────────────────────────────────────────────────────

interface EntityDocLink {
  id: number;
  entity_id: number;
  entity?: {
    id: number;
    name: string;
    type: string;
    file_path: string;
    start_line: number;
    end_line: number;
  };
  doc_title: string;
  doc_url: string | null;
  source_type: string | null;
  score: number | null;
  link_type: string;
  status: string;
  context: string | null;
  created_by: string;
}

interface KnowledgeLink {
  id: number;
  source_a: { type: string; title: string; url: string | null; source_type: string | null };
  source_b: { type: string; title: string; url: string | null; source_type: string | null };
  score: number | null;
  link_type: string;
  status: string;
  context: string | null;
  created_by: string;
}

interface LinkCounts { pending: number; approved: number; rejected: number; }

interface LinkManagerViewProps {
  isOpen: boolean;
  onClose: () => void;
  selectedProject: { id: number; name: string } | null;
  theme: string;
  currentUser?: { is_admin?: boolean } | null;
  projects?: any[];
  onSelectProject?: (project: any | null) => void;
  llmProfiles?: any[];
  activeProfileId?: string;
  setActiveProfileId?: (val: string) => void;
  showToast?: (msg: string, type: 'success' | 'error') => void;
}

type Segment = 'links' | 'topics';
type TabStatus = 'pending' | 'approved' | 'rejected';
type KindFilter = 'all' | 'entity' | 'knowledge';

interface UnifiedSide {
  label: string;
  caption?: string | null;
  sourceType?: string | null;
  url?: string | null;
  icon?: 'code';
}

interface UnifiedLink {
  id: string;
  kind: 'entity' | 'knowledge';
  rawId: number;
  left: UnifiedSide;
  right: UnifiedSide;
  score: number | null;
  linkType: string;
  status: string;
  context: string | null;
}

// ── Min-confidence setting ──────────────────────────────────────────────────
// Mirrors parser/tasks/link_builder.py + cross_link_builder.py LLM_MIN_CONFIDENCE
// (35) — the user's last-used value is remembered per browser (same pattern as
// the active-profile-id below), not persisted server-side, since it configures
// the *next* search run rather than a standing project setting.
const MIN_CONFIDENCE_STORAGE_KEY = 'doctus-link-min-confidence';
const MIN_CONFIDENCE_DEFAULT = 35;

function readStoredMinConfidence(): number {
  if (typeof window === 'undefined') return MIN_CONFIDENCE_DEFAULT;
  const parsed = parseInt(localStorage.getItem(MIN_CONFIDENCE_STORAGE_KEY) ?? '', 10);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 100 ? parsed : MIN_CONFIDENCE_DEFAULT;
}

// score is stored as a 0..1 float and rounded for display (ScoreBadge: Math.round(score * 100)).
// Guard against float noise (e.g. 0.999999...) so "100%" candidates are still caught.
const PERFECT_SCORE_THRESHOLD = 0.995;

// ── Small helpers ─────────────────────────────────────────────────────────────

// Backend returns prefixed string IDs ("ent_123") shared with the sidebar tree.
// Strip the prefix to recover the numeric DB id before submitting to the API.
const parseEntityId = (id: string | number): number => parseInt(String(id).replace(/^ent_/, ''));

function ScoreBadge({ score, isDark }: { score: number | null; isDark: boolean }) {
  const { t } = useLanguage();
  if (score === null)
    return <span className={cn('text-xs', isDark ? 'text-ds-zinc-500' : 'text-ds-zinc-400')}>{t('graphLabels.linkTypes.manual')}</span>;
  const pct = Math.round(score * 100);
  const color = pct >= 80 ? 'text-ds-emerald-500' : pct >= 60 ? 'text-ds-yellow-500' : 'text-ds-orange-500';
  return <span className={`text-xs font-mono font-semibold ${color}`}>{pct}%</span>;
}

// ── Main component ────────────────────────────────────────────────────────────

export function LinkManagerView({
  isOpen, onClose, selectedProject, theme, currentUser,
  projects = [], onSelectProject, llmProfiles = [], activeProfileId, setActiveProfileId, showToast,
}: LinkManagerViewProps) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';
  const isAdmin = !!currentUser?.is_admin;
  const activeProfile = llmProfiles.find(p => p.id === activeProfileId) || null;

  // Segment: links | topics
  const [segment, setSegment] = useState<Segment>('links');
  const [viewMode, setViewMode] = useState<'list' | 'chat'>('list');

  // Shared list state (both entity- and knowledge-links share one tab/filter/search bar)
  const [tab, setTab] = useState<TabStatus>('pending');
  const [kindFilter, setKindFilter] = useState<KindFilter>('all');
  const [minScore, setMinScore] = useState(0);
  const [minConfidence, setMinConfidence] = useState<number>(readStoredMinConfidence);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isComputing, setIsComputing] = useState(false);
  const [isAcceptingAll, setIsAcceptingAll] = useState(false);
  const [reviewingLinkIds, setReviewingLinkIds] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState<{ type: 'info' | 'success' | 'empty'; text: string } | null>(null);
  const [showManualForm, setShowManualForm] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevPendingRef = useRef(0);

  // Entity-Links data
  const [entityLinks, setEntityLinks] = useState<EntityDocLink[]>([]);
  const [entityCounts, setEntityCounts] = useState<LinkCounts>({ pending: 0, approved: 0, rejected: 0 });

  // Knowledge-Links data
  const [knowledgeLinks, setKnowledgeLinks] = useState<KnowledgeLink[]>([]);
  const [knowledgeCounts, setKnowledgeCounts] = useState<LinkCounts>({ pending: 0, approved: 0, rejected: 0 });

  // Manual link form state
  const [manualKind, setManualKind] = useState<'entity' | 'knowledge' | null>(null);
  const [entities, setEntities] = useState<any[]>([]);
  const [entitySearchInput, setEntitySearchInput] = useState('');
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(null);
  const [selectedEntityObj, setSelectedEntityObj] = useState<any | null>(null);
  const [docSearchQuery, setDocSearchQuery] = useState('');
  const [docResults, setDocResults] = useState<any[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<any | null>(null);
  const [docAQuery, setDocAQuery] = useState('');
  const [docAResults, setDocAResults] = useState<any[]>([]);
  const [selectedDocA, setSelectedDocA] = useState<any | null>(null);
  const [docBQuery, setDocBQuery] = useState('');
  const [docBResults, setDocBResults] = useState<any[]>([]);
  const [selectedDocB, setSelectedDocB] = useState<any | null>(null);
  const [isSubmittingManual, setIsSubmittingManual] = useState(false);
  const [manualError, setManualError] = useState('');

  const projectId = selectedProject?.id;

  // ── Theme tokens ──────────────────────────────────────────────────────────

  const overlay      = isDark ? 'bg-ds-black/60'                : 'bg-ds-black/30';
  const modalBg      = isDark ? 'bg-ds-zinc-900 border-ds-zinc-700': 'bg-ds-white border-ds-zinc-200';
  const divider      = isDark ? 'border-ds-zinc-800'            : 'border-ds-zinc-200';
  const titleText    = isDark ? 'text-ds-zinc-100'              : 'text-ds-zinc-900';
  const subText      = isDark ? 'text-ds-zinc-500'              : 'text-ds-zinc-500';
  const iconColor    = isDark ? 'text-ds-indigo-400'            : 'text-ds-indigo-600';
  const ghostBtn     = isDark
    ? 'text-ds-zinc-400 hover:text-ds-zinc-100 hover:bg-ds-zinc-800 rounded-md transition-colors'
    : 'text-ds-zinc-500 hover:text-ds-zinc-900 hover:bg-ds-zinc-100 rounded-md transition-colors';
  const accentBtn    = isDark
    ? 'text-ds-indigo-400 hover:text-ds-indigo-300 hover:bg-ds-indigo-900/30 border border-ds-indigo-700/50 rounded-md transition-colors'
    : 'text-ds-indigo-600 hover:text-ds-indigo-700 hover:bg-ds-indigo-50 border border-ds-indigo-300 rounded-md transition-colors';
  const tabActive    = isDark ? 'bg-ds-zinc-700 text-ds-zinc-100'  : 'bg-ds-zinc-200 text-ds-zinc-900';
  const tabInact     = isDark ? 'text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800' : 'text-ds-zinc-500 hover:text-ds-zinc-700 hover:bg-ds-zinc-100';
  const tabBadgeA    = isDark ? 'bg-ds-zinc-600 text-ds-zinc-200'  : 'bg-ds-zinc-300 text-ds-zinc-700';
  const tabBadgeI    = isDark ? 'bg-ds-zinc-800 text-ds-zinc-500'  : 'bg-ds-zinc-100 text-ds-zinc-500';
  const inputCls     = isDark
    ? 'bg-ds-zinc-800 border-ds-zinc-700 text-ds-zinc-200 placeholder:text-ds-zinc-600 focus:border-ds-zinc-500'
    : 'bg-ds-zinc-100 border-ds-zinc-300 text-ds-zinc-900 placeholder:text-ds-zinc-400 focus:border-ds-zinc-400';
  const cardCls      = isDark
    ? 'bg-ds-zinc-800/60 border-ds-zinc-700/60 hover:border-ds-zinc-600'
    : 'bg-ds-zinc-50 border-ds-zinc-200 hover:border-ds-zinc-300';
  const cardLabel    = isDark ? 'text-ds-zinc-200'              : 'text-ds-zinc-800';
  const cardMuted    = isDark ? 'text-ds-zinc-500'              : 'text-ds-zinc-400';
  const typeTag      = isDark ? 'bg-ds-zinc-700 text-ds-zinc-400'  : 'bg-ds-zinc-200 text-ds-zinc-500';
  const arrowColor   = isDark ? 'text-ds-zinc-600'              : 'text-ds-zinc-300';
  const emptyText    = isDark ? 'text-ds-zinc-600'              : 'text-ds-zinc-400';
  const manualBg     = isDark ? 'bg-ds-indigo-950/30 border-ds-indigo-900/50' : 'bg-ds-indigo-50/60 border-ds-indigo-200';
  const manualTitle  = isDark ? 'text-ds-indigo-300'            : 'text-ds-indigo-700';
  const manualDesc   = isDark ? 'text-ds-indigo-400/70'         : 'text-ds-indigo-500';
  const selectCls    = isDark
    ? 'bg-ds-zinc-800 border-ds-zinc-700 text-ds-zinc-200 focus:border-ds-indigo-500'
    : 'bg-ds-white border-ds-zinc-300 text-ds-zinc-900 focus:border-ds-indigo-400';
  const dropdownBg   = isDark ? 'bg-ds-zinc-800 border-ds-zinc-700 shadow-ds-black/40' : 'bg-ds-white border-ds-zinc-200 shadow-ds-zinc-200/60';
  const dropItem     = isDark ? 'text-ds-zinc-300 hover:bg-ds-zinc-700' : 'text-ds-zinc-700 hover:bg-ds-zinc-100';
  const actionApprove = isDark
    ? 'text-ds-zinc-500 hover:text-ds-emerald-400 hover:bg-ds-emerald-900/30'
    : 'text-ds-zinc-400 hover:text-ds-emerald-600 hover:bg-ds-emerald-50';
  const actionReject = isDark
    ? 'text-ds-zinc-500 hover:text-ds-red-400 hover:bg-ds-red-900/30'
    : 'text-ds-zinc-400 hover:text-ds-red-500 hover:bg-ds-red-50';
  const actionDel    = isDark
    ? 'text-ds-zinc-600 hover:text-ds-red-400 hover:bg-ds-red-900/30'
    : 'text-ds-zinc-400 hover:text-ds-red-500 hover:bg-ds-red-50';
  const kindChipActive = isDark ? 'bg-ds-indigo-900/50 text-ds-indigo-300 border-ds-indigo-700' : 'bg-ds-indigo-100 text-ds-indigo-700 border-ds-indigo-300';
  const kindChipInact  = isDark ? 'text-ds-zinc-500 border-ds-zinc-700 hover:text-ds-zinc-300' : 'text-ds-zinc-500 border-ds-zinc-300 hover:text-ds-zinc-700';

  const sourceColors: Record<string, string> = isDark
    ? { Confluence: 'bg-ds-blue-900/50 text-ds-blue-300 border-ds-blue-700', Jira: 'bg-ds-sky-900/50 text-ds-sky-300 border-ds-sky-700', Local: 'bg-ds-zinc-800 text-ds-zinc-300 border-ds-zinc-600', Git: 'bg-ds-emerald-900/50 text-ds-emerald-300 border-ds-emerald-700' }
    : { Confluence: 'bg-ds-blue-100 text-ds-blue-700 border-ds-blue-300', Jira: 'bg-ds-sky-100 text-ds-sky-700 border-ds-sky-300', Local: 'bg-ds-zinc-100 text-ds-zinc-600 border-ds-zinc-300', Git: 'bg-ds-emerald-100 text-ds-emerald-700 border-ds-emerald-300' };

  const segmentActive = isDark ? 'bg-ds-zinc-700 text-ds-zinc-100' : 'bg-ds-zinc-200 text-ds-zinc-900';
  const segmentInact  = isDark ? 'text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800' : 'text-ds-zinc-500 hover:text-ds-zinc-700 hover:bg-ds-zinc-100';

  const computeBanner = (msg: { type: string; text: string } | null, isDark: boolean) => {
    if (!msg) return '';
    if (msg.type === 'success') return isDark ? 'bg-ds-emerald-950/40 border-ds-emerald-900/50 text-ds-emerald-300' : 'bg-ds-emerald-50 border-ds-emerald-200 text-ds-emerald-700';
    if (msg.type === 'empty')   return isDark ? 'bg-ds-amber-950/30 border-ds-amber-900/40 text-ds-amber-300'   : 'bg-ds-amber-50 border-ds-amber-200 text-ds-amber-700';
    return isDark ? 'bg-ds-indigo-950/30 border-ds-indigo-900/40 text-ds-indigo-300' : 'bg-ds-indigo-50 border-ds-indigo-200 text-ds-indigo-700';
  };

  // ── Data fetching ─────────────────────────────────────────────────────────

  const fetchEntityLinks = useCallback(async (silent = false) => {
    if (!projectId) return null;
    if (!silent) setIsLoading(true);
    try {
      const params = new URLSearchParams({ status: tab });
      if (minScore > 0) params.set('min_score', String(minScore / 100));
      const res = await fetch(`${API_URL}/projects/${projectId}/link-recommendations?${params}`, { credentials: 'include' });
      const data = await res.json();
      setEntityLinks(data.links || []);
      setEntityCounts(data.counts || { pending: 0, approved: 0, rejected: 0 });
      return data;
    } catch { return null; }
    finally { if (!silent) setIsLoading(false); }
  }, [projectId, tab, minScore]);

  const fetchKnowledgeLinks = useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true);
    try {
      const scoreParam = minScore > 0 ? `&min_score=${minScore / 100}` : '';
      const [listRes, pRes, aRes, rRes] = await Promise.all([
        fetch(`${API_URL}/knowledge-links?status=${tab}${scoreParam}`, { credentials: 'include' }),
        fetch(`${API_URL}/knowledge-links?status=pending${scoreParam}`, { credentials: 'include' }),
        fetch(`${API_URL}/knowledge-links?status=approved${scoreParam}`, { credentials: 'include' }),
        fetch(`${API_URL}/knowledge-links?status=rejected${scoreParam}`, { credentials: 'include' }),
      ]);
      const [list, p, a, r] = await Promise.all([listRes.json(), pRes.json(), aRes.json(), rRes.json()]);
      setKnowledgeLinks(list || []);
      const counts = { pending: (p || []).length, approved: (a || []).length, rejected: (r || []).length };
      setKnowledgeCounts(counts);
      return { links: list, counts };
    } catch { return null; }
    finally { if (!silent) setIsLoading(false); }
  }, [tab, minScore]);

  useEffect(() => {
    if (isOpen && segment === 'links') {
      (async () => {
        await Promise.all([fetchEntityLinks(), fetchKnowledgeLinks()]);
      })();
    }
  }, [isOpen, segment, fetchEntityLinks, fetchKnowledgeLinks]);

  useEffect(() => {
    if (isOpen && projectId && manualKind === 'entity' && entities.length === 0) {
      fetch(`${API_URL}/projects/${projectId}/entities`, { credentials: 'include' })
        .then(r => r.json()).then(setEntities).catch(() => {});
    }
  }, [isOpen, projectId, manualKind, entities.length]);

  useEffect(() => {
    if (!projectId || !docSearchQuery.trim()) {
      (() => setDocResults([]))();
      return;
    }
    const timeout = setTimeout(() => {
      fetch(`${API_URL}/projects/${projectId}/doc-chunks/search?q=${encodeURIComponent(docSearchQuery)}`, { credentials: 'include' })
        .then(r => r.json()).then(setDocResults).catch(() => {});
    }, 300);
    return () => clearTimeout(timeout);
  }, [projectId, docSearchQuery]);

  useEffect(() => {
    if (!projectId || !docAQuery.trim()) {
      (() => setDocAResults([]))();
      return;
    }
    const timeout = setTimeout(() => {
      fetch(`${API_URL}/projects/${projectId}/doc-chunks/search?q=${encodeURIComponent(docAQuery)}`, { credentials: 'include' })
        .then(r => r.json()).then(setDocAResults).catch(() => {});
    }, 300);
    return () => clearTimeout(timeout);
  }, [projectId, docAQuery]);

  useEffect(() => {
    if (!projectId || !docBQuery.trim()) {
      (() => setDocBResults([]))();
      return;
    }
    const timeout = setTimeout(() => {
      fetch(`${API_URL}/projects/${projectId}/doc-chunks/search?q=${encodeURIComponent(docBQuery)}`, { credentials: 'include' })
        .then(r => r.json()).then(setDocBResults).catch(() => {});
    }, 300);
    return () => clearTimeout(timeout);
  }, [projectId, docBQuery]);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  // ── Actions ───────────────────────────────────────────────────────────────

  const handleMinConfidenceChange = (value: number) => {
    const clamped = Math.min(100, Math.max(0, Math.round(value)));
    setMinConfidence(clamped);
    localStorage.setItem(MIN_CONFIDENCE_STORAGE_KEY, String(clamped));
  };

  const triggerAutoLink = async () => {
    if (isComputing) return;
    prevPendingRef.current = entityCounts.pending + knowledgeCounts.pending;
    setIsComputing(true);
    setMessage({ type: 'info', text: t('linkManagerView.computeMessages.started') });

    const confidenceParam = `min_confidence=${minConfidence}`;
    await Promise.all([
      projectId
        ? fetch(`${API_URL}/projects/${projectId}/link-recommendations/compute?${confidenceParam}`, { method: 'POST', credentials: 'include' }).catch(() => {})
        : Promise.resolve(),
      fetch(`${API_URL}/knowledge-links/compute?${confidenceParam}`, { method: 'POST', credentials: 'include' }).catch(() => {}),
    ]);

    const poll = async (attempt: number) => {
      const [entityData, knowledgeData] = await Promise.all([
        projectId ? fetchEntityLinks(true) : Promise.resolve(null),
        fetchKnowledgeLinks(true),
      ]);
      const newPending = (entityData?.counts?.pending ?? 0) + (knowledgeData?.counts?.pending ?? 0);
      if (newPending > prevPendingRef.current) {
        setMessage({ type: 'success', text: t('linkManagerView.computeMessages.newLinks', { count: newPending - prevPendingRef.current }) });
        setTab('pending');
        setIsComputing(false);
      } else if (attempt >= 2) {
        setMessage({ type: 'empty', text: t('linkManagerView.computeMessages.noneFound') });
        setIsComputing(false);
      } else {
        timerRef.current = setTimeout(() => poll(attempt + 1), 5000);
      }
    };
    timerRef.current = setTimeout(() => poll(0), 4000);
  };

  const updateLinkStatus = async (link: UnifiedLink, status: 'approved' | 'rejected') => {
    const url = link.kind === 'entity' ? `${API_URL}/entity-doc-links/${link.rawId}` : `${API_URL}/knowledge-links/${link.rawId}`;
    let ok = false;
    try {
      const res = await fetch(url, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      ok = res.ok;
    } catch { ok = false; }

    // Bisher wurde der Eintrag unabhängig vom Request-Ergebnis aus der Liste entfernt —
    // bei einem fehlgeschlagenen PATCH lief die UI dadurch aus dem Server-Stand. Jetzt
    // nur bei Erfolg lokal aktualisieren, sonst Fehler-Feedback statt stiller Diskrepanz.
    if (!ok) {
      showToast?.(t('linkManagerView.toast.updateFailed'), 'error');
      return;
    }

    if (link.kind === 'entity') {
      setEntityLinks(prev => prev.filter(l => l.id !== link.rawId));
      setEntityCounts(prev => ({ ...prev, pending: tab === 'pending' ? Math.max(0, prev.pending - 1) : prev.pending, [status]: prev[status as keyof LinkCounts] + 1 }));
    } else {
      setKnowledgeLinks(prev => prev.filter(l => l.id !== link.rawId));
      setKnowledgeCounts(prev => ({ ...prev, pending: tab === 'pending' ? Math.max(0, prev.pending - 1) : prev.pending, [status]: prev[status as keyof LinkCounts] + 1 }));
    }

    if (status === 'approved') {
      const messageKey = tab === 'rejected' ? 'reapproved' : 'approved';
      showToast?.(t(`linkManagerView.toast.${messageKey}`, { title: link.right.label }), 'success');
    }
  };

  // Bulk-approves every pending 100%-match link at once, so the user can focus
  // review effort on the less obvious (lower-confidence) candidates instead.
  const acceptAllPerfectMatches = async () => {
    if (isAcceptingAll || perfectPendingLinks.length === 0) return;
    setIsAcceptingAll(true);
    const targets = perfectPendingLinks;
    const results = await Promise.all(targets.map(async link => {
      const url = link.kind === 'entity' ? `${API_URL}/entity-doc-links/${link.rawId}` : `${API_URL}/knowledge-links/${link.rawId}`;
      try {
        const res = await fetch(url, {
          method: 'PATCH',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'approved' }),
        });
        return { link, ok: res.ok };
      } catch { return { link, ok: false }; }
    }));

    const succeeded = results.filter(r => r.ok).map(r => r.link);
    const failedCount = results.length - succeeded.length;
    const approvedEntityIds = new Set(succeeded.filter(l => l.kind === 'entity').map(l => l.rawId));
    const approvedKnowledgeIds = new Set(succeeded.filter(l => l.kind === 'knowledge').map(l => l.rawId));

    if (approvedEntityIds.size > 0) {
      setEntityLinks(prev => prev.filter(l => !approvedEntityIds.has(l.id)));
      setEntityCounts(prev => ({ ...prev, pending: Math.max(0, prev.pending - approvedEntityIds.size), approved: prev.approved + approvedEntityIds.size }));
    }
    if (approvedKnowledgeIds.size > 0) {
      setKnowledgeLinks(prev => prev.filter(l => !approvedKnowledgeIds.has(l.id)));
      setKnowledgeCounts(prev => ({ ...prev, pending: Math.max(0, prev.pending - approvedKnowledgeIds.size), approved: prev.approved + approvedKnowledgeIds.size }));
    }

    if (failedCount > 0) {
      showToast?.(t('linkManagerView.toast.acceptAllPartial', { failed: failedCount }), 'error');
    } else if (succeeded.length > 0) {
      showToast?.(t('linkManagerView.toast.acceptAllSuccess', { count: succeeded.length }), 'success');
    }
    setIsAcceptingAll(false);
  };

  // Lets the user re-check a single suggestion via LLM on demand instead of waiting
  // for the next full compute run — updates score (and reason, as `context`) to the
  // LLM's judgement in place, leaves status untouched (user still decides approve/reject).
  const llmReviewLink = async (link: UnifiedLink) => {
    if (reviewingLinkIds.has(link.id)) return;
    setReviewingLinkIds(prev => new Set(prev).add(link.id));
    const url = link.kind === 'entity'
      ? `${API_URL}/entity-doc-links/${link.rawId}/llm-review`
      : `${API_URL}/knowledge-links/${link.rawId}/llm-review`;
    try {
      const res = await fetch(url, { method: 'POST', credentials: 'include' });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        showToast?.(err?.detail || t('linkManagerView.toast.llmReviewFailed'), 'error');
        return;
      }
      const updated = await res.json();
      if (link.kind === 'entity') {
        setEntityLinks(prev => prev.map(l => l.id === link.rawId ? { ...l, score: updated.score, context: updated.context } : l));
      } else {
        setKnowledgeLinks(prev => prev.map(l => l.id === link.rawId ? { ...l, score: updated.score, context: updated.context } : l));
      }
      showToast?.(t('linkManagerView.toast.llmReviewDone', { pct: Math.round((updated.score ?? 0) * 100) }), 'success');
    } catch {
      showToast?.(t('linkManagerView.toast.llmReviewFailed'), 'error');
    } finally {
      setReviewingLinkIds(prev => { const next = new Set(prev); next.delete(link.id); return next; });
    }
  };

  const deleteLink = async (link: UnifiedLink) => {
    const url = link.kind === 'entity' ? `${API_URL}/entity-doc-links/${link.rawId}` : `${API_URL}/knowledge-links/${link.rawId}`;
    await fetch(url, { method: 'DELETE', credentials: 'include' });
    if (link.kind === 'entity') {
      setEntityLinks(prev => prev.filter(l => l.id !== link.rawId));
      setEntityCounts(prev => ({ ...prev, [tab]: Math.max(0, prev[tab as keyof LinkCounts] - 1) }));
    } else {
      setKnowledgeLinks(prev => prev.filter(l => l.id !== link.rawId));
      setKnowledgeCounts(prev => ({ ...prev, [tab]: Math.max(0, prev[tab as keyof LinkCounts] - 1) }));
    }
  };

  const resetManualForm = () => {
    setShowManualForm(false);
    setManualKind(null);
    setEntitySearchInput('');
    setSelectedEntityId(null);
    setSelectedEntityObj(null);
    setDocSearchQuery('');
    setDocResults([]);
    setSelectedDoc(null);
    setDocAQuery(''); setDocAResults([]); setSelectedDocA(null);
    setDocBQuery(''); setDocBResults([]); setSelectedDocB(null);
    setManualError('');
  };

  const submitManualLink = async () => {
    setIsSubmittingManual(true);
    setManualError('');
    try {
      if (manualKind === 'entity') {
        if (!projectId || !selectedEntityId || !selectedDoc) return;
        const res = await fetch(`${API_URL}/projects/${projectId}/link-recommendations`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entity_id: selectedEntityId, doc_title: selectedDoc.title, doc_url: selectedDoc.url || null, source_type: selectedDoc.source_type || null }),
        });
        if (!res.ok) { const err = await res.json(); setManualError(err.detail || t('linkManagerView.manualForm.genericError')); return; }
        resetManualForm();
        setEntityCounts(prev => ({ ...prev, approved: prev.approved + 1 }));
        setTab('approved');
        fetchEntityLinks();
      } else if (manualKind === 'knowledge') {
        if (!selectedDocA || !selectedDocB) return;
        const res = await fetch(`${API_URL}/knowledge-links`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_a_type: 'document', source_a_title: selectedDocA.title, source_a_url: selectedDocA.url || null, source_a_source_type: selectedDocA.source_type || null,
            source_b_type: 'document', source_b_title: selectedDocB.title, source_b_url: selectedDocB.url || null, source_b_source_type: selectedDocB.source_type || null,
            link_type: 'manual', status: 'approved',
          }),
        });
        if (!res.ok) { const err = await res.json(); setManualError(err.detail || t('linkManagerView.manualForm.genericError')); return; }
        resetManualForm();
        setKnowledgeCounts(prev => ({ ...prev, approved: prev.approved + 1 }));
        setTab('approved');
        fetchKnowledgeLinks();
      }
    } catch { setManualError(t('linkManagerView.manualForm.networkError')); }
    finally { setIsSubmittingManual(false); }
  };

  // ── Derived ───────────────────────────────────────────────────────────────

  const unifiedLinks: UnifiedLink[] = useMemo(() => {
    const fromEntity: UnifiedLink[] = entityLinks.map(l => ({
      id: `e-${l.id}`,
      kind: 'entity',
      rawId: l.id,
      left: {
        label: l.entity?.name ?? t('linkManagerView.entityFallbackName', { id: l.entity_id }),
        caption: `${l.entity?.type ?? ''}${l.entity?.file_path ? ' · ' + l.entity.file_path : ''}${l.entity?.start_line ? ':' + l.entity.start_line : ''}`,
        icon: 'code',
      },
      right: { label: l.doc_title, sourceType: l.source_type, url: l.doc_url },
      score: l.score,
      linkType: l.link_type,
      status: l.status,
      context: l.context,
    }));
    const fromKnowledge: UnifiedLink[] = knowledgeLinks.map(l => ({
      id: `k-${l.id}`,
      kind: 'knowledge',
      rawId: l.id,
      left: { label: l.source_a.title, caption: l.source_a.type, sourceType: l.source_a.source_type, url: l.source_a.url },
      right: { label: l.source_b.title, caption: l.source_b.type, sourceType: l.source_b.source_type, url: l.source_b.url },
      score: l.score,
      linkType: l.link_type,
      status: l.status,
      context: l.context,
    }));
    return [...fromEntity, ...fromKnowledge].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  }, [entityLinks, knowledgeLinks, t]);

  const filteredLinks = useMemo(() => unifiedLinks.filter(l => {
    if (kindFilter !== 'all' && l.kind !== kindFilter) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return l.left.label?.toLowerCase().includes(q) || l.right.label?.toLowerCase().includes(q) || (l.left.caption ?? '').toLowerCase().includes(q);
  }), [unifiedLinks, kindFilter, search]);

  const perfectPendingLinks = useMemo(
    () => (tab === 'pending' ? filteredLinks.filter(l => (l.score ?? 0) >= PERFECT_SCORE_THRESHOLD) : []),
    [filteredLinks, tab]
  );

  const filteredEntityEntities = useMemo(() =>
    entities.filter(e =>
      !String(e.id).startsWith('ref_') &&
      (!entitySearchInput || e.name.toLowerCase().includes(entitySearchInput.toLowerCase()) || e.file_path.toLowerCase().includes(entitySearchInput.toLowerCase()))
    ),
    [entities, entitySearchInput]
  );

  const counts: LinkCounts = {
    pending: entityCounts.pending + knowledgeCounts.pending,
    approved: entityCounts.approved + knowledgeCounts.approved,
    rejected: entityCounts.rejected + knowledgeCounts.rejected,
  };

  if (!isOpen) return null;

  // ── Doc picker sub-render (reused for entity-doc and doc-doc forms) ────────

  const renderDocPicker = (query: string, setQuery: (v: string) => void, results: any[], selected: any | null, setSelected: (v: any | null) => void) => (
    selected ? (
      <div className={cn('flex items-center gap-2 px-3 py-2 rounded-md border', isDark ? 'bg-ds-zinc-800 border-ds-zinc-600' : 'bg-ds-white border-ds-zinc-300')}>
        {selected.source_type && (
          <span className={cn('text-[10px] px-1.5 py-0.5 rounded border shrink-0',
            sourceColors[selected.source_type] ?? (isDark ? 'bg-ds-zinc-700 text-ds-zinc-400 border-ds-zinc-600' : 'bg-ds-zinc-100 text-ds-zinc-500 border-ds-zinc-300'))}>
            {selected.source_type}
          </span>
        )}
        <p className={cn('text-xs font-medium flex-1 truncate', cardLabel)}>{selected.title}</p>
        <button onClick={() => { setSelected(null); setQuery(''); }}
          className={cn('shrink-0 p-0.5', isDark ? 'text-ds-zinc-600 hover:text-ds-zinc-400' : 'text-ds-zinc-400 hover:text-ds-zinc-600')}>
          <X className="w-3 h-3" />
        </button>
      </div>
    ) : (
      <div className="relative">
        <input type="text" placeholder={t('linkManagerView.manualForm.docSearchPlaceholder')}
          value={query} onChange={e => { setQuery(e.target.value); setSelected(null); }}
          className={cn('w-full text-xs rounded-md px-2.5 py-1.5 border focus:outline-none', inputCls)} />
        {results.length > 0 && (
          <div className={cn('absolute top-full mt-1 left-0 right-0 border rounded-md shadow-lg z-20 max-h-44 overflow-y-auto', dropdownBg)}>
            {results.map((doc: any, i: number) => (
              <button key={i}
                onClick={() => { setSelected(doc); setQuery(doc.title); }}
                className={cn('w-full text-left px-3 py-2 text-xs flex items-center gap-2 border-b last:border-0', dropItem, divider)}>
                {doc.source_type && (
                  <span className={cn('text-[10px] px-1.5 py-0.5 rounded border shrink-0',
                    sourceColors[doc.source_type] ?? (isDark ? 'bg-ds-zinc-700 text-ds-zinc-400 border-ds-zinc-600' : 'bg-ds-zinc-100 text-ds-zinc-500 border-ds-zinc-300'))}>
                    {doc.source_type}
                  </span>
                )}
                <span className="truncate">{doc.title}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    )
  );

  const renderSide = (side: UnifiedSide) => (
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 mb-1">
        {side.icon === 'code' && <FileCode className={cn('w-3.5 h-3.5 shrink-0', subText)} />}
        {side.sourceType && (
          <span className={cn('text-[10px] px-1.5 py-0.5 rounded border shrink-0',
            sourceColors[side.sourceType] ?? (isDark ? 'bg-ds-zinc-700 text-ds-zinc-400 border-ds-zinc-600' : 'bg-ds-zinc-100 text-ds-zinc-500 border-ds-zinc-300'))}>
            {side.sourceType}
          </span>
        )}
        <span className={cn('text-xs font-medium truncate', cardLabel)}>{side.label}</span>
        {side.url && (
          <a href={side.url} target="_blank" rel="noopener noreferrer"
            className={cn('shrink-0', isDark ? 'text-ds-zinc-600 hover:text-ds-zinc-400' : 'text-ds-zinc-400 hover:text-ds-zinc-600')}>
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
      {side.caption && <p className={cn('text-[11px] truncate', side.icon === 'code' ? 'pl-5' : '', cardMuted)}>{side.caption}</p>}
    </div>
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className={cn('fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm', overlay)}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.15 }}
        className={cn('border rounded-lg shadow-2xl w-full max-w-5xl max-h-[92vh] flex flex-col mx-4', modalBg)}
      >
        {/* ── Header ── */}
        <div className={cn('flex flex-col sm:flex-row items-start sm:items-center justify-between px-4 sm:px-6 py-4 border-b shrink-0 gap-3', divider)}>
          <div className="flex items-center gap-3">
            <Network className={cn('w-5 h-5 shrink-0', iconColor)} />
            <h2 className={cn('text-sm font-semibold shrink-0', titleText)}>{t('linkManagerView.title')}</h2>

            {/* Project selector */}
            {onSelectProject && (
              <Select
                value={selectedProject ? String(selectedProject.id) : '__none__'}
                onValueChange={(val) => {
                  if (val === '__none__') { onSelectProject(null); return; }
                  const project = projects.find((p: any) => String(p.id) === val);
                  if (project) onSelectProject(project);
                }}
              >
                <SelectTrigger className={cn(
                  'h-7 max-w-[160px] text-[11px] sm:text-xs border focus:ring-0 shrink-0 rounded-md font-medium px-2 gap-1',
                  isDark ? 'bg-ds-zinc-800/80 border-ds-zinc-700 text-ds-zinc-300 hover:bg-ds-zinc-800' : 'bg-ds-zinc-100 border-ds-zinc-200 text-ds-zinc-700 hover:bg-ds-zinc-200/60'
                )}>
                  <FolderKanban className="w-3.5 h-3.5 shrink-0 opacity-70" />
                  <SelectValue placeholder={t('linkManagerView.selectProjectPlaceholder')} />
                </SelectTrigger>
                <SelectContent className={isDark ? 'bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200' : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-800'}>
                  <SelectItem value="__none__" className="text-xs">{t('linkManagerView.generalContextOption')}</SelectItem>
                  {projects.map((p: any) => (
                    <SelectItem key={p.id} value={String(p.id)} className="text-xs">{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <div className="flex items-center flex-wrap gap-2 w-full sm:w-auto">

            {/* Model selector */}
            {setActiveProfileId && llmProfiles.length > 0 && (
              <Select
                value={activeProfileId}
                onValueChange={(val) => {
                  setActiveProfileId(val);
                  localStorage.setItem('doctus-active-profile-id', val);
                  const selectedProf = llmProfiles.find((p: any) => p.id === val);
                  if (selectedProf && showToast) {
                    showToast(t('chatView.modelSwitchedToast', { name: selectedProf.name }), 'success');
                  }
                }}
              >
                <SelectTrigger className={cn(
                  'h-7 max-w-[150px] text-[11px] sm:text-xs border focus:ring-0 shrink-0 rounded-md font-medium px-2 gap-1',
                  isDark ? 'bg-ds-zinc-800/80 border-ds-zinc-700 text-ds-zinc-300 hover:bg-ds-zinc-800' : 'bg-ds-zinc-100 border-ds-zinc-200 text-ds-zinc-700 hover:bg-ds-zinc-200/60'
                )}>
                  <Cpu className="w-3.5 h-3.5 shrink-0 text-ds-indigo-500" />
                  <SelectValue placeholder={t('chatView.selectModel')} />
                </SelectTrigger>
                <SelectContent className={isDark ? 'bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200' : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-800'}>
                  {llmProfiles.map((prof: any) => (
                    <SelectItem key={prof.id} value={prof.id} className="text-xs">{prof.name} ({prof.model})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}

            {/* Segment switcher */}
            <div className={cn('flex rounded-md border p-0.5 gap-0.5', isDark ? 'border-ds-zinc-700 bg-ds-zinc-800/50' : 'border-ds-zinc-200 bg-ds-zinc-100')}>
              <button
                onClick={() => setSegment('links')}
                className={cn('flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded transition-colors', segment === 'links' ? segmentActive : segmentInact)}
              >
                <Link2 className="w-3 h-3" />
                {t('linkManagerView.segments.links')}
              </button>
              {isAdmin && (
                <button
                  onClick={() => setSegment('topics')}
                  className={cn('flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded transition-colors', segment === 'topics' ? segmentActive : segmentInact)}
                >
                  <Tag className="w-3 h-3" />
                  {t('linkManagerView.segments.topics')}
                </button>
              )}
            </div>

            {/* Segment-specific actions */}
            {segment === 'links' && (
              <>
                <div
                  className={cn('flex items-center gap-1 px-1.5 py-1 rounded-md border text-[10px] sm:text-xs', isDark ? 'border-ds-zinc-700 text-ds-zinc-400' : 'border-ds-zinc-300 text-ds-zinc-500')}
                  title={t('linkManagerView.minConfidenceTooltip')}
                >
                  <Percent className="w-3 h-3 shrink-0 opacity-70" />
                  <input
                    type="number" min={0} max={100} step={5}
                    value={minConfidence}
                    onChange={e => handleMinConfidenceChange(Number(e.target.value))}
                    disabled={isComputing}
                    aria-label={t('linkManagerView.minConfidenceLabel')}
                    className={cn('w-8 bg-transparent text-right focus:outline-none disabled:opacity-50', isDark ? 'text-ds-zinc-200' : 'text-ds-zinc-800')}
                  />
                  <span className="hidden xs:inline">%</span>
                </div>
                <button onClick={triggerAutoLink} disabled={isComputing}
                  className={cn('text-[10px] sm:text-xs flex items-center gap-1.5 px-2 py-1.5 disabled:opacity-40', ghostBtn)}>
                  <RefreshCw className={cn('w-3.5 h-3.5', isComputing && 'animate-spin')} />
                  <span className="hidden xs:inline">{isComputing ? t('linkManagerView.computingLabel') : t('linkManagerView.autoLinkLabel')}</span>
                </button>
                <button onClick={() => setShowManualForm(v => !v)} disabled={!projectId} title={!projectId ? t('linkManagerView.noProjectSelected') : undefined}
                  className={cn('text-[10px] sm:text-xs flex items-center gap-1.5 px-2 py-1.5 disabled:opacity-40', accentBtn)}>
                  <Plus className="w-3.5 h-3.5" />
                  <span className="hidden xs:inline">{t('linkManagerView.manualLabel')}</span>
                </button>
                <button onClick={() => setViewMode('chat')}
                  className={cn('text-[10px] sm:text-xs flex items-center gap-1.5 px-2 py-1.5', viewMode === 'chat' ? tabActive : ghostBtn)}>
                  <MessageSquare className="w-3.5 h-3.5" />
                  <span className="hidden xs:inline">{t('linkManagerView.chatLabel')}</span>
                </button>
                <button onClick={() => setViewMode('list')}
                  className={cn('text-[10px] sm:text-xs flex items-center gap-1.5 px-2 py-1.5', viewMode === 'list' ? tabActive : ghostBtn)}>
                  <LayoutList className="w-3.5 h-3.5" />
                  <span className="hidden xs:inline">{t('linkManagerView.overviewLabel')}</span>
                </button>
              </>
            )}

            <div className={cn('hidden sm:block w-px h-4 mx-1', divider)} />
            <button onClick={onClose}
              className={cn('ml-auto p-1.5 rounded-md transition-colors', isDark ? 'text-ds-zinc-500 hover:text-ds-zinc-200 hover:bg-ds-zinc-800' : 'text-ds-zinc-400 hover:text-ds-zinc-700 hover:bg-ds-zinc-100')}>
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* ── Topics segment (admin-only, mirrors backend require_admin on /topics) ── */}
        {segment === 'topics' && isAdmin && <TopicsPanel theme={theme} />}

        {/* ── Links segment ── */}
        {segment === 'links' && (
          viewMode === 'chat' ? (
            <div className="flex-1 min-h-0 overflow-hidden">
              <LinkChatView theme={theme} selectedProject={selectedProject} activeProfile={activeProfile} />
            </div>
          ) : (
            <>
              {/* Compute banner */}
              <AnimatePresence>
                {message && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden shrink-0">
                    <div className={cn('flex items-start gap-2.5 px-6 py-3 text-xs border-b', computeBanner(message, isDark))}>
                      {message.type === 'success' ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" /> : <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
                      <span className="leading-relaxed">{message.text}</span>
                      <button onClick={() => setMessage(null)} className="ml-auto shrink-0 opacity-60 hover:opacity-100"><X className="w-3 h-3" /></button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Tabs + kind filter + search row */}
              <div className={cn('flex flex-col gap-3 px-4 sm:px-6 py-3 border-b shrink-0', divider)}>
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div className="flex gap-1 overflow-x-auto w-full sm:w-auto no-scrollbar pb-1 sm:pb-0">
                    {(['pending', 'approved', 'rejected'] as const).map(tabOption => (
                      <button key={tabOption} onClick={() => setTab(tabOption)}
                        className={cn('px-3 py-1.5 rounded-md text-[11px] sm:text-xs font-medium transition-colors shrink-0', tab === tabOption ? tabActive : tabInact)}>
                        {t(`linkManagerView.tabLabels.${tabOption}`)}
                        <span className={cn('ml-1.5 px-1.5 py-0.5 rounded text-[9px] sm:text-[10px]', tab === tabOption ? tabBadgeA : tabBadgeI)}>
                          {counts[tabOption]}
                        </span>
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2 w-full sm:w-auto">
                    <div className="relative flex-1 sm:flex-initial">
                      <Search className={cn('absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3', subText)} />
                      <input type="text" placeholder={t('linkManagerView.searchPlaceholder')} value={search} onChange={e => setSearch(e.target.value)}
                        className={cn('text-[11px] sm:text-xs rounded-md pl-7 pr-3 py-1.5 w-full sm:w-32 md:w-40 border focus:outline-none', inputCls)} />
                    </div>
                    {tab === 'pending' && (
                      <select value={minScore} onChange={e => setMinScore(Number(e.target.value))}
                        className={cn('text-[11px] sm:text-xs rounded-md px-1.5 py-1.5 border focus:outline-none', selectCls)}>
                        <option value={0}>{t('linkManagerView.scoreFilter.all')}</option>
                        <option value={60}>{t('linkManagerView.scoreFilter.min60')}</option>
                        <option value={80}>{t('linkManagerView.scoreFilter.min80')}</option>
                      </select>
                    )}
                    {tab === 'pending' && perfectPendingLinks.length > 0 && (
                      <button onClick={acceptAllPerfectMatches} disabled={isAcceptingAll}
                        title={t('linkManagerView.acceptAllTooltip')}
                        className={cn('text-[10px] sm:text-xs flex items-center gap-1.5 px-2 py-1.5 shrink-0 disabled:opacity-40', accentBtn)}>
                        {isAcceptingAll ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                        <span className="hidden xs:inline">{t('linkManagerView.acceptAllLabel')}</span>
                        <span className={cn('px-1 rounded text-[9px] sm:text-[10px]', tabBadgeA)}>{perfectPendingLinks.length}</span>
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  {(['all', 'entity', 'knowledge'] as const).map(kind => (
                    <button key={kind} onClick={() => setKindFilter(kind)}
                      className={cn('px-2.5 py-1 rounded-sm text-[10px] sm:text-[11px] font-medium border transition-colors', kindFilter === kind ? kindChipActive : kindChipInact)}>
                      {t(`linkManagerView.kindFilter.${kind}`)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Manual link form */}
              <AnimatePresence>
                {showManualForm && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden shrink-0">
                    <div className={cn('px-6 py-4 border-b', manualBg, divider)}>
                      <div className="flex items-start justify-between mb-1">
                        <p className={cn('text-xs font-semibold flex items-center gap-2', manualTitle)}>
                          {manualKind && (
                            <button onClick={() => setManualKind(null)} className="shrink-0"><ArrowLeft className="w-3.5 h-3.5" /></button>
                          )}
                          {t('linkManagerView.manualForm.title')}
                        </p>
                        <button onClick={resetManualForm} className={cn('p-0.5 rounded transition-colors', isDark ? 'text-ds-zinc-600 hover:text-ds-zinc-400' : 'text-ds-zinc-400 hover:text-ds-zinc-600')}>
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      {!manualKind ? (
                        <>
                          <p className={cn('text-[11px] mb-3', manualDesc)}>{t('linkManagerView.manualForm.kindQuestion')}</p>
                          <div className="flex gap-2">
                            <button onClick={() => setManualKind('entity')} disabled={!projectId}
                              className={cn('flex-1 text-xs px-3 py-2.5 rounded-md border transition-colors disabled:opacity-40 flex items-center gap-2 justify-center', isDark ? 'bg-ds-zinc-800 border-ds-zinc-600 text-ds-zinc-200 hover:border-ds-indigo-600' : 'bg-ds-white border-ds-zinc-300 text-ds-zinc-800 hover:border-ds-indigo-400')}>
                              <FileCode className="w-3.5 h-3.5" />{t('linkManagerView.manualForm.kindEntityOption')}
                            </button>
                            <button onClick={() => setManualKind('knowledge')} disabled={!projectId}
                              className={cn('flex-1 text-xs px-3 py-2.5 rounded-md border transition-colors disabled:opacity-40 flex items-center gap-2 justify-center', isDark ? 'bg-ds-zinc-800 border-ds-zinc-600 text-ds-zinc-200 hover:border-ds-indigo-600' : 'bg-ds-white border-ds-zinc-300 text-ds-zinc-800 hover:border-ds-indigo-400')}>
                              <BookOpen className="w-3.5 h-3.5" />{t('linkManagerView.manualForm.kindKnowledgeOption')}
                            </button>
                          </div>
                        </>
                      ) : manualKind === 'entity' ? (
                        <>
                          <p className={cn('text-[11px] mb-4', manualDesc)}>{t('linkManagerView.manualForm.description')}</p>
                          <div className="flex items-start gap-4">
                            {/* Entity picker */}
                            <div className="flex-1 min-w-0">
                              <label className={cn('text-[11px] font-medium block mb-1.5', subText)}>{t('linkManagerView.manualForm.step1Label')}</label>
                              {selectedEntityObj ? (
                                <div className={cn('flex items-center gap-2 px-3 py-2 rounded-md border', isDark ? 'bg-ds-zinc-800 border-ds-zinc-600' : 'bg-ds-white border-ds-zinc-300')}>
                                  <FileCode className={cn('w-3.5 h-3.5 shrink-0', subText)} />
                                  <div className="flex-1 min-w-0">
                                    <p className={cn('text-xs font-medium truncate', cardLabel)}>{selectedEntityObj.name}</p>
                                    <p className={cn('text-[10px] truncate', subText)}>{selectedEntityObj.file_path}</p>
                                  </div>
                                  <button onClick={() => { setSelectedEntityId(null); setSelectedEntityObj(null); setEntitySearchInput(''); }}
                                    className={cn('shrink-0 p-0.5', isDark ? 'text-ds-zinc-600 hover:text-ds-zinc-400' : 'text-ds-zinc-400 hover:text-ds-zinc-600')}>
                                    <X className="w-3 h-3" />
                                  </button>
                                </div>
                              ) : (
                                <div className="relative">
                                  <input type="text" placeholder={t('linkManagerView.manualForm.entitySearchPlaceholder')}
                                    value={entitySearchInput} onChange={e => setEntitySearchInput(e.target.value)}
                                    className={cn('w-full text-xs rounded-md px-2.5 py-1.5 border focus:outline-none', inputCls)} />
                                  {entitySearchInput && filteredEntityEntities.length > 0 && (
                                    <div className={cn('absolute top-full mt-1 left-0 right-0 border rounded-md shadow-lg z-20 max-h-44 overflow-y-auto', dropdownBg)}>
                                      {filteredEntityEntities.slice(0, 30).map(ent => (
                                        <button key={ent.id}
                                          onClick={() => { setSelectedEntityId(parseEntityId(ent.id)); setSelectedEntityObj(ent); setEntitySearchInput(''); }}
                                          className={cn('w-full text-left px-3 py-2 text-xs flex items-center gap-2 border-b last:border-0', dropItem, divider)}>
                                          <span className={cn('text-[10px] px-1 py-0.5 rounded shrink-0', typeTag)}>{ent.type}</span>
                                          <span className="font-medium truncate">{ent.name}</span>
                                          <span className={cn('text-[10px] truncate ml-auto', subText)}>{ent.file_path}</span>
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                            <div className={cn('shrink-0 mt-7 text-sm font-light select-none', arrowColor)}>→</div>
                            {/* Doc picker */}
                            <div className="flex-1 min-w-0">
                              <label className={cn('text-[11px] font-medium block mb-1.5', subText)}>{t('linkManagerView.manualForm.step2Label')}</label>
                              {renderDocPicker(docSearchQuery, setDocSearchQuery, docResults, selectedDoc, setSelectedDoc)}
                            </div>
                          </div>
                        </>
                      ) : (
                        <>
                          <p className={cn('text-[11px] mb-4', manualDesc)}>{t('linkManagerView.manualForm.descriptionKnowledge')}</p>
                          <div className="flex items-start gap-4">
                            <div className="flex-1 min-w-0">
                              <label className={cn('text-[11px] font-medium block mb-1.5', subText)}>{t('linkManagerView.manualForm.stepALabel')}</label>
                              {renderDocPicker(docAQuery, setDocAQuery, docAResults, selectedDocA, setSelectedDocA)}
                            </div>
                            <div className={cn('shrink-0 mt-7 text-sm font-light select-none', arrowColor)}>↔</div>
                            <div className="flex-1 min-w-0">
                              <label className={cn('text-[11px] font-medium block mb-1.5', subText)}>{t('linkManagerView.manualForm.stepBLabel')}</label>
                              {renderDocPicker(docBQuery, setDocBQuery, docBResults, selectedDocB, setSelectedDocB)}
                            </div>
                          </div>
                        </>
                      )}

                      {manualError && (
                        <p className="text-xs text-ds-red-500 mt-3 flex items-center gap-1">
                          <AlertCircle className="w-3 h-3" />{manualError}
                        </p>
                      )}
                      {manualKind && (
                        <div className="flex gap-2 mt-4">
                          <button onClick={submitManualLink}
                            disabled={(manualKind === 'entity' ? (!selectedEntityId || !selectedDoc) : (!selectedDocA || !selectedDocB)) || isSubmittingManual}
                            className={cn('text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors disabled:opacity-40', 'bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-500')}>
                            {isSubmittingManual ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                            {t('linkManagerView.manualForm.saveButton')}
                          </button>
                          <button onClick={resetManualForm}
                            className={cn('text-xs px-3 py-1.5 rounded-md transition-colors', ghostBtn)}>
                            {t('common.cancel')}
                          </button>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Unified link list */}
              <ScrollArea className="flex-1 min-h-0">
                {isLoading ? (
                  <div className="flex items-center justify-center py-20">
                    <Loader2 className={cn('w-5 h-5 animate-spin', subText)} />
                  </div>
                ) : filteredLinks.length === 0 ? (
                  <div className={cn('flex flex-col items-center justify-center py-20', emptyText)}>
                    <Link2 className="w-8 h-8 mb-3 opacity-40" />
                    <p className="text-sm">{t(`linkManagerView.emptyLinks.${tab}`)}</p>
                    {tab === 'pending' && (
                      <p className={cn('text-xs mt-1', isDark ? 'text-ds-zinc-700' : 'text-ds-zinc-300')}>
                        {t('linkManagerView.noResultsAutoLinkHint', { action: t('linkManagerView.autoLinkLabel') })}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="p-4 space-y-2">
                    {filteredLinks.map(link => (
                      <div key={link.id} className={cn('border rounded-lg px-4 py-3 flex items-start gap-4 transition-colors', cardCls)}>
                        {renderSide(link.left)}
                        <div className={cn('shrink-0 pt-0.5 text-xs select-none', arrowColor)}>{link.kind === 'entity' ? '→' : '↔'}</div>
                        <div className="flex-1 min-w-0">
                          {renderSide(link.right)}
                          <div className="flex items-center gap-2 mt-1">
                            <ScoreBadge score={link.score} isDark={isDark} />
                            {link.linkType !== 'semantic' && <span className={cn('text-[10px] px-1 rounded', cardMuted)}>{link.linkType}</span>}
                            {link.context && (
                              <span className={cn('text-[10px] truncate max-w-[200px]', cardMuted)} title={link.context}>{link.context}</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0 pt-0.5">
                          {tab === 'pending' && (
                            <>
                              <button onClick={() => llmReviewLink(link)} disabled={reviewingLinkIds.has(link.id)} title={t('linkManagerView.actions.llmReview')}
                                className={cn('p-1.5 rounded-md transition-colors disabled:opacity-40', ghostBtn)}>
                                {reviewingLinkIds.has(link.id) ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                              </button>
                              <button onClick={() => updateLinkStatus(link, 'approved')} title={t('linkManagerView.actions.approve')}
                                className={cn('p-1.5 rounded-md transition-colors', actionApprove)}><Check className="w-3.5 h-3.5" /></button>
                              <button onClick={() => updateLinkStatus(link, 'rejected')} title={t('linkManagerView.actions.reject')}
                                className={cn('p-1.5 rounded-md transition-colors', actionReject)}><Ban className="w-3.5 h-3.5" /></button>
                            </>
                          )}
                          {tab === 'approved' && (
                            <button onClick={() => deleteLink(link)} title={t('linkManagerView.actions.remove')}
                              className={cn('p-1.5 rounded-md transition-colors', actionDel)}><X className="w-3.5 h-3.5" /></button>
                          )}
                          {tab === 'rejected' && (
                            <>
                              <button onClick={() => updateLinkStatus(link, 'approved')} title={t('linkManagerView.actions.reapprove')}
                                className={cn('p-1.5 rounded-md transition-colors', actionApprove)}><Check className="w-3.5 h-3.5" /></button>
                              <button onClick={() => deleteLink(link)} title={t('linkManagerView.actions.delete')}
                                className={cn('p-1.5 rounded-md transition-colors', actionDel)}><X className="w-3.5 h-3.5" /></button>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </>
          )
        )}
      </motion.div>
    </div>
  );
}
