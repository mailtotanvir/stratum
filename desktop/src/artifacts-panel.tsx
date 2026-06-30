import { useEffect, useState } from 'react';
import { getRuntimeApiBaseUrl } from './api/config';
import {
  getActiveRuntimeWorkspace,
  getRuntimeDashboard,
  getRuntimeSessionArtifacts,
  getRuntimeStatus,
  getRuntimeWorkspaceArtifacts,
  listRuntimeWorkspaces,
  type RuntimeDashboard,
  type RuntimeSessionOverview,
  type RuntimeStatus,
  type RuntimeWorkspace,
  type RuntimeWorkspaceArtifact,
  type RuntimeWorkspaceSummary,
} from './api/runtime';

type LoadState = 'loading' | 'ready' | 'empty' | 'error';

function formatArtifactLabel(artifact: RuntimeWorkspaceArtifact) {
  return [artifact.path ?? artifact.artifact?.path ?? 'no path', artifact.artifact_type, artifact.tool]
    .join(' · ');
}

function formatWorkspaceSummary(workspaces: RuntimeWorkspaceSummary[]) {
  if (!workspaces.length) return 'No workspace summaries returned yet.';
  return workspaces
    .slice(0, 3)
    .map((workspace) => `${workspace.name} (${workspace.root_path})${workspace.active ? ' active' : ''}`)
    .join(' | ');
}

