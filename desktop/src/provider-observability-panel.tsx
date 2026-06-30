import { useEffect, useState } from 'react';
import { getRuntimeApiBaseUrl } from './api/config';
import {
  getProviderHealth,
  getProviderLiveDiagnostics,
  getProviderObservability,
  type ModelUsageSummary,
  type ProviderHealth,
  type ProviderLiveDiagnostics,
  type ProviderObservabilityReport,
  type ProviderUsageSummary,
} from './api/runtime';

type LoadState = 'loading' | 'ready' | 'empty' | 'error';

type ProviderBundle = {
  observability: ProviderObservabilityReport | null;
  health: ProviderHealth | null;
  diagnostics: ProviderLiveDiagnostics | null;
};

function formatNumber(value: number | null | undefined) {
  if (value == null) return 'n/a';
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
}

function summaryLine(item: ProviderUsageSummary | ModelUsageSummary) {
  return `${item.provider_name} · ${item.model_name} · ${item.total_requests} requests`;
}

export function ProviderObservabilityPanel() {
  const [state, setState] = useState<LoadState>('loading');
  const [bundle, setBundle] = useState<ProviderBundle>({
    observability: null,
    health: null,
    diagnostics: null,
  });
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const apiBaseUrl = getRuntimeApiBaseUrl();

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [observability, health, diagnostics] = await Promise.all([
        getProviderObservability(),
        getProviderHealth().catch(() => null),
        getProviderLiveDiagnostics().catch(() => null),
      ]);
      setBundle({ observability, health, diagnostics });
      const hasData =
        observability.provider_reports.length > 0 ||
        observability.model_usage.length > 0 ||
        observability.costs.length > 0 ||
        health != null ||
        diagnostics != null;
      setState(hasData ? 'ready' : 'empty');
    } catch (err) {
      setBundle({ observability: null, health: null, diagnostics: null });
      setState('error');
      setError(err instanceof Error ? err.message : `Backend unavailable at ${apiBaseUrl}`);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const observability = bundle.observability;
  const providerSummary = observability?.provider_reports[0] ?? null;
  const modelSummary = observability?.model_usage[0] ?? null;
  const costSummary = observability?.costs[0] ?? null;

  return (
    <main className="console-shell">
      <header className="console-hero">
        <div>
          <p className="eyebrow">Desktop Runtime Console</p>
          <h1>Provider observability</h1>
          <p className="hero-copy">
            Connected to <code>{apiBaseUrl}</code>
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void refresh()} disabled={refreshing}>
          {refreshing ? 'Refreshing' : 'Refresh'}
        </button>
      </header>

      <section className={`banner ${state === 'error' ? 'error' : ''}`}>
        {state === 'loading' ? 'Loading provider observability, health, and diagnostics.' : null}
        {state === 'ready' ? 'Provider observability loaded.' : null}
        {state === 'empty' ? 'No provider observability data returned yet.' : null}
        {state === 'error' ? error ?? 'Backend unavailable.' : null}
      </section>

      <section className="summary-grid">
        <article className="summary-card">
          <span>Providers</span>
          <strong>{observability?.provider_count ?? 0}</strong>
        </article>
        <article className="summary-card">
          <span>Models</span>
          <strong>{observability?.model_count ?? 0}</strong>
        </article>
        <article className="summary-card">
          <span>Total requests</span>
          <strong>{observability?.total_requests ?? 0}</strong>
        </article>
        <article className="summary-card">
          <span>Estimated cost</span>
          <strong>${formatNumber(costSummary?.estimated_cost_usd ?? observability?.observability_metrics.provider_estimated_cost_total)}</strong>
        </article>
      </section>

      <section className="console-grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Provider summary</h2>
          </div>
          {providerSummary ? (
            <div className="session-details">
              <p className="request-text">{summaryLine(providerSummary)}</p>
              <dl className="details">
                <div><dt>Success</dt><dd>{providerSummary.successful_requests}</dd></div>
                <div><dt>Failed</dt><dd>{providerSummary.failed_requests}</dd></div>
                <div><dt>Latency</dt><dd>{formatNumber(providerSummary.average_latency_ms)} ms</dd></div>
                <div><dt>Tokens</dt><dd>{formatNumber(providerSummary.estimated_total_tokens)}</dd></div>
              </dl>
            </div>
          ) : (
            <p className="empty">
              {state === 'error'
                ? 'Provider summary is unavailable while the backend is unreachable.'
                : 'No provider summary returned yet.'}
            </p>
          )}
        </article>

        <article className="panel">
          <div className="panel-header">
            <h2>Health</h2>
          </div>
          {bundle.health ? (
            <div className="session-details">
              <p className="request-text">
                <strong>{bundle.health.status}</strong>
                <br />
                {bundle.health.provider_id ?? 'no provider id'}
              </p>
              <dl className="details">
                <div><dt>Configured</dt><dd>{String(bundle.health.configured)}</dd></div>
                <div><dt>Ready</dt><dd>{String(bundle.health.ready)}</dd></div>
                <div><dt>Enabled</dt><dd>{String(bundle.health.enabled)}</dd></div>
                <div><dt>Streaming</dt><dd>{String(bundle.health.supports_streaming)}</dd></div>
              </dl>
            </div>
          ) : bundle.diagnostics ? (
            <div className="session-details">
              <p className="request-text">
                <strong>{bundle.diagnostics.ready ? 'ready' : 'not ready'}</strong>
                <br />
                {bundle.diagnostics.display_name ?? bundle.diagnostics.provider_id ?? 'live diagnostics'}
              </p>
              <dl className="details">
                <div><dt>Configured</dt><dd>{String(bundle.diagnostics.configured)}</dd></div>
                <div><dt>API key</dt><dd>{String(bundle.diagnostics.has_api_key)}</dd></div>
                <div><dt>Enabled</dt><dd>{String(bundle.diagnostics.enabled)}</dd></div>
                <div><dt>Streaming</dt><dd>{String(bundle.diagnostics.supports_streaming)}</dd></div>
              </dl>
              {bundle.diagnostics.issues.length ? (
                <ul className="timeline">
                  {bundle.diagnostics.issues.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : (
            <p className="empty">
              {state === 'error'
                ? 'Health diagnostics are unavailable while the backend is unreachable.'
                : 'No provider health or live diagnostics returned yet.'}
            </p>
          )}
        </article>
      </section>

      <section className="panel panel-wide provider-lists">
        <div className="panel-header">
          <h2>Model and cost detail</h2>
        </div>
        {modelSummary ? (
          <div className="session-details">
            <p className="request-text">{summaryLine(modelSummary)}</p>
            <dl className="details">
              <div><dt>Requests</dt><dd>{modelSummary.total_requests}</dd></div>
              <div><dt>Cost</dt><dd>${formatNumber(modelSummary.estimated_cost_usd)}</dd></div>
              <div><dt>Tokens</dt><dd>{formatNumber(modelSummary.estimated_total_tokens)}</dd></div>
              <div><dt>Last used</dt><dd>{modelSummary.last_used_at ?? 'n/a'}</dd></div>
            </dl>
          </div>
        ) : (
          <p className="empty">No model usage summary returned yet.</p>
        )}
        {costSummary ? (
          <div className="session-details">
            <p className="request-text">
              <strong>{costSummary.provider_name}</strong>
              <br />
              {costSummary.model_name}
            </p>
            <dl className="details">
              <div><dt>Estimated</dt><dd>{String(costSummary.cost_estimated)}</dd></div>
              <div><dt>Missing records</dt><dd>{costSummary.missing_token_or_cost_records}</dd></div>
              <div><dt>Total tokens</dt><dd>{formatNumber(costSummary.estimated_total_tokens)}</dd></div>
              <div><dt>Cost</dt><dd>${formatNumber(costSummary.estimated_cost_usd)}</dd></div>
            </dl>
          </div>
        ) : null}
      </section>
    </main>
  );
}
