import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/app/services/api';

type Translate = (key: string, values?: Record<string, unknown>) => string;
type Toast = (message: string, type?: string) => void;

interface UseProjectsOptions {
  isLoggedIn: boolean;
  isSettingsOpen: boolean;
  t: Translate;
  showToast: Toast;
}

/**
 * Owns project data and the project-scoped analysis data used by the app.
 *
 * Keeping polling, statistics, and entity loading here prevents the page from
 * coordinating several related effects with subtly different lifetimes. The
 * hook deliberately exposes the selected project and its setters: navigation
 * and chat/session code still decide when a project switch should reset other
 * domains.
 */
export function useProjects({ isLoggedIn, isSettingsOpen, t, showToast }: UseProjectsOptions) {
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProject, setSelectedProject] = useState<any | null>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [branch, setBranch] = useState('main');
  const [projectEntities, setProjectEntities] = useState<any[]>([]);
  const [projectStats, setProjectStats] = useState<Record<number, any>>({});
  const [backendStatus, setBackendStatus] = useState('connecting');

  const projectsRef = useRef(projects);
  const selectedProjectRef = useRef(selectedProject);
  const fetchedProjectStatsIdsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    projectsRef.current = projects;
  }, [projects]);

  useEffect(() => {
    selectedProjectRef.current = selectedProject;
  }, [selectedProject]);

  useEffect(() => {
    if (!isLoggedIn) return;

    api.getProjects()
      .then((res) => {
        setProjects(res.data);
        setBackendStatus('connected');
      })
      .catch((error) => {
        console.error(error);
        setBackendStatus('error');
        showToast(t('page.toast.backendConnectionFailed'), 'error');
      });
  // Authentication is the lifecycle boundary for the initial project load.
  // The translation function is intentionally not a reload trigger.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn]);

  useEffect(() => {
    if (!isSettingsOpen || projects.length === 0) return;

    projects.forEach((project) => {
      if (fetchedProjectStatsIdsRef.current.has(project.id)) return;
      fetchedProjectStatsIdsRef.current.add(project.id);
      api.getProjectStats(project.id)
        .then((res) => {
          setProjectStats((previous) => ({ ...previous, [project.id]: res.data }));
        })
        .catch((error) => {
          console.error(`Error fetching stats for project ${project.id}:`, error);
          fetchedProjectStatsIdsRef.current.delete(project.id);
        });
    });
  }, [isSettingsOpen, projects]);

  const hasActiveTask = projects.some(
    (project) => project.status === 'parsing' || project.status === 'pending'
  );

  useEffect(() => {
    if (!hasActiveTask) return;

    const interval = setInterval(async () => {
      try {
        const res = await api.getProjects();
        const updatedProjects = res.data;
        const currentProjects = projectsRef.current;
        const currentSelectedProject = selectedProjectRef.current;

        currentProjects.forEach((oldProject) => {
          const newProject = updatedProjects.find((project: any) => project.id === oldProject.id);
          if (!newProject || oldProject.status === newProject.status) return;

          if (newProject.status === 'completed') {
            showToast(t('page.toast.projectAnalyzed', { name: newProject.name }), 'success');
            api.getProjectStats(newProject.id)
              .then((statRes) => {
                setProjectStats((previous) => ({ ...previous, [newProject.id]: statRes.data }));
              })
              .catch((error) => console.error(`Error fetching stats for completed project ${newProject.id}:`, error));

            if (currentSelectedProject?.id === newProject.id) {
              setSelectedProject(newProject);
              api.getProjectFiles(newProject.id)
                .then((fileRes) => setFiles(fileRes.data))
                .catch(console.error);
              api.getProjectEntities(newProject.id)
                .then((entityRes) => setProjectEntities(entityRes.data))
                .catch(console.error);
            }
          } else if (newProject.status === 'error') {
            showToast(t('page.toast.projectAnalysisError', { name: newProject.name }), 'error');
          }
        });

        setProjects(updatedProjects);
      } catch (error) {
        console.error('Error polling project status:', error);
      }
    }, 2000);

    return () => clearInterval(interval);
  // The polling interval is enabled by the derived active-task flag.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasActiveTask]);

  useEffect(() => {
    if (!selectedProject) {
      return;
    }

    api.getProjectEntities(selectedProject.id)
      .then((res) => setProjectEntities(res.data))
      .catch((error) => console.error('Failed to load project entities:', error));
  }, [selectedProject]);

  /**
   * Select a project and load its file list. Session reset decisions stay in
   * the page because they cross the project/chat/workspace domain boundary.
   */
  const selectProject = useCallback(async (project: any | null) => {
    if (!project) {
      setSelectedProject(null);
      setFiles([]);
      setProjectEntities([]);
      setBranch('main');
      return;
    }

    // Projects without a Git URL are valid local projects and have no parsing
    // status. Only attached repositories need to be fully analyzed first.
    if (project.url && project.status !== 'completed') {
      showToast(t('page.toast.projectStillAnalyzing', { name: project.name }), 'warning');
      return;
    }

    setSelectedProject(project);
    setBranch(project.branch || 'main');

    try {
      const res = await api.getProjectFiles(project.id);
      setFiles(res.data);
      showToast(t('page.toast.projectSelected', { name: project.name }), 'success');
    } catch (error) {
      console.error('Failed to load project files:', error);
      showToast(t('page.toast.filesFetchFailed'), 'error');
    }
  }, [showToast, t]);

  return {
    projects,
    setProjects,
    selectedProject,
    setSelectedProject,
    files,
    setFiles,
    branch,
    setBranch,
    projectEntities,
    setProjectEntities,
    projectStats,
    setProjectStats,
    backendStatus,
    selectProject,
  };
}
