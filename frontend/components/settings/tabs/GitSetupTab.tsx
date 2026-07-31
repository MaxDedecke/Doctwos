"use client";

import React, { useState } from 'react';
import {
  Check, X, Github, Activity, Database, Globe, ChevronRight, ChevronLeft,
  Loader2, Search, GitBranch, Sparkles,
} from 'lucide-react';
import { cn } from "@/lib/utils";
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Aus SettingsModal herausgelöster 'git-setup'-Tab (docs/TECH_DEBT_CLEANUP_PLAN.md
// §5, Schritt 2). Der 5-schrittige Git-Anbindungs-Wizard ist attach-only: sein
// einziger Einstieg ist der "Git-Repository anbinden"-Button auf einer Projektkarte
// (projects-Tab), der targetProjectId setzt und hierher navigiert. Alle Wizard-
// States/Handler sind lokal; targetProjectId kommt als Prop, die Navigation zurück
// über onDone. Der lokale State wird beim Verlassen (Unmount) ohnehin zurückgesetzt,
// daher navigiert "Abbrechen"/"Fertig" schlicht via onDone.
interface GitSetupTabProps {
  targetProjectId: number | null;
  onDone: () => void;
}

export const GitSetupTab: React.FC<GitSetupTabProps> = ({ targetProjectId, onDone }) => {
  const { t } = useLanguage();
  const { theme, showToast, setProjects, setConnectedSources } = useSettings();

  const [repoType, setRepoType] = useState("public"); // 'public' | 'github' | 'bitbucket' | 'gitlab'
  const [repoUsername, setRepoUsername] = useState("");
  const [repoToken, setRepoToken] = useState("");
  const [bitbucketServerUrl, setBitbucketServerUrl] = useState("");
  const [newRepoName, setNewRepoName] = useState("");
  const [newRepoUrl, setNewRepoUrl] = useState("");
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'success' | 'error' | null>(null);
  const [connectionError, setConnectionError] = useState("");
  const [fetchedRepos, setFetchedRepos] = useState<any[]>([]);
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);
  const [repoSearchQuery, setRepoSearchQuery] = useState("");
  const [selectedRepoFullName, setSelectedRepoFullName] = useState("");
  const [fetchedBranches, setFetchedBranches] = useState<string[]>([]);
  const [isLoadingBranches, setIsLoadingBranches] = useState(false);
  const [selectedBranchName, setSelectedBranchName] = useState("main");
  const [wizardStep, setWizardStep] = useState(1);

  const parsePublicGitUrl = (url: string) => {
    try {
      const cleanUrl = url.trim().replace(/\.git$/, "");
      if (cleanUrl.includes("github.com")) {
        const parts = cleanUrl.split("github.com/")[1]?.split("/");
        if (parts && parts.length >= 2) {
          return { type: "github", repo_name: `${parts[0]}/${parts[1]}` };
        }
      } else if (cleanUrl.includes("gitlab.com")) {
        const parts = cleanUrl.split("gitlab.com/")[1]?.split("/");
        if (parts && parts.length >= 2) {
          return { type: "gitlab", repo_name: parts.join("/") };
        }
      } else if (cleanUrl.includes("bitbucket.org")) {
        const parts = cleanUrl.split("bitbucket.org/")[1]?.split("/");
        if (parts && parts.length >= 2) {
          return { type: "bitbucket", repo_name: `${parts[0]}/${parts[1]}` };
        }
      }
    } catch (e) {
      console.error("Error parsing public git URL", e);
    }
    return null;
  };

  const handleTestConnection = async () => {
    setIsTestingConnection(true);
    setConnectionStatus(null);
    setConnectionError("");

    try {
      if (repoType === 'public') {
        if (!newRepoUrl) {
          setConnectionStatus('error');
          setConnectionError(t('settings.toast.invalidGitUrl'));
          setIsTestingConnection(false);
          return;
        }

        const parsed = parsePublicGitUrl(newRepoUrl);
        if (parsed) {
          try {
            const branchRes = await api.getConnectorBranches({
              type: parsed.type,
              repo_name: parsed.repo_name,
            });
            if (branchRes.data && branchRes.data.length > 0) {
              setFetchedBranches(branchRes.data);
              setSelectedBranchName(branchRes.data[0]);
            }
            setNewRepoName(parsed.repo_name.split('/').pop() || "");
            setConnectionStatus('success');
            showToast(t('settings.toast.repoUrlVerified'), "success");
          } catch (e) {
            const inferredName = newRepoUrl.split('/').pop()?.replace(/\.git$/, "") || "public-repo";
            setNewRepoName(inferredName);
            setConnectionStatus('success');
            showToast(t('settings.toast.gitUrlAcceptedNoBranches'), "success");
          }
        } else {
          const inferredName = newRepoUrl.split('/').pop()?.replace(/\.git$/, "") || "public-repo";
          setNewRepoName(inferredName);
          setConnectionStatus('success');
          showToast(t('settings.toast.gitUrlAccepted'), "success");
        }
      } else {
        const res = await api.testConnector({
          type: repoType,
          username: repoUsername || undefined,
          token: repoToken,
          url: repoType === 'bitbucket' && bitbucketServerUrl ? bitbucketServerUrl : undefined,
        });

        if (res.data && res.data.success) {
          setConnectionStatus('success');
          showToast(res.data.message || t('settings.toast.connectionSuccessGeneric'), "success");

          setIsLoadingRepos(true);
          try {
            const reposRes = await api.getConnectorRepos({
              type: repoType,
              username: repoUsername || undefined,
              token: repoToken,
              url: repoType === 'bitbucket' && bitbucketServerUrl ? bitbucketServerUrl : undefined,
            });
            setFetchedRepos(reposRes.data || []);
          } catch (err) {
            console.error("Error fetching repositories:", err);
            showToast(t('settings.toast.repoListFetchFailed'), "error");
          } finally {
            setIsLoadingRepos(false);
          }
        } else {
          setConnectionStatus('error');
          setConnectionError(res.data?.message || t('settings.toast.connectionEstablishFailed'));
          showToast(t('settings.toast.connectionFailed'), "error");
        }
      }
    } catch (err: any) {
      console.error(err);
      setConnectionStatus('error');
      setConnectionError(err.response?.data?.detail || t('settings.toast.networkTestError'));
      showToast(t('settings.toast.connectionFailed'), "error");
    } finally {
      setIsTestingConnection(false);
    }
  };

  const handleSelectRepoInWizard = async (fullName: string) => {
    setSelectedRepoFullName(fullName);
    setIsLoadingBranches(true);
    setFetchedBranches([]);

    const selected = fetchedRepos.find((r: any) => r.full_name === fullName);
    if (selected) {
      setNewRepoName(selected.name);
      setNewRepoUrl(selected.clone_url);
    }

    try {
      const res = await api.getConnectorBranches({
        type: repoType,
        username: repoUsername || undefined,
        token: repoToken,
        repo_name: fullName,
        url: repoType === 'bitbucket' && bitbucketServerUrl ? bitbucketServerUrl : undefined,
      });
      setFetchedBranches(res.data || []);
      if (res.data && res.data.length > 0) {
        setSelectedBranchName(res.data[0]);
      } else {
        setSelectedBranchName("main");
      }
    } catch (err) {
      console.error("Error fetching branches:", err);
      showToast(t('settings.toast.branchesFetchFailed'), "error");
      setSelectedBranchName("main");
    } finally {
      setIsLoadingBranches(false);
    }
  };

  const handleNextStep = async () => {
    if (wizardStep === 1) {
      setWizardStep(2);
      setConnectionStatus(null);
      setConnectionError("");
    } else if (wizardStep === 2) {
      if (repoType === 'public') {
        setIsLoadingBranches(true);
        const parsed = parsePublicGitUrl(newRepoUrl);
        if (parsed) {
          try {
            const res = await api.getConnectorBranches({
              type: parsed.type,
              repo_name: parsed.repo_name
            });
            setFetchedBranches(res.data || []);
            if (res.data && res.data.length > 0) {
              setSelectedBranchName(res.data[0]);
            }
          } catch (e) {
            console.error("Failed to fetch public branches:", e);
          }
        }
        setIsLoadingBranches(false);
        setWizardStep(4);
      } else {
        setWizardStep(3);
      }
    } else if (wizardStep === 3) {
      setWizardStep(4);
    }
  };

  const handleWizardSubmit = async (e: any) => {
    if (e) e.preventDefault();

    let cloneUrl = newRepoUrl;
    let repoName = newRepoName;

    if (repoType !== 'public') {
      const selected = fetchedRepos.find((r: any) => r.full_name === selectedRepoFullName);
      if (selected) {
        cloneUrl = selected.clone_url;
        repoName = selected.name;
      }
    }

    if (!repoName || !cloneUrl) {
      showToast(t('settings.toast.repoNameAndUrlRequired'), "error");
      return;
    }

    if (!targetProjectId) {
      // The wizard is attach-only — its single entry point (the "Git-Repository
      // anbinden" button on a project card) always sets this first.
      console.error("Git-setup wizard submitted without a target project");
      showToast(t('settings.toast.repoAddFailed'), "error");
      return;
    }

    try {
      const res = await api.createGitSource({
        name: repoName,
        url: cloneUrl,
        branch: selectedBranchName || "main",
        username: repoType === 'public' ? null : repoUsername,
        token: repoType === 'public' ? null : repoToken,
        project_id: targetProjectId
      });

      setConnectedSources(prev => [...prev, res.data]);
      const projectsRes = await api.getProjects();
      setProjects(projectsRes.data);
      setWizardStep(5);
      showToast(t('settings.toast.repoAdded'), "success");
    } catch (err) {
      console.error(err);
      showToast(t('settings.toast.repoAddFailed'), "error");
    }
  };

  return (
    <div className="space-y-4 animate-in fade-in duration-200">
      <div className="flex items-center justify-between">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-550")}>
          {t('settings.header.gitSetupWizard')}
        </h4>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onDone}
          className={cn("h-7 text-xs font-semibold px-2.5 rounded-lg transition-all", theme === 'dark' ? "text-zinc-500 hover:text-zinc-350 hover:bg-zinc-800" : "text-zinc-450 hover:text-zinc-800 hover:bg-zinc-100")}
        >
          {t('common.cancel')}
        </Button>
      </div>

      <div className={cn(
        "border rounded-lg p-4 sm:p-5 transition-all space-y-5",
        theme === 'dark' ? "bg-zinc-950/40 border-zinc-800" : "bg-zinc-50 border-zinc-200"
      )}>
        {/* Wizard Step Progress Indicator */}
        {wizardStep <= 4 && (
          <div className="relative flex items-center justify-between w-full max-w-md mx-auto mb-6 px-4">
            <div className={cn("absolute left-0 right-0 h-0.5 top-1/2 -translate-y-1/2 z-0", theme === 'dark' ? "bg-zinc-800" : "bg-zinc-200")} />
            <div
              className="absolute left-0 h-0.5 top-1/2 -translate-y-1/2 bg-indigo-500 transition-all duration-300 z-0"
              style={{ width: `${((wizardStep - 1) / 3) * 100}%` }}
            />

            {[
              { step: 1, label: t('settings.gitSetup.steps.source') },
              { step: 2, label: t('settings.gitSetup.steps.connection') },
              { step: 3, label: t('settings.gitSetup.steps.repository') },
              { step: 4, label: t('settings.gitSetup.steps.branch') }
            ].map((item) => {
              const isCompleted = item.step < wizardStep;
              const isActive = item.step === wizardStep;
              return (
                <div key={item.step} className="flex flex-col items-center relative z-10">
                  <div className={cn(
                    "w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300 border shadow-sm",
                    isCompleted
                      ? "bg-indigo-500 border-indigo-500 text-white"
                      : isActive
                        ? (theme === 'dark' ? "bg-zinc-900 border-indigo-500 text-indigo-400 scale-110 shadow-indigo-500/10" : "bg-white border-indigo-600 text-indigo-650 scale-110 shadow-indigo-650/10")
                        : (theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-500" : "bg-white border-zinc-200 text-zinc-400")
                  )}>
                    {isCompleted ? (
                      <Check className="w-4 h-4 stroke-[3px]" />
                    ) : (
                      item.step
                    )}
                  </div>
                  <span className={cn(
                    "text-[10px] font-semibold mt-1.5 transition-colors duration-300",
                    isActive
                      ? "text-indigo-500 font-bold"
                      : (theme === 'dark' ? "text-zinc-500" : "text-zinc-400")
                  )}>
                    {item.label}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Step 1: Select Source */}
        {wizardStep === 1 && (
          <div className="space-y-4 animate-in fade-in duration-200">
            <div className="space-y-1 text-center">
              <h5 className={cn("text-sm font-bold", theme === 'dark' ? "text-zinc-100" : "text-zinc-850")}>{t('settings.gitSetup.step1.title')}</h5>
              <p className={cn("text-[11px]", theme === 'dark' ? "text-zinc-450" : "text-zinc-500")}>
                {t('settings.gitSetup.step1.description')}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
              {[
                { id: 'github', name: 'GitHub', icon: Github, desc: t('settings.gitSetup.step1.descPrivatePublic') },
                { id: 'gitlab', name: 'GitLab', icon: Activity, desc: t('settings.gitSetup.step1.descPrivatePublic') },
                { id: 'bitbucket', name: 'BitBucket', icon: Database, desc: t('settings.gitSetup.step1.descPrivatePublic') },
                { id: 'public', name: t('settings.gitSetup.step1.publicGit'), icon: Globe, desc: t('settings.gitSetup.step1.descAnyPublicUrl') }
              ].map((provider) => {
                const isSel = repoType === provider.id;
                const ProviderIcon = provider.icon;
                return (
                  <button
                    key={provider.id}
                    type="button"
                    onClick={() => {
                      setRepoType(provider.id);
                      setConnectionStatus(null);
                      setConnectionError("");
                    }}
                    className={cn(
                      "flex flex-col items-center gap-2 p-4 rounded-lg border text-center transition-all group",
                      isSel
                        ? (theme === 'dark' ? "border-indigo-500 bg-indigo-500/5 text-indigo-400" : "border-indigo-600 bg-indigo-50/50 text-indigo-650 shadow-md shadow-indigo-600/5")
                        : (theme === 'dark' ? "bg-zinc-900/40 border-zinc-800/80 text-zinc-400 hover:border-zinc-700/80 hover:bg-zinc-900" : "bg-white border-zinc-200 text-zinc-600 hover:border-zinc-300 hover:bg-zinc-50")
                    )}
                  >
                    <ProviderIcon className={cn(
                      "w-6 h-6 transition-transform group-hover:scale-105",
                      isSel ? "text-indigo-500" : "text-zinc-500"
                    )} />
                    <div className="space-y-0.5">
                      <p className={cn("text-xs font-bold", theme === 'dark' ? "text-zinc-200" : "text-zinc-800")}>{provider.name}</p>
                      <p className="text-[9px] text-zinc-500">{provider.desc}</p>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="flex justify-end pt-3 border-t border-zinc-800/20">
              <Button
                type="button"
                onClick={handleNextStep}
                className="bg-indigo-650 hover:bg-indigo-600 text-white rounded-lg px-4 h-8 text-xs font-semibold flex items-center gap-1 shadow-lg shadow-indigo-600/10"
              >
                <span>{t('common.next')}</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Establish Connection */}
        {wizardStep === 2 && (
          <div className="space-y-4 animate-in fade-in duration-200">
            <div className="space-y-1 text-center">
              <h5 className={cn("text-sm font-bold", theme === 'dark' ? "text-zinc-100" : "text-zinc-850")}>
                {repoType === 'public' ? t('settings.gitSetup.step2.titleCloneUrl') : t('settings.gitSetup.step2.titleConnectTo', { provider: repoType === 'github' ? 'GitHub' : repoType === 'gitlab' ? 'GitLab' : 'Bitbucket' })}
              </h5>
              <p className={cn("text-[11px]", theme === 'dark' ? "text-zinc-450" : "text-zinc-500")}>
                {repoType === 'public'
                  ? t('settings.gitSetup.step2.descPublic')
                  : t('settings.gitSetup.step2.descPrivate')}
              </p>
            </div>

            {repoType === 'public' ? (
              <div className="space-y-1.5">
                <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.gitSetup.step2.cloneUrlLabel')}</label>
                <input
                  type="text"
                  placeholder="https://github.com/facebook/react.git"
                  value={newRepoUrl}
                  onChange={e => {
                    setNewRepoUrl(e.target.value);
                    setConnectionStatus(null);
                  }}
                  className={cn(
                    "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all font-mono",
                    theme === 'dark'
                      ? "bg-zinc-900 border-zinc-800 text-zinc-200 placeholder-zinc-700 focus:border-zinc-700"
                      : "bg-white border-zinc-200 text-zinc-900 placeholder-zinc-400 focus:border-zinc-300"
                  )}
                />
              </div>
            ) : (
              <div className="space-y-3">
                {repoType === 'bitbucket' && (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.gitSetup.step2.serverUrlLabel')} <span className="normal-case font-normal">{t('settings.gitSetup.step2.serverUrlHint')}</span></label>
                      <input
                        type="text"
                        placeholder="https://bitbucket.example.com"
                        value={bitbucketServerUrl}
                        onChange={e => { setBitbucketServerUrl(e.target.value); setConnectionStatus(null); }}
                        className={cn(
                          "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all",
                          theme === 'dark'
                            ? "bg-zinc-900 border-zinc-800 text-zinc-200 placeholder-zinc-700 focus:border-zinc-700"
                            : "bg-white border-zinc-200 text-zinc-900 placeholder-zinc-400 focus:border-zinc-300"
                        )}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">
                        {bitbucketServerUrl ? t('settings.gitSetup.step2.usernameLabelPatOnly') : t('settings.gitSetup.step2.usernameLabelBitbucket')}
                      </label>
                      <input
                        type="text"
                        placeholder={bitbucketServerUrl ? t('settings.gitSetup.step2.usernamePlaceholderPat') : t('settings.gitSetup.step2.usernamePlaceholderBitbucket')}
                        value={repoUsername}
                        onChange={e => { setRepoUsername(e.target.value); setConnectionStatus(null); }}
                        className={cn(
                          "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all",
                          theme === 'dark'
                            ? "bg-zinc-900 border-zinc-800 text-zinc-200 placeholder-zinc-700 focus:border-zinc-700"
                            : "bg-white border-zinc-200 text-zinc-900 placeholder-zinc-400 focus:border-zinc-300"
                        )}
                      />
                    </div>
                  </div>
                )}

                {repoType === 'github' && (
                  <div className="space-y-1.5">
                    <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.gitSetup.step2.usernameOrgLabel')}</label>
                    <input
                      type="text"
                      placeholder={t('settings.gitSetup.step2.usernamePlaceholderGithub')}
                      value={repoUsername}
                      onChange={e => {
                        setRepoUsername(e.target.value);
                        setConnectionStatus(null);
                      }}
                      className={cn(
                        "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all",
                        theme === 'dark'
                          ? "bg-zinc-900 border-zinc-800 text-zinc-200 placeholder-zinc-700 focus:border-zinc-700"
                          : "bg-white border-zinc-200 text-zinc-900 placeholder-zinc-400 focus:border-zinc-300"
                      )}
                    />
                  </div>
                )}

                <div className="space-y-1.5">
                  <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">
                    {repoType === 'github'
                      ? t('settings.gitSetup.step2.tokenLabelPat')
                      : repoType === 'gitlab'
                        ? t('settings.gitSetup.step2.tokenLabelPrivate')
                        : bitbucketServerUrl
                          ? t('settings.gitSetup.step2.tokenLabelPat')
                          : t('settings.gitSetup.step2.tokenLabelAppPassword')}
                  </label>
                  <input
                    type="password"
                    placeholder={repoType === 'github' ? 'ghp_...' : repoType === 'gitlab' ? 'glpat-...' : bitbucketServerUrl ? t('settings.gitSetup.step2.tokenPlaceholderPatEnter') : t('settings.gitSetup.step2.tokenPlaceholderAppPasswordEnter')}
                    value={repoToken}
                    onChange={e => {
                      setRepoToken(e.target.value);
                      setConnectionStatus(null);
                    }}
                    className={cn(
                      "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all font-mono",
                      theme === 'dark'
                        ? "bg-zinc-900 border-zinc-800 text-zinc-200 placeholder-zinc-700 focus:border-zinc-700"
                        : "bg-white border-zinc-200 text-zinc-900 placeholder-zinc-400 focus:border-zinc-300"
                    )}
                  />
                </div>
              </div>
            )}

            {/* Connection feedback */}
            {connectionStatus === 'success' && (
              <div className="flex items-center gap-2 p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 text-emerald-500 text-xs font-semibold animate-in fade-in duration-200">
                <Check className="w-4.5 h-4.5 stroke-[3px] text-emerald-500 border border-emerald-500 rounded-full p-0.5 shrink-0" />
                <span>{t('settings.gitSetup.step2.connectionSuccessHint')}</span>
              </div>
            )}

            {connectionStatus === 'error' && (
              <div className="flex items-start gap-2 p-3 rounded-lg border border-red-500/20 bg-red-500/5 text-red-650 dark:text-red-400 text-xs font-medium animate-in fade-in duration-200">
                <X className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p className="font-bold">{t('settings.gitSetup.step2.connectionErrorTitle')}</p>
                  <p className="text-[10px] font-mono leading-tight">{connectionError}</p>
                </div>
              </div>
            )}

            <div className="flex justify-between items-center pt-3 border-t border-zinc-800/20">
              <Button
                type="button"
                onClick={() => setWizardStep(1)}
                className="h-8 text-xs font-semibold px-3 rounded-lg flex items-center gap-1 bg-black text-white hover:bg-zinc-800 border-0"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>{t('common.back')}</span>
              </Button>

              <div className="flex gap-2">
                <Button
                  type="button"
                  disabled={isTestingConnection}
                  onClick={handleTestConnection}
                  className={cn(
                    "h-8 text-xs font-bold px-3.5 rounded-lg flex items-center gap-1.5 transition-all shadow-md",
                    connectionStatus === 'success'
                      ? "bg-zinc-800/20 text-zinc-500 border border-zinc-700/30 hover:bg-zinc-850 cursor-default"
                      : "bg-indigo-650 hover:bg-indigo-600 text-white shadow-indigo-650/10"
                  )}
                >
                  {isTestingConnection ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>{t('settings.gitSetup.step2.checking')}</span>
                    </>
                  ) : (
                    <span>{repoType === 'public' ? t('settings.gitSetup.step2.verify') : t('settings.gitSetup.step2.testConnection')}</span>
                  )}
                </Button>

                <Button
                  type="button"
                  disabled={connectionStatus !== 'success'}
                  onClick={handleNextStep}
                  className="bg-indigo-650 hover:bg-indigo-600 disabled:opacity-40 text-white rounded-lg px-4 h-8 text-xs font-semibold flex items-center gap-1 shadow-lg shadow-indigo-600/10"
                >
                  <span>{t('common.next')}</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Select Repository */}
        {wizardStep === 3 && (
          <div className="space-y-4 animate-in fade-in duration-200">
            <div className="space-y-1 text-center">
              <h5 className={cn("text-sm font-bold", theme === 'dark' ? "text-zinc-100" : "text-zinc-850")}>{t('settings.gitSetup.step3.title')}</h5>
              <p className={cn("text-[11px]", theme === 'dark' ? "text-zinc-450" : "text-zinc-500")}>
                {t('settings.gitSetup.step3.description')}
              </p>
            </div>

            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
              <input
                type="text"
                placeholder={t('settings.gitSetup.step3.filterPlaceholder')}
                value={repoSearchQuery}
                onChange={e => setRepoSearchQuery(e.target.value)}
                className={cn(
                  "w-full border rounded-lg pl-8 pr-3 py-1.5 text-xs focus:outline-none transition-all",
                  theme === 'dark'
                    ? "bg-zinc-900 border-zinc-800 text-zinc-200 placeholder-zinc-700 focus:border-zinc-700"
                    : "bg-white border-zinc-200 text-zinc-900 placeholder-zinc-400 focus:border-zinc-300"
                )}
              />
            </div>

            <ScrollArea className="h-44 border rounded-lg overflow-hidden p-1.5 transition-colors">
              {isLoadingRepos ? (
                <div className="h-32 flex flex-col items-center justify-center gap-2 text-xs text-zinc-500">
                  <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
                  <span>{t('settings.gitSetup.step3.fetchingList')}</span>
                </div>
              ) : fetchedRepos.length === 0 ? (
                <div className="h-32 flex items-center justify-center text-xs italic text-zinc-500">
                  {t('settings.gitSetup.step3.noReposFound')}
                </div>
              ) : (
                <div className="space-y-1">
                  {fetchedRepos
                    .filter((r: any) =>
                      r.name.toLowerCase().includes(repoSearchQuery.toLowerCase()) ||
                      r.full_name.toLowerCase().includes(repoSearchQuery.toLowerCase())
                    )
                    .map((r: any) => {
                      const isSelected = selectedRepoFullName === r.full_name;
                      return (
                        <button
                          key={r.full_name}
                          type="button"
                          onClick={() => handleSelectRepoInWizard(r.full_name)}
                          className={cn(
                            "w-full text-left px-3 py-2 rounded-lg text-xs transition-all flex items-center justify-between border",
                            isSelected
                              ? (theme === 'dark' ? "bg-indigo-500/10 border-indigo-500 text-indigo-400 font-semibold" : "bg-indigo-50/50 border-indigo-600 text-indigo-650 font-semibold")
                              : (theme === 'dark' ? "bg-transparent border-transparent text-zinc-400 hover:bg-zinc-900/60 hover:text-zinc-200" : "bg-transparent border-transparent text-zinc-700 hover:bg-zinc-100/80 hover:text-zinc-900")
                          )}
                        >
                          <div className="min-w-0 flex-1 pr-2">
                            <p className={theme === 'dark' ? "text-zinc-200" : "text-zinc-800"}>{r.name}</p>
                            <p className="text-[10px] text-zinc-500 font-mono truncate">{r.full_name}</p>
                          </div>
                          {isSelected && <Check className="w-3.5 h-3.5 text-indigo-500 shrink-0 stroke-[3px]" />}
                        </button>
                      );
                    })}
                </div>
              )}
            </ScrollArea>

            <div className="flex justify-between items-center pt-3 border-t border-zinc-800/20">
              <Button
                type="button"
                onClick={() => setWizardStep(2)}
                className="h-8 text-xs font-semibold px-3 rounded-lg flex items-center gap-1 bg-black text-white hover:bg-zinc-800 border-0"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>{t('common.back')}</span>
              </Button>

              <Button
                type="button"
                disabled={!selectedRepoFullName}
                onClick={handleNextStep}
                className="bg-indigo-650 hover:bg-indigo-600 disabled:opacity-40 text-white rounded-lg px-4 h-8 text-xs font-semibold flex items-center gap-1 shadow-lg shadow-indigo-600/10"
              >
                <span>{t('common.next')}</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 4: Branch Selection */}
        {wizardStep === 4 && (
          <div className="space-y-4 animate-in fade-in duration-200">
            <div className="space-y-1 text-center">
              <h5 className={cn("text-sm font-bold", theme === 'dark' ? "text-zinc-100" : "text-zinc-850")}>{t('settings.gitSetup.step4.title')}</h5>
              <p className={cn("text-[11px]", theme === 'dark' ? "text-zinc-450" : "text-zinc-500")}>
                {t('settings.gitSetup.step4.description')}
              </p>
            </div>

            <div className="space-y-3 p-3 rounded-lg border transition-all bg-indigo-500/[0.02] border-indigo-500/10">
              <div className="flex items-center gap-2 text-xs font-semibold">
                <GitBranch className="w-4 h-4 text-indigo-500 shrink-0" />
                <span className={theme === 'dark' ? "text-zinc-200" : "text-zinc-800"}>{t('settings.gitSetup.step4.repositoryLabel')}</span>
                <span className="font-mono text-zinc-500 truncate max-w-[200px]">
                  {repoType === 'public' ? (newRepoUrl.split('/').pop()?.replace(/\.git$/, "") || newRepoUrl) : selectedRepoFullName}
                </span>
              </div>

              <div className="space-y-1.5">
                <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.gitSetup.step4.targetBranchLabel')}</label>

                {isLoadingBranches ? (
                  <div className="h-10 flex items-center gap-2 text-xs text-zinc-500 pl-2">
                    <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
                    <span>{t('settings.gitSetup.step4.fetchingBranches')}</span>
                  </div>
                ) : fetchedBranches.length > 0 ? (
                  <Select value={selectedBranchName} onValueChange={setSelectedBranchName}>
                    <SelectTrigger className={cn(
                      "w-full h-8 text-xs focus:ring-0 font-mono",
                      theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-350" : "bg-white border-zinc-200 text-zinc-750"
                    )}>
                      <SelectValue placeholder={t('settings.gitSetup.step4.selectBranchPlaceholder')} />
                    </SelectTrigger>
                    <SelectContent className={theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-200" : "bg-white border-zinc-200 text-zinc-850"}>
                      {fetchedBranches.map((br) => (
                        <SelectItem key={br} value={br} className="font-mono text-xs">{br}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <div className="space-y-1">
                    <input
                      type="text"
                      placeholder="main"
                      value={selectedBranchName}
                      onChange={e => setSelectedBranchName(e.target.value)}
                      className={cn(
                        "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all font-mono",
                        theme === 'dark'
                          ? "bg-zinc-900 border-zinc-800 text-zinc-200 placeholder-zinc-700 focus:border-zinc-700"
                          : "bg-white border-zinc-200 text-zinc-900 placeholder-zinc-400 focus:border-zinc-300"
                      )}
                    />
                    <p className="text-[9px] text-zinc-500 pl-0.5">
                      {t('settings.gitSetup.step4.manualBranchHint')}
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="flex justify-between items-center pt-3 border-t border-zinc-800/20">
              <Button
                type="button"
                onClick={() => {
                  if (repoType === 'public') {
                    setWizardStep(2);
                  } else {
                    setWizardStep(3);
                  }
                }}
                className="h-8 text-xs font-semibold px-3 rounded-lg flex items-center gap-1 bg-black text-white hover:bg-zinc-800 border-0"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>{t('common.back')}</span>
              </Button>

              <Button
                type="button"
                onClick={handleWizardSubmit}
                className="bg-indigo-650 hover:bg-indigo-600 text-white rounded-lg px-4 h-8 text-xs font-semibold flex items-center gap-1.5 shadow-lg shadow-indigo-600/10"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>{t('settings.gitSetup.step4.addAndIndex')}</span>
              </Button>
            </div>
          </div>
        )}

        {/* Step 5: Success Completion Feedback Screen */}
        {wizardStep === 5 && (
          <div className="space-y-6 text-center animate-in fade-in duration-300 py-4 max-w-md mx-auto">
            <div className="flex flex-col items-center gap-3">
              <div className="w-14 h-14 rounded-full bg-emerald-500/10 border border-emerald-500 flex items-center justify-center text-emerald-500 shadow-lg shadow-emerald-500/10 animate-bounce">
                <Check className="w-8 h-8 stroke-[3.5px]" />
              </div>
              <h5 className={cn("text-base font-extrabold tracking-tight", theme === 'dark' ? "text-zinc-100" : "text-zinc-900")}>
                {t('settings.gitSetup.step5.title')}
              </h5>
              <p className={cn("text-xs leading-relaxed max-w-sm", theme === 'dark' ? "text-zinc-400" : "text-zinc-650")}>
                {t('settings.gitSetup.step5.description')}
              </p>
            </div>

            <div className={cn(
              "p-4 rounded-lg border text-left space-y-2 text-xs transition-all",
              theme === 'dark' ? "bg-zinc-900/40 border-zinc-800" : "bg-white border-zinc-200 shadow-sm"
            )}>
              <div className="flex items-center justify-between border-b pb-2 border-zinc-800/20">
                <span className="text-zinc-500 font-bold uppercase text-[9px]">{t('settings.gitSetup.step5.statusLabel')}</span>
                <span className="bg-emerald-500/15 text-emerald-505 text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider animate-pulse">
                  {t('settings.gitSetup.step5.parsingStarted')}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-1 pt-1">
                <span className="text-zinc-500 font-semibold text-[10px]">{t('settings.gitSetup.step5.repositoryLabel')}</span>
                <span className={cn("col-span-2 font-semibold truncate", theme === 'dark' ? "text-zinc-200" : "text-zinc-800")}>
                  {newRepoName}
                </span>

                <span className="text-zinc-500 font-semibold text-[10px]">{t('settings.gitSetup.step5.gitSourceLabel')}</span>
                <span className={cn("col-span-2 capitalize font-semibold", theme === 'dark' ? "text-zinc-355" : "text-zinc-700")}>
                  {repoType === 'public' ? t('settings.gitSetup.step5.public') : repoType}
                </span>

                <span className="text-zinc-500 font-semibold text-[10px]">{t('settings.gitSetup.step5.targetBranchLabel')}</span>
                <span className="col-span-2 font-mono text-[10px] text-indigo-500 bg-indigo-500/5 border border-indigo-500/10 px-1 rounded w-fit">
                  {selectedBranchName}
                </span>
              </div>
            </div>

            <div className="pt-2 flex justify-center">
              <Button
                type="button"
                onClick={onDone}
                className="bg-indigo-650 hover:bg-indigo-600 text-white rounded-lg px-6 h-9 text-xs font-semibold shadow-lg shadow-indigo-655/15 transition-all"
              >
                {t('settings.gitSetup.step5.finishAndClose')}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
