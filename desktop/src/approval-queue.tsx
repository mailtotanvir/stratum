import { useEffect, useState } from 'react';
import { getRuntimeApiBaseUrl } from './api/config';
import {
  getRuntimeDashboard,
  getRuntimeSessionGovernance,
  respondToAgentLoopApproval,
  continueAgentLoopApproval,
  resumeAgentLoopApproval,
  type RuntimeDashboard,
  type RuntimeGovernanceSnapshot,
  type RuntimeSessionOverview,
} from './api/runtime';

type LoadState = 'loading' | 'ready' | 'error';

type ApprovalActionState = {
  approvalId: string | null;
  kind: 'approve' | 'reject' | null;
};

function formatApprovalContext(session: RuntimeSessionOverview) {
  const parts = [
    session.provider ?? 'no provider',
    session.model ?? 'no model',
    session.current_iteration != null && session.max_iterations != null
      ? `iteration ${session.current_iteration}/${session.max_iterations}`
      : null,
    session.updated_at,
  ].filter((value): value is string => value !== null);

  return parts.join(' · ');
}

function approvalSummary(session: RuntimeSessionOverview) {
  if (session.user_request) {
    return session.user_request;
  }
  if (session.last_tool) {
    return `Tool pending approval: ${session.last_tool}`;
  }
  return 'Approval pending for this session.';
}

