import { useEffect, useState } from 'react';
import { getRuntimeApiBaseUrl } from './api/config';
import {
  getRuntimeDashboard,
  getRuntimeSessionTimeline,
  getRuntimeStatus,
  listRuntimeSessions,
  type RuntimeDashboard,
  type RuntimeSessionListItem,
  type RuntimeSessionOverview,
  type RuntimeStatus,
  type RuntimeTimelineItem,
} from './api/runtime';

type LoadState = 'loading' | 'ready' | 'error';

type SessionOption = {
  sessionId: string;
  status: string;
  label: string;
  detail: string;
};

function toSessionOptions(
  sessions: RuntimeSessionListItem[] | RuntimeSessionOverview[],
): SessionOption[] {
  return sessions.map((session) => {
    const sessionId = 'session_id' in session ? session.session_id : session.id;
    const status = session.status;
    const startedAt = 'started_at' in session ? session.started_at : session.created_at;
    const taskId = 'task_id' in session ? session.task_id : session.user_request ?? session.session_id;

    return {
      sessionId,
      status,
      label: sessionId,
      detail: `${taskId} · ${startedAt}`,
    };
  });
}

function describeTimelineItem(item: RuntimeTimelineItem) {
  return `${item.title}: ${item.summary}`;
}

export function SessionTimeline() {
  const [state, setState] = useState<LoadState>('loading');
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [dashboard, setDashboard] = useState<RuntimeDashboard | null>(null);
  const [sessions, setSessions] = useState<SessionOption[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<RuntimeTimelineItem[]>([]);
  const [timelineState, setTimelineState] = useState<LoadState>('loading');
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const apiBaseUrl = getRuntimeApiBaseUrl();

  const loadTimeline = async (sessionId: string | null) => {
    if (!sessionId) {
      setTimeline([]);
      setTimelineState('ready');
      return;
    }
    setTimelineState('loading');
    try {
      const items = await getRuntimeSessionTimeline(sessionId);
      setTimeline(items);
      setTimelineState('ready');
    } catch (err) {
      setTimeline([]);
      setTimelineState('error');
      setError(err instanceof Error ? err.message : 'Timeline unavailable.');
    }
  };

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

      let sessionOptions = toSessionOptions(dashboardData.latest_sessions);
      try {
        sessionOptions = toSessionOptions(await listRuntimeSessions());
      } catch {
        // Keep dashboard-backed session choices when the sessions endpoint is unavailable.
      }
      setSessions(sessionOptions);
      const nextSessionId = selectedSessionId ?? sessionOptions[0]?.sessionId ?? null;
      setSelectedSessionId(nextSessionId);
      setState('ready');
      await loadTimeline(nextSessionId);
    } catch (err) {
      setStatus(null);
      setDashboard(null);
      setSessions([]);
      setSelectedSessionId(null);
      setTimeline([]);
      setTimelineState('loading');
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
    void loadTimeline(selectedSessionId);
  }, [selectedSessionId]);

  const selectedSession = sessions.find((session) => session.sessionId === selectedSessionId) ?? null;

  return (
    <main className="console-shell">
      <header className="console-hero">
        <div>
          <p className="eyebrow">Desktop Runtime Console</p>
          <h1>Session timeline</h1>
          <p className="hero-copy">
            Connected to <code>{apiBaseUrl}</code>
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void refresh()} disabled={refreshing}>
          {refreshing ? 'Refreshing' : 'Refresh'}
        </button>
      </header>

      <section className={`banner ${state === 'error' ? 'error' : ''}`}>
        {state === 'loading' ? 'Loading runtime status, sessions, and timeline.' : null}
        {state === 'ready' ? 'Backend online. Session timeline loaded.' : null}
        {state === 'error' ? error ?? 'Backend unavailable.' : null}
      </section>

      <section className="summary-grid">
        <article className="summary-card">
          <span>Runtime</span>
          <strong>{status?.runtime_status ?? 'unknown'}</strong>
        </article>
        <article className="summary-card">
          <span>Provider</span>
          <strong>{status?.provider_status ?? 'unknown'}</strong>
        </article>
        <article className="summary-card">
          <span>Sessions</span>
          <strong>{dashboard?.latest_sessions.length ?? sessions.length ?? 0}</strong>
        </article>
        <article className="summary-card">
          <span>Events</span>
          <strong>{timeline.length}</strong>
        </article>
      </section>

      <section className="console-grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Sessions</h2>
          </div>
          {sessions.length ? (
            <ul className="session-list">
              {sessions.map((session) => (
                <li key={session.sessionId}>
                  <button
                    type="button"
                    className={session.sessionId === selectedSessionId ? 'selected' : ''}
                    onClick={() => setSelectedSessionId(session.sessionId)}
                  >
                    <strong>{session.label}</strong>
                    <span>{session.status}</span>
                  </button>
                  <p className="session-meta">{session.detail}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">
              {state === 'error'
                ? 'No sessions are available while the backend is unreachable.'
                : 'No runtime sessions returned yet.'}
            </p>
          )}
        </article>

        <article className="panel panel-wide">
          <div className="panel-header">
            <h2>Timeline</h2>
          </div>
          {selectedSession ? (
            <div className="session-details">
              <p className="request-text">
                <strong>{selectedSession.label}</strong>
                <br />
                {selectedSession.detail}
              </p>
              {timelineState === 'loading' ? <p className="empty">Loading timeline events.</p> : null}
              {timelineState === 'error' ? <p className="empty">Timeline unavailable for this session.</p> : null}
              {timelineState === 'ready' && timeline.length ? (
                <ul className="timeline">
                  {timeline.map((item) => (
                    <li key={`${item.timestamp}-${item.event_type}-${item.title}`}>
                      <div className="timeline-row">
                        <strong>{item.title}</strong>
                        <span>{item.severity}</span>
                      </div>
                      <p>{describeTimelineItem(item)}</p>
                      <time>{item.timestamp}</time>
                    </li>
                  ))}
                </ul>
              ) : null}
              {timelineState === 'ready' && !timeline.length ? (
                <p className="empty">No timeline events returned for this session.</p>
              ) : null}
            </div>
          ) : (
            <p className="empty">
              {state === 'error'
                ? 'Session timeline is offline because the backend could not be reached.'
                : 'Select a session to view its timeline.'}
            </p>
          )}
        </article>
      </section>
    </main>
  );
}