export function ArtifactsPanel() {
  const [state, setState] = useState<LoadState>('loading');
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [dashboard, setDashboard] = useState<RuntimeDashboard | null>(null);
  const [activeWorkspace, setActiveWorkspace] = useState<RuntimeWorkspace | null>(null);
  const [workspaces, setWorkspaces] = useState<RuntimeWorkspaceSummary[]>([]);
  const [sessions, setSessions] = useState<RuntimeSessionOverview[]>([]);
  const [artifacts, setArtifacts] = useState<RuntimeWorkspaceArtifact[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const apiBaseUrl = getRuntimeApiBaseUrl();

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [statusData, dashboardData, workspacesData, activeWorkspaceData] = await Promise.all([
        getRuntimeStatus(),
        getRuntimeDashboard(),
        listRuntimeWorkspaces().catch(() => []),
        getActiveRuntimeWorkspace().catch(() => null),
      ]);
      setStatus(statusData);
      setDashboard(dashboardData);
      setWorkspaces(workspacesData);
      setActiveWorkspace(activeWorkspaceData);
      setSessions(dashboardData.latest_sessions);

      const nextSessionId = selectedSessionId ?? dashboardData.latest_sessions[0]?.session_id ?? null;
      setSelectedSessionId(nextSessionId);

      if (nextSessionId) {
        const sessionArtifacts = await getRuntimeSessionArtifacts(nextSessionId).catch(() => []);
        setArtifacts(sessionArtifacts);
      } else if (activeWorkspaceData?.workspace_id) {
        const workspaceArtifacts = await getRuntimeWorkspaceArtifacts(
          activeWorkspaceData.workspace_id,
        ).catch(() => []);
        setArtifacts(workspaceArtifacts);
      } else {
        setArtifacts([]);
      }

      const hasData =
        workspacesData.length > 0 ||
        dashboardData.latest_sessions.length > 0 ||
        activeWorkspaceData != null ||
        statusData.active_sessions > 0 ||
        artifacts.length > 0;
      setState(hasData ? 'ready' : 'empty');
    } catch (err) {
      setStatus(null);
      setDashboard(null);
      setActiveWorkspace(null);
      setWorkspaces([]);
      setSessions([]);
      setArtifacts([]);
      setState('error');
      setError(err instanceof Error ? err.message : `Backend unavailable at ${apiBaseUrl}`);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!selectedSessionId && !activeWorkspace?.workspace_id) return;

    let active = true;
    const load = async () => {
      try {
        const nextArtifacts = selectedSessionId
          ? await getRuntimeSessionArtifacts(selectedSessionId)
          : activeWorkspace?.workspace_id
            ? await getRuntimeWorkspaceArtifacts(activeWorkspace.workspace_id)
            : [];
        if (!active) return;
        setArtifacts(nextArtifacts);
      } catch {
        if (!active) return;
        setArtifacts([]);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [activeWorkspace, selectedSessionId]);

  const selectedArtifact = artifacts[0] ?? null;

  return (
    <main className="console-shell">
      <header className="console-hero">
        <div>
          <p className="eyebrow">Desktop Runtime Console</p>
          <h1>Artifacts panel</h1>
          <p className="hero-copy">
            Connected to <code>{apiBaseUrl}</code>
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void refresh()} disabled={refreshing}>
          {refreshing ? 'Refreshing' : 'Refresh'}
        </button>
      </header>

      <section className={`banner ${state === 'error' ? 'error' : ''}`}>
        {state === 'loading' ? 'Loading runtime status, workspaces, and artifacts.' : null}
        {state === 'ready' ? 'Runtime artifacts loaded.' : null}
        {state === 'empty' ? 'No artifacts returned yet.' : null}
        {state === 'error' ? error ?? 'Backend unavailable.' : null}
      </section>

      <section className="summary-grid">
        <article className="summary-card">
          <span>Artifacts</span>
          <strong>{artifacts.length}</strong>
        </article>
        <article className="summary-card">
          <span>Workspace</span>
          <strong>{activeWorkspace?.name ?? workspaces[0]?.name ?? 'unknown'}</strong>
        </article>
        <article className="summary-card">
          <span>Session</span>
          <strong>{selectedSessionId ?? dashboard?.latest_sessions[0]?.session_id ?? 'none'}</strong>
        </article>
        <article className="summary-card">
          <span>Backend</span>
          <strong>{status?.runtime_status ?? 'unknown'}</strong>
        </article>
      </section>

      <section className="console-grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Workspace binding</h2>
          </div>
          {activeWorkspace ? (
            <div className="session-details">
              <p className="request-text">
                <strong>{activeWorkspace.name}</strong>
                <br />
                {activeWorkspace.root_path}
              </p>
              <dl className="details">
                <div><dt>Workspace</dt><dd>{activeWorkspace.workspace_id}</dd></div>
                <div><dt>Active</dt><dd>{String(activeWorkspace.active)}</dd></div>
                <div><dt>Metadata</dt><dd>{Object.keys(activeWorkspace.metadata).length ? 'present' : 'empty'}</dd></div>
                <div><dt>Recent</dt><dd>{formatWorkspaceSummary(workspaces)}</dd></div>
              </dl>
            </div>
          ) : workspaces.length ? (
            <div className="session-details">
              <p className="request-text">
                <strong>{workspaces[0].name}</strong>
                <br />
                {workspaces[0].root_path}
              </p>
              <dl className="details">
                <div><dt>Workspace</dt><dd>{workspaces[0].workspace_id}</dd></div>
                <div><dt>Active</dt><dd>{String(workspaces[0].active)}</dd></div>
                <div><dt>Summary</dt><dd>{formatWorkspaceSummary(workspaces)}</dd></div>
                <div><dt>Binding</dt><dd>{selectedSessionId ?? 'workspace only'}</dd></div>
              </dl>
            </div>
          ) : (
            <p className="empty">
              {state === 'error'
                ? 'Workspace binding is unavailable while the backend is unreachable.'
                : 'No runtime workspace returned yet.'}
            </p>
          )}
        </article>

        <article className="panel panel-wide">
          <div className="panel-header">
            <h2>Recent artifacts</h2>
          </div>
          {artifacts.length ? (
            <ul className="timeline">
              {artifacts.map((artifact) => (
                <li key={artifact.artifact_id}>
                  <div className="timeline-row">
                    <strong>{artifact.artifact_id}</strong>
                    <span>{artifact.artifact_type}</span>
                  </div>
                  <p>{formatArtifactLabel(artifact)}</p>
                  <p className="session-meta">{artifact.summary}</p>
                  <dl className="details">
                    <div><dt>Session</dt><dd>{artifact.session_id ?? 'none'}</dd></div>
                    <div><dt>Workspace</dt><dd>{artifact.workspace_id}</dd></div>
                    <div><dt>Path</dt><dd>{artifact.path ?? artifact.artifact?.path ?? 'n/a'}</dd></div>
                    <div><dt>Tool</dt><dd>{artifact.tool}</dd></div>
                  </dl>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">
              {state === 'loading'
                ? 'Loading artifact records.'
                : state === 'error'
                  ? 'Artifacts are unavailable while the backend is unreachable.'
                  : 'No artifacts returned for the selected session or workspace.'}
            </p>
          )}
          {selectedArtifact ? (
            <div className="session-details">
              <h3>Selected artifact</h3>
              <p className="request-text">
                <strong>{selectedArtifact.path ?? selectedArtifact.artifact?.path ?? selectedArtifact.artifact_id}</strong>
                <br />
                {selectedArtifact.artifact?.kind ?? selectedArtifact.artifact_type}
              </p>
              <dl className="details">
                <div><dt>Session link</dt><dd>{selectedArtifact.session_id ?? 'none'}</dd></div>
                <div><dt>Artifact link</dt><dd>{selectedArtifact.artifact?.id ?? selectedArtifact.artifact_id}</dd></div>
                <div><dt>Created</dt><dd>{selectedArtifact.created_at}</dd></div>
                <div><dt>Metadata</dt><dd>{Object.keys(selectedArtifact.metadata).length ? 'present' : 'empty'}</dd></div>
              </dl>
            </div>
          ) : null}
        </article>
      </section>
    </main>
  );
}
