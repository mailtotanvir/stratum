import React from 'react';
import ReactDOM from 'react-dom/client';
import { getRuntimeApiBaseUrl } from './api/config';
import { PlatformPanel } from './platform-panel';
import {
  createRuntimeTask,
  cancelAgentInvocation,
  cancelExecutionInvocation,
  continueAgentLoopApproval,
  createAgentInvocation,
  createExecutionInvocation,
  getActiveRuntimeWorkspace,
  getExecutionInvocations,
  getExecutionParticipantDiagnostics,
  getExecutionParticipantCapabilities,
  getExecutionParticipants,
  getAgentAdapterDiagnostics,
  getAgentAdapters,
  getAgentEventNormalizationCatalog,
  getAgentInvocationHistory,
  getAgentInvocationRecent,
  getAgentInvocationStatus,
  getArtifactMemory,
  getArtifactRecords,
  getDecisionIntelligence,
  getEvaluationAccountabilityProjection,
  getDecisionMemory,
  getEngineeringKnowledge,
  getProviderExecutionRecent,
  getProviderHealth,
  getProviderLiveDiagnostics,
  getProviderObservability,
  getRepositoryIntelligence,
  getRepositoryChangeSummary,
  getPatchRecords,
  getTransformationHistory,
  getTransformationSessions,
  createTransformationSession,
  getRepositoryMemory,
  getMemoryDiagnostics,
  getRuntimeDashboard,
  getRuntimeSession,
  getRuntimeSessionArtifacts,
  getRuntimeSessionTimeline,
  getRuntimeStatus,
  getRuntimeWorkspaceArtifacts,
  getSkillRegistry,
  getSkillRegistryDiagnostics,
  getWorkingMemory,
  getRepositoryIntelligenceDiagnostics,
  interruptRuntimeTask,
  interruptExecutionInvocation,
  listRuntimeSessions,
  listRuntimeWorkspaces,
  respondToAgentLoopApproval,
  runAgentLoop,
  runRuntimeTask,
  routeExecutionCapability,
  stopRuntimeTask,
  startExecutionInvocation,
  completeExecutionInvocation,
  type AgentAdapterCatalogEntry,
  type AgentAdapterRegistryDiagnostics,
  type AgentCapabilityManifest,
  type AgentEventNormalizationCatalog,
  type AgentInvocationHistorySummary,
  type AgentInvocationRecord,
  type AgentInvocationSummary,
  type AgentLoopResult,
  type ArtifactMemory,
  type ArtifactRecordView,
  type DecisionIntelligenceSummary,
  type EvaluationAccountabilityProjection,
  type DecisionMemory,
  type EngineeringKnowledgeCatalog,
  type MemorySourceSummary,
  type ProviderExecutionRecentItem,
  type ProviderHealth,
  type ProviderLiveDiagnostics,
  type ProviderObservabilityReport,
  type RepositoryMemory,
  type RuntimeDashboard,
  type RuntimeSessionListItem,
  type RuntimeSessionOverview,
  type RuntimeStatus,
  type RuntimeTimelineItem,
  type RuntimeTask,
  type RuntimeWorkspace,
  type RuntimeWorkspaceArtifact,
  type RuntimeWorkspaceSummary,
  type RepositoryIntelligenceSummary,
  type RepositoryIntelligenceDiagnostics,
  type RepositoryChangeSummary,
  type PatchRecordView,
  type TransformationSessionSummary,
  type SkillRegistryCatalog,
  type SkillRegistryDiagnostics,
  type MemoryDiagnostics,
  type WorkingMemory,
  type TransformationHistoryProjection,
  type ExecutionParticipant,
  type ExecutionParticipantRegistry,
  type ExecutionParticipantRegistryDiagnostics,
  type ExecutionInvocation,
} from './api/runtime';
import './styles.css';

type ViewId =
  | 'dashboard'
  | 'sessions'
  | 'session-detail'
  | 'timeline'
  | 'approvals'
  | 'provider'
  | 'artifacts'
  | 'workspace'
  | 'settings'
  | 'marketplace'
  | 'execution-fabric'
  | 'skills'
  | 'memory'
  | 'repository-intelligence'
  | 'engineering-knowledge'
  | 'transformation'
  | 'decision-intelligence'
  | 'evaluation-accountability'
  | 'platform';

type LoadState = 'loading' | 'ready' | 'empty' | 'error';

type PropsWithChildren<P = unknown> = P & {
  children?: React.ReactNode;
};

type ConsoleSnapshot = {
  status: RuntimeStatus | null;
  dashboard: RuntimeDashboard | null;
  sessions: RuntimeSessionListItem[];
  sessionOverview: RuntimeSessionOverview[];
  selectedSessionId: string | null;
  selectedTask: RuntimeTask | null;
  selectedSession: RuntimeSessionOverview | null;
  timeline: RuntimeTimelineItem[];
  sessionArtifacts: RuntimeWorkspaceArtifact[];
  workspaceArtifacts: RuntimeWorkspaceArtifact[];
  activeWorkspace: RuntimeWorkspace | null;
  workspaces: RuntimeWorkspaceSummary[];
  providerObservability: ProviderObservabilityReport | null;
  providerHealth: ProviderHealth | null;
  providerDiagnostics: ProviderLiveDiagnostics | null;
  providerExecutions: ProviderExecutionRecentItem[];
  agentAdapters: AgentAdapterCatalogEntry[];
  agentAdapterDiagnostics: AgentAdapterRegistryDiagnostics | null;
  agentEventNormalization: AgentEventNormalizationCatalog | null;
  agentInvocations: AgentInvocationRecord[];
  executionParticipants: ExecutionParticipant[];
  executionParticipantCapabilities: ExecutionParticipant['capability_manifest'];
  executionParticipantDiagnostics: ExecutionParticipantRegistryDiagnostics | null;
  executionInvocations: ExecutionInvocation[];
  executionRoutePreview: ExecutionParticipantRegistry | null;
  selectedInvocationId: string | null;
  selectedInvocationSummary: AgentInvocationSummary | null;
  selectedInvocationHistory: AgentInvocationHistorySummary | null;
  skillRegistry: SkillRegistryCatalog | null;
  skillRegistryDiagnostics: SkillRegistryDiagnostics | null;
  workingMemory: WorkingMemory | null;
  memoryDiagnostics: MemoryDiagnostics | null;
  repositoryMemory: RepositoryMemory | null;
  artifactMemory: ArtifactMemory[];
  decisionMemory: DecisionMemory[];
  repositoryIntelligence: RepositoryIntelligenceSummary | null;
  repositoryIntelligenceDiagnostics: RepositoryIntelligenceDiagnostics | null;
  repositoryChangeSummary: RepositoryChangeSummary | null;
  artifactRecords: ArtifactRecordView[];
  patchRecords: PatchRecordView[];
  transformationHistory: TransformationHistoryProjection | null;
  transformationSessions: TransformationSessionSummary[];
  engineeringKnowledge: EngineeringKnowledgeCatalog | null;
  decisionIntelligence: DecisionIntelligenceSummary | null;
  evaluationAccountability: EvaluationAccountabilityProjection | null;
};

type LaunchForm = {
  taskTitle: string;
  request: string;
  spec: string;
  context: string;
  runtimeConfig: string;
  maxIterations: string;
  providerId: string;
  model: string;
};

type InvocationForm = {
  adapterId: string;
  capabilityId: string;
  metadata: string;
};

const views: Array<{ id: ViewId; label: string; description: string }> = [
  { id: 'dashboard', label: 'Runtime Dashboard', description: 'Status and live counts' },
  { id: 'sessions', label: 'Session List', description: 'All runtime sessions' },
  { id: 'session-detail', label: 'Session Detail', description: 'Selected session summary' },
  { id: 'timeline', label: 'Timeline', description: 'Event stream and reconstruction' },
  { id: 'approvals', label: 'Pending Approvals', description: 'Operator decisions' },
  { id: 'provider', label: 'Provider Health', description: 'Diagnostics and observability' },
  { id: 'artifacts', label: 'Runtime Artifacts', description: 'Session and workspace outputs' },
  { id: 'workspace', label: 'Workspace Binding', description: 'Repository binding summary' },
  { id: 'settings', label: 'Settings', description: 'Configuration summary' },
  { id: 'marketplace', label: 'Agent Marketplace', description: 'Adapters and invocations' },
  { id: 'execution-fabric', label: 'Execution Fabric', description: 'Participants, capabilities, and invocations' },
  { id: 'skills', label: 'Skills', description: 'Registered skills summary' },
  { id: 'memory', label: 'Memory', description: 'Derived repository memory' },
  { id: 'repository-intelligence', label: 'Repository Intelligence', description: 'Architecture and inventory projections' },
  { id: 'engineering-knowledge', label: 'Engineering Knowledge', description: 'Reusable deterministic knowledge' },
  { id: 'transformation', label: 'Transformation Lifecycle', description: 'Artifacts, patches, and repository changes' },
  { id: 'decision-intelligence', label: 'Decision Intelligence', description: 'Decision patterns and outcomes' },
  { id: 'evaluation-accountability', label: 'Evaluation Accountability', description: 'Scenarios, runs, and regressions' },
  { id: 'platform', label: 'Platform Explorer', description: 'Extensions and diagnostics' },
];

