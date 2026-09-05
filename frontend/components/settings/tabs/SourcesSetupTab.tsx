"use client";

import React, { useState } from 'react';
import { Loader2, ClipboardList, Wrench, Folder, Building2, Plus, Send } from 'lucide-react';
import { cn } from "@/lib/utils";
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import { GitSetupTab } from './GitSetupTab';

// Aus SettingsModal herausgelöster 'sources-setup'-Tab (docs/TECH_DEBT_CLEANUP_PLAN.md
// §5, Schritt 2). Der Wissensquellen-Anlege-Wizard wird aus dem sources-Tab heraus
// betreten (der setzt activeSourceType + selectedSourceRepoId und navigiert hierher),
// daher kommen beide als Props. Alle Wizard-Formularzustände + Connect-Handler sind
// lokal; onDone kapselt "activeSourceType zurücksetzen + zurück zu sources". Neue
// Quellen werden an die geteilte connectedSources-Liste (Context) angehängt.
interface SourcesSetupTabProps {
  activeSourceType: string;
  selectedSourceRepoId: string;
  onDone: () => void;
}

export const SourcesSetupTab: React.FC<SourcesSetupTabProps> = ({ activeSourceType, selectedSourceRepoId, onDone }) => {
  const { t } = useLanguage();
  const { theme, showToast, setConnectedSources, projects } = useSettings();

  const [sourceInstanceName, setSourceInstanceName] = useState("");
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceUsername, setSourceUsername] = useState("");
  const [sourceToken, setSourceToken] = useState("");
  const [sourceSpaces, setSourceSpaces] = useState("");
  const [isConnectingSource, setIsConnectingSource] = useState(false);
  const [isTestingSourceConn, setIsTestingSourceConn] = useState(false);
  const [sourceConnStatus, setSourceConnStatus] = useState<'success' | 'error' | null>(null);
  const [sourceConnError, setSourceConnError] = useState("");
  const [folderPath, setFolderPath] = useState("/watched");
  const [folderName, setFolderName] = useState("");
  const [isConnectingFolder, setIsConnectingFolder] = useState(false);

  const handleConnectSource = async () => {
    if (!sourceInstanceName) {
      showToast(t('settings.toast.nameRequired'), "error");
      return;
    }

    let typeCode = "";
    if (activeSourceType === "Confluence") typeCode = "confluence";
    else if (activeSourceType === "Jira Software") typeCode = "jira";
    else return;

    if (!sourceUrl) {
      showToast(t('settings.toast.serverUrlRequired'), "error");
      return;
    }
    if (!sourceToken) {
      showToast(t('settings.toast.apiTokenRequired'), "error");
      return;
    }

    setIsConnectingSource(true);
    try {
      const parsedSpaces = sourceSpaces
        ? sourceSpaces.split(",").map(s => s.trim()).filter(Boolean)
        : ["ALL"];

      const spacesPayload = parsedSpaces;

      const payload = {
        name: sourceInstanceName,
        type: typeCode,
        url: sourceUrl || null,
        username: sourceUsername || null,
        token: sourceToken || null,
        project_id: selectedSourceRepoId === "all" ? null : parseInt(selectedSourceRepoId),
        spaces: spacesPayload
      };

      const res = await api.createKnowledgeSource(payload);
      setConnectedSources(prev => [...prev, res.data]);
      showToast(t('settings.toast.sourceConnected', { type: activeSourceType }), "success");
      onDone();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.sourceConnectFailed', { type: activeSourceType }), "error");
    } finally {
      setIsConnectingSource(false);
    }
  };

  const handleTestSourceConnection = async () => {
    setIsTestingSourceConn(true);
    setSourceConnStatus(null);
    setSourceConnError("");

    let typeCode = "";
    if (activeSourceType === "Confluence") typeCode = "confluence";
    else if (activeSourceType === "Jira Software") typeCode = "jira";
    else {
      setIsTestingSourceConn(false);
      return;
    }

    if (!sourceUrl) {
      setSourceConnStatus('error');
      setSourceConnError(t('settings.toast.serverUrlRequired'));
      showToast(t('settings.toast.serverUrlRequired'), "error");
      setIsTestingSourceConn(false);
      return;
    }
    if (!sourceToken) {
      setSourceConnStatus('error');
      setSourceConnError(t('settings.toast.apiTokenRequired'));
      showToast(t('settings.toast.apiTokenRequired'), "error");
      setIsTestingSourceConn(false);
      return;
    }

    try {
      const res = await api.testConnector({
        type: typeCode,
        url: sourceUrl || undefined,
        username: sourceUsername || undefined,
        token: sourceToken
      });

      if (res.data && res.data.success) {
        setSourceConnStatus('success');
        showToast(res.data.message || t('settings.toast.connectionEstablished'), "success");
      } else {
        setSourceConnStatus('error');
        setSourceConnError(res.data.message || t('settings.toast.connectionFailed'));
        showToast(res.data.message || t('settings.toast.connectionFailed'), "error");
      }
    } catch (err: any) {
      console.error(err);
      setSourceConnStatus('error');
      setSourceConnError(err.response?.data?.detail || t('settings.toast.networkTestError'));
      showToast(t('settings.toast.connectionFailed'), "error");
    } finally {
      setIsTestingSourceConn(false);
    }
  };

  const handleFileUpload = async () => {
    if (!selectedUploadFile) return;
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', selectedUploadFile);
      formData.append('name', selectedUploadFile.name);
      if (selectedSourceRepoId !== 'all') {
        formData.append('project_id', selectedSourceRepoId);
      }

      const res = await api.uploadLocalDocument(formData);
      setConnectedSources(prev => [...prev, res.data]);
      showToast(t('settings.toast.documentUploaded'), "success");
      onDone();
    } catch (err: any) {
      console.error(err);
      showToast(err?.response?.data?.detail || t('settings.toast.documentUploadFailed'), "error");
    } finally {
      setIsUploading(false);
      setSelectedUploadFile(null);
    }
  };

  const handleConnectFolderWatch = async () => {
    if (!folderName.trim() || !folderPath.trim()) return;
    setIsConnectingFolder(true);
    try {
      const res = await api.createFolderWatchSource({
        name: folderName.trim(),
        folder_path: folderPath.trim(),
        project_id: selectedSourceRepoId !== 'all' ? parseInt(selectedSourceRepoId) : null,
      });
      setConnectedSources(prev => [...prev, res.data]);
      showToast(t('settings.toast.sourceConnected', { type: t('settings.sourcesTab.types.folderwatch.name') }), "success");
      setFolderPath("/watched");
      setFolderName("");
      onDone();
    } catch (err: any) {
      showToast(err?.response?.data?.detail || t('settings.toast.sourceConnectFailed', { type: t('settings.sourcesTab.types.folderwatch.name') }), "error");
    } finally {
      setIsConnectingFolder(false);
    }
  };

  if (activeSourceType === "Git") {
    return <GitSetupTab targetProjectId={selectedSourceRepoId === "all" ? null : parseInt(selectedSourceRepoId)} onDone={onDone} />;
  }

  return (
    <div className="space-y-4 animate-in fade-in duration-200">
      <div className="flex items-center justify-between">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>
          {activeSourceType === t('settings.sourcesTab.types.local.name')
            ? t('settings.sourcesSetup.uploadDocsTitle')
            : activeSourceType === t('settings.sourcesTab.types.folderwatch.name')
              ? t('settings.sourcesSetup.folderWatchTitle')
              : t('settings.sourcesSetup.setupWizardTitle', { type: activeSourceType })}
        </h4>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onDone}
          className={cn("h-7 text-xs font-semibold px-2.5 rounded-lg transition-all", theme === 'dark' ? "text-ds-zinc-500 hover:text-ds-zinc-350 hover:bg-ds-zinc-800" : "text-ds-zinc-450 hover:text-ds-zinc-800 hover:bg-ds-zinc-100")}
        >
          {t('common.cancel')}
        </Button>
      </div>

      <div className={cn(
        "border rounded-lg p-4 sm:p-5 transition-all space-y-5",
        theme === 'dark' ? "bg-ds-zinc-950/40 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
      )}>
        {activeSourceType === t('settings.sourcesTab.types.folderwatch.name') ? (
          <div className="space-y-5 animate-in fade-in duration-250">
            <div className="space-y-1.5">
              <h5 className={cn("text-sm font-bold", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")}>{t('settings.sourcesSetup.folderWatchTitle')}</h5>
              <p className={cn("text-[11px]", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-555")}>
                {t('settings.sourcesSetup.folderWatchDesc')}
              </p>
            </div>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-[10px] font-bold text-ds-zinc-500 uppercase px-0.5">{t('settings.sourcesSetup.folderNameLabel')}</label>
                <input
                  type="text"
                  placeholder={t('settings.sourcesSetup.folderNamePlaceholder')}
                  value={folderName}
                  onChange={e => setFolderName(e.target.value)}
                  className={cn(
                    "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all",
                    theme === 'dark'
                      ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200 placeholder-zinc-700 focus:border-ds-zinc-700"
                      : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900 placeholder-zinc-400 focus:border-ds-zinc-300"
                  )}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-[10px] font-bold text-ds-zinc-500 uppercase px-0.5">{t('settings.sourcesSetup.folderPathLabel')}</label>
                <input
                  type="text"
                  placeholder={t('settings.sourcesSetup.folderPathPlaceholder')}
                  value={folderPath}
                  onChange={e => setFolderPath(e.target.value)}
                  className={cn(
                    "w-full border rounded-lg px-3 py-1.5 text-xs font-mono focus:outline-none transition-all",
                    theme === 'dark'
                      ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200 placeholder-zinc-700 focus:border-ds-zinc-700"
                      : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900 placeholder-zinc-400 focus:border-ds-zinc-300"
                  )}
                />
              </div>
            </div>
            <div className="flex justify-end pt-2 border-t border-ds-zinc-800/10">
              <Button
                type="button"
                disabled={isConnectingFolder || !folderName.trim() || !folderPath.trim()}
                onClick={handleConnectFolderWatch}
                className={cn(
                  "h-8 text-xs font-semibold px-4 rounded-lg flex items-center gap-1.5 transition-all",
                  theme === 'dark'
                    ? "bg-ds-emerald-600 hover:bg-ds-emerald-500 text-ds-white disabled:opacity-40"
                    : "bg-ds-emerald-600 hover:bg-ds-emerald-700 text-ds-white disabled:opacity-40"
                )}
              >
                {isConnectingFolder ? (
                  <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>{t('settings.sourcesSetup.folderConnecting')}</span></>
                ) : (
                  <><Folder className="w-3.5 h-3.5" /><span>{t('settings.sourcesSetup.folderConnect')}</span></>
                )}
              </Button>
            </div>
          </div>
        ) : activeSourceType === t('settings.sourcesTab.types.local.name') ? (
          <div className="space-y-5 animate-in fade-in duration-250">
            <div className="space-y-1.5">
              <h5 className={cn("text-sm font-bold", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")}>{t('settings.sourcesSetup.selectFileTitle')}</h5>
              <p className={cn("text-[11px]", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-555")}>
                {t('settings.sourcesSetup.selectFileDesc', { project: selectedSourceRepoId === 'all' ? t('settings.sourcesTab.global') : (projects.find((p: any) => p.id.toString() === selectedSourceRepoId)?.name || '') })}
              </p>
            </div>

            <div
              className={cn(
                "border-2 border-dashed rounded-lg p-8 flex flex-col items-center justify-center text-center gap-3 transition-all relative",
                theme === 'dark'
                  ? "bg-ds-zinc-900/40 border-ds-zinc-800 hover:border-ds-indigo-500/50 hover:bg-ds-zinc-900/60"
                  : "bg-ds-white border-ds-zinc-200 hover:border-ds-indigo-400 hover:bg-ds-zinc-50/50"
              )}
            >
              <div className={cn(
                "w-12 h-12 rounded-full flex items-center justify-center",
                theme === 'dark' ? "bg-ds-indigo-500/10 text-ds-indigo-400" : "bg-ds-indigo-50 text-ds-indigo-600"
              )}>
                <Plus className="w-6 h-6" />
              </div>

              <div className="space-y-1">
                <p className={cn("text-xs font-bold", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")}>
                  {selectedUploadFile ? selectedUploadFile.name : t('settings.sourcesSetup.dropzoneText')}
                </p>
                <p className="text-[10px] text-ds-zinc-500">{t('settings.sourcesSetup.dropzoneHint')}</p>
              </div>

              <input
                type="file"
                accept=".pdf,.md,.txt,.docx,.doc"
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    setSelectedUploadFile(e.target.files[0]);
                  }
                }}
              />
            </div>

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setSelectedUploadFile(null);
                  onDone();
                }}
                className={cn("h-9 text-xs font-semibold px-4 rounded-lg", theme === 'dark' ? "text-ds-zinc-400 hover:bg-ds-zinc-800" : "text-ds-zinc-550 hover:bg-ds-zinc-100")}
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="button"
                disabled={!selectedUploadFile || isUploading}
                onClick={handleFileUpload}
                className="bg-ds-indigo-650 hover:bg-ds-indigo-600 text-ds-white rounded-lg px-6 h-9 text-xs font-semibold shadow-md flex items-center gap-2"
              >
                {isUploading ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>{t('settings.sourcesSetup.uploading')}</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>{t('settings.sourcesSetup.uploadAndIndex')}</span>
                  </>
                )}
              </Button>
            </div>
          </div>
        ) : (
          <>
            {/* Functional Integration connection forms */}
            <div className="space-y-4 animate-in fade-in duration-200">
              <p className={cn("text-xs", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>
                {t('settings.sourcesSetup.integrationSetupDesc', { type: activeSourceType })}
              </p>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-ds-zinc-500 uppercase px-0.5">{t('settings.sourcesSetup.integrationNameLabel')}</label>
                  <input
                    type="text"
                    placeholder={t('settings.sourcesSetup.integrationNamePlaceholder', { type: activeSourceType })}
                    value={sourceInstanceName}
                    onChange={e => setSourceInstanceName(e.target.value)}
                    className={cn(
                      "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all",
                      theme === 'dark'
                        ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200 placeholder-zinc-700 focus:border-ds-zinc-700"
                        : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900 placeholder-zinc-400 focus:border-ds-zinc-300"
                    )}
                  />
                </div>

                {(
                  <>
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-bold text-ds-zinc-500 uppercase px-0.5">{t('settings.sourcesSetup.serverUrlLabel')}</label>
                      <input
                        type="text"
                        placeholder={activeSourceType === "Jira Software" ? "https://jira.company.com" : "https://company.atlassian.net"}
                        value={sourceUrl}
                        onChange={e => setSourceUrl(e.target.value)}
                        className={cn(
                          "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all",
                          theme === 'dark'
                            ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200 placeholder-zinc-700 focus:border-ds-zinc-700"
                            : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900 placeholder-zinc-400 focus:border-ds-zinc-300"
                        )}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-bold text-ds-zinc-500 uppercase px-0.5">{t('settings.sourcesSetup.emailUsernameLabel')}</label>
                      <input
                        type="text"
                        placeholder="user@company.com"
                        value={sourceUsername}
                        onChange={e => setSourceUsername(e.target.value)}
                        className={cn(
                          "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all",
                          theme === 'dark'
                            ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200 placeholder-zinc-700 focus:border-ds-zinc-700"
                            : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900 placeholder-zinc-400 focus:border-ds-zinc-300"
                        )}
                      />
                    </div>
                  </>
                )}

                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-ds-zinc-500 uppercase px-0.5">
                    {t('settings.sourcesSetup.apiTokenPasswordLabel')}
                  </label>
                  <input
                    type="password"
                    placeholder={t('settings.sourcesSetup.tokenPlaceholder')}
                    value={sourceToken}
                    onChange={e => setSourceToken(e.target.value)}
                    className={cn(
                      "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all",
                      theme === 'dark'
                        ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200 placeholder-zinc-700 focus:border-ds-zinc-700"
                        : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900 placeholder-zinc-400 focus:border-ds-zinc-300"
                    )}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-ds-zinc-500 uppercase px-0.5">
                    {t('settings.sourcesSetup.spacesProjectKeysLabel')}
                  </label>
                  <input
                    type="text"
                    placeholder={t('settings.sourcesSetup.spacesProjectKeysPlaceholder')}
                    value={sourceSpaces}
                    onChange={e => setSourceSpaces(e.target.value)}
                    className={cn(
                      "w-full border rounded-lg px-3 py-1.5 text-xs focus:outline-none transition-all",
                      theme === 'dark'
                        ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200 placeholder-zinc-700 focus:border-ds-zinc-700"
                        : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900 placeholder-zinc-400 focus:border-ds-zinc-300"
                    )}
                  />
                </div>
              </div>
              <div className="flex flex-col gap-2 pt-2 border-t border-ds-zinc-800/10 w-full">
                <div className="flex justify-end gap-2 w-full">
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={isConnectingSource}
                    onClick={onDone}
                    className={cn("h-9 text-xs font-semibold px-4 rounded-lg", theme === 'dark' ? "text-ds-zinc-400 hover:bg-ds-zinc-800" : "text-ds-zinc-550 hover:bg-ds-zinc-100")}
                  >
                    {t('common.cancel')}
                  </Button>
                  <Button
                    type="button"
                    disabled={isTestingSourceConn || isConnectingSource}
                    onClick={handleTestSourceConnection}
                    className={cn(
                      "h-9 text-xs font-semibold px-4 rounded-lg flex items-center gap-1.5 transition-all shadow-md border",
                      sourceConnStatus === 'success'
                        ? "bg-ds-green-600 hover:bg-ds-green-500 text-ds-white border-ds-green-600 shadow-ds-green-650/10"
                        : theme === 'dark'
                          ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-indigo-400 hover:bg-ds-zinc-800 hover:text-ds-indigo-350"
                          : "bg-ds-white border-ds-zinc-200 text-ds-indigo-600 hover:bg-ds-zinc-50 hover:text-ds-indigo-700"
                    )}
                  >
                    {isTestingSourceConn ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>{t('settings.sourcesSetup.checking')}</span>
                      </>
                    ) : sourceConnStatus === 'success' ? (
                      <span>{t('settings.sourcesSetup.connectionSuccess')}</span>
                    ) : (
                      <span>{t('settings.sourcesSetup.testConnection')}</span>
                    )}
                  </Button>
                  <Button
                    type="button"
                    disabled={isConnectingSource}
                    onClick={handleConnectSource}
                    className="bg-ds-indigo-650 hover:bg-ds-indigo-600 text-ds-white rounded-lg px-6 h-9 text-xs font-semibold shadow-md flex items-center gap-2"
                  >
                    {isConnectingSource ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>{t('settings.sourcesSetup.connecting')}</span>
                      </>
                    ) : (
                      <span>{t('settings.sourcesSetup.connect')}</span>
                    )}
                  </Button>
                </div>
                {sourceConnStatus === 'error' && sourceConnError && (
                  <div className="text-[10px] text-ds-red-500 text-right w-full mt-1 font-medium animate-in fade-in slide-in-from-top-1 duration-200">
                    {sourceConnError}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
