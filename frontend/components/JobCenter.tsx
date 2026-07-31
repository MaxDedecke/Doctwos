"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Activity, AlertTriangle, ChevronDown, Loader2, Play, X } from "lucide-react";
import { api } from "@/app/services/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/lib/i18n/LanguageContext";

type Job = {
  key: string; kind: string; id: number; label: string; status: string;
  progress: number | null; progress_message?: string; error_message?: string;
  created_at?: string; can_resume: boolean;
};

export function JobCenter({ theme }: { theme: string }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeCount, setActiveCount] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [resuming, setResuming] = useState<string | null>(null);
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
    refresh();
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
    setResuming(job.key);
    try {
      await api.resumeJob(job.kind, job.id);
      await refresh();
    } finally {
      setResuming(null);
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
            {jobs.length === 0 && <p className="p-6 text-center text-xs text-ds-zinc-500">{t("jobCenter.empty")}</p>}
            {jobs.map(job => {
              const failed = job.status === "failed";
              const running = ["pending", "running"].includes(job.status);
              return <article key={job.key} className={cn("rounded-lg border p-3 mb-2", theme === "dark" ? "border-ds-zinc-800 bg-ds-zinc-900/50" : "border-ds-zinc-200 bg-ds-zinc-50")}>
                <div className="flex items-start gap-2">
                  {failed ? <AlertTriangle className="h-4 w-4 text-ds-rose-500 shrink-0" /> : <Loader2 className="h-4 w-4 text-ds-indigo-500 animate-spin shrink-0" />}
                  <div className="min-w-0 flex-1"><p className="text-xs font-semibold truncate">{job.label}</p><p className="text-[10px] text-ds-zinc-500">{t(`jobCenter.status.${job.status}`)}</p></div>
                  {failed && job.error_message && <button onClick={() => setExpanded(expanded === job.key ? null : job.key)} aria-expanded={expanded === job.key} className="text-ds-zinc-500"><ChevronDown className={cn("h-4 w-4 transition-transform", expanded === job.key && "rotate-180")} /></button>}
                </div>
                {running && job.progress !== null && <div className="mt-2 h-1.5 rounded bg-ds-zinc-700/30 overflow-hidden"><div className="h-full bg-ds-indigo-500" style={{ width: `${Math.max(2, Math.min(100, job.progress))}%` }} /></div>}
                {job.progress_message && <p className="mt-1.5 text-[10px] text-ds-zinc-500">{job.progress_message}</p>}
                {expanded === job.key && <pre className="mt-2 whitespace-pre-wrap break-words rounded bg-ds-rose-950/20 p-2 text-[10px] text-ds-rose-400">{job.error_message}</pre>}
                {job.can_resume && <button disabled={resuming === job.key} onClick={() => resume(job)} className="mt-2 flex items-center gap-1.5 text-[10px] font-semibold text-ds-indigo-500 disabled:opacity-50"><Play className="h-3 w-3" />{t("jobCenter.resume")}</button>}
              </article>;
            })}
          </div>
        </section>
      )}
    </div>
  );
}
