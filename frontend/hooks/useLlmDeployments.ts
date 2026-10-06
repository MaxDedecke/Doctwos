"use client";
import { api } from '@/app/services/api';
import { useCallback, useEffect, useState } from 'react';

export type DeploymentEngine = 'ollama' | 'vllm' | 'llamacpp';
export type DeploymentStatus = 'starting' | 'pulling' | 'ready' | 'stopped' | 'failed' | string;

export interface LlmDeployment {
  name: string;
  engine: DeploymentEngine;
  role: 'chat' | 'embedding';
  model: string;
  gpu: boolean;
  status: DeploymentStatus;
  detail?: string;
  baseUrl: string;
}

export interface DeploymentCapabilities { gpu: boolean }

const POLL_MS = 5000;

/**
 * Lokale Deployments (Ollama, vLLM, llama.cpp) samt Hostfähigkeiten, solange `enabled` gilt.
 * Fragt alle 5 s nach, damit Start/Download-Fortschritt sichtbar wird. `error` ist gesetzt, wenn der
 * Deployer nicht erreichbar oder nicht eingerichtet ist (dann lässt sich nur Remote/Cloud nutzen).
 */
export function useLlmDeployments(enabled: boolean) {
  const [deployments, setDeployments] = useState<LlmDeployment[]>([]);
  const [capabilities, setCapabilities] = useState<DeploymentCapabilities>({ gpu: false });
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const response = await api.getLlmDeployments();
      const data = response.data as { capabilities?: DeploymentCapabilities; deployments?: Array<Record<string, unknown>> };
      setCapabilities({ gpu: Boolean(data.capabilities?.gpu) });
      setDeployments((data.deployments ?? []).map(item => ({
        name: String(item.name), engine: item.engine as DeploymentEngine, role: (item.role as LlmDeployment['role']) ?? 'chat',
        model: String(item.model ?? ''), gpu: Boolean(item.gpu), status: String(item.status ?? ''),
        detail: item.detail ? String(item.detail) : undefined, baseUrl: String(item.base_url ?? ''),
      })));
      setError(null);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || (err instanceof Error ? err.message : 'error'));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [enabled, refresh]);

  return { deployments, capabilities, error, loaded, refresh };
}
