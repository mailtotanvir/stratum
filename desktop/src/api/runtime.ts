import { getRuntimeApiBaseUrl } from './config';

export type RuntimeSessionOverview = {
  session_id: string;
  status: string;
  user_request?: string | null;
  provider?: string | null;
  model?: string | null;
  current_iteration?: number | null;
  max_iterations?: number | null;
  pending_approval: boolean;
  pending_approval_id?: string | null;
  last_tool?: string | null;
  final_answer?: string | null;
  error?: string | null;
  started_at: string;
  updated_at: string;
};

export type RuntimeDashboard = {
  active_sessions: number;
  pending_approvals: number;
  completed_today: number;
  failed_today: number;
  stopped_today: number;
  latest_sessions: RuntimeSessionOverview[];
};

export type RuntimeWorkspaceSummary = {
  workspace_id: string;
  name: string;
  root_path: string;
  active: boolean;
};

export type RuntimeWorkspace = {
  workspace_id: string;
  name: string;
  root_path: string;
  created_at: string;
  metadata: Record<string, unknown>;
  active: boolean;
};

export type RuntimeWorkspaceRepositoryStatus = {
  path: string;
  is_git_repository: boolean;
  branch?: string | null;
  head_commit?: string | null;
  dirty?: boolean | null;
  status?: string | null;
  checkpoint_status?: string | null;
  safe_to_run: boolean;
  issues: string[];
  metadata: Record<string, unknown>;
};

export type RuntimeWorkspaceBindingStatus = {
  workspace: RuntimeWorkspace;
  repository: RuntimeWorkspaceRepositoryStatus;
  workspace_artifact_count: number;
  session_artifact_count: number;
  linked_session_ids: string[];
  runtime_execution_allowed: boolean;
  runtime_execution_reason: string;
  checked_at: string;
};

export type RuntimeSessionListItem = {
  id: string;
  task_id: string;
  status: string;
  created_at: string;
  completed_at?: string | null;
};

export type RuntimeTask = {
  id: string;
  status: string;
  title: string;
  created_at: string;
  completed_at?: string | null;
  summary?: string | null;
};

export type RuntimeStatus = {
  backend_version: string;
  provider_status: string;
  runtime_status: string;
  registered_tools: string[];
  registered_providers: string[];
  event_count: number;
  active_sessions: number;
};

export type RuntimeTimelineItem = {
  timestamp: string;
  event_type: string;
  title: string;
  summary: string;
  severity: string;
  payload: Record<string, unknown>;
};

export type RuntimeWorkspaceArtifact = {
  artifact_id: string;
  workspace_id: string;
  session_id?: string | null;
  tool: string;
  path?: string | null;
  artifact_type: string;
  summary: string;
  created_at: string;
  metadata: Record<string, unknown>;
  artifact?: {
    id: string;
    task_id?: string | null;
    proposal_id?: string | null;
    path: string;
    kind: string;
    created_at: string;
    metadata?: Record<string, unknown> | null;
  };
};

export type ProviderExecutionSummary = {
  total_executions: number;
  completed: number;
  failed: number;
  by_provider: Record<string, number>;
  by_model: Record<string, number>;
  budget_warnings_count: number;
};

export type ProviderExecutionRecentItem = {
  provider_id: string;
  model: string;
  status: string;
  routing_source?: string | null;
  routing_reason?: string | null;
  budget_policy?: Record<string, unknown> | null;
  created_at?: string | null;
  timestamp?: string | null;
};

export type ProviderUsageSummary = {
  provider_name: string;
  model_name: string;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  average_latency_ms?: number | null;
  max_latency_ms?: number | null;
  estimated_input_tokens?: number | null;
  estimated_output_tokens?: number | null;
  estimated_total_tokens?: number | null;
  estimated_cost_usd?: number | null;
  last_used_at?: string | null;
};

export type ModelUsageSummary = {
  provider_name: string;
  model_name: string;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  estimated_total_tokens?: number | null;
  estimated_cost_usd?: number | null;
  last_used_at?: string | null;
};

export type ProviderLatencySummary = {
  provider_name: string;
  model_name: string;
  latency_sample_count: number;
  average_latency_ms?: number | null;
  max_latency_ms?: number | null;
};

export type ProviderCostSummary = {
  provider_name: string;
  model_name: string;
  estimated_input_tokens?: number | null;
  estimated_output_tokens?: number | null;
  estimated_total_tokens?: number | null;
  estimated_cost_usd?: number | null;
  cost_estimated: boolean;
  missing_token_or_cost_records: number;
};

export type ProviderObservabilityReport = {
  generated_at: string;
  provider_reports: ProviderUsageSummary[];
  model_usage: ModelUsageSummary[];
  latency: ProviderLatencySummary[];
  costs: ProviderCostSummary[];
  provider_count: number;
  model_count: number;
  total_requests: number;
  malformed_event_count: number;
  estimated: boolean;
  metadata: Record<string, unknown>;
  observability_metrics: Record<string, number>;
};

