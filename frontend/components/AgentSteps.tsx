"use client";

import React, { useState } from 'react';
import { 
  ChevronDown, 
  ChevronRight, 
  Brain, 
  Terminal, 
  Database, 
  Search, 
  FileCode, 
  CheckCircle2, 
  Eye, 
  EyeOff
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/lib/i18n/LanguageContext';

interface AgentStep {
    type: "thought" | "tool_call" | "tool_result";
    content?: string;
    name?: string;
    arguments?: any;
    result?: string;
    id?: string;
}

interface AgentStepsProps {
    steps: AgentStep[];
    theme: string;
    isLive?: boolean;
}

export function AgentSteps({ steps, theme, isLive }: AgentStepsProps) {
    const { t } = useLanguage();
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
        if (name.includes("search")) return <Search className="w-3.5 h-3.5 text-amber-400" />;
        if (name.includes("list")) return <Database className="w-3.5 h-3.5 text-blue-400" />;
        if (name.includes("view") || name.includes("read")) return <FileCode className="w-3.5 h-3.5 text-emerald-400" />;
        return <Terminal className="w-3.5 h-3.5 text-indigo-400" />;
    };

    // Count how many tool calls were executed
    const toolCallCount = steps.filter(s => s.type === 'tool_call').length;

    return (
        <div className={cn(
            "mb-3 border rounded-lg overflow-hidden transition-all duration-300",
            theme === 'dark' 
                ? "bg-zinc-950/40 border-zinc-800/80 hover:border-zinc-700/80" 
                : "bg-zinc-50 border-zinc-200 hover:border-zinc-300"
        )}>
            {/* Header Accordion Trigger */}
            <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                className={cn(
                    "w-full px-4 py-2.5 flex items-center justify-between text-xs font-semibold transition-colors cursor-pointer",
                    theme === 'dark' 
                        ? "text-zinc-300 hover:bg-zinc-900/50" 
                        : "text-zinc-700 hover:bg-zinc-100"
                )}
            >
                <div className="flex items-center gap-2.5">
                    <Brain className={cn("w-3.5 h-3.5 text-indigo-500", isLive && "animate-pulse")} />
                    <span className="font-semibold tracking-wide">
                        {isOpen ? t('agentSteps.hideThoughts') : t('agentSteps.showThoughts')}
                    </span>
                    {!isOpen && (
                        <span className={cn(
                            "px-1.5 py-0.5 rounded-sm text-[9px] font-bold tracking-wide opacity-80",
                            theme === 'dark' ? "bg-zinc-900 text-zinc-400" : "bg-zinc-200/80 text-zinc-600"
                        )}>
                            {t('agentSteps.toolsStepsCount', { tools: toolCallCount, steps: steps.length })}
                        </span>
                    )}
                </div>
                {isOpen ? <ChevronDown className="w-3.5 h-3.5 text-zinc-500" /> : <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />}
            </button>

            {/* Steps Timeline Area */}
            {isOpen && (
                <div className={cn(
                    "p-4 border-t text-xs space-y-4 relative",
                    theme === 'dark' ? "border-zinc-800/60" : "border-zinc-200"
                )}>
                    {/* Vertical line timeline helper */}
                    <div className={cn(
                        "absolute left-6 top-6 bottom-6 w-0.5 pointer-events-none",
                        theme === 'dark' ? "bg-zinc-800" : "bg-zinc-200"
                    )} />

                    {steps.map((step, idx) => {
                        const isThought = step.type === 'thought';
                        const isCall = step.type === 'tool_call';
                        const isResult = step.type === 'tool_result';

                        return (
                            <div key={idx} className="flex gap-4 relative items-start">
                                {/* Timeline Icon */}
                                <div className={cn(
                                    "w-5 h-5 rounded-full flex items-center justify-center shrink-0 z-10 shadow-sm border",
                                    isThought
                                        ? (theme === 'dark' ? "bg-purple-950/60 border-purple-500/30 text-purple-400" : "bg-purple-50 border-purple-200 text-purple-600")
                                        : isCall
                                        ? (theme === 'dark' ? "bg-blue-950/60 border-blue-500/30 text-blue-400" : "bg-blue-50 border-blue-200 text-blue-600")
                                        : (theme === 'dark' ? "bg-emerald-950/60 border-emerald-500/30 text-emerald-400" : "bg-emerald-50 border-emerald-200 text-emerald-600")
                                )}>
                                    {isThought && <Brain className="w-2.5 h-2.5" />}
                                    {isCall && getToolIcon(step.name)}
                                    {isResult && <CheckCircle2 className="w-2.5 h-2.5" />}
                                </div>

                                {/* Content block */}
                                <div className="flex-1 min-w-0 pt-0.5">
                                    {isThought && (
                                        <div className={cn(
                                            "p-3 rounded-lg border italic font-serif leading-relaxed",
                                            theme === 'dark'
                                                ? "bg-zinc-900/30 border-zinc-800 text-zinc-300"
                                                : "bg-white border-zinc-200 text-zinc-700"
                                        )}>
                                            <p className="whitespace-pre-wrap">{step.content}</p>
                                        </div>
                                    )}

                                    {isCall && (
                                        <div className="space-y-1">
                                            <span className={cn(
                                                "font-semibold",
                                                theme === 'dark' ? "text-zinc-200" : "text-zinc-800"
                                            )}>
                                                {t('agentSteps.toolCalled')} <span className="font-mono text-[11px] text-blue-500">{step.name}</span>
                                            </span>
                                            <pre className={cn(
                                                "p-2 rounded-lg border font-mono text-[10px] overflow-x-auto",
                                                theme === 'dark' 
                                                    ? "bg-zinc-900/60 border-zinc-800/80 text-zinc-300" 
                                                    : "bg-zinc-100 border-zinc-200 text-zinc-700"
                                            )}>
                                                {JSON.stringify(step.arguments, null, 2)}
                                            </pre>
                                        </div>
                                    )}

                                    {isResult && (
                                        <div className="space-y-1">
                                            <div className="flex items-center justify-between">
                                                <span className={cn(
                                                    "font-medium",
                                                    theme === 'dark' ? "text-zinc-400" : "text-zinc-500"
                                                )}>
                                                    {t('agentSteps.resultFrom')} <span className="font-mono text-[11px]">{step.name}</span>
                                                </span>
                                                <button
                                                    type="button"
                                                    onClick={() => toggleResult(idx)}
                                                    className={cn(
                                                        "flex items-center gap-1 text-[10px] font-bold transition-colors cursor-pointer",
                                                        theme === 'dark' ? "text-indigo-400 hover:text-indigo-300" : "text-indigo-600 hover:text-indigo-500"
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
                                                    "p-2.5 rounded-lg border font-mono text-[10px] overflow-x-auto max-h-60 overflow-y-auto leading-normal",
                                                    theme === 'dark' 
                                                        ? "bg-zinc-950 border-zinc-800/80 text-zinc-300" 
                                                        : "bg-zinc-100 border-zinc-200 text-zinc-700"
                                                )}>
                                                    {step.result}
                                                </pre>
                                            ) : (
                                                <div className={cn(
                                                    "p-1 px-2.5 rounded border text-[10px] font-mono inline-block",
                                                    theme === 'dark' ? "bg-zinc-900/40 border-zinc-800/60 text-zinc-500" : "bg-zinc-100 border-zinc-200 text-zinc-500"
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
