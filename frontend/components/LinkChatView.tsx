"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send, Loader2, Bot, User, Link2, Check, X, Search,
  ExternalLink, Sparkles, ChevronDown, RotateCcw, FileCode,
  BookOpen, Database
} from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { escapeHtml, sanitizeHtml } from '@/lib/sanitize';
import { API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';

/* ── Types ──────────────────────────────────────────────────────────────────── */

interface ChatMsg {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  sources_json?: any[];
  metadata_json?: {
    type?: string;
    suggestions?: Suggestion[];
    search_results_count?: number;
    action?: string;
    link_count?: number;
  };
  created_at?: string;
}

interface Suggestion {
  source_a_title: string;
  source_a_source_type?: string;
  source_a_chunk_id?: number;
  source_a_url?: string;
  source_b_title: string;
  source_b_source_type?: string;
  source_b_chunk_id?: number;
  source_b_url?: string;
  context?: string;
  score?: number;
}

interface SourceInfo {
  id: string;
  type: string;
  name: string;
  item_count: number;
  project_id?: number;
  source_id?: number;
}

interface LinkChatViewProps {
  theme: string;
  selectedProject: { id: number; name: string } | null;
  activeProfile?: { provider?: string; model?: string; apiKey?: string; baseUrl?: string } | null;
}

/* ── Source-Type Icon Helper ────────────────────────────────────────────────── */

function SourceIcon({ type, className }: { type: string; className?: string }) {
  switch (type) {
    case 'Git': return <FileCode className={className} />;
    case 'Confluence': case 'Jira': return <BookOpen className={className} />;
    case 'Local': return <Database className={className} />;
    default: return <BookOpen className={className} />;
  }
}

/* ── Main Component ─────────────────────────────────────────────────────────── */

export function LinkChatView({ theme, selectedProject, activeProfile }: LinkChatViewProps) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [confirmedSuggestions, setConfirmedSuggestions] = useState<Set<string>>(new Set());

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // ── Theme tokens ──────────────────────────────────────────────────────────
  const chatBg      = isDark ? 'bg-ds-zinc-900/50'               : 'bg-ds-zinc-50/50';
  const msgUserBg   = isDark ? 'bg-ds-indigo-900/30 border-ds-indigo-800/40' : 'bg-ds-indigo-50 border-ds-indigo-200';
  const msgBotBg    = isDark ? 'bg-ds-zinc-800/60 border-ds-zinc-700/50'     : 'bg-ds-white border-ds-zinc-200';
  const inputBg     = isDark ? 'bg-ds-zinc-800 border-ds-zinc-700'           : 'bg-ds-white border-ds-zinc-300';
  const inputText   = isDark ? 'text-ds-zinc-200 placeholder:text-ds-zinc-600' : 'text-ds-zinc-900 placeholder:text-ds-zinc-400';
  const titleText   = isDark ? 'text-ds-zinc-100' : 'text-ds-zinc-900';
  const subText     = isDark ? 'text-ds-zinc-500' : 'text-ds-zinc-500';
  const cardBg      = isDark ? 'bg-ds-zinc-800/80 border-ds-zinc-700/60 hover:border-ds-zinc-600' : 'bg-ds-zinc-50 border-ds-zinc-200 hover:border-ds-zinc-300';
  const cardLabel   = isDark ? 'text-ds-zinc-200' : 'text-ds-zinc-800';
  const cardMuted   = isDark ? 'text-ds-zinc-500' : 'text-ds-zinc-400';
  const sourceTag: Record<string, string> = isDark
    ? { Confluence: 'bg-ds-blue-900/50 text-ds-blue-300 border-ds-blue-700', Jira: 'bg-ds-sky-900/50 text-ds-sky-300 border-ds-sky-700', Local: 'bg-ds-zinc-700 text-ds-zinc-300 border-ds-zinc-600', Git: 'bg-ds-emerald-900/50 text-ds-emerald-300 border-ds-emerald-700' }
    : { Confluence: 'bg-ds-blue-100 text-ds-blue-700 border-ds-blue-300', Jira: 'bg-ds-sky-100 text-ds-sky-700 border-ds-sky-300', Local: 'bg-ds-zinc-100 text-ds-zinc-600 border-ds-zinc-300', Git: 'bg-ds-emerald-100 text-ds-emerald-700 border-ds-emerald-300' };
  const defaultTag = isDark ? 'bg-ds-zinc-700 text-ds-zinc-400 border-ds-zinc-600' : 'bg-ds-zinc-100 text-ds-zinc-500 border-ds-zinc-300';

  // ── Auto-scroll to bottom ─────────────────────────────────────────────────
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isSending]);

  // ── Initialize session ────────────────────────────────────────────────────
  const initSession = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/link-chat/sessions`, { method: 'POST', credentials: 'include' });
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages([{
        id: 0,
        role: 'assistant',
        content: data.welcome_message,
        metadata_json: { type: 'link_chat' }
      }]);
      setConfirmedSuggestions(new Set());
    } catch (e) {
      console.error('Failed to create link chat session:', e);
    }
  }, []);

  // ── Load available sources ────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${API_URL}/link-chat/sources`, { credentials: 'include' })
      .then(r => r.json())
      .then(setSources)
      .catch(() => {});
  }, []);

  // ── Initialize on mount ───────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      await initSession();
    })();
  }, [initSession]);

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessage = async () => {
    if (!input.trim() || !sessionId || isSending) return;
    const userMsg = input.trim();
    setInput('');
    setIsSending(true);

    // Optimistically add user message
    setMessages(prev => [...prev, {
      id: Date.now(),
      role: 'user',
      content: userMsg,
    }]);

    try {
      const res = await fetch(`${API_URL}/link-chat/sessions/${sessionId}/messages`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          project_id: selectedProject?.id ?? null,
          llm_provider: activeProfile?.provider || 'ollama',
          llm_model: activeProfile?.model || undefined,
          llm_api_key: activeProfile?.apiKey || undefined,
          llm_base_url: activeProfile?.baseUrl || undefined,
        }),
      });
      if (!res.body) throw new Error('no stream');

      // Backend streams SSE (link_suggestions, content_chunk, answer) — see link_chat.py.
      const assistantId = Date.now() + 1;
      setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '', metadata_json: { type: 'link_chat', suggestions: [] } }]);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let content = '';
      let suggestions: Suggestion[] = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.indexOf('\n\n');
        while (boundary !== -1) {
          const raw = buffer.slice(0, boundary).trim();
          buffer = buffer.slice(boundary + 2);
          boundary = buffer.indexOf('\n\n');
          if (raw.startsWith('data: ')) {
            try {
              const evt = JSON.parse(raw.slice(6));
              if (evt.type === 'link_suggestions') suggestions = evt.suggestions || [];
              else if (evt.type === 'content_chunk') content += evt.content;
              else if (evt.type === 'error') content = evt.error || t('linkChatView.commError');
              setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content, metadata_json: { type: 'link_chat', suggestions } } : m));
            } catch { /* partial/invalid event, skip */ }
          }
        }
      }
    } catch (e) {
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'assistant',
        content: t('linkChatView.commError'),
      }]);
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  };

  // ── Confirm a suggestion ──────────────────────────────────────────────────
  const confirmSuggestion = async (suggestion: Suggestion) => {
    if (!sessionId) return;
    const key = `${suggestion.source_a_title}→${suggestion.source_b_title}`;
    if (confirmedSuggestions.has(key)) return;

    try {
      await fetch(`${API_URL}/link-chat/sessions/${sessionId}/confirm`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([{
          source_a_type: 'document',
          source_a_title: suggestion.source_a_title,
          source_a_source_type: suggestion.source_a_source_type,
          source_a_chunk_id: suggestion.source_a_chunk_id,
          source_a_url: suggestion.source_a_url,
          source_b_type: 'document',
          source_b_title: suggestion.source_b_title,
          source_b_source_type: suggestion.source_b_source_type,
          source_b_chunk_id: suggestion.source_b_chunk_id,
          source_b_url: suggestion.source_b_url,
          context: suggestion.context,
          score: suggestion.score,
        }]),
      });
      setConfirmedSuggestions(prev => new Set(prev).add(key));
    } catch (e) {
      console.error('Failed to confirm suggestion:', e);
    }
  };

  // ── Handle Enter key ──────────────────────────────────────────────────────
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Parse and render markdown-like content ────────────────────────────────
  const renderContent = (content: string) => {
    // Remove suggestions JSON block from visible content
    let visibleContent = content;
    if (visibleContent.includes('```suggestions')) {
      visibleContent = visibleContent.split('```suggestions')[0].trim();
    }

    // Simple markdown: **bold**, *italic*, \n→<br>
    // WICHTIG: erst HTML escapen, dann die Markdown-Tags erzeugen — sonst würde
    // rohes HTML aus der LLM-Antwort (oder aus zitierten Dokumenten) live injiziert
    // (XSS). sanitizeHtml am Ende ist zusätzliche Absicherung.
    const parts = visibleContent.split('\n');
    return parts.map((line, i) => {
      let rendered = sanitizeHtml(escapeHtml(line)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code class="px-1 py-0.5 rounded text-[11px] ' + (isDark ? 'bg-ds-zinc-700' : 'bg-ds-zinc-200') + '">$1</code>'));
      return (
        <span key={i}>
          <span dangerouslySetInnerHTML={{ __html: rendered }} />
          {i < parts.length - 1 && <br />}
        </span>
      );
    });
  };

  // ── Render a suggestion card ──────────────────────────────────────────────
  const renderSuggestionCard = (suggestion: Suggestion, idx: number) => {
    const key = `${suggestion.source_a_title}→${suggestion.source_b_title}`;
    const isConfirmed = confirmedSuggestions.has(key);
    const scorePercent = suggestion.score ? Math.round(suggestion.score * 100) : null;

    return (
      <motion.div
        key={idx}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: idx * 0.1 }}
        className={cn(
          'border rounded-lg p-3 mt-2 transition-all',
          isConfirmed
            ? isDark ? 'bg-ds-emerald-950/30 border-ds-emerald-800/50' : 'bg-ds-emerald-50 border-ds-emerald-200'
            : cardBg
        )}
      >
        {/* Source A → Source B */}
        <div className="flex items-center gap-2 mb-2">
          <div className="flex items-center gap-1.5 flex-1 min-w-0">
            {suggestion.source_a_source_type && (
              <span className={cn('text-[9px] sm:text-[10px] px-1 sm:px-1.5 py-0.5 rounded border shrink-0',
                sourceTag[suggestion.source_a_source_type] ?? defaultTag)}>
                {suggestion.source_a_source_type}
              </span>
            )}
            <span className={cn('text-[11px] sm:text-xs font-medium truncate', cardLabel)}>{suggestion.source_a_title}</span>
          </div>
          <span className={cn('text-xs shrink-0', cardMuted)}>↔</span>
          <div className="flex items-center gap-1.5 flex-1 min-w-0">
            {suggestion.source_b_source_type && (
              <span className={cn('text-[9px] sm:text-[10px] px-1 sm:px-1.5 py-0.5 rounded border shrink-0',
                sourceTag[suggestion.source_b_source_type] ?? defaultTag)}>
                {suggestion.source_b_source_type}
              </span>
            )}
            <span className={cn('text-[11px] sm:text-xs font-medium truncate', cardLabel)}>{suggestion.source_b_title}</span>
          </div>
        </div>

        {/* Context + Score */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          {suggestion.context && (
            <p className={cn('text-[10px] sm:text-[11px] flex-1', cardMuted)}>{suggestion.context}</p>
          )}
          <div className="flex items-center justify-end gap-2 shrink-0">
            {scorePercent !== null && (
              <span className={cn('text-[10px] sm:text-[11px] font-mono font-semibold',
                scorePercent >= 80 ? 'text-ds-emerald-500' : scorePercent >= 60 ? 'text-ds-yellow-500' : 'text-ds-orange-500'
              )}>{scorePercent}%</span>
            )}
            {isConfirmed ? (
              <span className={cn('text-[10px] sm:text-[11px] flex items-center gap-1 px-1.5 sm:px-2 py-1 rounded-md',
                isDark ? 'text-ds-emerald-400 bg-ds-emerald-900/30' : 'text-ds-emerald-600 bg-ds-emerald-50')}>
                <Check className="w-3 h-3" /> <span className="hidden xs:inline">{t('linkChatView.linked')}</span>
              </span>
            ) : (
              <button
                onClick={() => confirmSuggestion(suggestion)}
                className={cn(
                  'text-[10px] sm:text-[11px] flex items-center gap-1 px-1.5 sm:px-2 py-1 rounded-md transition-colors font-medium',
                  isDark
                    ? 'text-ds-indigo-400 hover:text-ds-indigo-300 hover:bg-ds-indigo-900/30 border border-ds-indigo-700/50'
                    : 'text-ds-indigo-600 hover:text-ds-indigo-500 hover:bg-ds-indigo-50 border border-ds-indigo-300'
                )}>
                <Link2 className="w-3 h-3" /> {t('linkChatView.linkAction')}
              </button>
            )}
          </div>
        </div>
      </motion.div>
    );
  };

  // ── Render search results from sources_json ───────────────────────────────
  const renderSearchResults = (results: any[]) => {
    if (!results || results.length === 0) return null;
    return (
      <div className="mt-2 space-y-1">
        <p className={cn('text-[11px] font-medium', cardMuted)}>{t('linkChatView.foundContent')}</p>
        {results.slice(0, 5).map((r: any, i: number) => (
          <div key={i} className={cn('flex items-center gap-2 text-[11px] px-2 py-1.5 rounded-md border', cardBg)}>
            <SourceIcon type={r.source_type} className={cn('w-3 h-3 shrink-0', cardMuted)} />
            {r.source_type && (
              <span className={cn('text-[9px] px-1 py-0.5 rounded border shrink-0',
                sourceTag[r.source_type] ?? defaultTag)}>
                {r.source_type}
              </span>
            )}
            <span className={cn('truncate', cardLabel)}>{r.title}</span>
            {r.url && (
              <a href={r.url} target="_blank" rel="noopener noreferrer"
                className={cn('shrink-0', isDark ? 'text-ds-zinc-600 hover:text-ds-zinc-400' : 'text-ds-zinc-400 hover:text-ds-zinc-600')}>
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full">
      {/* Sources bar */}
      {sources.length > 0 && (
        <div className={cn('flex items-center gap-2 px-4 py-2.5 border-b shrink-0 overflow-x-auto',
          isDark ? 'border-ds-zinc-800 bg-ds-zinc-900/30' : 'border-ds-zinc-200 bg-ds-zinc-50/50')}>
          <span className={cn('text-[10px] font-medium shrink-0 uppercase tracking-wider', cardMuted)}>{t('linkChatView.sourcesLabel')}</span>
          {sources.map(s => (
            <span key={s.id}
              className={cn('text-[10px] px-2 py-1 rounded-sm border flex items-center gap-1 shrink-0 whitespace-nowrap',
                sourceTag[s.type] ?? defaultTag)}>
              <SourceIcon type={s.type} className="w-3 h-3" />
              {s.name}
              <span className="opacity-60">({s.item_count})</span>
            </span>
          ))}
        </div>
      )}

      {/* Chat messages area */}
      <div ref={scrollRef} className={cn('flex-1 overflow-y-auto px-4 py-4 space-y-3', chatBg)}>
        <AnimatePresence>
          {messages.map((msg, idx) => (
            <motion.div
              key={msg.id || idx}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={cn(
                'rounded-lg px-3 sm:px-4 py-3 border w-[90%] sm:max-w-[85%]',
                msg.role === 'user'
                  ? cn('ml-auto', msgUserBg)
                  : cn('mr-auto', msgBotBg)
              )}
            >
              {/* Role indicator */}
              <div className="flex items-center gap-1.5 mb-1.5">
                {msg.role === 'assistant' ? (
                  <Bot className={cn('w-3.5 h-3.5', isDark ? 'text-ds-indigo-400' : 'text-ds-indigo-600')} />
                ) : (
                  <User className={cn('w-3.5 h-3.5', isDark ? 'text-ds-zinc-400' : 'text-ds-zinc-600')} />
                )}
                <span className={cn('text-[10px] font-medium uppercase tracking-wider',
                  msg.role === 'assistant'
                    ? isDark ? 'text-ds-indigo-400' : 'text-ds-indigo-600'
                    : isDark ? 'text-ds-zinc-500' : 'text-ds-zinc-500'
                )}>
                  {msg.role === 'assistant' ? t('linkChatView.assistantName') : t('linkChatView.userName')}
                </span>
              </div>

              {/* Message content */}
              <div className={cn('text-xs leading-relaxed', cardLabel)}>
                {renderContent(msg.content)}
              </div>

              {/* Search results */}
              {msg.sources_json && msg.sources_json.length > 0 && renderSearchResults(msg.sources_json)}

              {/* Suggestions */}
              {msg.metadata_json?.suggestions && msg.metadata_json.suggestions.length > 0 && (
                <div className="mt-3">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Sparkles className={cn('w-3 h-3', isDark ? 'text-ds-amber-400' : 'text-ds-amber-500')} />
                    <span className={cn('text-[11px] font-medium', isDark ? 'text-ds-amber-400' : 'text-ds-amber-600')}>
                      {t('linkChatView.linkSuggestions')}
                    </span>
                  </div>
                  {msg.metadata_json.suggestions.map((s, i) => renderSuggestionCard(s, i))}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Typing indicator */}
        {isSending && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn('rounded-lg px-4 py-3 border mr-auto flex items-center gap-2', msgBotBg)}
          >
            <Bot className={cn('w-3.5 h-3.5', isDark ? 'text-ds-indigo-400' : 'text-ds-indigo-600')} />
            <div className="flex gap-1">
              <span className={cn('w-1.5 h-1.5 rounded-full animate-bounce', isDark ? 'bg-ds-zinc-500' : 'bg-ds-zinc-400')} style={{ animationDelay: '0ms' }} />
              <span className={cn('w-1.5 h-1.5 rounded-full animate-bounce', isDark ? 'bg-ds-zinc-500' : 'bg-ds-zinc-400')} style={{ animationDelay: '150ms' }} />
              <span className={cn('w-1.5 h-1.5 rounded-full animate-bounce', isDark ? 'bg-ds-zinc-500' : 'bg-ds-zinc-400')} style={{ animationDelay: '300ms' }} />
            </div>
            <span className={cn('text-[11px]', cardMuted)}>{t('linkChatView.searchingAndAnalyzing')}</span>
          </motion.div>
        )}
      </div>

      {/* Input area */}
      <div className={cn('border-t px-4 py-3 shrink-0', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
        {/* Quick action chips */}
        <div className="flex items-center gap-1.5 mb-2 overflow-x-auto">
          {[
            t('linkChatView.quickActions.showAllSources'),
            t('linkChatView.quickActions.searchConnections'),
            t('linkChatView.quickActions.findSimilarDocs'),
          ].map(chip => (
            <button
              key={chip}
              onClick={() => { setInput(chip); inputRef.current?.focus(); }}
              className={cn(
                'text-[10px] px-2 py-1 rounded-sm border shrink-0 transition-colors whitespace-nowrap',
                isDark
                  ? 'text-ds-zinc-500 border-ds-zinc-700 hover:text-ds-zinc-300 hover:border-ds-zinc-600 hover:bg-ds-zinc-800'
                  : 'text-ds-zinc-400 border-ds-zinc-200 hover:text-ds-zinc-600 hover:border-ds-zinc-300 hover:bg-ds-zinc-50'
              )}
            >
              {chip}
            </button>
          ))}
        </div>

        <div className="flex items-end gap-2">
          <div className="relative flex-1">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('linkChatView.inputPlaceholder')}
              rows={1}
              className={cn(
                'w-full text-xs rounded-lg px-3 py-2.5 border resize-none focus:outline-none focus:ring-1',
                inputBg, inputText,
                isDark ? 'focus:ring-ds-indigo-500/50 focus:border-ds-indigo-500' : 'focus:ring-ds-indigo-400/50 focus:border-ds-indigo-400'
              )}
              style={{ minHeight: '38px', maxHeight: '120px' }}
            />
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => { initSession(); }}
              title={t('linkChatView.newChatTitle')}
              className={cn(
                'p-2 rounded-lg transition-colors',
                isDark ? 'text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800' : 'text-ds-zinc-400 hover:text-ds-zinc-600 hover:bg-ds-zinc-100'
              )}
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button
              onClick={sendMessage}
              disabled={!input.trim() || isSending}
              className={cn(
                'p-2 rounded-lg transition-colors disabled:opacity-40',
                isDark
                  ? 'bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-500'
                  : 'bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-500'
              )}
            >
              {isSending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
