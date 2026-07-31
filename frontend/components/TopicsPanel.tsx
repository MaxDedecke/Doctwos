"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus, X, Check, Pencil, Trash2, GitBranch, FileCode,
  FileText, Database, Search, Loader2, AlertCircle, Tag,
  ChevronRight,
} from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Topic {
  id: number;
  name: string;
  description: string | null;
  color: string;
  node_count: number;
  created_at: string | null;
}

interface TopicNode {
  id: number;
  topic_id: number;
  node_type: string;
  node_id: number;
  node_label: string;
  node_url: string | null;
  node_meta: Record<string, unknown> | null;
}

interface SearchResult {
  node_type: string;
  node_id: number;
  node_label: string;
  node_url: string | null;
  node_meta: Record<string, unknown> | null;
}

interface TopicsPanelProps {
  theme: string;
}

// ── Color palette ─────────────────────────────────────────────────────────────

const COLORS = ['indigo', 'emerald', 'amber', 'rose', 'violet', 'sky', 'orange'] as const;

type Color = typeof COLORS[number];

const COLOR_MAP: Record<Color, { dot: string; lightBg: string; darkBg: string }> = {
  indigo:  { dot: 'bg-ds-indigo-500',  lightBg: 'bg-ds-indigo-100 text-ds-indigo-700',  darkBg: 'bg-ds-indigo-900/40 text-ds-indigo-300'  },
  emerald: { dot: 'bg-ds-emerald-500', lightBg: 'bg-ds-emerald-100 text-ds-emerald-700', darkBg: 'bg-ds-emerald-900/40 text-ds-emerald-300' },
  amber:   { dot: 'bg-ds-amber-500',   lightBg: 'bg-ds-amber-100 text-ds-amber-700',    darkBg: 'bg-ds-amber-900/40 text-ds-amber-300'    },
  rose:    { dot: 'bg-ds-rose-500',    lightBg: 'bg-ds-rose-100 text-ds-rose-700',      darkBg: 'bg-ds-rose-900/40 text-ds-rose-300'      },
  violet:  { dot: 'bg-ds-violet-500',  lightBg: 'bg-ds-violet-100 text-ds-violet-700',  darkBg: 'bg-ds-violet-900/40 text-ds-violet-300'  },
  sky:     { dot: 'bg-ds-sky-500',     lightBg: 'bg-ds-sky-100 text-ds-sky-700',        darkBg: 'bg-ds-sky-900/40 text-ds-sky-300'        },
  orange:  { dot: 'bg-ds-orange-500',  lightBg: 'bg-ds-orange-100 text-ds-orange-700',  darkBg: 'bg-ds-orange-900/40 text-ds-orange-300'  },
};

function getColor(color: string, isDark: boolean) {
  const c = COLOR_MAP[color as Color] ?? COLOR_MAP.indigo;
  return { dot: c.dot, badge: isDark ? c.darkBg : c.lightBg };
}

// ── Node type config ──────────────────────────────────────────────────────────

const NODE_TYPES = [
  { key: 'project',          labelKey: 'topicsPanel.nodeTypes.project',       Icon: GitBranch, iconCls: 'text-ds-sky-500'    },
  { key: 'entity',           labelKey: 'topicsPanel.nodeTypes.entity',           Icon: FileCode,  iconCls: 'text-ds-indigo-400' },
  { key: 'document',         labelKey: 'topicsPanel.nodeTypes.document',         Icon: FileText,  iconCls: 'text-ds-emerald-500' },
  { key: 'knowledge_source', labelKey: 'topicsPanel.nodeTypes.knowledgeSource',  Icon: Database,  iconCls: 'text-ds-amber-500'  },
] as const;

type NodeTypeKey = typeof NODE_TYPES[number]['key'];

// ── Component ─────────────────────────────────────────────────────────────────