function isMockAgentAdapter(entry: AgentAdapterCatalogEntry) {
  return entry.manifest.adapter_id === 'agent-mock-external' || Boolean(entry.manifest.metadata?.demo_only);
}

function formatDate(value: string | null | undefined) {
  return value ?? 'n/a';
}

function Panel({ title, action, children }: PropsWithChildren<{ title: string; action?: React.ReactNode }>) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function StateFrame({
  state,
  loading,
  empty,
  error,
  children,
}: PropsWithChildren<{ state: LoadState; loading: string; empty: string; error: string }>) {
  if (state === 'loading') return <p className="empty">{loading}</p>;
  if (state === 'empty') return <p className="empty">{empty}</p>;
  if (state === 'error') return <p className="empty error-copy">{error}</p>;
  return <>{children}</>;
}

function BadgeRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <article className="summary-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function useOperatorConsole() {
  const apiBaseUrl = getRuntimeApiBaseUrl();
  const [state, setState] = React.useState<LoadState>('loading');
  const [error, setError] = React.useState<string | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);
  const [selectedSessionId, setSelectedSessionId] = React.useState<string | null>(null);
  const [selectedInvocationId, setSelectedInvocationId] = React.useState<string | null>(null);
  const [launchState, setLaunchState] = React.useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [launchError, setLaunchError] = React.useState<string | null>(null);
  const [launchResult, setLaunchResult] = React.useState<AgentLoopResult | null>(null);
  const [launchTask, setLaunchTask] = React.useState<RuntimeTask | null>(null);
  const [launchForm, setLaunchForm] = React.useState<LaunchForm>({
    taskTitle: '',
    request: '',
    spec: '',
    context: '',
    runtimeConfig: '{\n  "mode": "governed"\n}',
    maxIterations: '5',
    providerId: '',
    model: '',
  });
  const [workflowError, setWorkflowError] = React.useState<string | null>(null);
  const [invocationForm, setInvocationForm] = React.useState<InvocationForm>({
    adapterId: '',
    capabilityId: '',
    metadata: '',
  });
  const [data, setData] = React.useState<ConsoleSnapshot>({
    status: null,
    dashboard: null,
    sessions: [],
    sessionOverview: [],
    selectedSessionId: null,
    selectedTask: null,
    selectedSession: null,
    timeline: [],
    sessionArtifacts: [],
    workspaceArtifacts: [],
    activeWorkspace: null,
    workspaces: [],
    providerObservability: null,
    providerHealth: null,
    providerDiagnostics: null,
    providerExecutions: [],
    agentAdapters: [],
    agentAdapterDiagnostics: null,
    agentEventNormalization: null,
    agentInvocations: [],
    executionParticipants: [],
    executionParticipantCapabilities: [],
    executionParticipantDiagnostics: null,
    executionInvocations: [],
    executionRoutePreview: null,
    selectedInvocationId: null,
    selectedInvocationSummary: null,
    selectedInvocationHistory: null,
    skillRegistry: null,
    skillRegistryDiagnostics: null,
    workingMemory: null,
    memoryDiagnostics: null,
    repositoryMemory: null,
    artifactMemory: [],
    decisionMemory: [],
    repositoryIntelligence: null,
    repositoryIntelligenceDiagnostics: null,
    repositoryChangeSummary: null,
    artifactRecords: [],
    patchRecords: [],
    transformationHistory: null,
    transformationSessions: [],
    engineeringKnowledge: null,
    decisionIntelligence: null,
    evaluationAccountability: null,
  });

  const loadSelectedSession = async (sessionId: string | null) => {
    if (!sessionId) return;
    const [selectedSession, timeline, sessionArtifacts, workingMemory] = await Promise.all([
      getRuntimeSession(sessionId),
      getRuntimeSessionTimeline(sessionId).catch(() => []),
      getRuntimeSessionArtifacts(sessionId).catch(() => []),
      getWorkingMemory(sessionId).catch(() => null),
    ]);
    setData((current) => ({
      ...current,
      selectedSessionId: sessionId,
      selectedSession,
      timeline,
      sessionArtifacts,
      workingMemory,
    }));
  };

  const loadSelectedInvocation = async (invocationId: string | null) => {
    if (!invocationId) return;
    const [summary, history] = await Promise.all([
      getAgentInvocationStatus(invocationId),
      getAgentInvocationHistory(invocationId),
    ]);
    setData((current) => ({
      ...current,
      selectedInvocationId: invocationId,
      selectedInvocationSummary: summary,
      selectedInvocationHistory: history,
    }));
  };

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [status, dashboard, sessions, workspaces, activeWorkspace, providerObservability, providerHealth, providerDiagnostics, providerExecutions, agentAdapters, agentAdapterDiagnostics, agentEventNormalization, agentInvocations, executionParticipants, executionParticipantCapabilities, executionParticipantDiagnostics, executionInvocations, skillRegistry, skillRegistryDiagnostics, memoryDiagnostics, repositoryMemory, artifactMemory, decisionMemory, artifactRecords, patchRecords, repositoryChangeSummary, transformationHistory, transformationSessions, repositoryIntelligence, repositoryIntelligenceDiagnostics, engineeringKnowledge, decisionIntelligence, evaluationAccountability] =
        await Promise.all([
          getRuntimeStatus(),
          getRuntimeDashboard(),
          listRuntimeSessions().catch(() => []),
          listRuntimeWorkspaces().catch(() => []),
          getActiveRuntimeWorkspace().catch(() => null),
          getProviderObservability().catch(() => null),
          getProviderHealth().catch(() => null),
          getProviderLiveDiagnostics().catch(() => null),
          getProviderExecutionRecent().catch(() => []),
          getAgentAdapters().catch(() => ({ adapters: [] })),
          getAgentAdapterDiagnostics().catch(() => null),
          getAgentEventNormalizationCatalog().catch(() => null),
          getAgentInvocationRecent().catch(() => ({ invocations: [] })),
          getExecutionParticipants().catch(() => []),
          getExecutionParticipantCapabilities().catch(() => []),
          getExecutionParticipantDiagnostics().catch(() => null),
          getExecutionInvocations().catch(() => []),
          getSkillRegistry().catch(() => null),
          getSkillRegistryDiagnostics().catch(() => null),
          getMemoryDiagnostics().catch(() => null),
          getRepositoryMemory().catch(() => null),
          getArtifactMemory().catch(() => []),
          getDecisionMemory().catch(() => []),
          getArtifactRecords().catch(() => []),
          getPatchRecords().catch(() => []),
          getRepositoryChangeSummary().catch(() => null),
          getTransformationHistory().catch(() => null),
          getTransformationSessions().catch(() => ({ items: [], total: 0 })),
          getRepositoryIntelligence().catch(() => null),
          getRepositoryIntelligenceDiagnostics().catch(() => null),
          getEngineeringKnowledge().catch(() => null),
          getDecisionIntelligence().catch(() => null),
          getEvaluationAccountabilityProjection().catch(() => null),
        ]);
      const sessionOverview = dashboard.latest_sessions;
      const nextSessionId = selectedSessionId ?? sessionOverview[0]?.session_id ?? sessions[0]?.id ?? null;
      const nextInvocationId = selectedInvocationId ?? agentInvocations.invocations[0]?.invocation_id ?? null;
      const nextWorkingMemory = nextSessionId ? await getWorkingMemory(nextSessionId).catch(() => null) : null;
      const nextWorkspaceArtifacts = activeWorkspace ? await getRuntimeWorkspaceArtifacts(activeWorkspace.workspace_id).catch(() => []) : [];
      setData({
        status,
        dashboard,
        sessions,
        sessionOverview,
        selectedSessionId: nextSessionId,
        selectedTask: null,
        selectedSession: null,
        timeline: [],
        sessionArtifacts: [],
        workspaceArtifacts: nextWorkspaceArtifacts,
        activeWorkspace,
        workspaces,
        providerObservability,
        providerHealth,
        providerDiagnostics,
        providerExecutions,
        agentAdapters: agentAdapters.adapters,
        agentAdapterDiagnostics,
        agentEventNormalization,
        agentInvocations: agentInvocations.invocations,
        executionParticipants,
        executionParticipantCapabilities,
        executionParticipantDiagnostics,
        executionInvocations,
        executionRoutePreview: null,
        selectedInvocationId: nextInvocationId,
        selectedInvocationSummary: null,
        selectedInvocationHistory: null,
        skillRegistry,
        skillRegistryDiagnostics,
        memoryDiagnostics,
        workingMemory: nextWorkingMemory,
        repositoryMemory,
        artifactMemory,
        decisionMemory,
        artifactRecords,
        patchRecords,
        repositoryChangeSummary,
        transformationHistory,
        transformationSessions: transformationSessions.items,
        repositoryIntelligence,
        repositoryIntelligenceDiagnostics,
        engineeringKnowledge,
        decisionIntelligence,
        evaluationAccountability,
      });
      setState(status || dashboard.latest_sessions.length || providerObservability || providerHealth ? 'ready' : 'empty');
      if (nextSessionId) await loadSelectedSession(nextSessionId);
      if (nextInvocationId) await loadSelectedInvocation(nextInvocationId);
    } catch (err) {
      setState('error');
      setData((current) => ({
        ...current,
        status: null,
        dashboard: null,
        sessions: [],
        sessionOverview: [],
        selectedSessionId: null,
        selectedTask: null,
        selectedSession: null,
        timeline: [],
        sessionArtifacts: [],
        workspaceArtifacts: [],
        activeWorkspace: null,
        workspaces: [],
        providerObservability: null,
        providerHealth: null,
        providerDiagnostics: null,
        providerExecutions: [],
        agentAdapters: [],
        agentAdapterDiagnostics: null,
        agentEventNormalization: null,
        agentInvocations: [],
        executionParticipants: [],
        executionParticipantCapabilities: [],
        executionParticipantDiagnostics: null,
        executionInvocations: [],
        executionRoutePreview: null,
        selectedInvocationId: null,
        selectedInvocationSummary: null,
        selectedInvocationHistory: null,
        skillRegistry: null,
        skillRegistryDiagnostics: null,
        workingMemory: null,
        memoryDiagnostics: null,
        repositoryMemory: null,
        artifactMemory: [],
        decisionMemory: [],
        artifactRecords: [],
        patchRecords: [],
        repositoryChangeSummary: null,
        transformationHistory: null,
        transformationSessions: [],
        repositoryIntelligence: null,
        repositoryIntelligenceDiagnostics: null,
        engineeringKnowledge: null,
        decisionIntelligence: null,
        evaluationAccountability: null,
      }));
      setError(err instanceof Error ? err.message : `Backend unavailable at ${apiBaseUrl}`);
    } finally {
      setRefreshing(false);
    }
  };

  const submitLaunch = async () => {
    if (!launchForm.request.trim()) {
      setLaunchState('error');
      setLaunchError('Task request is required.');
      return;
    }
    setLaunchState('running');
    setLaunchError(null);
    try {
      const runtimeConfig = launchForm.runtimeConfig.trim()
        ? JSON.parse(launchForm.runtimeConfig)
        : {};
      const task = await createRuntimeTask({
        title: launchForm.taskTitle.trim() || launchForm.request.trim(),
      });
      await runRuntimeTask(task.id);
      const session = (await listRuntimeSessions()).find((item) => item.task_id === task.id) ?? null;
      const requestPayload = [
        `Engineering task: ${launchForm.request.trim()}`,
        launchForm.spec.trim() ? `Specification:\n${launchForm.spec.trim()}` : null,
        launchForm.context.trim() ? `Context documents:\n${launchForm.context.trim()}` : null,
        `Runtime config:\n${JSON.stringify(runtimeConfig, null, 2)}`,
      ]
        .filter((part): part is string => Boolean(part))
        .join('\n\n');
      const response = await runAgentLoop({
        session_id: session?.id ?? task.id,
        user_request: requestPayload,
        max_iterations: Number(launchForm.maxIterations || '5'),
        workspace_id: data.activeWorkspace?.workspace_id ?? undefined,
        provider_id: launchForm.providerId.trim() || undefined,
        model: launchForm.model.trim() || undefined,
      });
      setLaunchResult(response);
      setLaunchTask(task);
      setLaunchState('done');
      setSelectedSessionId(response.session_id);
      await refresh();
    } catch (err) {
      setLaunchState('error');
      setLaunchError(err instanceof Error ? err.message : 'Runtime session launch failed.');
    }
  };

  const controlTask = async (taskId: string, action: 'interrupt' | 'stop') => {
    setWorkflowError(null);
    try {
      if (action === 'interrupt') {
        await interruptRuntimeTask(taskId);
      } else {
        await stopRuntimeTask(taskId);
      }
      await refresh();
    } catch (err) {
      setWorkflowError(err instanceof Error ? err.message : `${action} failed.`);
    }
  };

  const submitInvocation = async () => {
    try {
      const metadata = invocationForm.metadata.trim() ? JSON.parse(invocationForm.metadata) : {};
      const created = await createAgentInvocation({
        adapter_id: invocationForm.adapterId.trim(),
        capability_id: invocationForm.capabilityId.trim(),
        metadata,
      });
      setSelectedInvocationId(created.invocation_id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invocation creation failed.');
    }
  };

  const submitExecutionInvocation = async (capabilityId: string) => {
    const route = await routeExecutionCapability(capabilityId.trim());
    const created = await createExecutionInvocation(capabilityId.trim());
    setData((current) => ({
      ...current,
      executionRoutePreview: route,
      executionInvocations: [created, ...current.executionInvocations],
    }));
  };

  const advanceExecutionInvocation = async (invocationId: string, action: 'start' | 'complete' | 'cancel' | 'interrupt') => {
    const next =
      action === 'start'
        ? await startExecutionInvocation(invocationId)
        : action === 'complete'
          ? await completeExecutionInvocation(invocationId, { inspected_from: 'desktop-console' })
          : action === 'cancel'
            ? await cancelExecutionInvocation(invocationId)
            : await interruptExecutionInvocation(invocationId);
    setData((current) => ({
      ...current,
      executionInvocations: current.executionInvocations.map((item) =>
        item.invocation_id === invocationId ? next : item,
      ),
    }));
  };

  React.useEffect(() => {
    void refresh();
  }, []);

  return {
    apiBaseUrl,
    state,
    error,
    refreshing,
    refresh,
    data,
    selectedSessionId,
    selectedInvocationId,
    setSelectedSessionId,
    setSelectedInvocationId,
    loadSelectedSession,
    loadSelectedInvocation,
    launchForm,
    setLaunchForm,
    launchState,
    launchError,
    launchResult,
    launchTask,
    submitLaunch,
    workflowError,
    controlTask,
    invocationForm,
    setInvocationForm,
    submitInvocation,
    submitExecutionInvocation,
    advanceExecutionInvocation,
  };
}