export function ApprovalQueue() {
  const [state, setState] = useState<LoadState>('loading');
  const [dashboard, setDashboard] = useState<RuntimeDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [governanceBySession, setGovernanceBySession] = useState<Record<string, RuntimeGovernanceSnapshot>>({});
  const [actionState, setActionState] = useState<ApprovalActionState>({
    approvalId: null,
    kind: null,
  });

  const apiBaseUrl = getRuntimeApiBaseUrl();

  const pendingApprovals: RuntimeSessionOverview[] =
    dashboard?.latest_sessions.filter((session: RuntimeSessionOverview) => session.pending_approval) ?? [];

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const dashboardData = await getRuntimeDashboard();
      setDashboard(dashboardData);
      const snapshots = await Promise.all(
        dashboardData.latest_sessions
          .filter((session) => session.pending_approval || session.status === 'interrupted')
          .map(async (session) => [session.session_id, await getRuntimeSessionGovernance(session.session_id).catch(() => null)] as const),
      );
      setGovernanceBySession(
        Object.fromEntries(snapshots.filter((entry): entry is readonly [string, RuntimeGovernanceSnapshot] => entry[1] !== null)),
      );
      setState('ready');
    } catch (err) {
      setDashboard(null);
      setState('error');
      setError(err instanceof Error ? err.message : `Backend unavailable at ${apiBaseUrl}`);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const handleAction = async (approvalId: string, approved: boolean) => {
    setActionState({ approvalId, kind: approved ? 'approve' : 'reject' });
    setError(null);
    try {
      await respondToAgentLoopApproval(
        approvalId,
        approved,
        approved ? undefined : 'Rejected from desktop approval queue.',
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Approval action failed.');
    } finally {
      setActionState({ approvalId: null, kind: null });
    }
  };

  const handleResume = async (approvalId: string) => {
    setActionState({ approvalId, kind: 'approve' });
    try {
      await resumeAgentLoopApproval(approvalId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Resume action failed.');
    } finally {
      setActionState({ approvalId: null, kind: null });
    }
  };

  const handleContinue = async (approvalId: string) => {
    setActionState({ approvalId, kind: 'approve' });
    try {
      await continueAgentLoopApproval(approvalId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Continue action failed.');
    } finally {
      setActionState({ approvalId: null, kind: null });
    }
  };

  return (
    <main className="console-shell">
      <header className="console-hero">
        <div>
          <p className="eyebrow">Desktop Runtime Console</p>
          <h1>Approval queue</h1>
          <p className="hero-copy">
            Connected to <code>{apiBaseUrl}</code>
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void refresh()} disabled={refreshing}>
          {refreshing ? 'Refreshing' : 'Refresh'}
        </button>
      </header>

      <section className={`banner ${state === 'error' ? 'error' : ''}`}>
        {state === 'loading' ? 'Loading pending approvals.' : null}
        {state === 'ready' ? 'Pending approvals loaded.' : null}
        {state === 'error' ? error ?? 'Backend unavailable.' : null}
      </section>

      <section className="summary-grid">
        <article className="summary-card">
          <span>Pending approvals</span>
          <strong>{pendingApprovals.length}</strong>
        </article>
        <article className="summary-card">
          <span>Backend</span>
          <strong>{state === 'error' ? 'offline' : 'online'}</strong>
        </article>
        <article className="summary-card">
          <span>Last refresh</span>
          <strong>{refreshing ? 'refreshing' : 'current'}</strong>
        </article>
        <article className="summary-card">
          <span>Action</span>
          <strong>{actionState.kind ?? 'idle'}</strong>
        </article>
      </section>

      <section className="panel approval-panel">
        <div className="panel-header">
          <h2>Queue</h2>
        </div>
        {state === 'loading' ? <p className="empty">Loading approval queue.</p> : null}
        {state === 'error' ? (
          <p className="empty">Approval queue unavailable while the backend is unreachable.</p>
        ) : null}
        {state === 'ready' && !pendingApprovals.length ? (
          <p className="empty">No pending approvals.</p>
        ) : null}
        {pendingApprovals.length ? (
          <ul className="approval-list">
            {pendingApprovals.map((session) => {
              const isBusy = actionState.approvalId === session.pending_approval_id;
              return (
                <li key={session.pending_approval_id ?? session.session_id} className="approval-item">
                  <div className="approval-copy">
                    <div className="approval-topline">
                      <strong>{session.pending_approval_id ?? session.session_id}</strong>
                      <span>{session.status}</span>
                    </div>
                    <p className="approval-summary">{approvalSummary(session)}</p>
                    <p className="session-meta">{formatApprovalContext(session)}</p>
                    <dl className="approval-details">
                      <div>
                        <dt>Session</dt>
                        <dd>{session.session_id}</dd>
                      </div>
                      <div>
                        <dt>Tool</dt>
                        <dd>{session.last_tool ?? 'unknown'}</dd>
                      </div>
                      <div>
                        <dt>Result</dt>
                        <dd>{session.final_answer ?? session.error ?? 'Waiting for decision'}</dd>
                      </div>
                    </dl>
                    {governanceBySession[session.session_id] ? (
                      <div className="governance-history">
                        <h3>Approval history</h3>
                        <ul className="timeline">
                          {governanceBySession[session.session_id].approval_history.map((entry) => (
                            <li key={`${session.session_id}-${entry.timestamp}-${entry.status}`}>
                              <strong>{entry.status}</strong>
                              <span>{entry.message}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                  <div className="approval-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={isBusy || !session.pending_approval_id}
                      onClick={() => {
                        if (session.pending_approval_id) {
                          void handleAction(session.pending_approval_id, true);
                        }
                      }}
                    >
                      {isBusy && actionState.kind === 'approve' ? 'Approving' : 'Approve'}
                    </button>
                    <button
                      type="button"
                      className="secondary-button danger-button"
                      disabled={isBusy || !session.pending_approval_id}
                      onClick={() => {
                        if (session.pending_approval_id) {
                          void handleAction(session.pending_approval_id, false);
                        }
                      }}
                    >
                      {isBusy && actionState.kind === 'reject' ? 'Rejecting' : 'Reject'}
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={isBusy || !session.pending_approval_id}
                      onClick={() => {
                        if (session.pending_approval_id) {
                          void handleResume(session.pending_approval_id);
                        }
                      }}
                    >
                      Resume
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={isBusy || !session.pending_approval_id}
                      onClick={() => {
                        if (session.pending_approval_id) {
                          void handleContinue(session.pending_approval_id);
                        }
                      }}
                    >
                      Continue
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </section>
    </main>
  );
}
