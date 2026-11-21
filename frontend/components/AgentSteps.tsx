"use client";
import type { AgentStep } from '@/types/domain';

import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import {
  AlertTriangle,
  Archive,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Database,
  Eye,
  EyeOff,
  FileCode,
  Loader2,
  Scissors,
  Search,
  Terminal,
  XCircle
} from 'lucide-react';
import { useState } from 'react';



interface AgentStepsProps {
    steps: AgentStep[];
    theme: string;
    isLive?: boolean;
}

// Längeres Denken zeigt zuerst nur den Anfang; der Rest kommt auf Klick.
const REASONING_PREVIEW_CHARS = 600;

function formatDuration(ms: number, language: string): string {
    if (ms < 1000) return `${ms} ms`;
    return `${new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(ms / 1000)} s`;
}

export function AgentSteps({ steps, theme, isLive }: AgentStepsProps) {
    const { t, language } = useLanguage();
    const [isOpen, setIsOpen] = useState(false);
    const [expandedResults, setExpandedResults] = useState<Record<string, boolean>>({});

    // isOpen is otherwise user-toggled (see onClick below), so it can't just be
    // computed from isLive during render — snap it open/closed whenever isLive
    // changes, done during render instead of in an effect to avoid an extra
    // commit (https://react.dev/learn/you-might-not-need-an-effect).
    const [prevIsLive, setPrevIsLive] = useState(isLive);
    if (isLive !== prevIsLive) {
        setPrevIsLive(isLive);
        setIsOpen(!!isLive);
    }

    if (!steps || steps.length === 0) return null;

    const toggleResult = (idx: number) => {
        setExpandedResults(prev => ({
            ...prev,
            [idx]: !prev[idx]
        }));
    };

    // Helper to get matching icon for a tool
    const getToolIcon = (toolName?: string) => {
        if (!toolName) return <Terminal className="w-3.5 h-3.5" />;
        const name = toolName.toLowerCase();
        if (name.includes("search")) return <Search className="w-3.5 h-3.5 text-ds-amber-400" />;
        if (name.includes("list")) return <Database className="w-3.5 h-3.5 text-ds-blue-400" />;
        if (name.includes("view") || name.includes("read")) return <FileCode className="w-3.5 h-3.5 text-ds-emerald-400" />;
        return <Terminal className="w-3.5 h-3.5 text-ds-indigo-400" />;
    };

    // Count how many tool calls were executed
    const toolCallCount = steps.filter(s => s.type === 'tool_call').length;
    // O-168: Kürzungen (einzelnes Werkzeugergebnis zu groß, oder der Server hat
    // das Gespräch für eine Modellrunde ans Kontextfenster angepasst) und
    // fehlgeschlagene Werkzeuge stehen immer sichtbar im Header, auch eingeklappt.
    const truncatedCount = steps.filter(s => (s.type === 'tool_result' && s.truncated) || s.type === 'context_trimmed').length;
    const failedCount = steps.filter(s => s.type === 'tool_result' && s.status === 'error').length;
    const answeredCallIds = new Set(steps.flatMap(s => (s.type === 'tool_result' && s.id ? [s.id] : [])));

    return (
        <div className={cn(
            "mb-3 border rounded-lg overflow-hidden transition-all duration-300",
            theme === 'dark'
                ? "bg-ds-zinc-950/40 border-ds-zinc-800/80 hover:border-ds-zinc-700/80"
                : "bg-ds-zinc-50 border-ds-zinc-200 hover:border-ds-zinc-300"
        )}>
            {/* Header Accordion Trigger */}
            <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                className={cn(
                    "w-full px-4 py-2.5 flex items-center justify-between text-xs font-semibold transition-colors cursor-pointer",
                    theme === 'dark'
                        ? "text-ds-zinc-300 hover:bg-ds-zinc-900/50"
                        : "text-ds-zinc-700 hover:bg-ds-zinc-100"
                )}
            >
                <div className="flex items-center gap-2.5">
                    <Brain className={cn("w-3.5 h-3.5 text-ds-indigo-500", isLive && "animate-pulse")} />
                    <span className="font-semibold tracking-wide">
                        {isOpen ? t('agentSteps.hideThoughts') : t('agentSteps.showThoughts')}
                    </span>
                    {!isOpen && (
                        <span className={cn(
                            "px-1.5 py-0.5 rounded-sm text-[0.5625rem] font-bold tracking-wide opacity-80",
                            theme === 'dark' ? "bg-ds-zinc-900 text-ds-zinc-400" : "bg-ds-zinc-200/80 text-ds-zinc-600"
                        )}>
                            {t('agentSteps.toolsStepsCount', { tools: toolCallCount, steps: steps.length })}
                        </span>
                    )}
                    {truncatedCount > 0 && (
                        <span
                            title={t('agentSteps.contextTrimmedTooltip')}
                            className="flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[0.5625rem] font-bold tracking-wide border border-ds-amber-500/30 bg-ds-amber-500/10 text-ds-amber-500"
                        >
                            <AlertTriangle className="w-3 h-3 shrink-0" />
                            {t('agentSteps.contextTrimmed', { count: truncatedCount })}
                        </span>
                    )}
                    {failedCount > 0 && (
                        <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[0.5625rem] font-bold tracking-wide border border-ds-red-500/30 bg-ds-red-500/10 text-ds-red-500">
                            <XCircle className="w-3 h-3 shrink-0" />
                            {t('agentSteps.toolsFailed', { count: failedCount })}
                        </span>
                    )}
                </div>
                {isOpen ? <ChevronDown className="w-3.5 h-3.5 text-ds-zinc-500" /> : <ChevronRight className="w-3.5 h-3.5 text-ds-zinc-500" />}
            </button>

            {/* Steps Timeline Area */}
            {isOpen && (
                <div className={cn(
                    "p-4 border-t text-xs space-y-4 relative",
                    theme === 'dark' ? "border-ds-zinc-800/60" : "border-ds-zinc-200"
                )}>
                    {/* Vertical line timeline helper */}
                    <div className={cn(
                        "absolute left-6 top-6 bottom-6 w-0.5 pointer-events-none",
                        theme === 'dark' ? "bg-ds-zinc-800" : "bg-ds-zinc-200"
                    )} />

                    {steps.map((step, idx) => {
                        const isThought = step.type === 'thought';
                        const isCall = step.type === 'tool_call';
                        const isResult = step.type === 'tool_result';
                        const isTrim = step.type === 'context_trimmed';
                        const isReasoning = step.type === 'reasoning';
                        const isCompaction = step.type === 'history_compacted';
                        // Ansichtsaktionen und unbekannte Schritte haben hier keine eigene Darstellung.
                        if (!isThought && !isCall && !isResult && !isTrim && !isReasoning && !isCompaction) return null;
                        const failed = isResult && step.status === 'error';
                        // Ohne Ergebnis: läuft noch (live) oder wurde mit der Runde abgebrochen.
                        const pending = isCall && !!step.id && !answeredCallIds.has(step.id);

                        return (
                            <div key={idx} className="flex gap-4 relative items-start">
                                {/* Timeline Icon */}
                                <div className={cn(
                                    "w-5 h-5 rounded-full flex items-center justify-center shrink-0 z-10 shadow-sm border",
                                    isThought || isReasoning
                                        ? (theme === 'dark' ? "bg-ds-purple-950/60 border-ds-purple-500/30 text-ds-purple-400" : "bg-ds-purple-50 border-ds-purple-200 text-ds-purple-600")
                                        : isCompaction
                                        ? (theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-700 text-ds-zinc-400" : "bg-ds-zinc-100 border-ds-zinc-300 text-ds-zinc-600")
                                        : failed
                                        ? (theme === 'dark' ? "bg-ds-red-950/60 border-ds-red-500/30 text-ds-red-400" : "bg-ds-red-50 border-ds-red-200 text-ds-red-600")
                                        : isTrim
                                        ? (theme === 'dark' ? "bg-ds-amber-950/60 border-ds-amber-500/30 text-ds-amber-400" : "bg-ds-amber-50 border-ds-amber-200 text-ds-amber-600")
                                        : isCall
                                        ? (theme === 'dark' ? "bg-ds-blue-950/60 border-ds-blue-500/30 text-ds-blue-400" : "bg-ds-blue-50 border-ds-blue-200 text-ds-blue-600")
                                        : (theme === 'dark' ? "bg-ds-emerald-950/60 border-ds-emerald-500/30 text-ds-emerald-400" : "bg-ds-emerald-50 border-ds-emerald-200 text-ds-emerald-600")
                                )}>
                                    {(isThought || isReasoning) && <Brain className="w-2.5 h-2.5" />}
                                    {isCompaction && (step.status === 'running' && isLive ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <Archive className="w-2.5 h-2.5" />)}
                                    {isCall && getToolIcon(step.name)}
                                    {isResult && (failed ? <XCircle className="w-2.5 h-2.5" /> : <CheckCircle2 className="w-2.5 h-2.5" />)}
                                    {isTrim && <Scissors className="w-2.5 h-2.5" />}
                                </div>

                                {/* Content block */}
                                <div className="flex-1 min-w-0 pt-0.5">
                                    {isThought && (
                                        <div className={cn(
                                            "p-3 rounded-lg border font-sans italic leading-relaxed",
                                            theme === 'dark'
                                                ? "bg-ds-zinc-900/30 border-ds-zinc-800 text-ds-zinc-300"
                                                : "bg-ds-white border-ds-zinc-200 text-ds-zinc-700"
                                        )}>
                                            <p className="whitespace-pre-wrap">{step.content}</p>
                                        </div>
                                    )}

                                    {isCall && (
                                        <div className="space-y-1">
                                            <span className={cn(
                                                "font-semibold",
                                                theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800"
                                            )}>
                                                {t('agentSteps.toolCalled')} <span className="font-mono text-[0.6875rem] text-ds-blue-500">{step.name}</span>
                                            </span>
                                            {pending && (
                                                <span className="ml-2 inline-flex items-center gap-1 text-[0.625rem] text-ds-zinc-500">
                                                    {isLive && <Loader2 className="w-3 h-3 animate-spin" />}
                                                    {t(isLive ? 'agentSteps.toolRunning' : 'agentSteps.toolAborted')}
                                                </span>
                                            )}
                                            <pre className={cn(
                                                "p-2 rounded-lg border font-mono text-[0.625rem] overflow-x-auto",
                                                theme === 'dark'
                                                    ? "bg-ds-zinc-900/60 border-ds-zinc-800/80 text-ds-zinc-300"
                                                    : "bg-ds-zinc-100 border-ds-zinc-200 text-ds-zinc-700"
                                            )}>
                                                {JSON.stringify(step.arguments, null, 2)}
                                            </pre>
                                        </div>
                                    )}

                                    {isReasoning && (
                                        <div className="space-y-1">
                                            <span className={cn("font-semibold", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-700")}>
                                                {t('agentSteps.reasoningTitle')}
                                            </span>
                                            <p className={cn("whitespace-pre-wrap font-sans leading-relaxed", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-600")}>
                                                {expandedResults[idx] || step.content.length <= REASONING_PREVIEW_CHARS ? step.content : `${step.content.slice(0, REASONING_PREVIEW_CHARS)} …`}
                                            </p>
                                            {step.content.length > REASONING_PREVIEW_CHARS && (
                                                <button type="button" onClick={() => toggleResult(idx)} className="text-[0.625rem] font-bold text-ds-indigo-500 hover:text-ds-indigo-400">
                                                    {t(expandedResults[idx] ? 'agentSteps.hide' : 'agentSteps.showMore')}
                                                </button>
                                            )}
                                        </div>
                                    )}

                                    {isCompaction && (
                                        <div className={cn("font-medium", step.status === 'failed' ? "text-ds-amber-500" : theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-600")}>
                                            {t(`agentSteps.compaction.${step.status}`, { count: step.messages })}
                                        </div>
                                    )}

                                    {isTrim && (
                                        <div className={cn("font-medium", theme === 'dark' ? "text-ds-amber-400" : "text-ds-amber-700")}>
                                            {t('agentSteps.contextTrimmedStep', {
                                                parts: step.parts.map(part => t(`agentSteps.trimPart.${part}`)).join(', '),
                                            })}
                                        </div>
                                    )}

                                    {isResult && (
                                        <div className="space-y-1">
                                            <div className="flex items-center justify-between">
                                                <span className={cn(
                                                    "font-medium",
                                                    theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500"
                                                )}>
                                                    {t('agentSteps.resultFrom')} <span className="font-mono text-[0.6875rem]">{step.name}</span>
                                                    {failed && <span className="ml-2 font-semibold text-ds-red-500">{t('agentSteps.toolFailed')}</span>}
                                                    {step.duration_ms != null && <span className="ml-2 font-mono text-[0.625rem] opacity-70">{formatDuration(step.duration_ms, language)}</span>}
                                                </span>
                                                <button
                                                    type="button"
                                                    onClick={() => toggleResult(idx)}
                                                    className={cn(
                                                        "flex items-center gap-1 text-[0.625rem] font-bold transition-colors cursor-pointer",
                                                        theme === 'dark' ? "text-ds-indigo-400 hover:text-ds-indigo-300" : "text-ds-indigo-600 hover:text-ds-indigo-500"
                                                    )}
                                                >
                                                    {expandedResults[idx] ? (
                                                        <>
                                                            <EyeOff className="w-3 h-3" />
                                                            {t('agentSteps.hide')}
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Eye className="w-3 h-3" />
                                                            {t('agentSteps.showContent')}
                                                        </>
                                                    )}
                                                </button>
                                            </div>

                                            {expandedResults[idx] ? (
                                                <pre className={cn(
                                                    "p-2.5 rounded-lg border font-mono text-[0.625rem] overflow-x-auto max-h-60 overflow-y-auto leading-normal",
                                                    theme === 'dark'
                                                        ? "bg-ds-zinc-950 border-ds-zinc-800/80 text-ds-zinc-300"
                                                        : "bg-ds-zinc-100 border-ds-zinc-200 text-ds-zinc-700"
                                                )}>
                                                    {step.result}
                                                </pre>
                                            ) : (
                                                <div className={cn(
                                                    "p-1 px-2.5 rounded border text-[0.625rem] font-mono inline-block",
                                                    theme === 'dark' ? "bg-ds-zinc-900/40 border-ds-zinc-800/60 text-ds-zinc-500" : "bg-ds-zinc-100 border-ds-zinc-200 text-ds-zinc-500"
                                                )}>
                                                    {step.result ? t('agentSteps.charsReturned', { count: step.result.length }) : t('agentSteps.emptyResult')}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
