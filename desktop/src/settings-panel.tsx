import { useEffect, useState } from 'react';
import { getRuntimeApiBaseUrl } from './api/config';
import {
  activateRuntimeWorkspace,
  getActiveRuntimeWorkspace,
  getProviderExecutionRecent,
  getProviderHealth,
  getProviderLiveDiagnostics,
  getRuntimeWorkspaceBindingStatus,
  listRuntimeWorkspaces,
  type ProviderExecutionRecentItem,
  type ProviderHealth,
  type ProviderLiveDiagnostics,
  type RuntimeWorkspaceBindingStatus,
  type RuntimeWorkspace,
  type RuntimeWorkspaceSummary,
} from './api/runtime';

type LoadState = 'loading' | 'ready' | 'empty' | 'error';

function firstString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function formatSummary(parts: Array<string | null | undefined>) {
  return parts.filter((part): part is string => Boolean(part)).join(' · ');
}

function summarizeRouting(recent: ProviderExecutionRecentItem[]) {
  for (const item of recent) {
    const route = firstString(item.routing_reason) ?? firstString(item.routing_source);
    if (route) {
      return formatSummary([
        item.provider_id,
        item.model,
        route,
        item.status,
      ]);
    }
  }
  return null;
}

function summarizeBudget(recent: ProviderExecutionRecentItem[]) {
  for (const item of recent) {
    const budget = item.budget_policy;
    if (!budget || typeof budget !== 'object') continue;
    const classification = firstString((budget as Record<string, unknown>).classification);
    const warnings = Array.isArray((budget as Record<string, unknown>).warnings)
      ? ((budget as Record<string, unknown>).warnings as unknown[])
          .map((warning) => firstString(warning))
          .filter((warning): warning is string => Boolean(warning))
      : [];
    if (classification || warnings.length) {
      return formatSummary([
        classification ?? null,
        warnings.length ? `${warnings.length} warning${warnings.length === 1 ? '' : 's'}` : null,
      ]);
    }
  }
  return null;
}

function summarizeWorkspaceBinding(
  activeWorkspace: RuntimeWorkspace | null,
  workspaces: RuntimeWorkspaceSummary[],
) {
  if (!activeWorkspace) return null;
  const workspaceCount = workspaces.length;
  return formatSummary([
    activeWorkspace.name,
    activeWorkspace.workspace_id,
    activeWorkspace.root_path,
    workspaceCount ? `${workspaceCount} workspace${workspaceCount === 1 ? '' : 's'} registered` : null,
  ]);
}

function summarizeProviderHealth(
  health: ProviderHealth | null,
  diagnostics: ProviderLiveDiagnostics | null,
) {
  if (health) {
    return formatSummary([
      health.provider_id ?? null,
      health.status,
      health.enabled ? 'enabled' : 'disabled',
      health.ready ? 'ready' : 'not ready',
    ]);
  }
  if (diagnostics) {
    return formatSummary([
      diagnostics.provider_id ?? null,
      diagnostics.display_name ?? null,
      diagnostics.ready ? 'ready' : 'not ready',
      diagnostics.configured ? 'configured' : 'unconfigured',
    ]);
  }
  return null;
}