export type ProviderHealth = {
  provider_id?: string | null;
  ready: boolean;
  configured: boolean;
  enabled: boolean;
  transport: string;
  protocol: string;
  supports_completion: boolean;
  supports_streaming: boolean;
  status: string;
};

export type ProviderLiveDiagnostics = {
  configured: boolean;
  ready: boolean;
  provider_id?: string | null;
  display_name?: string | null;
  api_style?: string | null;
  base_url?: string | null;
  default_model?: string | null;
  enabled: boolean;
  supports_streaming: boolean;
  has_api_key: boolean;
  issues: string[];
  metadata: Record<string, unknown>;
};

export type ProviderConfiguration = {
  provider_id: string;
  display_name: string;
  api_style: string;
  base_url?: string | null;
  supports_streaming: boolean;
  supports_tools: boolean;
  supports_json_mode: boolean;
  supports_reasoning: boolean;
  supports_vision: boolean;
  supports_embeddings: boolean;
  supports_audio: boolean;
  default_model?: string | null;
  available_models: string[];
  metadata: Record<string, unknown>;
};

export type ProviderConfigurationSnapshot = {
  providers: ProviderConfiguration[];
  metadata: Record<string, unknown>;
};

export type SkillRegistryEntry = {
  skill_id: string;
  name: string;
  version: number;
  category: string;
  source: string;
};

export type SkillRegistryCatalog = {
  skills: SkillRegistryEntry[];
  registered_skills_total: number;
};

export type MemorySourceSummary = {
  event_count: number;
  artifact_count: number;
  workspace_artifact_count: number;
  session_count: number;
};

export type WorkingMemory = {
  session_id?: string | null;
  task_id?: string | null;
  latest_event_id?: number | null;
  latest_event_type?: string | null;
  active_skill_ids: string[];
  recent_artifact_ids: string[];
  summary: string;
};

export type SessionMemory = {
  session_id: string;
  task_id?: string | null;
  status: string;
  event_count: number;
  artifact_ids: string[];
  skill_ids: string[];
  last_activity_at?: string | null;
  summary: string;
};

export type RepositoryMemory = {
  repository_id: string;
  generated_at: string;
  source_summary: MemorySourceSummary;
  session_memories: SessionMemory[];
  skill_ids: string[];
  artifact_ids: string[];
  summary: string;
};

export type ProviderRoutingDecision = {
  provider_id: string;
  model: string;
  reason: string;
  source: string;
  adapter_provider_name?: string | null;
  base_url?: string | null;
  timeout_seconds?: number | null;
  enabled?: boolean | null;
  metadata: Record<string, unknown>;
};

export type ProviderRoutingResult = {
  resolved: boolean;
  decision?: ProviderRoutingDecision | null;
  error_message?: string | null;
  metadata: Record<string, unknown>;
};

export type ProviderBudgetPolicySummary = {
  classification?: string | null;
  warnings?: string[] | null;
  metadata?: Record<string, unknown> | null;
};

export type RuntimeAgentLoopEvent = {
  id?: string | null;
  ts?: string | null;
  type: string;
  message?: string | null;
  metadata?: Record<string, unknown>;
};

export type AgentCapabilityManifest = {
  adapter_id: string;
  display_name: string;
  version?: string | null;
  description?: string | null;
  transport: string;
  provider_family?: string | null;
  supported_agent_types: string[];
  supported_capabilities: string[];
  supported_modalities: string[];
  supports_streaming: boolean;
  supports_tool_use: boolean;
  supports_approvals: boolean;
  supports_multi_agent: boolean;
  supports_memory: boolean;
  supports_artifacts: boolean;
  supports_observability: boolean;
  metadata: Record<string, unknown>;
};

export type AgentAdapterCatalogEntry = {
  manifest: AgentCapabilityManifest;
};

export type AgentAdapterCatalog = {
  adapters: AgentAdapterCatalogEntry[];
};

export type AgentAdapterRegistryDiagnostics = {
  status: 'healthy' | 'degraded';
  total_registered: number;
  duplicate_adapter_ids: string[];
  invalid_adapter_ids: string[];
  warnings: string[];
};

export type AgentEventNormalizationCatalog = {
  source_event_kinds: string[];
  runtime_event_types: string[];
  severities: string[];
};

export type AgentInvocationLifecycleState =
  | 'created'
  | 'accepted'
  | 'running'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type AgentInvocationLifecycleEventType =
  | 'created'
  | 'accepted'
  | 'running'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'external_event';

export type AgentInvocationLifecycleEvent = {
  event_type: AgentInvocationLifecycleEventType;
  state: AgentInvocationLifecycleState;
  message: string;
  timestamp: string;
  source_event_type?: string | null;
  metadata: Record<string, unknown>;
};