function App() {
  const [view, setView] = React.useState<ViewId>('dashboard');
  const c = useOperatorConsole();
  const selectedSession =
    c.data.selectedSession ?? c.data.sessionOverview.find((session) => session.session_id === c.selectedSessionId) ?? null;
  const pendingApprovals = c.data.sessionOverview.filter((session) => session.pending_approval);
  const mockAdapter = c.data.agentAdapters.find(isMockAgentAdapter) ?? null;
  const hasData = Boolean(c.data.dashboard || c.data.status || c.data.providerObservability || c.data.skillRegistry || c.data.repositoryIntelligence || c.data.evaluationAccountability);
  const backendUnavailable = c.state === 'error' && !hasData;

  const selectSession = (sessionId: string) => {
    c.setSelectedSessionId(sessionId);
    setView('session-detail');
    void c.loadSelectedSession(sessionId);
  };

  const selectedInvocation =
    c.data.selectedInvocationHistory ?? c.data.selectedInvocationSummary ?? null;

  const submitTransformationSession = async () => {
    if (!c.launchForm.request.trim() || !c.launchForm.spec.trim()) {
      return;
    }
    try {
      await createTransformationSession({
        title: c.launchForm.taskTitle.trim() || c.launchForm.request.trim(),
        objective: c.launchForm.request.trim(),
        specification: c.launchForm.spec.trim(),
        context_markdown: c.launchForm.context.trim() || null,
        requested_by: 'operator',
        validation_command: 'git diff --check',
      });
      await c.refresh();
    } catch {
      // Keep the transformation workflow non-blocking in the console.
    }
  };

  return (
    <div className="desktop-app-shell">
      <aside className="desktop-nav">
        <div className="desktop-brand">
          <p className="eyebrow">Stratum</p>
          <h1>Operator Console</h1>
          <p className="hero-copy">Local desktop control surface over FastAPI in WSL.</p>
        </div>
        <nav className="desktop-nav-list" aria-label="Operator console sections">
          {views.map((item) => (
            <button
              key={item.id}
              type="button"
              className={view === item.id ? 'desktop-nav-item selected' : 'desktop-nav-item'}
              onClick={() => setView(item.id)}
            >
              <span>{item.label}</span>
              <small>{item.description}</small>
            </button>
          ))}
        </nav>
      </aside>
      <section className="desktop-content">
        <main className="console-shell">
          <header className="console-hero">
            <div>
              <p className="eyebrow">Desktop Operator Console</p>
              <h1>{views.find((item) => item.id === view)?.label ?? 'Operator Console'}</h1>
              <p className="hero-copy">
                Connected to <code>{c.apiBaseUrl}</code>
              </p>
            </div>
            <button type="button" className="secondary-button" onClick={() => void c.refresh()} disabled={c.refreshing}>
              {c.refreshing ? 'Refreshing' : 'Refresh'}
            </button>
          </header>
          <section className={`banner ${c.state === 'error' ? 'error' : ''}`}>
            {c.state === 'loading'
              ? 'Loading runtime dashboard, sessions, approvals, provider health, skills, and memory summaries.'
              : c.state === 'ready'
                ? 'Operator console loaded.'
                : c.state === 'empty'
                  ? 'Backend responded, but no runtime data is available yet.'
                  : c.error ?? `Backend unavailable at ${c.apiBaseUrl}.`}
          </section>
          {backendUnavailable ? (
            <p className="empty error-copy">The backend could not be reached. The console is offline until localhost FastAPI is available.</p>
          ) : null}
          <section className="summary-grid">
            <BadgeRow label="Runtime" value={c.data.status?.runtime_status ?? 'unknown'} />
            <BadgeRow label="Provider" value={c.data.status?.provider_status ?? 'unknown'} />
            <BadgeRow label="Active Sessions" value={c.data.dashboard?.active_sessions ?? c.data.status?.active_sessions ?? 0} />
            <BadgeRow label="Pending Approvals" value={c.data.dashboard?.pending_approvals ?? pendingApprovals.length} />
          </section>

          {view === 'dashboard' ? (
            <section className="console-grid">
              <Panel title="Runtime Overview">
                <StateFrame state={c.state} loading="Loading runtime overview." empty="No runtime overview returned yet." error={c.error ?? 'Runtime overview unavailable.'}>
                  <dl className="details">
                    <div><dt>Backend</dt><dd>{c.data.status?.backend_version ?? 'unknown'}</dd></div>
                    <div><dt>Runtime status</dt><dd>{c.data.status?.runtime_status ?? 'unknown'}</dd></div>
                    <div><dt>Provider status</dt><dd>{c.data.status?.provider_status ?? 'unknown'}</dd></div>
                    <div><dt>Registered tools</dt><dd>{c.data.status?.registered_tools.length ?? 0}</dd></div>
                  </dl>
                </StateFrame>
              </Panel>
              <Panel title="Task Launcher">
                <StateFrame state={c.state} loading="Loading launch context." empty="No launch context available." error={c.error ?? 'Launch form unavailable.'}>
                  <form className="launch-form" onSubmit={(event: { preventDefault(): void }) => { event.preventDefault(); void c.submitLaunch(); }}>
                    <label><span>Task title</span><input value={c.launchForm.taskTitle} onChange={(event: { target: { value: string } }) => c.setLaunchForm((current) => ({ ...current, taskTitle: event.target.value }))} placeholder="operator session task" /></label>
                    <label><span>Task request</span><textarea value={c.launchForm.request} rows={4} onChange={(event: { target: { value: string } }) => c.setLaunchForm((current) => ({ ...current, request: event.target.value }))} /></label>
                    <label><span>Specification</span><textarea value={c.launchForm.spec} rows={4} onChange={(event: { target: { value: string } }) => c.setLaunchForm((current) => ({ ...current, spec: event.target.value }))} placeholder="Acceptance criteria, implementation notes, or engineering constraints." /></label>
                    <label><span>Context documents</span><textarea value={c.launchForm.context} rows={4} onChange={(event: { target: { value: string } }) => c.setLaunchForm((current) => ({ ...current, context: event.target.value }))} placeholder="Paste design docs, issue summaries, or repository context." /></label>
                    <label><span>Runtime config</span><textarea value={c.launchForm.runtimeConfig} rows={5} onChange={(event: { target: { value: string } }) => c.setLaunchForm((current) => ({ ...current, runtimeConfig: event.target.value }))} /></label>
                    <div className="launch-grid">
                      <label><span>Workspace</span><input value={c.data.activeWorkspace?.name ?? 'active workspace'} readOnly /></label>
                      <label><span>Provider</span><input value={c.launchForm.providerId} onChange={(event: { target: { value: string } }) => c.setLaunchForm((current) => ({ ...current, providerId: event.target.value }))} /></label>
                      <label><span>Model</span><input value={c.launchForm.model} onChange={(event: { target: { value: string } }) => c.setLaunchForm((current) => ({ ...current, model: event.target.value }))} /></label>
                      <label><span>Max iterations</span><input value={c.launchForm.maxIterations} inputMode="numeric" onChange={(event: { target: { value: string } }) => c.setLaunchForm((current) => ({ ...current, maxIterations: event.target.value }))} /></label>
                    </div>
                    <div className="launch-actions">
                      <button type="submit" className="secondary-button" disabled={c.launchState === 'running'}>{c.launchState === 'running' ? 'Launching' : 'Run session'}</button>
                      <span className="session-meta">{c.data.activeWorkspace ? `Bound to ${c.data.activeWorkspace.workspace_id}` : 'No active workspace'}</span>
                    </div>
                  </form>
                  {c.launchError ? <p className="empty error-copy">{c.launchError}</p> : null}
                    {c.launchResult ? (
                      <div className="session-details">
                        <h3>Latest launch</h3>
                        <dl className="details">
                          <div><dt>Task</dt><dd>{c.launchTask?.id ?? 'pending'}</dd></div>
                          <div><dt>Session</dt><dd>{c.launchResult.session_id}</dd></div>
                          <div><dt>Status</dt><dd>{c.launchResult.status}</dd></div>
                        <div><dt>Iterations</dt><dd>{c.launchResult.iterations_used}</dd></div>
                        <div><dt>Answer</dt><dd>{c.launchResult.final_answer ?? c.launchResult.error ?? 'Pending'}</dd></div>
                      </dl>
                      {c.launchTask?.id ? (
                        <div className="launch-actions">
                          <button type="button" className="secondary-button" onClick={() => void c.controlTask(c.launchTask!.id, 'interrupt')}>Interrupt task</button>
                          <button type="button" className="secondary-button danger-button" onClick={() => void c.controlTask(c.launchTask!.id, 'stop')}>Stop task</button>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {c.workflowError ? <p className="empty error-copy">{c.workflowError}</p> : null}
                </StateFrame>
              </Panel>
            </section>
          ) : null}

          {view === 'sessions' ? (
            <section className="console-grid">
              <Panel title="Session List">
                <StateFrame state={c.state} loading="Loading session inventory." empty="No sessions available yet." error={c.error ?? 'Session inventory unavailable.'}>
                  <ul className="session-list">
                    {(c.data.sessionOverview.length ? c.data.sessionOverview : c.data.dashboard?.latest_sessions ?? []).map((session) => (
                      <li key={session.session_id}>
                        <button type="button" onClick={() => selectSession(session.session_id)} className={session.session_id === c.selectedSessionId ? 'selected' : ''}>
                          <strong>{session.session_id}</strong>
                          <span>{session.status}</span>
                        </button>
                        <p className="session-meta">{session.user_request ?? session.last_tool ?? 'No request text'} · {formatDate(session.started_at)}</p>
                      </li>
                    ))}
                  </ul>
                </StateFrame>
              </Panel>
              <Panel title="Session Snapshot">
                <StateFrame state={selectedSession ? 'ready' : 'empty'} loading="Loading selected session." empty="Select a session to inspect its detail view." error={c.error ?? 'Session snapshot unavailable.'}>
                  {selectedSession ? (
                    <dl className="details">
                      <div><dt>Status</dt><dd>{selectedSession.status}</dd></div>
                      <div><dt>Provider</dt><dd>{selectedSession.provider ?? 'n/a'}</dd></div>
                      <div><dt>Model</dt><dd>{selectedSession.model ?? 'n/a'}</dd></div>
                      <div><dt>Result</dt><dd>{selectedSession.final_answer ?? selectedSession.error ?? 'Pending'}</dd></div>
                    </dl>
                  ) : null}
                </StateFrame>
              </Panel>
            </section>
          ) : null}

          {view === 'session-detail' ? (
            <section className="console-grid">
              <Panel title="Session Detail">
                <StateFrame state={selectedSession ? 'ready' : 'empty'} loading="Loading session detail." empty="Select a session to inspect its detail view." error={c.error ?? 'Session detail unavailable.'}>
                  {selectedSession ? (
                    <div className="session-details">
                      <p className="request-text"><strong>{selectedSession.session_id}</strong><br />{selectedSession.user_request ?? 'No request text'}</p>
                      <dl className="details">
                        <div><dt>Status</dt><dd>{selectedSession.status}</dd></div>
                        <div><dt>Provider</dt><dd>{selectedSession.provider ?? 'n/a'}</dd></div>
                        <div><dt>Model</dt><dd>{selectedSession.model ?? 'n/a'}</dd></div>
                        <div><dt>Result</dt><dd>{selectedSession.final_answer ?? selectedSession.error ?? 'Pending'}</dd></div>
                      </dl>
                    </div>
                  ) : null}
                </StateFrame>
              </Panel>
              <Panel title="Session Controls">
                <dl className="details">
                  <div><dt>Approval</dt><dd>{selectedSession?.pending_approval ? 'pending' : 'clear'}</dd></div>
                  <div><dt>Selected</dt><dd>{c.selectedSessionId ?? 'none'}</dd></div>
                  <div><dt>Loading</dt><dd>{String(c.state === 'loading')}</dd></div>
                  <div><dt>View</dt><dd>session detail</dd></div>
                </dl>
              </Panel>
            </section>
          ) : null}

          {view === 'timeline' ? (
            <Panel title="Timeline / Event Stream">
              <StateFrame state={c.data.timeline.length ? 'ready' : c.state} loading="Loading session timeline." empty="Select a session with timeline data." error={c.error ?? 'Timeline unavailable.'}>
                <ul className="timeline">
                  {c.data.timeline.map((item) => (
                    <li key={`${item.timestamp}-${item.event_type}-${item.title}`}>
                      <div className="timeline-row"><strong>{item.title}</strong><span>{item.severity}</span></div>
                      <p>{item.summary}</p>
                      <time>{item.timestamp}</time>
                    </li>
                  ))}
                </ul>
              </StateFrame>
            </Panel>
          ) : null}

          {view === 'approvals' ? (
            <Panel title="Pending Approvals">
              <StateFrame state={pendingApprovals.length ? 'ready' : c.state} loading="Loading pending approvals." empty="No pending approvals." error={c.error ?? 'Pending approvals unavailable.'}>
                <ul className="approval-list">
                  {pendingApprovals.map((session) => (
                    <li key={session.pending_approval_id ?? session.session_id} className="approval-item">
                      <div className="approval-copy">
                        <div className="approval-topline"><strong>{session.pending_approval_id ?? session.session_id}</strong><span>{session.status}</span></div>
                        <p className="approval-summary">{session.user_request ?? session.last_tool ?? 'Approval pending for this session.'}</p>
                        <p className="session-meta">{session.provider ?? 'no provider'} · {formatDate(session.updated_at)}</p>
                      </div>
                      <div className="approval-actions">
                        <button type="button" className="secondary-button" onClick={() => session.pending_approval_id && void respondToAgentLoopApproval(session.pending_approval_id, true)}>Approve</button>
                        <button type="button" className="secondary-button danger-button" onClick={() => session.pending_approval_id && void respondToAgentLoopApproval(session.pending_approval_id, false, 'Rejected from desktop approval queue.')}>Reject</button>
                        <button type="button" className="secondary-button" onClick={() => session.pending_approval_id && void continueAgentLoopApproval(session.pending_approval_id)}>Continue</button>
                      </div>
                    </li>
                  ))}
                </ul>
              </StateFrame>
            </Panel>
          ) : null}

          {view === 'provider' ? (
            <section className="console-grid">
              <Panel title="Provider Health / Observability">
                <StateFrame state={c.data.providerObservability || c.data.providerHealth || c.data.providerDiagnostics ? 'ready' : c.state} loading="Loading provider observability." empty="No provider observability returned yet." error={c.error ?? 'Provider observability unavailable.'}>
                  <dl className="details">
                    <div><dt>Providers</dt><dd>{c.data.providerObservability?.provider_count ?? 0}</dd></div>
                    <div><dt>Models</dt><dd>{c.data.providerObservability?.model_count ?? 0}</dd></div>
                    <div><dt>Total requests</dt><dd>{c.data.providerObservability?.total_requests ?? 0}</dd></div>
                    <div><dt>Estimated</dt><dd>{String(c.data.providerObservability?.estimated ?? false)}</dd></div>
                  </dl>
                </StateFrame>
              </Panel>
              <Panel title="Diagnostics">
                <dl className="details">
                  <div><dt>Health</dt><dd>{c.data.providerHealth?.status ?? 'n/a'}</dd></div>
                  <div><dt>Ready</dt><dd>{String(c.data.providerHealth?.ready ?? c.data.providerDiagnostics?.ready ?? false)}</dd></div>
                  <div><dt>Configured</dt><dd>{String(c.data.providerHealth?.configured ?? c.data.providerDiagnostics?.configured ?? false)}</dd></div>
                  <div><dt>Streaming</dt><dd>{String(c.data.providerHealth?.supports_streaming ?? c.data.providerDiagnostics?.supports_streaming ?? false)}</dd></div>
                </dl>
              </Panel>
            </section>
          ) : null}

          {view === 'artifacts' ? (
            <section className="console-grid">
              <Panel title="Session Artifacts">
                <StateFrame state={c.data.sessionArtifacts.length ? 'ready' : c.state} loading="Loading artifacts." empty="No artifacts returned for the selected session." error={c.error ?? 'Artifacts unavailable.'}>
                  <ul className="timeline">
                    {c.data.sessionArtifacts.map((artifact) => (
                      <li key={artifact.artifact_id}>
                        <div className="timeline-row"><strong>{artifact.artifact_id}</strong><span>{artifact.artifact_type}</span></div>
                        <p>{artifact.summary}</p>
                        <p className="session-meta">{artifact.path ?? artifact.artifact?.path ?? 'n/a'}</p>
                      </li>
                    ))}
                  </ul>
                </StateFrame>
              </Panel>
              <Panel title="Workspace Artifacts">
                <StateFrame state={c.data.workspaceArtifacts.length ? 'ready' : c.state} loading="Loading workspace artifacts." empty="No workspace artifacts returned yet." error={c.error ?? 'Workspace artifacts unavailable.'}>
                  <ul className="timeline">
                    {c.data.workspaceArtifacts.map((artifact) => (
                      <li key={artifact.artifact_id}>
                        <div className="timeline-row"><strong>{artifact.artifact_id}</strong><span>{artifact.artifact_type}</span></div>
                        <p>{artifact.summary}</p>
                        <p className="session-meta">{artifact.path ?? artifact.artifact?.path ?? 'n/a'}</p>
                      </li>
                    ))}
                  </ul>
                </StateFrame>
              </Panel>
            </section>
          ) : null}

          {view === 'workspace' ? (
            <section className="console-grid">
              <Panel title="Workspace Binding Summary">
                <StateFrame state={c.data.activeWorkspace || c.data.workspaces.length ? 'ready' : c.state} loading="Loading workspace binding." empty="No workspace binding available." error={c.error ?? 'Workspace binding unavailable.'}>
                  <dl className="details">
                    <div><dt>Active workspace</dt><dd>{c.data.activeWorkspace?.name ?? 'n/a'}</dd></div>
                    <div><dt>Root path</dt><dd>{c.data.activeWorkspace?.root_path ?? 'n/a'}</dd></div>
                    <div><dt>Registered workspaces</dt><dd>{c.data.workspaces.length}</dd></div>
                    <div><dt>Binding</dt><dd>{c.data.activeWorkspace?.workspace_id ?? c.data.workspaces[0]?.workspace_id ?? 'n/a'}</dd></div>
                  </dl>
                </StateFrame>
              </Panel>
              <Panel title="Workspace List">
                <ul className="timeline">
                  {c.data.workspaces.map((workspace) => (
                    <li key={workspace.workspace_id}>
                      <div className="timeline-row"><strong>{workspace.name}</strong><span>{workspace.active ? 'active' : 'idle'}</span></div>
                      <p>{workspace.root_path}</p>
                    </li>
                  ))}
                </ul>
              </Panel>
            </section>
          ) : null}

          {view === 'settings' ? (
            <section className="console-grid">
              <Panel title="Configuration Summary">
                <dl className="details">
                  <div><dt>API base</dt><dd>{c.apiBaseUrl}</dd></div>
                  <div><dt>Workspace</dt><dd>{c.data.activeWorkspace?.name ?? 'n/a'}</dd></div>
                  <div><dt>Binding</dt><dd>{c.data.activeWorkspace?.root_path ?? 'n/a'}</dd></div>
                  <div><dt>Registered workspaces</dt><dd>{c.data.workspaces.length}</dd></div>
                </dl>
              </Panel>
              <Panel title="Routing Snapshot">
                <dl className="details">
                  <div><dt>Recent executions</dt><dd>{c.data.providerExecutions.length}</dd></div>
                  <div><dt>Provider status</dt><dd>{c.data.providerHealth?.status ?? c.data.providerDiagnostics?.display_name ?? 'n/a'}</dd></div>
                  <div><dt>Tools</dt><dd>{c.data.status?.registered_tools.length ?? 0}</dd></div>
                  <div><dt>Data</dt><dd>{hasData ? 'available' : 'empty'}</dd></div>
                </dl>
              </Panel>
            </section>
          ) : null}

          {view === 'marketplace' ? (
            <section className="console-grid">
              <Panel title="Agent Marketplace">
                <StateFrame state={c.data.agentAdapters.length ? 'ready' : c.state} loading="Loading agent adapters." empty="No agent adapters were returned." error={c.error ?? 'Agent adapter catalog unavailable.'}>
                  <ul className="catalog-list">
                    {c.data.agentAdapters.map((entry) => (
                      <li key={entry.manifest.adapter_id} className={`catalog-item ${isMockAgentAdapter(entry) ? 'mock-highlight' : ''}`}>
                        <div className="timeline-row"><strong>{entry.manifest.display_name}</strong><span>{entry.manifest.transport}</span></div>
                        <p className="session-meta">{entry.manifest.adapter_id} · {entry.manifest.version ?? 'no version'}</p>
                        <p className="request-text">{entry.manifest.description ?? 'No description provided.'}</p>
                        <dl className="details">
                          <div><dt>Capabilities</dt><dd>{entry.manifest.supported_capabilities.join(', ') || 'none'}</dd></div>
                          <div><dt>Agents</dt><dd>{entry.manifest.supported_agent_types.join(', ') || 'none'}</dd></div>
                          <div><dt>Modalities</dt><dd>{entry.manifest.supported_modalities.join(', ') || 'none'}</dd></div>
                          <div><dt>Observability</dt><dd>{String(entry.manifest.supports_observability)}</dd></div>
                        </dl>
                      </li>
                    ))}
                  </ul>
                </StateFrame>
              </Panel>
            </section>
          ) : null}

          {view === 'execution-fabric' ? (
            <section className="console-grid">
              <Panel title="Participant Explorer">
                <StateFrame state={c.data.executionParticipants.length ? 'ready' : c.state} loading="Loading execution participants." empty="No execution participants returned." error={c.error ?? 'Execution participant registry unavailable.'}>
                  <div className="details">
                    <div><dt>Total participants</dt><dd>{c.data.executionParticipantDiagnostics?.total_participants ?? c.data.executionParticipants.length}</dd></div>
                    <div><dt>Registry status</dt><dd>{c.data.executionParticipantDiagnostics?.status ?? 'unknown'}</dd></div>
                    <div><dt>Routing policy</dt><dd>{c.data.executionParticipantDiagnostics?.routing_policy ?? 'deterministic-human-governed'}</dd></div>
                    <div><dt>Warnings</dt><dd>{c.data.executionParticipantDiagnostics?.warnings.length ?? 0}</dd></div>
                  </div>
                  <ul className="catalog-list">
                    {c.data.executionParticipants.map((participant) => (
                      <li key={participant.participant_id} className="catalog-item">
                        <div className="timeline-row"><strong>{participant.display_name}</strong><span>{participant.kind}</span></div>
                        <p className="session-meta">{participant.participant_id} · {participant.version} · {participant.lifecycle}</p>
                        <p className="request-text">{participant.availability}</p>
                        <dl className="details">
                          <div><dt>Capabilities</dt><dd>{participant.capability_manifest.map((capability) => capability.capability_id).join(', ') || 'none'}</dd></div>
                          <div><dt>Health</dt><dd>{participant.health}</dd></div>
                          <div><dt>Operations</dt><dd>{participant.supported_operations.join(', ') || 'none'}</dd></div>
                        </dl>
                      </li>
                    ))}
                  </ul>
                </StateFrame>
              </Panel>
              <Panel title="Capability Explorer">
                <StateFrame state={c.data.executionParticipantCapabilities.length ? 'ready' : c.state} loading="Loading execution capabilities." empty="No execution capabilities returned." error={c.error ?? 'Execution capability manifests unavailable.'}>
                  <dl className="details">
                    <div><dt>Capabilities</dt><dd>{c.data.executionParticipantDiagnostics?.capabilities ? Object.keys(c.data.executionParticipantDiagnostics.capabilities).length : c.data.executionParticipantCapabilities.length}</dd></div>
                    <div><dt>Registry views</dt><dd>{c.data.executionParticipantDiagnostics?.registry_views.join(', ') ?? 'participant, capability, invocation'}</dd></div>
                    <div><dt>Route preview</dt><dd>{c.data.executionRoutePreview?.selected_participant_id ?? 'none'}</dd></div>
                    <div><dt>Eligible routes</dt><dd>{c.data.executionRoutePreview?.eligible_participant_ids.length ?? 0}</dd></div>
                  </dl>
                  <ul className="timeline">
                    {c.data.executionParticipantCapabilities.map((capability) => (
                      <li key={`${capability.participant_id}:${capability.capability_id}`}>
                        <div className="timeline-row"><strong>{capability.display_name}</strong><span>{capability.kind}</span></div>
                        <p>{capability.participant_id} · route {capability.route_order}</p>
                        <p className="session-meta">{capability.capability_id} · {capability.lifecycle} · {capability.health}</p>
                      </li>
                    ))}
                  </ul>
                </StateFrame>
              </Panel>
              <Panel title="Invocation Explorer">
                <StateFrame state={c.data.executionInvocations.length ? 'ready' : c.state} loading="Loading execution invocations." empty="No execution invocations returned." error={c.error ?? 'Execution invocation history unavailable.'}>
                  <ul className="session-list">
                    {c.data.executionInvocations.map((invocation) => (
                      <li key={invocation.invocation_id}>
                        <button type="button" className={invocation.invocation_id === c.selectedInvocationId ? 'selected' : ''} onClick={() => void c.loadSelectedInvocation(invocation.invocation_id)}>
                          <strong>{invocation.invocation_id}</strong>
                          <span>{invocation.state}</span>
                        </button>
                        <p className="session-meta">{invocation.participant_id} · {invocation.capability_id}</p>
                        <div className="launch-actions">
                          <button type="button" className="secondary-button" onClick={() => void c.advanceExecutionInvocation(invocation.invocation_id, 'start')}>Start</button>
                          <button type="button" className="secondary-button" onClick={() => void c.advanceExecutionInvocation(invocation.invocation_id, 'complete')}>Complete</button>
                          <button type="button" className="secondary-button danger-button" onClick={() => void c.advanceExecutionInvocation(invocation.invocation_id, 'interrupt')}>Interrupt</button>
                        </div>
                      </li>
                    ))}
                  </ul>
                  <form className="launch-form" onSubmit={(event: { preventDefault(): void }) => { event.preventDefault(); void c.submitExecutionInvocation(c.invocationForm.capabilityId || 'approval'); }}>
                    <h3>Launch governed invocation</h3>
                    <label><span>Capability id</span><input value={c.invocationForm.capabilityId} onChange={(event: { target: { value: string } }) => c.setInvocationForm((current) => ({ ...current, capabilityId: event.target.value }))} placeholder="approval" /></label>
                    <div className="launch-actions">
                      <button type="submit" className="secondary-button">Create governed invocation</button>
                      <button type="button" className="secondary-button danger-button" onClick={() => c.selectedInvocationId && void c.advanceExecutionInvocation(c.selectedInvocationId, 'cancel')}>Cancel selected</button>
                    </div>
                  </form>
                </StateFrame>
              </Panel>
            </section>
          ) : null}

          {view === 'skills' ? (
            <section className="console-grid">
              <Panel title="Skills Summary">
                <StateFrame state={c.data.skillRegistry ? 'ready' : c.state} loading="Loading skills." empty="No skills returned yet." error={c.error ?? 'Skills unavailable.'}>
                  <dl className="details">
                    <div><dt>Registered skills</dt><dd>{c.data.skillRegistry?.registered_skills_total ?? 0}</dd></div>
                    <div><dt>Top skill</dt><dd>{c.data.skillRegistry?.skills[0]?.name ?? 'n/a'}</dd></div>
                    <div><dt>Category</dt><dd>{c.data.skillRegistry?.skills[0]?.category ?? 'n/a'}</dd></div>
                    <div><dt>Source</dt><dd>{c.data.skillRegistry?.skills[0]?.source ?? 'n/a'}</dd></div>
                  </dl>
                  <p className="session-meta">{c.data.skillRegistryDiagnostics?.status ?? 'no diagnostics'} · warnings: {c.data.skillRegistryDiagnostics?.warnings.length ?? 0}</p>
                </StateFrame>
              </Panel>
              <Panel title="Registered Skills">
                <ul className="timeline">
                  {c.data.skillRegistry?.skills.map((skill) => (
                    <li key={skill.skill_id}>
                      <div className="timeline-row"><strong>{skill.name}</strong><span>v{skill.version}</span></div>
                      <p>{skill.skill_id}</p>
                      <p className="session-meta">{skill.category} · {skill.source}</p>
                    </li>
                  )) ?? null}
                </ul>
              </Panel>
            </section>
          ) : null}

          {view === 'memory' ? (
            <section className="console-grid">
              <Panel title="Working Memory">
                <StateFrame state={c.data.workingMemory ? 'ready' : c.state} loading="Loading working memory." empty="No working memory returned yet." error={c.error ?? 'Working memory unavailable.'}>
                  <dl className="details">
                    <div><dt>Session</dt><dd>{c.data.workingMemory?.session_id ?? 'n/a'}</dd></div>
                    <div><dt>Task</dt><dd>{c.data.workingMemory?.task_id ?? 'n/a'}</dd></div>
                    <div><dt>Latest event</dt><dd>{c.data.workingMemory?.latest_event_type ?? 'n/a'}</dd></div>
                    <div><dt>Recent artifacts</dt><dd>{c.data.workingMemory?.recent_artifact_ids.length ?? 0}</dd></div>
                  </dl>
                  <p className="session-meta">working status: {c.data.memoryDiagnostics?.status ?? 'no diagnostics'} · reconstructed from {c.data.memoryDiagnostics?.source_summary.event_count ?? 0} events</p>
                  <p className="request-text">{c.data.workingMemory?.summary ?? 'n/a'}</p>
                </StateFrame>
              </Panel>
              <Panel title="Repository Memory">
                <StateFrame state={c.data.repositoryMemory ? 'ready' : c.state} loading="Loading repository memory." empty="No repository memory returned yet." error={c.error ?? 'Repository memory unavailable.'}>
                  <dl className="details">
                    <div><dt>Repository</dt><dd>{c.data.repositoryMemory?.repository_id ?? 'n/a'}</dd></div>
                    <div><dt>Generated</dt><dd>{c.data.repositoryMemory?.generated_at ?? 'n/a'}</dd></div>
                    <div><dt>Sessions</dt><dd>{c.data.repositoryMemory?.session_memories.length ?? 0}</dd></div>
                    <div><dt>Artifacts</dt><dd>{c.data.repositoryMemory?.artifact_ids.length ?? 0}</dd></div>
                  </dl>
                  <p className="request-text">{c.data.repositoryMemory?.summary ?? 'n/a'}</p>
                </StateFrame>
              </Panel>
            </section>
          ) : null}

          {view === 'repository-intelligence' ? (
            <section className="console-grid">
              <Panel title="Repository Intelligence">
                <StateFrame state={c.data.repositoryIntelligence ? 'ready' : c.state} loading="Loading repository intelligence." empty="No repository intelligence returned yet." error={c.error ?? 'Repository intelligence unavailable.'}>
                  <dl className="details">
                    <div><dt>Repository</dt><dd>{c.data.repositoryIntelligence?.repository_id ?? 'n/a'}</dd></div>
                    <div><dt>Generated</dt><dd>{c.data.repositoryIntelligence?.generated_at ?? 'n/a'}</dd></div>
                    <div><dt>Modules</dt><dd>{c.data.repositoryIntelligence?.module_map.length ?? 0}</dd></div>
                    <div><dt>Evidence</dt><dd>{c.data.repositoryIntelligence?.evidence_sources.join(', ') ?? 'n/a'}</dd></div>
                  </dl>
                  <p className="session-meta">diagnostics: {c.data.repositoryIntelligenceDiagnostics?.module_count ?? 0} modules · {c.data.repositoryIntelligenceDiagnostics?.runtime_inventory_count ?? 0} runtime items</p>
                  <p className="request-text">{c.data.repositoryIntelligence?.architecture_summary ?? 'n/a'}</p>
                </StateFrame>
              </Panel>
              <Panel title="Inventory">
                <ul className="timeline">
                  {c.data.repositoryIntelligence?.runtime_inventory.map((item) => (
                    <li key={item.name}>
                      <div className="timeline-row"><strong>{item.name}</strong><span>{item.status}</span></div>
                      <p>{JSON.stringify(item.metadata)}</p>
                    </li>
                  )) ?? null}
                </ul>
              </Panel>
            </section>
          ) : null}

          {view === 'engineering-knowledge' ? (
            <section className="console-grid">
              <Panel title="Engineering Knowledge">
                <StateFrame state={c.data.engineeringKnowledge ? 'ready' : c.state} loading="Loading engineering knowledge." empty="No engineering knowledge returned yet." error={c.error ?? 'Engineering knowledge unavailable.'}>
                  <dl className="details">
                    <div><dt>Generated</dt><dd>{c.data.engineeringKnowledge?.generated_at ?? 'n/a'}</dd></div>
                    <div><dt>Entries</dt><dd>{c.data.engineeringKnowledge?.entries.length ?? 0}</dd></div>
                  </dl>
                </StateFrame>
              </Panel>
              <Panel title="Reusable Knowledge">
                <ul className="timeline">
                  {c.data.engineeringKnowledge?.entries.map((entry) => (
                    <li key={entry.knowledge_id}>
                      <div className="timeline-row"><strong>{entry.title}</strong><span>{entry.category}</span></div>
                      <p>{entry.summary}</p>
                      <p className="session-meta">{entry.evidence.join(', ')}</p>
                    </li>
                  )) ?? null}
                </ul>
              </Panel>
            </section>
          ) : null}

          {view === 'transformation' ? (
            <section className="console-grid">
              <Panel title="Lifecycle Summary">
                <StateFrame state={c.data.transformationHistory ? 'ready' : c.state} loading="Loading transformation history." empty="No transformation history returned yet." error={c.error ?? 'Transformation history unavailable.'}>
                  <dl className="details">
                    <div><dt>Events</dt><dd>{c.data.transformationHistory?.summary.total_events ?? 0}</dd></div>
                    <div><dt>Failures</dt><dd>{c.data.transformationHistory?.summary.failed_attempts ?? 0}</dd></div>
                    <div><dt>Sessions</dt><dd>{c.data.transformationHistory?.summary.sessions_with_transformations ?? 0}</dd></div>
                    <div><dt>Patterns</dt><dd>{c.data.transformationHistory?.summary.repeated_patterns.length ?? 0}</dd></div>
                  </dl>
                </StateFrame>
              </Panel>
              <Panel title="Repository Change Summary">
                <StateFrame state={c.data.repositoryChangeSummary ? 'ready' : c.state} loading="Loading repository change summary." empty="No repository change summary returned yet." error={c.error ?? 'Repository change summary unavailable.'}>
                  <dl className="details">
                    <div><dt>Branch</dt><dd>{c.data.repositoryChangeSummary?.branch ?? 'n/a'}</dd></div>
                    <div><dt>Head</dt><dd>{c.data.repositoryChangeSummary?.head_commit ?? 'n/a'}</dd></div>
                    <div><dt>Dirty</dt><dd>{String(c.data.repositoryChangeSummary?.dirty_workspace ?? false)}</dd></div>
                    <div><dt>Checkpoint</dt><dd>{c.data.repositoryChangeSummary?.checkpoint_commit ?? 'n/a'}</dd></div>
                  </dl>
                  <p className="session-meta">{c.data.repositoryChangeSummary?.warnings.join(', ') ?? 'No warnings.'}</p>
                </StateFrame>
              </Panel>
              <Panel title="Patches">
                <div className="launch-actions">
                  <button type="button" className="secondary-button" onClick={() => void submitTransformationSession()}>
                    Create transformation session
                  </button>
                  <span className="session-meta">Uses the current task, request, specification, and context fields.</span>
                </div>
                <ul className="timeline">
                  {c.data.transformationSessions.slice(0, 5).map((session) => (
                    <li key={session.transformation_id}>
                      <div className="timeline-row"><strong>{session.transformation_id}</strong><span>{session.patch.status}</span></div>
                      <p>{session.summary}</p>
                      <p className="session-meta">{session.validation_command ?? 'no validation command'} · {session.rollback_reference ?? 'no rollback reference'}</p>
                    </li>
                  ))}
                </ul>
                <h3>Derived patch records</h3>
                <ul className="timeline">
                  {c.data.patchRecords.slice(0, 10).map((patch) => (
                    <li key={patch.id}>
                      <div className="timeline-row"><strong>{patch.id}</strong><span>{patch.status}</span></div>
                      <p>{patch.affected_files.join(', ') || 'No affected files recorded.'}</p>
                      <p className="session-meta">{patch.validation_result ?? 'no validation'} · {patch.rollback_reference ?? 'no rollback reference'}</p>
                    </li>
                  ))}
                </ul>
              </Panel>
              <Panel title="Artifacts">
                <ul className="timeline">
                  {c.data.artifactRecords.slice(0, 10).map((artifact) => (
                    <li key={artifact.id}>
                      <div className="timeline-row"><strong>{artifact.path}</strong><span>{artifact.type}</span></div>
                      <p>{artifact.producer ?? 'unknown producer'}</p>
                      <p className="session-meta">{artifact.session_id ?? 'no session'} · {artifact.checksum ?? 'no checksum'}</p>
                    </li>
                  ))}
                </ul>
              </Panel>
              <Panel title="Transformation Timeline">
                <ul className="timeline">
                  {c.data.transformationHistory?.items.slice(0, 20).map((item) => (
                    <li key={`${item.timestamp}-${item.event_id ?? item.stage}`}>
                      <div className="timeline-row"><strong>{item.stage}</strong><span>{item.status}</span></div>
                      <p>{item.summary}</p>
                      <p className="session-meta">{item.proposal_id ?? item.patch_id ?? item.artifact_id ?? 'unlinked'}</p>
                    </li>
                  )) ?? null}
                </ul>
              </Panel>
            </section>
          ) : null}

          {view === 'decision-intelligence' ? (
            <section className="console-grid">
              <Panel title="Decision Intelligence">
                <StateFrame state={c.data.decisionIntelligence ? 'ready' : c.state} loading="Loading decision intelligence." empty="No decision intelligence returned yet." error={c.error ?? 'Decision intelligence unavailable.'}>
                  <dl className="details">
                    <div><dt>Generated</dt><dd>{c.data.decisionIntelligence?.generated_at ?? 'n/a'}</dd></div>
                    <div><dt>Recurring decisions</dt><dd>{c.data.decisionIntelligence?.recurring_decisions.length ?? 0}</dd></div>
                    <div><dt>Proposal outcomes</dt><dd>{c.data.decisionIntelligence?.proposal_outcomes.length ?? 0}</dd></div>
                  </dl>
                </StateFrame>
              </Panel>
              <Panel title="Decision Patterns">
                <ul className="timeline">
                  {c.data.decisionIntelligence?.recurring_decisions.map((decision) => (
                    <li key={decision.decision_key}>
                      <div className="timeline-row"><strong>{decision.decision_key}</strong><span>{decision.occurrences}x</span></div>
                      <p>{decision.rationale}</p>
                      <p className="session-meta">failures: {decision.failures}</p>
                    </li>
                  )) ?? null}
                </ul>
              </Panel>
            </section>
          ) : null}

          {view === 'evaluation-accountability' ? (
            <section className="console-grid">
              <Panel title="Evaluation Dashboard">
                <StateFrame state={c.data.evaluationAccountability ? 'ready' : c.state} loading="Loading evaluation accountability." empty="No accountability data returned yet." error={c.error ?? 'Evaluation accountability unavailable.'}>
                  <dl className="details">
                    <div><dt>Scenarios</dt><dd>{c.data.evaluationAccountability?.scenarios.length ?? 0}</dd></div>
                    <div><dt>Runs</dt><dd>{c.data.evaluationAccountability?.runs.length ?? 0}</dd></div>
                    <div><dt>Scorecards</dt><dd>{c.data.evaluationAccountability?.scorecards.length ?? 0}</dd></div>
                    <div><dt>Regressions</dt><dd>{c.data.evaluationAccountability?.regressions.regressed_count ?? 0}</dd></div>
                  </dl>
                </StateFrame>
              </Panel>
              <Panel title="Scenario Browser">
                <ul className="timeline">
                  {c.data.evaluationAccountability?.scenarios.map((scenario) => (
                    <li key={scenario.scenario_id}>
                      <div className="timeline-row"><strong>{scenario.title}</strong><span>{scenario.target_type}</span></div>
                      <p>{scenario.purpose}</p>
                      <p className="session-meta">{scenario.risk_level} · v{scenario.version} · {scenario.tags.join(', ')}</p>
                    </li>
                  )) ?? null}
                </ul>
              </Panel>
              <Panel title="Regression View">
                <ul className="timeline">
                  {c.data.evaluationAccountability?.regressions.findings.map((finding) => (
                    <li key={`${finding.target_type}-${finding.target_id}-${String(finding.comparison_run_id)}`}>
                      <div className="timeline-row"><strong>{String(finding.status)}</strong><span>{finding.target_type}</span></div>
                      <p>{String(finding.target_id)} · delta {String(finding.score_delta ?? 'n/a')}</p>
                      <p className="session-meta">{String(finding.signature)}</p>
                    </li>
                  )) ?? null}
                </ul>
              </Panel>
            </section>
          ) : null}

          {view === 'platform' ? <PlatformPanel /> : null}

          <Panel title="Invocation Detail">
            <StateFrame state={selectedInvocation ? 'ready' : c.state} loading="Loading invocation detail." empty="Select an invocation to inspect it." error={c.error ?? 'Invocation detail unavailable.'}>
              {c.data.selectedInvocationSummary || c.data.selectedInvocationHistory ? (
                <div className="session-details">
                  <dl className="details">
                    <div><dt>State</dt><dd>{c.data.selectedInvocationSummary?.state ?? c.data.selectedInvocationHistory?.events.at(-1)?.state ?? 'n/a'}</dd></div>
                    <div><dt>Adapter</dt><dd>{c.data.selectedInvocationSummary?.adapter_id ?? 'n/a'}</dd></div>
                    <div><dt>Capability</dt><dd>{c.data.selectedInvocationSummary?.capability_id ?? 'n/a'}</dd></div>
                    <div><dt>Runtime session</dt><dd>{c.data.selectedInvocationSummary?.runtime_session_id ?? c.data.selectedInvocationHistory?.runtime_session_id ?? 'n/a'}</dd></div>
                  </dl>
                  {c.data.selectedInvocationHistory ? (
                    <ul className="timeline">
                      {c.data.selectedInvocationHistory.events.map((event) => (
                        <li key={`${event.timestamp}-${event.event_type}`}>
                          <div className="timeline-row"><strong>{event.event_type}</strong><span>{event.state}</span></div>
                          <p className="session-meta">normalized agent event · {event.source_event_type ?? event.event_type}</p>
                          <p>{event.message}</p>
                          <time>{event.timestamp}</time>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}
            </StateFrame>
          </Panel>
        </main>
      </section>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
