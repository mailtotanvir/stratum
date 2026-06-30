import { useEffect, useState } from 'react';
import { getRuntimeApiBaseUrl } from './api/config';
import {
  getRuntimeDashboard,
  getRuntimeSessionEvents,
  getRuntimeStatus,
  type RuntimeDashboard,
  type RuntimeSessionOverview,
  type RuntimeStatus,
} from './api/runtime';

type LoadState = 'idle' | 'loading' | 'ready' | 'error';

function describeSession(session: RuntimeSessionOverview) {
  return [
    session.provider ?? 'no provider',
    session.model ?? 'no model',
    session.updated_at,
  ].join(' · ');
}

export function RuntimeConsole() {
  const [state, setState] = useState<LoadState>('loading');
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [dashboard, setDashboard] = useState<RuntimeDashboard | null>(null);
  const [sessions, setSessions] = useState<RuntimeSessionOverview[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<RuntimeSessionOverview | null>(null);
  const [selectedSessionEvents, setSelectedSessionEvents] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const apiBaseUrl = getRuntimeApiBaseUrl();

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [statusData, dashboardData] = await Promise.all([
        getRuntimeStatus(),
        getRuntimeDashboard(),
      ]);
      setStatus(statusData);
      setDashboard(dashboardData);
      setSessions(dashboardData.latest_sessions);
      setState('ready');
      const nextSessionId = selectedSessionId ?? dashboardData.latest_sessions[0]?.session_id ?? null;
      setSelectedSessionId(nextSessionId);
      setSelectedSession(
        dashboardData.latest_sessions.find((session) => session.session_id === nextSessionId) ?? null,
      );
      if (nextSessionId) {
        const events = await getRuntimeSessionEvents(nextSessionId);
        setSelectedSessionEvents(
          events.slice(0, 6).map((event) => `${event.type}${event.message ? `: ${event.message}` : ''}`),
        );
      } else {
        setSelectedSessionEvents([]);
      }
    } catch (err) {
      setStatus(null);
      setDashboard(null);
      setSessions([]);
      setSelectedSession(null);
      setSelectedSessionEvents([]);
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
    if (!selectedSessionId) return;
    let active = true;
    getRuntimeSessionEvents(selectedSessionId)
      .then((events) => {
        if (!active) return;
        setSelectedSessionEvents(
          events.slice(0, 6).map((event) => `${event.type}${event.message ? `: ${event.message}` : ''}`),
        );
      })
      .catch(() => {
        if (!active) return;
        setSelectedSessionEvents(['No runtime event feed available for this session.']);
      });
    return () => {
      active = false;
    };
  }, [selectedSessionId]);

  const runtimeStatus = status?.runtime_status ?? 'unknown';
  const providerStatus = status?.provider_status ?? 'unknown';
  const activeSession = selectedSession ?? sessions[0] ?? null;

  return (
    <main className="console-shell">
      <header className="console-hero">
        <div>
          <p className="eyebrow">Desktop Runtime Console</p>
          <h1>Local backend monitor</h1>
          <p className="hero-copy">
            Connected to <code>{apiBaseUrl}</code>
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void refresh()} disabled={refreshing}>
          {refreshing ? 'Refreshing' : 'Refresh'}
        </button>
      </header>

      <section className={`banner ${state === 'error' ? 'error' : ''}`}>
        {state === 'loading' ? 'Loading runtime status and dashboard.' : null}
        {state === 'ready' ? 'Backend online. Runtime dashboard loaded.' : null}
        {state === 'error' ? error ?? 'Backend unavailable.' : null}
      </section>

      <section className="summary-grid">
        <article className="summary-card">
          <span>Runtime</span>
          <strong>{runtimeStatus}</strong>
        </article>
        <article className="summary-card">
          <span>Provider</span>
          <strong>{providerStatus}</strong>
        </article>
        <article className="summary-card">
          <span>Active sessions</span>
          <strong>{status?.active_sessions ?? dashboard?.active_sessions ?? 0}</strong>
        </article>
        <article className="summary-card">
          <span>Pending approvals</span>
          <strong>{dashboard?.pending_approvals ?? 0}</strong>
        </article>
      </section>

      <section className="console-grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Recent sessions</h2>
          </div>
          {sessions.length ? (
            <ul className="session-list">
              {sessions.map((session) => (
                <li key={session.session_id}>
                  <button
                    type="button"
                    className={session.session_id === selectedSessionId ? 'selected' : ''}
                    onClick={() => setSelectedSessionId(session.session_id)}
                  >
                    <strong>{session.session_id}</strong>
                    <span>{session.status}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">
              {state === 'error'
                ? 'No dashboard data available while the backend is unreachable.'
                : 'No runtime sessions returned yet.'}
            </p>
          )}
        </article>

        <article className="panel panel-wide">
          <div className="panel-header">
            <h2>Selected session</h2>
          </div>
          {activeSession ? (
            <div className="session-details">
              <p className="request-text">
                {selectedSessionId ? (
                  <>
                    <strong>{selectedSessionId}</strong>
                    <br />
                    {describeSession(activeSession)}
                  </>
                ) : (
                  'Select a session to inspect its recent runtime events.'
                )}
              </p>
              <dl className="details">
                <div><dt>Status</dt><dd>{activeSession.status}</dd></div>
                <div><dt>Request</dt><dd>{activeSession.user_request ?? 'No request text'}</dd></div>
                <div><dt>Result</dt><dd>{activeSession.final_answer ?? activeSession.error ?? 'Pending'}</dd></div>
              </dl>
              <h3>Recent events</h3>
              {selectedSessionEvents.length ? (
                <ul className="timeline">
                  {selectedSessionEvents.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              ) : (
                <p className="empty">No recent runtime events returned.</p>
              )}
            </div>
          ) : (
            <p className="empty">
              {state === 'error'
                ? 'Runtime console is offline because the backend could not be reached.'
                : 'Select a recent session to view its runtime details.'}
            </p>
          )}
        </article>
      </section>
    </main>
  );
}