export function SettingsPanel() {
  const [state, setState] = useState<LoadState>('loading');
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [health, setHealth] = useState<ProviderHealth | null>(null);
  const [diagnostics, setDiagnostics] = useState<ProviderLiveDiagnostics | null>(null);
  const [recentExecutions, setRecentExecutions] = useState<ProviderExecutionRecentItem[]>([]);
  const [activeWorkspace, setActiveWorkspace] = useState<RuntimeWorkspace | null>(null);
  const [workspaces, setWorkspaces] = useState<RuntimeWorkspaceSummary[]>([]);
  const [bindingStatus, setBindingStatus] = useState<RuntimeWorkspaceBindingStatus | null>(null);

  const apiBaseUrl = getRuntimeApiBaseUrl();

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [healthData, diagnosticsData, recentData, activeWorkspaceData, workspacesData, bindingData] = await Promise.all([
        getProviderHealth().catch(() => null),
        getProviderLiveDiagnostics().catch(() => null),
        getProviderExecutionRecent().catch(() => []),
        getActiveRuntimeWorkspace().catch(() => null),
        listRuntimeWorkspaces().catch(() => []),
        getRuntimeWorkspaceBindingStatus().catch(() => null),
      ]);
      setHealth(healthData);
      setDiagnostics(diagnosticsData);
      setRecentExecutions(recentData);
      setActiveWorkspace(activeWorkspaceData);
      setWorkspaces(workspacesData);
      setBindingStatus(bindingData);
      const hasData =
        healthData != null ||
        diagnosticsData != null ||
        recentData.length > 0 ||
        activeWorkspaceData != null ||
        bindingData != null ||
        workspacesData.length > 0;
      setState(hasData ? 'ready' : 'empty');
    } catch (err) {
      setHealth(null);
      setDiagnostics(null);
      setRecentExecutions([]);
      setActiveWorkspace(null);
      setWorkspaces([]);
      setBindingStatus(null);
      setState('error');
      setError(err instanceof Error ? err.message : `Backend unavailable at ${apiBaseUrl}`);
    } finally {
      setRefreshing(false);
    }
  };

  const handleActivateWorkspace = async (workspaceId: string) => {
    setRefreshing(true);
    setError(null);
    try {
      await activateRuntimeWorkspace(workspaceId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to activate workspace');
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const routingSummary = summarizeRouting(recentExecutions);
  const budgetSummary = summarizeBudget(recentExecutions);
  const workspaceSummary = summarizeWorkspaceBinding(activeWorkspace, workspaces);
  const providerSummary = summarizeProviderHealth(health, diagnostics);
  const executionAllowed = bindingStatus?.runtime_execution_allowed ?? false;

  return (
    <main className="console-shell">
      <header className="console-hero">
        <div>
          <p className="eyebrow">Desktop Runtime Console</p>
          <h1>Settings</h1>
          <p className="hero-copy">
            Connected to <code>{apiBaseUrl}</code>
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void refresh()} disabled={refreshing}>
          {refreshing ? 'Refreshing' : 'Refresh'}
        </button>
      </header>

      <section className={`banner ${state === 'error' ? 'error' : ''}`}>
        {state === 'loading' ? 'Loading settings and runtime configuration.' : null}
        {state === 'ready' ? 'Settings and configuration data loaded.' : null}
        {state === 'empty' ? 'No settings data returned yet.' : null}
        {state === 'error' ? error ?? 'Backend unavailable.' : null}
      </section>

      <section className="summary-grid">
        <article className="summary-card">
          <span>Backend URL</span>
          <strong>{apiBaseUrl}</strong>
        </article>
        <article className="summary-card">
          <span>Routing</span>
          <strong>{routingSummary ?? 'Unavailable'}</strong>
        </article>
        <article className="summary-card">
          <span>Budget policy</span>
          <strong>{budgetSummary ?? 'Unavailable'}</strong>
        </article>
        <article className="summary-card">
          <span>Workspace binding</span>
          <strong>{workspaceSummary ?? bindingStatus?.runtime_execution_reason ?? 'Unavailable'}</strong>
        </article>
      </section>

      <section className="console-grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Provider status</h2>
          </div>
          {providerSummary ? (
            <div className="session-details">
              <p className="request-text">{providerSummary}</p>
              <dl className="details">
                <div>
                  <dt>Health</dt>
                  <dd>{health?.status ?? (diagnostics?.ready ? 'available' : 'unknown')}</dd>
                </div>
                <div><dt>Configured</dt><dd>{String(health?.configured ?? diagnostics?.configured ?? false)}</dd></div>
                <div><dt>Enabled</dt><dd>{String(health?.enabled ?? diagnostics?.enabled ?? false)}</dd></div>
                <div><dt>Base URL</dt><dd>{diagnostics?.base_url ?? 'Not exposed'}</dd></div>
              </dl>
            </div>
          ) : (
            <p className="empty">
              {state === 'error'
                ? 'Provider status is unavailable while the backend is unreachable.'
                : 'No provider status returned yet.'}
            </p>
          )}
        </article>

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
                <div><dt>Workspace ID</dt><dd>{activeWorkspace.workspace_id}</dd></div>
                <div><dt>Active</dt><dd>{String(activeWorkspace.active)}</dd></div>
                <div><dt>Registered</dt><dd>{workspaces.length}</dd></div>
                <div><dt>Backend</dt><dd>{apiBaseUrl}</dd></div>
              </dl>
            </div>
          ) : bindingStatus ? (
            <div className="session-details">
              <p className="request-text">
                <strong>{bindingStatus.workspace.name}</strong>
                <br />
                {bindingStatus.repository.path}
              </p>
              <dl className="details">
                <div><dt>Repository</dt><dd>{bindingStatus.repository.is_git_repository ? 'git' : 'not git'}</dd></div>
                <div><dt>Branch</dt><dd>{bindingStatus.repository.branch ?? 'n/a'}</dd></div>
                <div><dt>Checkpoint</dt><dd>{bindingStatus.repository.checkpoint_status ?? 'unknown'}</dd></div>
                <div><dt>Execution</dt><dd>{executionAllowed ? 'allowed' : 'blocked'}</dd></div>
              </dl>
              <p className="session-meta">{bindingStatus.runtime_execution_reason}</p>
            </div>
          ) : (
            <p className="empty">
              {state === 'error'
                ? 'Workspace binding is unavailable while the backend is unreachable.'
                : 'No active workspace returned yet.'}
            </p>
          )}
        </article>

        <article className="panel">
          <div className="panel-header">
            <h2>Workspace registry</h2>
          </div>
          {workspaces.length ? (
            <ul className="session-list">
              {workspaces.map((workspace) => (
                <li key={workspace.workspace_id}>
                  <div className={workspace.active ? 'selected' : ''} style={{ width: '100%' }}>
                    <strong>{workspace.name}</strong>
                    <span>{workspace.root_path}</span>
                    <span>{workspace.active ? 'active binding' : 'available binding'}</span>
                    {!workspace.active ? (
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => void handleActivateWorkspace(workspace.workspace_id)}
                        disabled={refreshing}
                      >
                        Activate
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">No registered workspaces returned yet.</p>
          )}
        </article>
      </section>

      <section className="panel panel-wide provider-lists">
        <div className="panel-header">
          <h2>Latest execution signals</h2>
        </div>
        {recentExecutions.length ? (
          <div className="session-details">
            <p className="request-text">Using the newest provider execution records to summarize routing and budget behavior.</p>
            <dl className="details">
              <div><dt>Recent executions</dt><dd>{recentExecutions.length}</dd></div>
              <div><dt>Routing summary</dt><dd>{routingSummary ?? 'Unavailable'}</dd></div>
              <div><dt>Budget summary</dt><dd>{budgetSummary ?? 'Unavailable'}</dd></div>
              <div><dt>Provider status</dt><dd>{providerSummary ?? 'Unavailable'}</dd></div>
            </dl>
          </div>
        ) : (
          <p className="empty">No recent execution records were returned by the backend.</p>
        )}
      </section>
    </main>
  );
}
