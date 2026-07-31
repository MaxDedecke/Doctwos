"use client";

import React, { useState } from 'react';
import { Plus, Edit, Trash2 } from 'lucide-react';
import { cn } from "@/lib/utils";
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useFeatures } from '@/lib/FeaturesContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Aus SettingsModal herausgelöster 'ai'-Tab (docs/TECH_DEBT_CLEANUP_PLAN.md §5,
// Schritt 2). Die LLM-Profil-Formularzustände lagen zuvor auf Modal-Ebene, wurden
// aber ausschließlich von diesem Tab genutzt und sind jetzt hier lokal gekapselt.
// Die zugehörigen Handler (Add/Edit/Delete/Save Profile, Save AI-Params) sind
// mitgewandert. Global geteilte LLM-Settings (llmProfiles, activeProfileId,
// temperature, systemPrompt) kommen weiterhin via useSettings() aus dem Context.
export const AiSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const features = useFeatures();
  const {
    theme,
    showToast,
    temperature,
    setTemperature,
    systemPrompt,
    setSystemPrompt,
    llmProfiles,
    setLlmProfiles,
    activeProfileId,
    setActiveProfileId,
  } = useSettings();

  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [profileNameInput, setProfileNameInput] = useState("");
  const [profileProviderInput, setProfileProviderInput] = useState("ollama");
  const [profileModelInput, setProfileModelInput] = useState("");
  const [profileApiKeyInput, setProfileApiKeyInput] = useState("");
  const [profileBaseUrlInput, setProfileBaseUrlInput] = useState("");
  const [showProfileForm, setShowProfileForm] = useState(false);

  const handleStartAddProfile = () => {
    setEditingProfileId(null);
    setProfileNameInput("");
    setProfileProviderInput("ollama");
    setProfileModelInput("qwen2.5:1.5b");
    setProfileApiKeyInput("");
    setProfileBaseUrlInput("");
    setShowProfileForm(true);
  };

  const handleStartEditProfile = (prof: any) => {
    setEditingProfileId(prof.id);
    setProfileNameInput(prof.name);
    setProfileProviderInput(prof.provider);
    setProfileModelInput(prof.model);
    setProfileApiKeyInput(prof.apiKey || "");
    setProfileBaseUrlInput(prof.baseUrl || "");
    setShowProfileForm(true);
  };

  const handleDeleteProfile = (id: string) => {
    if (llmProfiles.length <= 1) {
      showToast(t('settings.toast.lastProfileCannotDelete'), "error");
      return;
    }
    const updated = llmProfiles.filter(p => p.id !== id);
    setLlmProfiles(updated);
    localStorage.setItem('doctus-llm-profiles', JSON.stringify(updated));
    if (activeProfileId === id) {
      const nextActiveId = updated[0].id;
      setActiveProfileId(nextActiveId);
      localStorage.setItem('doctus-active-profile-id', nextActiveId);
    }
    showToast(t('settings.toast.profileDeleted'), "success");
  };

  const handleSaveProfile = () => {
    if (!profileNameInput.trim()) {
      showToast(t('settings.toast.profileNameRequired'), "error");
      return;
    }
    if (!profileModelInput.trim()) {
      showToast(t('settings.toast.modelNameRequired'), "error");
      return;
    }

    let updatedProfiles = [...llmProfiles];
    if (editingProfileId) {
      // Edit
      updatedProfiles = updatedProfiles.map(p => {
        if (p.id === editingProfileId) {
          return {
            ...p,
            name: profileNameInput,
            provider: profileProviderInput,
            model: profileModelInput,
            apiKey: profileApiKeyInput,
            baseUrl: profileBaseUrlInput
          };
        }
        return p;
      });
      showToast(t('settings.toast.profileUpdated'), "success");
    } else {
      // Add
      const newProf = {
        id: "prof-" + Date.now(),
        name: profileNameInput,
        provider: profileProviderInput,
        model: profileModelInput,
        apiKey: profileApiKeyInput,
        baseUrl: profileBaseUrlInput
      };
      updatedProfiles.push(newProf);
      showToast(t('settings.toast.profileCreated'), "success");
    }

    setLlmProfiles(updatedProfiles);
    localStorage.setItem('doctus-llm-profiles', JSON.stringify(updatedProfiles));
    setShowProfileForm(false);
  };

  const handleSaveAiParams = async () => {
    try {
      // Save to active profile for profile-specific persistence
      const updatedProfiles = llmProfiles.map(p => {
        if (p.id === activeProfileId) {
          return { ...p, temperature, systemPrompt };
        }
        return p;
      });
      setLlmProfiles(updatedProfiles);
      localStorage.setItem('doctus-llm-profiles', JSON.stringify(updatedProfiles));

      const activeProfile = updatedProfiles.find(p => p.id === activeProfileId);
      if (activeProfile && activeProfile.provider === 'ollama') {
        await api.updateModelInfo({
          llm: activeProfile.model
        });
      }
      showToast(t('settings.toast.aiParamsSaved'), "success");
    } catch (err) {
      console.error("Failed to save model info:", err);
      showToast(t('settings.toast.aiParamsSaveFailed'), "error");
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200 w-full min-w-0">
      <div className="space-y-3">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-zinc-400" : "text-zinc-500")}>{t('settings.profilesTab.title')}</h4>
        <p className={cn("text-xs leading-relaxed", theme === 'dark' ? "text-zinc-450" : "text-zinc-500")}>
          {t('settings.profilesTab.description')}
        </p>
      </div>

      {/* Profiles Manager list / view */}
      <div className={cn(
        "space-y-4 border rounded-lg p-4 transition-colors",
        theme === 'dark' ? "bg-zinc-950/40 border-zinc-800" : "bg-zinc-50 border-zinc-200"
      )}>

        {!showProfileForm ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">{t('settings.profilesTab.configuredProfiles')}</span>
              <Button
                type="button"
                size="sm"
                onClick={handleStartAddProfile}
                className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold px-3 h-7 flex items-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>{t('settings.profilesTab.addProfile')}</span>
              </Button>
            </div>

            <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
              {llmProfiles.map((prof) => {
                const isActive = activeProfileId === prof.id;
                return (
                  <div
                    key={prof.id}
                    className={cn(
                      "p-3 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-all",
                      isActive
                        ? (theme === 'dark' ? "bg-indigo-500/10 border-indigo-500/50" : "bg-indigo-50/50 border-indigo-300")
                        : (theme === 'dark' ? "bg-zinc-900/40 border-zinc-850 hover:bg-zinc-850/60" : "bg-white border-zinc-200 hover:bg-zinc-50")
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={cn("text-xs font-semibold truncate", theme === 'dark' ? "text-zinc-200" : "text-zinc-800")}>
                          {prof.name}
                        </span>
                        {isActive && (
                          <span className={cn(
                            "text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.2 rounded border",
                            theme === 'dark' ? "bg-indigo-500/20 border-indigo-500/30 text-indigo-400" : "bg-indigo-100 border-indigo-200 text-indigo-700"
                          )}>
                            {t('settings.profilesTab.active')}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-500">
                        <span className="uppercase">{prof.provider}</span>
                        <span>•</span>
                        <span className="truncate">{prof.model}</span>
                        {prof.baseUrl && (
                          <>
                            <span>•</span>
                            <span className="truncate max-w-[120px]">{prof.baseUrl}</span>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-1 shrink-0 w-full sm:w-auto justify-end">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => handleStartEditProfile(prof)}
                        className={cn("h-7 w-7 rounded-lg", theme === 'dark' ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800" : "text-zinc-500 hover:text-zinc-800 hover:bg-zinc-150")}
                        title={t('settings.profilesTab.editProfileTitle')}
                      >
                        <Edit className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        disabled={llmProfiles.length <= 1}
                        onClick={() => handleDeleteProfile(prof.id)}
                        className={cn(
                          "h-7 w-7 rounded-lg",
                          theme === 'dark'
                            ? "text-zinc-500 hover:text-red-400 hover:bg-zinc-800 disabled:opacity-30"
                            : "text-zinc-400 hover:text-red-600 hover:bg-zinc-150 disabled:opacity-30"
                        )}
                        title={t('settings.profilesTab.deleteProfileTitle')}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="space-y-4 pt-1 animate-in fade-in slide-in-from-top-1 duration-150">
            <div className="flex items-center justify-between border-b pb-2 mb-2"
                 style={{ borderColor: theme === 'dark' ? 'rgba(63, 63, 70, 0.4)' : 'rgba(228, 228, 231, 0.6)' }}>
              <span className="text-[10px] font-bold text-indigo-500 uppercase tracking-wider">
                {editingProfileId ? t('settings.profilesTab.editProfileHeading') : t('settings.profilesTab.newProfileHeading')}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5 col-span-2 sm:col-span-1">
                <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.profilesTab.profileNameLabel')}</label>
                <input
                  type="text"
                  placeholder={t('settings.profilesTab.profileNamePlaceholder')}
                  value={profileNameInput}
                  onChange={e => setProfileNameInput(e.target.value)}
                  className={cn(
                    "w-full h-8 border rounded-lg px-2.5 text-xs focus:outline-none font-sans",
                    theme === 'dark'
                      ? "bg-zinc-900 border-zinc-800 text-zinc-200 focus:border-zinc-700"
                      : "bg-white border-zinc-200 text-zinc-900 focus:border-zinc-300"
                  )}
                />
              </div>

              <div className="space-y-1.5 col-span-2 sm:col-span-1">
                <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.profilesTab.providerLabel')}</label>
                <Select
                  value={profileProviderInput}
                  onValueChange={val => {
                    setProfileProviderInput(val);
                    const defaults = ["qwen2.5:1.5b", "gpt-4o", "gemini-1.5-flash", "claude-3-5-sonnet-20241022"];
                    if (!profileModelInput || defaults.includes(profileModelInput)) {
                      if (val === 'ollama') setProfileModelInput("qwen2.5:1.5b");
                      else if (val === 'openai') setProfileModelInput("gpt-4o");
                      else if (val === 'gemini') setProfileModelInput("gemini-1.5-flash");
                      else if (val === 'anthropic') setProfileModelInput("claude-3-5-sonnet-20241022");
                    }
                  }}
                >
                  <SelectTrigger className={cn(
                    "w-full h-8 text-xs focus:ring-0",
                    theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-300" : "bg-white border-zinc-200 text-zinc-800"
                  )}>
                    <SelectValue placeholder={t('settings.profilesTab.providerPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent className={theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-200" : "bg-white border-zinc-200 text-zinc-800"}>
                    <SelectItem value="ollama">{t('settings.profilesTab.providerOptions.ollama')}</SelectItem>
                    {features.llm.allowCloudProviders && (
                      <>
                        <SelectItem value="openai">{t('settings.profilesTab.providerOptions.openai')}</SelectItem>
                        <SelectItem value="gemini">{t('settings.profilesTab.providerOptions.gemini')}</SelectItem>
                        <SelectItem value="anthropic">{t('settings.profilesTab.providerOptions.anthropic')}</SelectItem>
                      </>
                    )}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5 col-span-2 sm:col-span-1">
                <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.profilesTab.modelNameLabel')}</label>
                <input
                  type="text"
                  placeholder={
                    profileProviderInput === 'ollama' ? "qwen2.5:1.5b" :
                    profileProviderInput === 'openai' ? "gpt-4o, gpt-3.5-turbo, etc." :
                    profileProviderInput === 'gemini' ? "gemini-1.5-flash" :
                    "claude-3-5-sonnet-20241022"
                  }
                  value={profileModelInput}
                  onChange={e => setProfileModelInput(e.target.value)}
                  className={cn(
                    "w-full h-8 border rounded-lg px-2.5 text-xs focus:outline-none font-sans",
                    theme === 'dark'
                      ? "bg-zinc-900 border-zinc-800 text-zinc-200 focus:border-zinc-700"
                      : "bg-white border-zinc-200 text-zinc-900 focus:border-zinc-300"
                  )}
                />
              </div>

              <div className="space-y-1.5 col-span-2 sm:col-span-1">
                <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">
                  {profileProviderInput === 'ollama' ? t('settings.profilesTab.apiKeyOptionalLabel') : t('settings.profilesTab.apiKeyLabel')}
                </label>
                <input
                  type="password"
                  placeholder={t('settings.profilesTab.apiKeyPlaceholder')}
                  value={profileApiKeyInput}
                  onChange={e => setProfileApiKeyInput(e.target.value)}
                  className={cn(
                    "w-full h-8 border rounded-lg px-2.5 text-xs focus:outline-none font-sans",
                    theme === 'dark'
                      ? "bg-zinc-900 border-zinc-800 text-zinc-200 focus:border-zinc-700"
                      : "bg-white border-zinc-200 text-zinc-900 focus:border-zinc-300"
                  )}
                />
              </div>
            </div>

            {profileProviderInput === 'openai' && (
              <div className="space-y-1.5 animate-in fade-in duration-100">
                <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.profilesTab.baseUrlLabel')}</label>
                <input
                  type="text"
                  placeholder={t('settings.profilesTab.baseUrlPlaceholder')}
                  value={profileBaseUrlInput}
                  onChange={e => setProfileBaseUrlInput(e.target.value)}
                  className={cn(
                    "w-full h-8 border rounded-lg px-2.5 text-xs focus:outline-none font-sans",
                    theme === 'dark'
                      ? "bg-zinc-900 border-zinc-800 text-zinc-200 focus:border-zinc-700"
                      : "bg-white border-zinc-200 text-zinc-900 focus:border-zinc-300"
                  )}
                />
                <p className="text-[9px] text-zinc-500 px-0.5">
                  {t('settings.profilesTab.baseUrlHint')}
                </p>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t"
                 style={{ borderColor: theme === 'dark' ? 'rgba(63, 63, 70, 0.4)' : 'rgba(228, 228, 231, 0.6)' }}>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowProfileForm(false)}
                className={cn("h-8 text-xs font-semibold px-4 rounded-lg", theme === 'dark' ? "text-zinc-400 hover:bg-zinc-800" : "text-zinc-550 hover:bg-zinc-100")}
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={handleSaveProfile}
                className="bg-indigo-650 hover:bg-indigo-600 text-white rounded-lg px-5 h-8 text-xs font-semibold shadow-md"
              >
                {t('settings.profilesTab.saveProfile')}
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Global AI parameters */}
      <div className={cn(
        "space-y-4 border rounded-lg p-4 transition-colors",
        theme === 'dark' ? "bg-zinc-950/40 border-zinc-800" : "bg-zinc-50 border-zinc-200"
      )}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.profilesTab.activeProfileLabel')}</label>
            <Select
              value={activeProfileId}
              onValueChange={val => {
                setActiveProfileId(val);
                localStorage.setItem('doctus-active-profile-id', val);

                // Sync temperature and systemPrompt when profile changes
                const profile = llmProfiles.find(p => p.id === val);
                if (profile) {
                  if (profile.temperature !== undefined) setTemperature(profile.temperature);
                  if (profile.systemPrompt !== undefined) setSystemPrompt(profile.systemPrompt);
                }
              }}
            >
              <SelectTrigger className={cn(
                "w-full h-8 text-xs focus:ring-0",
                theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-300" : "bg-white border-zinc-200 text-zinc-800"
              )}>
                <SelectValue placeholder={t('settings.profilesTab.profilePlaceholder')} />
              </SelectTrigger>
              <SelectContent className={theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-200" : "bg-white border-zinc-200 text-zinc-800"}>
                {llmProfiles.map(p => (
                  <SelectItem key={p.id} value={p.id} className="text-xs">
                    {p.name} ({p.model})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5 flex justify-between">
              <span>{t('settings.profilesTab.temperatureLabel')}</span>
              <span className="text-indigo-600 font-mono font-semibold">{temperature}</span>
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={temperature}
              onChange={e => setTemperature(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500 mt-2.5"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-[9px] font-bold text-zinc-500 uppercase px-0.5">{t('settings.profilesTab.systemPromptLabel')}</label>
          <textarea
            rows={3}
            value={systemPrompt}
            onChange={e => setSystemPrompt(e.target.value)}
            className={cn(
              "w-full border rounded-lg p-2.5 text-xs focus:outline-none resize-none font-sans",
              theme === 'dark'
                ? "bg-zinc-900 border-zinc-800 text-zinc-200 focus:border-zinc-700"
                : "bg-white border-zinc-200 text-zinc-900 focus:border-zinc-300"
            )}
          />
        </div>

        <div className="flex justify-end pt-1">
          <Button
            type="button"
            size="sm"
            onClick={handleSaveAiParams}
            className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold px-4 h-8"
          >
            {t('settings.profilesTab.saveAiSettings')}
          </Button>
        </div>
      </div>
    </div>
  );
};