export function TopicsPanel({ theme }: TopicsPanelProps) {
  const isDark = theme === 'dark';
  const { t } = useLanguage();

  // Topic list
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicSearch, setTopicSearch] = useState('');
  const [selectedTopicId, setSelectedTopicId] = useState<number | null>(null);
  const [isLoadingTopics, setIsLoadingTopics] = useState(false);

  // Topic nodes
  const [nodes, setNodes] = useState<TopicNode[]>([]);
  const [isLoadingNodes, setIsLoadingNodes] = useState(false);

  // Create topic form
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newColor, setNewColor] = useState<Color>('indigo');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  // Edit topic inline
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editColor, setEditColor] = useState<Color>('indigo');
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // Add node form
  const [showAddNode, setShowAddNode] = useState(false);
  const [addNodeType, setAddNodeType] = useState<NodeTypeKey>('project');
  const [addNodeSearch, setAddNodeSearch] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [addNodeError, setAddNodeError] = useState('');

  // ── Theme tokens ──────────────────────────────────────────────────────────

  const panelBg      = isDark ? 'bg-ds-zinc-900'       : 'bg-ds-white';
  const sidebarBg    = isDark ? 'bg-ds-zinc-900'       : 'bg-ds-zinc-50';
  const divider      = isDark ? 'border-ds-zinc-800'   : 'border-ds-zinc-200';
  const titleText    = isDark ? 'text-ds-zinc-100'     : 'text-ds-zinc-900';
  const subText      = isDark ? 'text-ds-zinc-500'     : 'text-ds-zinc-500';
  const cardCls      = isDark
    ? 'bg-ds-zinc-800/50 border-ds-zinc-700/60 hover:border-ds-zinc-500'
    : 'bg-ds-white border-ds-zinc-200 hover:border-ds-zinc-300';
  const inputCls     = isDark
    ? 'bg-ds-zinc-800 border-ds-zinc-700 text-ds-zinc-200 placeholder:text-ds-zinc-600 focus:border-ds-zinc-500'
    : 'bg-ds-white border-ds-zinc-300 text-ds-zinc-900 placeholder:text-ds-zinc-400 focus:border-ds-zinc-400';
  const ghostBtn     = isDark
    ? 'text-ds-zinc-400 hover:text-ds-zinc-100 hover:bg-ds-zinc-800 rounded-md transition-colors'
    : 'text-ds-zinc-500 hover:text-ds-zinc-900 hover:bg-ds-zinc-100 rounded-md transition-colors';
  const activeItem   = isDark ? 'bg-ds-zinc-800 border-ds-zinc-600' : 'bg-ds-zinc-100 border-ds-zinc-300';
  const inactItem    = isDark
    ? 'border-transparent hover:bg-ds-zinc-800/60'
    : 'border-transparent hover:bg-ds-zinc-100';
  const dropdownBg   = isDark ? 'bg-ds-zinc-800 border-ds-zinc-700 shadow-ds-black/40' : 'bg-ds-white border-ds-zinc-200 shadow-ds-zinc-200/60';
  const dropItem     = isDark ? 'text-ds-zinc-300 hover:bg-ds-zinc-700' : 'text-ds-zinc-700 hover:bg-ds-zinc-100';
  const emptyText    = isDark ? 'text-ds-zinc-600' : 'text-ds-zinc-400';
  const sectionLabel = isDark ? 'text-ds-zinc-500' : 'text-ds-zinc-400';
  const chipCls      = isDark
    ? 'bg-ds-zinc-800 border-ds-zinc-700 text-ds-zinc-200 hover:border-ds-zinc-500'
    : 'bg-ds-zinc-50 border-ds-zinc-200 text-ds-zinc-700 hover:border-ds-zinc-300';

  // ── Data fetching ─────────────────────────────────────────────────────────

  const fetchTopics = useCallback(async () => {
    setIsLoadingTopics(true);
    try {
      const res = await fetch(`${API_URL}/topics`, { credentials: 'include' });
      const data = await res.json();
      setTopics(data);
    } catch { /* silent */ }
    finally { setIsLoadingTopics(false); }
  }, []);

  const fetchNodes = useCallback(async (topicId: number) => {
    setIsLoadingNodes(true);
    try {
      const res = await fetch(`${API_URL}/topics/${topicId}/nodes`, { credentials: 'include' });
      setNodes(await res.json());
    } catch { /* silent */ }
    finally { setIsLoadingNodes(false); }
  }, []);

  useEffect(() => {
    (async () => {
      await fetchTopics();
    })();
  }, [fetchTopics]);

  useEffect(() => {
    (async () => {
      if (selectedTopicId !== null) await fetchNodes(selectedTopicId);
      else setNodes([]);
    })();
  }, [selectedTopicId, fetchNodes]);

  // Node search with debounce
  useEffect(() => {
    if (!showAddNode) {
      (() => setSearchResults([]))();
      return;
    }
    const t = setTimeout(async () => {
      if (!addNodeSearch.trim() && addNodeType !== 'project' && addNodeType !== 'knowledge_source') {
        setSearchResults([]);
        return;
      }
      setIsSearching(true);
      try {
        const params = new URLSearchParams({ q: addNodeSearch, types: addNodeType });
        const res = await fetch(`${API_URL}/topics/search-nodes?${params}`, { credentials: 'include' });
        setSearchResults(await res.json());
      } catch { /* silent */ }
      finally { setIsSearching(false); }
    }, 250);
    return () => clearTimeout(t);
  }, [addNodeSearch, addNodeType, showAddNode]);

  // Trigger search immediately when type changes or panel opens — done
  // during render (guarded by state comparisons) rather than in an effect.
  const [prevAddNodeType, setPrevAddNodeType] = useState(addNodeType);
  const [prevShowAddNode, setPrevShowAddNode] = useState(showAddNode);
  if (addNodeType !== prevAddNodeType || showAddNode !== prevShowAddNode) {
    setPrevAddNodeType(addNodeType);
    setPrevShowAddNode(showAddNode);
    if (showAddNode) setAddNodeSearch('');
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  const createTopic = async () => {
    if (!newName.trim()) { setCreateError(t('topicsPanel.errors.nameRequired')); return; }
    setIsCreating(true);
    setCreateError('');
    try {
      const res = await fetch(`${API_URL}/topics`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() || null, color: newColor }),
      });
      if (!res.ok) { setCreateError(t('topicsPanel.errors.createFailed')); return; }
      const created: Topic = await res.json();
      setTopics(prev => [created, ...prev]);
      setSelectedTopicId(created.id);
      setShowCreate(false);
      setNewName(''); setNewDesc(''); setNewColor('indigo');
    } catch { setCreateError(t('topicsPanel.errors.networkError')); }
    finally { setIsCreating(false); }
  };

  const deleteTopic = async (topicId: number) => {
    await fetch(`${API_URL}/topics/${topicId}`, { method: 'DELETE', credentials: 'include' });
    setTopics(prev => prev.filter(t => t.id !== topicId));
    if (selectedTopicId === topicId) setSelectedTopicId(null);
  };

  const startEdit = (topic: Topic) => {
    setEditName(topic.name);
    setEditDesc(topic.description ?? '');
    setEditColor((topic.color as Color) ?? 'indigo');
    setIsEditing(true);
  };

  const saveEdit = async () => {
    if (!selectedTopicId || !editName.trim()) return;
    setIsSavingEdit(true);
    try {
      const res = await fetch(`${API_URL}/topics/${selectedTopicId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: editName.trim(), description: editDesc.trim() || null, color: editColor }),
      });
      const updated: Topic = await res.json();
      setTopics(prev => prev.map(t => t.id === selectedTopicId ? updated : t));
      setIsEditing(false);
    } catch { /* silent */ }
    finally { setIsSavingEdit(false); }
  };

  const attachNode = async (result: SearchResult) => {
    if (!selectedTopicId) return;
    setAddNodeError('');
    try {
      const res = await fetch(`${API_URL}/topics/${selectedTopicId}/nodes`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_type: result.node_type,
          node_id: result.node_id,
          node_label: result.node_label,
          node_url: result.node_url,
          node_meta: result.node_meta,
        }),
      });
      if (res.status === 409) { setAddNodeError(t('topicsPanel.errors.alreadyLinked')); return; }
      if (!res.ok) { setAddNodeError(t('topicsPanel.errors.linkFailed')); return; }
      const node: TopicNode = await res.json();
      setNodes(prev => [...prev, node]);
      setTopics(prev => prev.map(t => t.id === selectedTopicId ? { ...t, node_count: t.node_count + 1 } : t));
      setAddNodeSearch('');
      setSearchResults([]);
    } catch { setAddNodeError(t('topicsPanel.errors.networkError')); }
  };

  const detachNode = async (nodeId: number) => {
    if (!selectedTopicId) return;
    await fetch(`${API_URL}/topics/${selectedTopicId}/nodes/${nodeId}`, { method: 'DELETE', credentials: 'include' });
    setNodes(prev => prev.filter(n => n.id !== nodeId));
    setTopics(prev => prev.map(t => t.id === selectedTopicId ? { ...t, node_count: Math.max(0, t.node_count - 1) } : t));
  };

  // ── Derived ───────────────────────────────────────────────────────────────

  const filteredTopics = topics.filter(t =>
    !topicSearch || t.name.toLowerCase().includes(topicSearch.toLowerCase())
  );
  const selectedTopic = topics.find(t => t.id === selectedTopicId) ?? null;

  const nodesByType = NODE_TYPES.map(nt => ({
    ...nt,
    nodes: nodes.filter(n => n.node_type === nt.key),
  }));

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className={cn('flex flex-1 min-h-0 overflow-hidden', panelBg)}>

      {/* ── Left: Topic list ── */}
      <div className={cn('w-56 shrink-0 border-r flex flex-col', sidebarBg, divider)}>
        {/* Search */}
        <div className={cn('p-3 border-b', divider)}>
          <div className="relative">
            <Search className={cn('absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3', subText)} />
            <input
              type="text"
              placeholder={t('topicsPanel.searchPlaceholder')}
              value={topicSearch}
              onChange={e => setTopicSearch(e.target.value)}
              className={cn('w-full text-xs rounded-md pl-7 pr-3 py-1.5 border focus:outline-none', inputCls)}
            />
          </div>
        </div>

        {/* List */}
        <ScrollArea className="flex-1">
          {isLoadingTopics ? (
            <div className="flex justify-center py-8">
              <Loader2 className={cn('w-4 h-4 animate-spin', subText)} />
            </div>
          ) : filteredTopics.length === 0 ? (
            <p className={cn('text-[11px] text-center py-8 px-4', emptyText)}>
              {topicSearch ? t('topicsPanel.noTopicFound') : t('topicsPanel.noTopicsYet')}
            </p>
          ) : (
            <div className="p-1.5 space-y-0.5">
              {filteredTopics.map(t => {
                const { dot } = getColor(t.color, isDark);
                const isActive = selectedTopicId === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => { setSelectedTopicId(t.id); setIsEditing(false); setShowAddNode(false); }}
                    className={cn(
                      'w-full flex items-center gap-2 px-2.5 py-2 rounded-md border text-left transition-colors',
                      isActive ? activeItem : inactItem,
                    )}
                  >
                    <span className={cn('w-2 h-2 rounded-full shrink-0', dot)} />
                    <span className={cn('text-xs flex-1 truncate', isActive ? titleText : subText)}>
                      {t.name}
                    </span>
                    <span className={cn('text-[10px] shrink-0', emptyText)}>{t.node_count}</span>
                    {isActive && <ChevronRight className={cn('w-3 h-3 shrink-0', subText)} />}
                  </button>
                );
              })}
            </div>
          )}
        </ScrollArea>

        {/* Create */}
        <div className={cn('border-t p-3', divider)}>
          <AnimatePresence>
            {showCreate ? (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="space-y-2">
                  <input
                    type="text"
                    placeholder={t('topicsPanel.namePlaceholder')}
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    autoFocus
                    onKeyDown={e => e.key === 'Enter' && createTopic()}
                    className={cn('w-full text-xs rounded-md px-2.5 py-1.5 border focus:outline-none', inputCls)}
                  />
                  <input
                    type="text"
                    placeholder={t('topicsPanel.descriptionPlaceholder')}
                    value={newDesc}
                    onChange={e => setNewDesc(e.target.value)}
                    className={cn('w-full text-xs rounded-md px-2.5 py-1.5 border focus:outline-none', inputCls)}
                  />
                  {/* Color picker */}
                  <div className="flex gap-1.5 flex-wrap">
                    {COLORS.map(c => (
                      <button
                        key={c}
                        onClick={() => setNewColor(c)}
                        className={cn(
                          'w-4 h-4 rounded-full transition-all',
                          COLOR_MAP[c].dot,
                          newColor === c ? 'ring-2 ring-offset-1 ring-ds-zinc-400 scale-125' : 'opacity-60 hover:opacity-100',
                        )}
                      />
                    ))}
                  </div>
                  {createError && (
                    <p className="text-[10px] text-ds-red-500 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3" />{createError}
                    </p>
                  )}
                  <div className="flex gap-1.5">
                    <button
                      onClick={createTopic}
                      disabled={isCreating}
                      className="flex-1 text-[11px] flex items-center justify-center gap-1 px-2 py-1.5 rounded-md bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-500 transition-colors disabled:opacity-50"
                    >
                      {isCreating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                      {t('topicsPanel.createButton')}
                    </button>
                    <button
                      onClick={() => { setShowCreate(false); setCreateError(''); setNewName(''); setNewDesc(''); }}
                      className={cn('px-2 py-1.5 rounded-md text-[11px]', ghostBtn)}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </motion.div>
            ) : (
              <button
                onClick={() => setShowCreate(true)}
                className={cn('w-full flex items-center gap-1.5 text-[11px] px-2 py-1.5 rounded-md', ghostBtn)}
              >
                <Plus className="w-3 h-3" />
                {t('topicsPanel.newTopicButton')}
              </button>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* ── Right: Topic detail ── */}
      {selectedTopic ? (
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Header */}
          <div className={cn('px-5 py-4 border-b shrink-0', divider)}>
            {isEditing ? (
              <div className="space-y-2">
                <input
                  type="text"
                  value={editName}
                  onChange={e => setEditName(e.target.value)}
                  autoFocus
                  className={cn('w-full text-sm font-semibold rounded-md px-2.5 py-1.5 border focus:outline-none', inputCls)}
                />
                <input
                  type="text"
                  value={editDesc}
                  onChange={e => setEditDesc(e.target.value)}
                  placeholder={t('topicsPanel.descriptionPlaceholderShort')}
                  className={cn('w-full text-xs rounded-md px-2.5 py-1.5 border focus:outline-none', inputCls)}
                />
                <div className="flex items-center gap-3">
                  <div className="flex gap-1.5">
                    {COLORS.map(c => (
                      <button
                        key={c}
                        onClick={() => setEditColor(c)}
                        className={cn(
                          'w-4 h-4 rounded-full transition-all',
                          COLOR_MAP[c].dot,
                          editColor === c ? 'ring-2 ring-offset-1 ring-ds-zinc-400 scale-125' : 'opacity-60 hover:opacity-100',
                        )}
                      />
                    ))}
                  </div>
                  <div className="flex gap-1.5 ml-auto">
                    <button
                      onClick={saveEdit}
                      disabled={isSavingEdit}
                      className="text-[11px] flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-500 transition-colors disabled:opacity-50"
                    >
                      {isSavingEdit ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                      {t('topicsPanel.saveButton')}
                    </button>
                    <button onClick={() => setIsEditing(false)} className={cn('text-[11px] px-2 py-1.5 rounded-md', ghostBtn)}>
                      {t('topicsPanel.cancelButton')}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5 min-w-0">
                  <span className={cn('w-3 h-3 rounded-full shrink-0 mt-0.5', getColor(selectedTopic.color, isDark).dot)} />
                  <div className="min-w-0">
                    <h3 className={cn('text-sm font-semibold', titleText)}>{selectedTopic.name}</h3>
                    {selectedTopic.description && (
                      <p className={cn('text-xs mt-0.5', subText)}>{selectedTopic.description}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => startEdit(selectedTopic)}
                    title={t('topicsPanel.editTitle')}
                    className={cn('p-1.5 rounded-md transition-colors', ghostBtn)}
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => deleteTopic(selectedTopic.id)}
                    title={t('topicsPanel.deleteTopicTitle')}
                    className={cn(
                      'p-1.5 rounded-md transition-colors',
                      isDark
                        ? 'text-ds-zinc-600 hover:text-ds-red-400 hover:bg-ds-red-900/30'
                        : 'text-ds-zinc-400 hover:text-ds-red-500 hover:bg-ds-red-50',
                    )}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Nodes */}
          <ScrollArea className="flex-1 min-h-0">
            {isLoadingNodes ? (
              <div className="flex justify-center py-12">
                <Loader2 className={cn('w-5 h-5 animate-spin', subText)} />
              </div>
            ) : nodes.length === 0 ? (
              <div className={cn('flex flex-col items-center justify-center py-16', emptyText)}>
                <Tag className="w-8 h-8 mb-3 opacity-30" />
                <p className="text-sm">{t('topicsPanel.noNodesYet')}</p>
                <p className={cn('text-xs mt-1', isDark ? 'text-ds-zinc-700' : 'text-ds-zinc-300')}>
                  {t('topicsPanel.noNodesHint')}
                </p>
              </div>
            ) : (
              <div className="p-5 space-y-5">
                {nodesByType.filter(nt => nt.nodes.length > 0).map(({ key, labelKey, Icon, iconCls, nodes: typeNodes }) => (
                  <div key={key}>
                    <p className={cn('text-[10px] uppercase font-semibold tracking-wider mb-2', sectionLabel)}>
                      {t(labelKey)} <span className="normal-case font-normal">({typeNodes.length})</span>
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {typeNodes.map(node => (
                        <div
                          key={node.id}
                          className={cn(
                            'group flex items-center gap-1.5 pl-2.5 pr-1.5 py-1.5 rounded-lg border text-xs transition-colors',
                            chipCls,
                          )}
                        >
                          <Icon className={cn('w-3.5 h-3.5 shrink-0', iconCls)} />
                          <span className={cn('max-w-[180px] truncate', titleText)}>{node.node_label}</span>
                          {node.node_meta?.type && (
                            <span className={cn('text-[10px] px-1 rounded shrink-0', subText)}>
                              {node.node_meta.type as string}
                            </span>
                          )}
                          {node.node_meta?.file_path && !node.node_meta?.type && (
                            <span className={cn('text-[10px] max-w-[100px] truncate', subText)}>
                              {(node.node_meta.file_path as string).split('/').pop()}
                            </span>
                          )}
                          <button
                            onClick={() => detachNode(node.id)}
                            className={cn(
                              'shrink-0 p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity',
                              isDark ? 'text-ds-zinc-600 hover:text-ds-red-400' : 'text-ds-zinc-400 hover:text-ds-red-500',
                            )}
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>

          {/* Add node */}
          <div className={cn('border-t px-5 py-3 shrink-0', divider)}>
            <AnimatePresence>
              {showAddNode ? (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden"
                >
                  <div className="pb-1 space-y-2">
                    {/* Type selector */}
                    <div className="flex gap-1.5 flex-wrap">
                      {NODE_TYPES.map(({ key, labelKey, Icon, iconCls }) => (
                        <button
                          key={key}
                          onClick={() => setAddNodeType(key)}
                          className={cn(
                            'flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border transition-colors',
                            addNodeType === key
                              ? isDark ? 'bg-ds-zinc-700 border-ds-zinc-500 text-ds-zinc-100' : 'bg-ds-zinc-200 border-ds-zinc-400 text-ds-zinc-900'
                              : isDark ? 'border-ds-zinc-700 text-ds-zinc-500 hover:bg-ds-zinc-800' : 'border-ds-zinc-200 text-ds-zinc-500 hover:bg-ds-zinc-100',
                          )}
                        >
                          <Icon className={cn('w-3 h-3', addNodeType === key ? iconCls : '')} />
                          {t(labelKey)}
                        </button>
                      ))}
                      <button
                        onClick={() => { setShowAddNode(false); setAddNodeSearch(''); setSearchResults([]); setAddNodeError(''); }}
                        className={cn('ml-auto p-1 rounded-md', ghostBtn)}
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {/* Search */}
                    <div className="relative">
                      <Search className={cn('absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3', subText)} />
                      <input
                        type="text"
                        placeholder={t('topicsPanel.searchTypePlaceholder', {
                          type: t(NODE_TYPES.find(n => n.key === addNodeType)?.labelKey ?? 'topicsPanel.nodeTypes.project'),
                        })}
                        value={addNodeSearch}
                        onChange={e => setAddNodeSearch(e.target.value)}
                        autoFocus
                        className={cn('w-full text-xs rounded-md pl-7 pr-3 py-1.5 border focus:outline-none', inputCls)}
                      />
                      {isSearching && (
                        <Loader2 className={cn('absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 animate-spin', subText)} />
                      )}
                      {searchResults.length > 0 && (
                        <div className={cn('absolute top-full mt-1 left-0 right-0 border rounded-md shadow-lg z-20 max-h-48 overflow-y-auto', dropdownBg)}>
                          {searchResults.map((r, i) => {
                            const nt = NODE_TYPES.find(n => n.key === r.node_type);
                            const Icon = nt?.Icon ?? Tag;
                            const iconCls = nt?.iconCls ?? 'text-ds-zinc-400';
                            return (
                              <button
                                key={i}
                                onClick={() => attachNode(r)}
                                className={cn(
                                  'w-full text-left px-3 py-2 text-xs flex items-center gap-2 border-b last:border-0',
                                  dropItem,
                                  isDark ? 'border-ds-zinc-700' : 'border-ds-zinc-100',
                                )}
                              >
                                <Icon className={cn('w-3.5 h-3.5 shrink-0', iconCls)} />
                                <span className="truncate flex-1">{r.node_label}</span>
                                {r.node_meta?.type && (
                                  <span className={cn('text-[10px] shrink-0', subText)}>{r.node_meta.type as string}</span>
                                )}
                                {r.node_meta?.file_path && !r.node_meta?.type && (
                                  <span className={cn('text-[10px] shrink-0 truncate max-w-[120px]', subText)}>
                                    {(r.node_meta.file_path as string).split('/').pop()}
                                  </span>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {addNodeError && (
                      <p className="text-[10px] text-ds-red-500 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />{addNodeError}
                      </p>
                    )}
                  </div>
                </motion.div>
              ) : (
                <button
                  onClick={() => { setShowAddNode(true); setAddNodeError(''); }}
                  className={cn('flex items-center gap-1.5 text-xs px-2 py-1.5 rounded-md', ghostBtn)}
                >
                  <Plus className="w-3.5 h-3.5" />
                  {t('topicsPanel.addNodeButton')}
                </button>
              )}
            </AnimatePresence>
          </div>
        </div>
      ) : (
        /* Empty state when no topic selected */
        <div className={cn('flex-1 flex flex-col items-center justify-center', emptyText)}>
          <Tag className="w-10 h-10 mb-3 opacity-20" />
          <p className="text-sm">{t('topicsPanel.selectTopic')}</p>
          <p className={cn('text-xs mt-1', isDark ? 'text-ds-zinc-700' : 'text-ds-zinc-300')}>
            {t('topicsPanel.selectTopicHint')}
          </p>
        </div>
      )}
    </div>
  );
}
