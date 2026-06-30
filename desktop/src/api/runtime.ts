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

export type RuntimeGovernanceHistoryItem = {
  approval_id?: string | null;
  status: string;
  reason?: string | null;
  iteration?: number | null;
  tool?: string | null;
  arguments?: Record<string, unknown> | null;
  message: string;
  timestamp: string;
};

export type RuntimeGovernanceSnapshot = {
  session_id: string;
  pending_approval: boolean;
  pending_approval_id?: string | null;
  approval_history: RuntimeGovernanceHistoryItem[];
  interrupted: boolean;
  interrupt_reason?: string | null;
  approval_events: RuntimeTimelineItem[];
  decision_evidence: RuntimeEvent[];
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

export type RuntimeEvent = {
  id: number;
  ts: string;
  type: string;
  severity: string;
  message: string;
  metadata: Record<string, unknown>;
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

export type ArtifactRecordView = {
  id: string;
  type: string;
  path: string;
  origin_event_id?: number | null;
  session_id?: string | null;
  workspace_id?: string | null;
  producer?: string | null;
  status: string;
  metadata: Record<string, unknown>;
  checksum?: string | null;
};

export type PatchRecordView = {
  id: string;
  session_id?: string | null;
  proposal_id?: string | null;
  artifact_id?: string | null;
  status: string;
  affected_files: string[];
  origin_event_id?: number | null;
  approval_event_id?: number | null;
  validation_result?: string | null;
  rollback_reference?: string | null;
  metadata: Record<string, unknown>;
};

export type RepositoryChangeSummary = {
  workspace_id?: string | null;
  path?: string | null;
  repository_detected: boolean;
  branch?: string | null;
  head_commit?: string | null;
  dirty_workspace: boolean;
  unsafe_workspace: boolean;
  modified_files: string[];
  added_files: string[];
  deleted_files: string[];
  diff_summaries: string[];
  git_status: string[];
  checkpoint_commit?: string | null;
  rollback_reference?: string | null;
  warnings: string[];
  status: string;
  metadata: Record<string, unknown>;
};

export type TransformationHistoryItem = {
  timestamp: string;
  session_id?: string | null;
  task_id?: string | null;
  proposal_id?: string | null;
  patch_id?: string | null;
  artifact_id?: string | null;
  event_id?: number | null;
  stage: string;
  status: string;
  summary: string;
  metadata: Record<string, unknown>;
};

export type TransformationHistoryProjection = {
  items: TransformationHistoryItem[];
  summary: {
    total_events: number;
    repeated_patterns: string[];
    failed_attempts: number;
    sessions_with_transformations: number;
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
  dependency_count: number;
  parameter_count: number;
};

export type SkillRegistryCatalog = {
  skills: SkillRegistryEntry[];
  registered_skills_total: number;
  categories: string[];
  version_summary: Record<string, number>;
};

export type SkillRegistryDiagnostics = {
  status: string;
  total_skills: number;
  duplicate_skill_ids: string[];
  invalid_skill_ids: string[];
  missing_dependency_ids: string[];
  warnings: string[];
};

export type SkillManifestDiagnostics = {
  skill_id: string;
  status: string;
  warnings: string[];
  dependency_ids: string[];
  parameter_names: string[];
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
  current_state: Record<string, unknown>;
  summary: string;
};

export type MemoryDiagnostics = {
  status: string;
  source_summary: MemorySourceSummary;
  working_memory_count: number;
  session_memory_count: number;
  repository_memory_count: number;
  artifact_memory_count: number;
  decision_memory_count: number;
  warnings: string[];
  build_timestamp: string;
};

export type SessionMemory = {
  session_id: string;
  task_id?: string | null;
  status: string;
  event_count: number;
  artifact_ids: string[];
  skill_ids: string[];
  last_activity_at?: string | null;
  completed_work: string[];
  decisions: string[];
  approvals: string[];
  observations: string[];
  summary: string;
};

export type RepositoryMemory = {
  repository_id: string;
  generated_at: string;
  source_summary: MemorySourceSummary;
  session_memories: SessionMemory[];
  skill_ids: string[];
  artifact_ids: string[];
  architecture_summaries: string[];
  technology_stack: string[];
  coding_conventions: string[];
  project_structure: string[];
  summary: string;
};

export type ArtifactMemory = {
  artifact_id: string;
  summary: string;
  created_at: string;
  artifact_type: string;
  metadata: Record<string, unknown>;
};

export type DecisionMemory = {
  decision_id: string;
  rationale: string;
  evidence: string[];
  alternatives: string[];
  outcome: string;
  session_id?: string | null;
  repeated_count: number;
};

export type RepositoryIntelligenceSummary = {
  repository_id: string;
  generated_at: string;
  architecture_summary: string;
  module_map: Array<{ module_name: string; path: string; kind: string }>;
  service_graph: string[];
  dependency_overview: Array<{ name: string; version?: string | null; scope: string }>;
  runtime_inventory: Array<{ name: string; status: string; metadata: Record<string, unknown> }>;
  provider_inventory: Array<{ name: string; status: string; metadata: Record<string, unknown> }>;
  tool_inventory: Array<{ name: string; status: string; metadata: Record<string, unknown> }>;
  evidence_sources: string[];
};

export type RepositoryIntelligenceDiagnostics = {
  repository_id: string;
  generated_at: string;
  module_count: number;
  runtime_inventory_count: number;
  provider_inventory_count: number;
  tool_inventory_count: number;
  evidence_sources: string[];
};

export type EngineeringKnowledgeCatalog = {
  generated_at: string;
  entries: Array<{
    knowledge_id: string;
    category: string;
    title: string;
    summary: string;
    evidence: string[];
    created_at: string;
  }>;
};

export type DecisionIntelligenceSummary = {
  generated_at: string;
  recurring_decisions: Array<{
    decision_key: string;
    decision_type: string;
    occurrences: number;
    failures: number;
    rationale: string;
  }>;
  repeated_failures: Array<{
    decision_key: string;
    decision_type: string;
    occurrences: number;
    failures: number;
    rationale: string;
  }>;
  evaluation_history: string[];
  proposal_outcomes: string[];
  engineering_rationale: string[];
};

export type EvaluationScenario = {
  scenario_id: string;
  title: string;
  purpose: string;
  input_fixture: string;
  expected_behavior: string;
  rubric: string;
  target_type: string;
  version: number;
  tags: string[];
  risk_level: string;
  created_at: string;
};

export type EvaluationRun = {
  run_id: string;
  scenario_id: string;
  target_type: string;
  target_id: string;
  target_runtime_event_id?: number | null;
  evaluator: string;
  evaluator_type: string;
  outcome: string;
  score?: number | null;
  evidence: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  scenario_version: number;
};

export type EvaluationScorecard = {
  target_type: string;
  target_id: string;
  evaluation_count: number;
  pass_count: number;
  fail_count: number;
  inconclusive_count: number;
  average_score?: number | null;
  latest_run_id?: string | null;
  latest_outcome?: string | null;
  latest_evaluated_at?: string | null;
};

export type EvaluationRegressionSummary = {
  total_targets: number;
  comparison_count: number;
  regressed_count: number;
  improved_count: number;
  unchanged_count: number;
  repeated_failure_signatures: Array<{ signature: string; count: number }>;
  quality_drift_indicators: string[];
  findings: Array<Record<string, unknown>>;
  generated_at: string;
};

export type EvaluationAccountabilityProjection = {
  scenarios: EvaluationScenario[];
  runs: EvaluationRun[];
  scorecards: EvaluationScorecard[];
  regressions: EvaluationRegressionSummary;
  decisions: Array<Record<string, unknown>>;
  generated_at: string;
};

export type ExtensionManifestDependency = {
  extension_id: string;
  minimum_version: string;
};

export type ExtensionManifest = {
  extension_id: string;
  name: string;
  version: string;
  author: string;
  description?: string | null;
  kind:
    | 'provider'
    | 'tool'
    | 'execution-participant'
    | 'agent-adapter'
    | 'skill'
    | 'evaluation-pack'
    | 'memory-provider'
    | 'artifact-provider'
    | 'workspace-provider';
  capabilities: string[];
  runtime_compatibility: Record<string, unknown>;
  dependencies: ExtensionManifestDependency[];
  permissions: string[];
  supported_protocols: string[];
  entrypoint?: string | null;
  enabled: boolean;
  metadata: Record<string, unknown>;
};

export type LoadedExtension = {
  manifest: ExtensionManifest;
  source_path: string;
};

export type PlatformExtensionDiagnostic = {
  extension_id: string;
  kind: string;
  status: string;
  compatible: boolean;
  dependency_issues: string[];
  warnings: string[];
  source_path: string;
};

export type PlatformDiagnostics = {
  installed_extensions: number;
  disabled_extensions: number;
  incompatible_extensions: number;
  version_mismatches: number;
  dependency_issues: number;
  extensions: PlatformExtensionDiagnostic[];
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

export type ExecutionParticipantKind =
  | 'human'
  | 'local_tool'
  | 'provider'
  | 'external_agent'
  | 'mcp_server'
  | 'a2a_agent'
  | 'future_adapter';

export type ExecutionParticipantHealth = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
export type ExecutionParticipantLifecycle = 'registered' | 'available' | 'unavailable' | 'degraded' | 'disabled';
export type ExecutionInvocationState =
  | 'created'
  | 'validated'
  | 'queued'
  | 'executing'
  | 'waiting'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timed_out'
  | 'interrupted';

export type ExecutionParticipant = {
  participant_id: string;
  display_name: string;
  kind: ExecutionParticipantKind;
  identity: Record<string, unknown>;
  capabilities: Array<{ capability_id: string; description?: string | null; operations: string[] }>;
  lifecycle: ExecutionParticipantLifecycle;
  health: ExecutionParticipantHealth;
  availability: string;
  diagnostics: Record<string, unknown>;
  version: string;
  supported_operations: string[];
  contract: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

export type ExecutionParticipantRegistryDiagnostics = {
  status: string;
  total_participants: number;
  kinds: Record<string, number>;
  warnings: string[];
  metadata: Record<string, unknown>;
};

export type ExecutionParticipantRegistry = {
  participants: ExecutionParticipant[];
  selected_participant_id?: string | null;
  eligible_participant_ids: string[];
};

export type ExecutionInvocation = {
  invocation_id: string;
  participant_id: string;
  capability_id: string;
  state: ExecutionInvocationState;
  requested_by: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  artifacts: Array<Record<string, unknown>>;
  events: string[];
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  metadata: Record<string, unknown>;
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
export const getRuntimeSessionGovernance = (sessionId: string) =>
  fetchJson<RuntimeGovernanceSnapshot>(
    `/runtime/session/${encodeURIComponent(sessionId)}/governance`,
  );
export const runAgentLoop = (request: AgentLoopRequest) =>
  postJson<AgentLoopResult>('/agent-loop/run', request);
export const runRuntimeTask = (taskId: string) =>
  postJson<Record<string, unknown>>(`/runtime/tasks/${encodeURIComponent(taskId)}/run`);
export const interruptRuntimeTask = (taskId: string, reason = 'Interrupted from desktop console') =>
  postJson<Record<string, unknown>>(`/runtime/tasks/${encodeURIComponent(taskId)}/interrupt`, {
    reason,
  });
export const stopRuntimeTask = (taskId: string, reason = 'Stopped from desktop console') =>
  postJson<Record<string, unknown>>(`/runtime/tasks/${encodeURIComponent(taskId)}/stop`, {
    reason,
  });
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
export const getSkillRegistryDiagnostics = () =>
  fetchJson<SkillRegistryDiagnostics>('/runtime/skills/diagnostics');
export const getExecutionParticipants = () =>
  fetchJson<ExecutionParticipant[]>('/runtime/execution-participants');
export const getExecutionParticipantDiagnostics = () =>
  fetchJson<ExecutionParticipantRegistryDiagnostics>('/runtime/execution-participants/diagnostics');
export const routeExecutionCapability = (capabilityId: string) =>
  postJson<ExecutionParticipantRegistry>('/runtime/execution-participants/route', {
    capability_id: capabilityId,
  });
export const getExecutionInvocations = () =>
  fetchJson<ExecutionInvocation[]>('/runtime/execution-invocations');
export const createExecutionInvocation = (capabilityId: string) =>
  postJson<ExecutionInvocation>('/runtime/execution-invocations', {
    capability_id: capabilityId,
  });
export const startExecutionInvocation = (invocationId: string) =>
  postJson<ExecutionInvocation>(`/runtime/execution-invocations/${encodeURIComponent(invocationId)}/start`);
export const completeExecutionInvocation = (invocationId: string, metadata: Record<string, unknown> = {}) =>
  postJson<ExecutionInvocation>(`/runtime/execution-invocations/${encodeURIComponent(invocationId)}/complete`, {
    metadata,
  });
export const failExecutionInvocation = (invocationId: string, reason = 'failed') =>
  postJson<ExecutionInvocation>(`/runtime/execution-invocations/${encodeURIComponent(invocationId)}/fail`, {
    reason,
  });
export const cancelExecutionInvocation = (invocationId: string, reason = 'cancelled') =>
  postJson<ExecutionInvocation>(`/runtime/execution-invocations/${encodeURIComponent(invocationId)}/cancel`, {
    reason,
  });
export const interruptExecutionInvocation = (invocationId: string, reason = 'interrupted') =>
  postJson<ExecutionInvocation>(`/runtime/execution-invocations/${encodeURIComponent(invocationId)}/interrupt`, {
    reason,
  });
export const getSkillDiagnostics = (skillId: string) =>
  fetchJson<SkillManifestDiagnostics>(`/runtime/skills/${encodeURIComponent(skillId)}/diagnostics`);
export const getWorkingMemory = (sessionId?: string | null) =>
  fetchJson<WorkingMemory>(
    `/runtime/memory/working${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''}`,
  );
export const getMemoryDiagnostics = () => fetchJson<MemoryDiagnostics>('/runtime/memory/diagnostics');
export const getRepositoryMemory = () => fetchJson<RepositoryMemory>('/runtime/memory/repository');
export const getArtifactMemory = () => fetchJson<ArtifactMemory[]>('/runtime/memory/artifacts');
export const getDecisionMemory = () => fetchJson<DecisionMemory[]>('/runtime/memory/decisions');
export const getArtifactRecords = () => fetchJson<ArtifactRecordView[]>('/runtime/artifacts');
export const getPatchRecords = () => fetchJson<PatchRecordView[]>('/runtime/patches');
export const getRepositoryChangeSummary = () =>
  fetchJson<RepositoryChangeSummary>('/runtime/repository-change-summary');
export const getTransformationHistory = () =>
  fetchJson<TransformationHistoryProjection>('/runtime/transformation-history');
export const getRepositoryIntelligence = () =>
  fetchJson<RepositoryIntelligenceSummary>('/runtime/repository-intelligence');
export const getRepositoryIntelligenceDiagnostics = () =>
  fetchJson<RepositoryIntelligenceDiagnostics>('/runtime/repository-intelligence/diagnostics');
export const getEngineeringKnowledge = () =>
  fetchJson<EngineeringKnowledgeCatalog>('/runtime/engineering-knowledge');
export const getDecisionIntelligence = () =>
  fetchJson<DecisionIntelligenceSummary>('/runtime/decision-intelligence');
export const getEvaluationAccountabilityProjection = () =>
  fetchJson<EvaluationAccountabilityProjection>('/evaluation-accountability/projection');
export const getEvaluationAccountabilityScenarios = () =>
  fetchJson<EvaluationScenario[]>('/evaluation-accountability/scenarios');
export const getEvaluationAccountabilityRuns = () =>
  fetchJson<EvaluationRun[]>('/evaluation-accountability/runs');
export const getEvaluationAccountabilityScorecards = () =>
  fetchJson<EvaluationScorecard[]>('/evaluation-accountability/scorecards');
export const getEvaluationAccountabilityRegressions = () =>
  fetchJson<EvaluationRegressionSummary>('/evaluation-accountability/regressions');
export const getPlatformExtensions = () =>
  fetchJson<{ extensions: LoadedExtension[] }>('/platform/extensions');
export const getPlatformDiagnostics = () =>
  fetchJson<PlatformDiagnostics>('/platform/diagnostics');
