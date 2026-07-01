import { useEffect, useState } from 'react';
import {
  getPlatformDiagnostics,
  getPlatformExtensions,
  getPlatformSdkSchema,
  type LoadedExtension,
  type PlatformDiagnostics,
  type PlatformSdkSchema,
} from './api/runtime';
import { getRuntimeApiBaseUrl } from './api/config';

type LoadState = 'loading' | 'ready' | 'empty' | 'error';

function badgeClass(status: string) {
  return status === 'healthy' ? 'badge healthy' : status === 'disabled' ? 'badge muted' : 'badge warning';
}

export function PlatformPanel() {
  const [state, setState] = useState<LoadState>('loading');
  const [extensions, setExtensions] = useState<LoadedExtension[]>([]);
  const [diagnostics, setDiagnostics] = useState<PlatformDiagnostics | null>(null);
  const [schema, setSchema] = useState<PlatformSdkSchema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const apiBaseUrl = getRuntimeApiBaseUrl();

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [ext, diag, sdkSchema] = await Promise.all([
        getPlatformExtensions(),
        getPlatformDiagnostics(),
        getPlatformSdkSchema(),
      ]);
      setExtensions(ext.extensions);
      setDiagnostics(diag);
      setSchema(sdkSchema);
      setState(ext.extensions.length ? 'ready' : 'empty');
    } catch (err) {
      setExtensions([]);
      setDiagnostics(null);
      setSchema(null);
      setState('error');
      setError(err instanceof Error ? err.message : `Backend unavailable at ${apiBaseUrl}`);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <main className="console-shell">
      <header className="console-hero">
        <div>
          <p className="eyebrow">Platform Explorer</p>
          <h1>Extensions and diagnostics</h1>
          <p className="hero-copy">Connected to <code>{apiBaseUrl}</code></p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void refresh()} disabled={refreshing}>
          {refreshing ? 'Refreshing' : 'Refresh'}
        </button>
      </header>

      <section className={`banner ${state === 'error' ? 'error' : ''}`}>
        {state === 'loading' ? 'Loading extension inventory and diagnostics.' : null}
        {state === 'ready' ? 'Platform inventory loaded.' : null}
        {state === 'empty' ? 'No extensions discovered yet.' : null}
        {state === 'error' ? error ?? 'Backend unavailable.' : null}
      </section>

      <section className="summary-grid">
        <article className="summary-card"><span>Installed</span><strong>{diagnostics?.installed_extensions ?? 0}</strong></article>
        <article className="summary-card"><span>Disabled</span><strong>{diagnostics?.disabled_extensions ?? 0}</strong></article>
        <article className="summary-card"><span>Compatibility</span><strong>{diagnostics?.incompatible_extensions ?? 0}</strong></article>
        <article className="summary-card"><span>Dependency issues</span><strong>{diagnostics?.dependency_issues ?? 0}</strong></article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>SDK Schema</h2>
        </div>
        <p className="session-meta">{schema?.contract.contract_id ?? 'n/a'} · v{schema?.contract.version ?? 'n/a'}</p>
        <p>{schema?.contract.description ?? 'Stable public SDK schema export.'}</p>
        <p className="session-meta">{schema?.contract.metadata ? Object.keys(schema.contract.metadata).join(', ') : 'No contract metadata.'}</p>
      </section>

      <section className="console-grid">
        <article className="panel">
          <div className="panel-header"><h2>Installed Extensions</h2></div>
          <ul className="timeline">
            {extensions.map((ext) => (
              <li key={ext.manifest.extension_id}>
                <div className="timeline-row">
                  <strong>{ext.manifest.name}</strong>
                  <span>{ext.manifest.kind}</span>
                </div>
                <p className="session-meta">{ext.manifest.extension_id} · v{ext.manifest.version} · {ext.manifest.author}</p>
                <p>{ext.manifest.supported_protocols.join(', ')}</p>
                {ext.warnings.length ? <p>{ext.warnings.join('; ')}</p> : null}
                {ext.dependency_issues.length ? <p>{ext.dependency_issues.join('; ')}</p> : null}
                <p className="session-meta">{ext.source_path}</p>
              </li>
            ))}
          </ul>
        </article>

        <article className="panel">
          <div className="panel-header"><h2>Extension Health</h2></div>
          <ul className="timeline">
            {diagnostics?.extensions.map((ext) => (
              <li key={ext.extension_id}>
                <div className="timeline-row">
                  <strong>{ext.extension_id}</strong>
                  <span className={badgeClass(ext.status)}>{ext.status}</span>
                </div>
                <p className="session-meta">{ext.kind} · compatible: {String(ext.compatible)}</p>
                {ext.dependency_issues.length ? <p>{ext.dependency_issues.join('; ')}</p> : <p>No dependency issues.</p>}
              </li>
            ))}
          </ul>
        </article>
      </section>
    </main>
  );
}