export type AgentInvocationRecord = {
  invocation_id: string;
  adapter_id: string;
  capability_id: string;
  runtime_session_id?: string | null;
  state: AgentInvocationLifecycleState;
  created_at: string;
  updated_at: string;
  history: AgentInvocationLifecycleEvent[];
  metadata: Record<string, unknown>;
};

export type AgentInvocationSummary = {
  invocation_id: string;
  adapter_id: string;
  capability_id: string;
  runtime_session_id?: string | null;
  state: AgentInvocationLifecycleState;
  history_length: number;
  last_event_type?: AgentInvocationLifecycleEventType | null;
  last_message?: string | null;
  metadata: Record<string, unknown>;
};

export type AgentInvocationHistorySummary = {
  invocation_id: string;
  adapter_id: string;
  capability_id: string;
  runtime_session_id?: string | null;
  created_at: string;
  updated_at: string;
  states: AgentInvocationLifecycleState[];
  events: AgentInvocationLifecycleEvent[];
};

export type AgentLoopApprovalResponse = {
  approval_id: string;
  session_id: string;
  iteration: number;
  tool: string;
  arguments: Record<string, unknown>;
  status: 'pending' | 'approved' | 'rejected';
  reason?: string | null;
};

export type AgentLoopApprovalResumeResult = {
  approval_id: string;
  session_id: string;
  status: 'pending' | 'approved' | 'rejected';
  tool: string;
  executed: boolean;
  already_resumed: boolean;
  tool_result?: {
    tool: string;
    output: string;
    completion_intent: boolean;
  } | null;
  reason?: string | null;
};

export type AgentLoopToolResult = {
  tool: string;
  output: string;
  completion_intent: boolean;
};

export type AgentLoopStep = {
  iteration: number;
  provider_output?: string | null;
  tool_call?: {
    tool: string;
    arguments: Record<string, unknown>;
  } | null;
  tool_result?: AgentLoopToolResult | null;
  error?: string | null;
};

export type AgentLoopResult = {
  session_id: string;
  status: 'running' | 'completed' | 'failed' | 'stopped' | 'paused';
  final_answer?: string | null;
  iterations_used: number;
  steps: AgentLoopStep[];
  error?: string | null;
};

export type AgentLoopRequest = {
  session_id: string;
  user_request: string;
  max_iterations?: number;
  workspace_id?: string | null;
  provider_id?: string | null;
  model?: string | null;
};

export type TaskCreateRequest = {
  title: string;
};

function buildApiUrl(path: string) {
  return `${getRuntimeApiBaseUrl().replace(/\/$/, '')}${path}`;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(buildApiUrl(path));
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === 'string') {
        detail = payload.detail;
      }
    } catch {
      // Fall back to the status text.
    }
    throw new Error(`Request failed: ${detail}`);
  }
  return (await response.json()) as T;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === 'string') {
        detail = payload.detail;
      }
    } catch {
      // Fall back to the status text.
    }
    throw new Error(`Request failed: ${detail}`);
  }
  return (await response.json()) as T;
}

export const getRuntimeStatus = () => fetchJson<RuntimeStatus>('/runtime/status');
export const getProviderConfigurations = () =>
  fetchJson<ProviderConfigurationSnapshot>('/runtime/providers/configurations');
export const getProviderRouting = () =>
  fetchJson<ProviderRoutingResult>('/runtime/providers/routing');
export const getProviderBudgetPolicy = () =>
  fetchJson<ProviderBudgetPolicySummary>('/runtime/providers/budget-policy');
export const listRuntimeSessions = () =>
  fetchJson<RuntimeSessionListItem[]>('/runtime/sessions');
export const createRuntimeTask = (request: TaskCreateRequest) =>
  postJson<RuntimeTask>('/tasks', request);
export const getRuntimeTask = (taskId: string) =>
  fetchJson<RuntimeTask>(`/tasks/${encodeURIComponent(taskId)}`);
export const listRuntimeWorkspaces = () =>
  fetchJson<RuntimeWorkspaceSummary[]>('/runtime/workspaces');
export const getActiveRuntimeWorkspace = () =>
  fetchJson<RuntimeWorkspace>('/runtime/workspaces/active');
export const getRuntimeWorkspaceBindingStatus = () =>
  fetchJson<RuntimeWorkspaceBindingStatus>('/runtime/workspaces/binding');
export const activateRuntimeWorkspace = (workspaceId: string) =>
  postJson<RuntimeWorkspace>(`/runtime/workspaces/${encodeURIComponent(workspaceId)}/activate`);
export const getRuntimeWorkspaceArtifacts = (workspaceId: string) =>
  fetchJson<RuntimeWorkspaceArtifact[]>(
    `/runtime/workspaces/${encodeURIComponent(workspaceId)}/artifacts`,
  );
