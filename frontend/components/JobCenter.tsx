"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, ChevronDown, Loader2, Play, RefreshCw, Square, X } from "lucide-react";
import { api } from "@/app/services/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/lib/i18n/LanguageContext";

type Job = {
  key: string; kind: string; id: number; label: string; status: string;
  progress: number | null; progress_message?: string; error_message?: string;
  created_at?: string; can_resume: boolean;
  can_start?: boolean; can_delete?: boolean; can_stop?: boolean;
};

export function JobCenter({ theme, currentUser }: { theme: string; currentUser?: { is_admin?: boolean } | null }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeCount, setActiveCount] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [resuming, setResuming] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [stopping, setStopping] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const response = await api.getJobs();
      setJobs(response.data.jobs || []);
      setActiveCount(response.data.active_count || 0);
    } catch (error: any) {
      if (error?.response?.status !== 401) console.error("Job center refresh failed", error);
    }
  }, []);

  useEffect(() => {
    // queueMicrotask: refresh() only ever sets state after its own await,
    // but calling it straight from the effect body still reads as a
    // synchronous setState-in-effect to the compiler's analysis.
    queueMicrotask(refresh);
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const resume = async (job: Job) => {
    setActionError(null);
    setResuming(job.key);
    try {
      await api.resumeJob(job.kind, job.id);
      await refresh();
    } catch (error: any) {
      setActionError(error?.response?.data?.detail || t("jobCenter.actionFailed"));
    } finally {
      setResuming(null);
    }
  };

  const start = async (job: Job) => {
    setActionError(null);
    setStarting(job.key);
    try {
      await api.startJob(job.kind, job.id);
      await refresh();
    } catch (error: any) {
      setActionError(error?.response?.data?.detail || t("jobCenter.actionFailed"));
    } finally {
      setStarting(null);
    }
  };

  const remove = async (job: Job) => {
    setActionError(null);
    setRemoving(job.key);
    try {
      await api.deleteJob(job.kind, job.id);
      setJobs(previous => previous.filter(item => item.key !== job.key));
    } catch (error: any) {
      setActionError(error?.response?.data?.detail || t("jobCenter.actionFailed"));
    } finally {
      setRemoving(null);
    }
  };

  const stop = async (job: Job) => {
    setActionError(null);
    setStopping(job.key);
    try {
      await api.stopJob(job.kind, job.id);
      await refresh();
    } catch (error: any) {
      setActionError(error?.response?.data?.detail || t("jobCenter.actionFailed"));
    } finally {
      setStopping(null);
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <Button
        variant="ghost" size="icon" onClick={() => setOpen(value => !value)}
        aria-label={t("jobCenter.title")} aria-expanded={open}
        className={cn("relative h-8 w-8 rounded-lg border", theme === "dark" ? "text-ds-zinc-400 border-ds-zinc-800 hover:bg-ds-zinc-900" : "text-ds-zinc-700 border-ds-zinc-200 hover:bg-ds-zinc-100")}
      >
        <Activity className="h-4 w-4" />
        {activeCount > 0 && <span className="absolute -right-1 -top-1 min-w-4 h-4 px-1 rounded-full bg-ds-rose-600 text-ds-white text-[9px] leading-4 font-bold">{activeCount}</span>}
      </Button>

      <span className="sr-only" aria-live="polite">{t("jobCenter.activeCount", { count: activeCount })}</span>
      {open && (
        <section className={cn("absolute right-0 top-10 z-[110] w-[min(26rem,calc(100vw-1rem))] rounded-xl border shadow-2xl", theme === "dark" ? "bg-ds-zinc-950 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200")} aria-label={t("jobCenter.title")}>
          <header className="flex items-center justify-between px-4 py-3 border-b border-ds-zinc-800/50">
            <div><h2 className="text-sm font-bold">{t("jobCenter.title")}</h2><p className="text-[10px] text-ds-zinc-500">{t("jobCenter.subtitle")}</p></div>
            <button onClick={() => setOpen(false)} aria-label={t("common.close")}><X className="h-4 w-4 text-ds-zinc-500" /></button>
          </header>
          <div className="max-h-[28rem] overflow-y-auto p-2">
            {actionError && <p role="alert" className="mx-2 mb-2 rounded-md bg-ds-rose-500/10 px-2 py-1.5 text-[10px] text-ds-rose-500">{actionError}</p>}
            {jobs.length === 0 && <p className="p-6 text-center text-xs text-ds-zinc-500">{t("jobCenter.empty")}</p>}
            {jobs.map(job => {
              const failed = job.status === "failed";
              const running = ["pending", "running", "syncing", "parsing"].includes(job.status);
              const completed = job.status === "completed";
              return <article key={job.key} className={cn("rounded-lg border p-3 mb-2", theme === "dark" ? "border-ds-zinc-800 bg-ds-zinc-900/50" : "border-ds-zinc-200 bg-ds-zinc-50")}>
                <div className="flex items-start gap-2">
                  {failed ? <AlertTriangle className="h-4 w-4 text-ds-rose-500 shrink-0" /> : completed ? <CheckCircle2 className="h-4 w-4 text-ds-emerald-500 shrink-0" /> : <Loader2 className="h-4 w-4 text-ds-indigo-500 animate-spin shrink-0" />}
                  <div className="min-w-0 flex-1"><p className="text-xs font-semibold truncate">{job.label}</p><p className="text-[10px] text-ds-zinc-500">{t(`jobCenter.status.${job.status}`)}</p></div>
                  {currentUser?.is_admin && job.can_delete && <button disabled={removing === job.key} onClick={() => remove(job)} aria-label={t("jobCenter.remove")} title={t("jobCenter.remove")} className="text-ds-zinc-500 hover:text-ds-rose-500 disabled:opacity-50"><X className="h-3.5 w-3.5" /></button>}
                  {failed && job.error_message && <button onClick={() => setExpanded(expanded === job.key ? null : job.key)} aria-expanded={expanded === job.key} className="text-ds-zinc-500"><ChevronDown className={cn("h-4 w-4 transition-transform", expanded === job.key && "rotate-180")} /></button>}
                </div>
                {running && job.progress !== null && <div className="mt-2 h-1.5 rounded bg-ds-zinc-700/30 overflow-hidden"><div className="h-full bg-ds-indigo-500" style={{ width: `${Math.max(2, Math.min(100, job.progress))}%` }} /></div>}
                {job.progress_message && <p className="mt-1.5 text-[10px] text-ds-zinc-500">{job.progress_message}</p>}
                {expanded === job.key && <pre className="mt-2 whitespace-pre-wrap break-words rounded bg-ds-rose-950/20 p-2 text-[10px] text-ds-rose-400">{job.error_message}</pre>}
                <div className="mt-2 flex items-center gap-3">
                  {job.can_resume && !currentUser?.is_admin && <button disabled={resuming === job.key || starting === job.key} onClick={() => resume(job)} className="flex items-center gap-1.5 text-[10px] font-semibold text-ds-indigo-500 disabled:opacity-50"><Play className="h-3 w-3" />{t("jobCenter.resume")}</button>}
                  {currentUser?.is_admin && job.can_start && <button disabled={resuming === job.key || starting === job.key} onClick={() => start(job)} className="flex items-center gap-1.5 text-[10px] font-semibold text-ds-indigo-500 disabled:opacity-50"><RefreshCw className={cn("h-3 w-3", starting === job.key && "animate-spin")} />{t("jobCenter.restart")}</button>}
                  {currentUser?.is_admin && job.can_stop && <button disabled={stopping === job.key} onClick={() => stop(job)} className="flex items-center gap-1.5 text-[10px] font-semibold text-ds-amber-500 disabled:opacity-50"><Square className="h-3 w-3" />{t("jobCenter.stop")}</button>}
                </div>
              </article>;
            })}
          </div>
        </section>
      )}
    </div>
  );
}