export const getRuntimeSessionArtifacts = (sessionId: string) =>
  fetchJson<RuntimeWorkspaceArtifact[]>(
    `/runtime/sessions/${encodeURIComponent(sessionId)}/artifacts`,
  );
export const getRuntimeDashboard = () =>
  fetchJson<RuntimeDashboard>('/runtime/dashboard');
export const getRuntimeSession = (sessionId: string) =>
  fetchJson<RuntimeSessionOverview>(`/runtime/session/${encodeURIComponent(sessionId)}`);
export const getRuntimeSessionTimeline = (sessionId: string) =>
  fetchJson<RuntimeTimelineItem[]>(
    `/runtime/session/${encodeURIComponent(sessionId)}/timeline`,
  );
export const runAgentLoop = (request: AgentLoopRequest) =>
  postJson<AgentLoopResult>('/agent-loop/run', request);
export const runRuntimeTask = (taskId: string) =>
  postJson<Record<string, unknown>>(`/runtime/tasks/${encodeURIComponent(taskId)}/run`);
export const getRuntimeSessionEvents = (sessionId: string) =>
  fetchJson<RuntimeAgentLoopEvent[]>(
    `/agent-loop/events/${encodeURIComponent(sessionId)}`,
  );
export const getProviderExecutionSummary = () =>
  fetchJson<ProviderExecutionSummary>('/providers/executions/summary');
export const getProviderExecutionRecent = () =>
  fetchJson<ProviderExecutionRecentItem[]>('/providers/executions/recent');
export const getProviderObservability = () =>
  fetchJson<ProviderObservabilityReport>('/runtime/providers/observability');
export const getProviderHealth = () => fetchJson<ProviderHealth>('/providers/health');
export const getProviderLiveDiagnostics = () =>
  fetchJson<ProviderLiveDiagnostics>('/providers/live/diagnostics');
export const getAgentAdapters = () =>
  fetchJson<AgentAdapterCatalog>('/agent-adapters');
export const getAgentAdapterManifest = (adapterId: string) =>
  fetchJson<AgentCapabilityManifest>(`/agent-adapters/${encodeURIComponent(adapterId)}`);
export const getAgentAdapterDiagnostics = () =>
  fetchJson<AgentAdapterRegistryDiagnostics>('/agent-adapters/diagnostics');
export const getAgentEventNormalizationCatalog = () =>
  fetchJson<AgentEventNormalizationCatalog>('/agent-adapters/normalization');
export const getAgentInvocationRecent = (limit = 20) =>
  fetchJson<{ invocations: AgentInvocationRecord[] }>(
    `/runtime/agent-invocations?limit=${encodeURIComponent(String(limit))}`,
  );
export const getAgentInvocationStatus = (invocationId: string) =>
  fetchJson<AgentInvocationSummary>(
    `/runtime/agent-invocations/${encodeURIComponent(invocationId)}/status`,
  );
export const getAgentInvocationHistory = (invocationId: string) =>
  fetchJson<AgentInvocationHistorySummary>(
    `/runtime/agent-invocations/${encodeURIComponent(invocationId)}/history`,
  );
export const createAgentInvocation = (request: {
  adapter_id: string;
  capability_id: string;
  metadata?: Record<string, unknown>;
}) => postJson<AgentInvocationRecord>('/runtime/agent-invocations', request);
export const cancelAgentInvocation = (
  invocationId: string,
  request?: { message?: string; metadata?: Record<string, unknown> },
) =>
  postJson<AgentInvocationRecord>(
    `/runtime/agent-invocations/${encodeURIComponent(invocationId)}/cancel`,
    request ?? {},
  );
export const respondToAgentLoopApproval = (
  approvalId: string,
  approved: boolean,
  reason?: string,
) =>
  postJson<AgentLoopApprovalResponse>(
    `/agent-loop/approvals/${encodeURIComponent(approvalId)}/respond`,
    { approved, reason },
  );
export const resumeAgentLoopApproval = (approvalId: string) =>
  postJson<AgentLoopApprovalResumeResult>(
    `/agent-loop/approvals/${encodeURIComponent(approvalId)}/resume`,
  );
export const continueAgentLoopApproval = (approvalId: string) =>
  postJson<AgentLoopApprovalResumeResult>(
    `/agent-loop/approvals/${encodeURIComponent(approvalId)}/continue`,
  );
export const getSkillRegistry = () => fetchJson<SkillRegistryCatalog>('/runtime/skills');
export const getWorkingMemory = (sessionId?: string | null) =>
  fetchJson<WorkingMemory>(
    `/runtime/memory/working${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''}`,
  );
export const getRepositoryMemory = () => fetchJson<RepositoryMemory>('/runtime/memory/repository');
