/* Stratum UAT console — vanilla JS client of the runtime API. */
"use strict";

const $ = (id) => document.getElementById(id);
const api = {
  executions: () => fetch("/executions").then(r => r.json()),
  events: (eid) => fetch(`/tasks/${eid}/events`).then(r => r.ok ? r.json() : []),
  task: (eid) => fetch(`/tasks/${eid}`).then(r => r.json()),
  create: (body) => fetch("/tasks", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  }),
  decide: (eid, decision) => fetch(`/tasks/${eid}/${decision}`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({decider: "web-operator"}),
  }),
};

let activeExecution = null;
let pollTimer = null;
let renderedEventCount = 0;

// ---------------------------------------------------------------- status

async function refreshBrokerBadge() {
  const badge = $("broker-badge");
  try {
    const health = await fetch("/healthz").then(r => r.json());
    badge.textContent = `broker: ${health.broker ? "connected" : "off"}`;
    badge.className = "badge " + (health.broker ? "on" : "off");
    $("provider-info").textContent =
      `${health.provider || ""} · model ${health.model || "?"}`;
  } catch {
    badge.textContent = "api: unreachable";
    badge.className = "badge off";
  }
}

// ---------------------------------------------------------------- submit

$("submit-task").addEventListener("click", async () => {
  const repo = $("repo-path").value.trim();
  const task = $("task-text").value.trim();
  if (!repo || !task) {
    $("submit-error").textContent = "repository path and task are required";
    return;
  }
  $("submit-error").textContent = "";
  const files = $("context-files").value.split(",").map(s => s.trim()).filter(Boolean);

  try {
    const resp = await api.create({
      repo_path: repo,
      task_description: task,
      selected_files: files.length ? files : null,
      markdown_context: $("markdown-context").value,
    });
    if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`);
    const body = await resp.json();
    showExecution(body.execution_id);
  } catch (err) {
    $("submit-error").textContent = String(err);
  }
});

// ------------------------------------------------------------ execution

function showExecution(eid) {
  activeExecution = eid;
  renderedEventCount = 0;
  $("new-task-panel").classList.add("hidden");
  $("run-panel").classList.remove("hidden");
  $("exec-id").textContent = eid;
  $("timeline").innerHTML = "";
  $("result-banner").className = "hidden";
  schedulePoll(0);
}

function backToForm() {
  if (pollTimer) clearTimeout(pollTimer);
  activeExecution = null;
  $("run-panel").classList.add("hidden");
  $("new-task-panel").classList.remove("hidden");
  refreshHistory();
}

function schedulePoll(delay) {
  if (!activeExecution) return;
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(pollActive, delay);
}

async function pollActive() {
  if (!activeExecution) return;
  let snapshot;
  try { snapshot = await api.task(activeExecution); }
  catch { return schedulePoll(2000); }

  setStatus(snapshot.status);
  renderPlan(snapshot);
  await renderEvents();

  if (TERMINAL.has(snapshot.status)) {
    showResult(snapshot.status, snapshot.error);
    refreshHistory();
    return; // stop polling
  }
  schedulePoll(snapshot.status === "APPROVAL_REQUIRED" ? 1500 : 800);
}

const TERMINAL = new Set(["COMPLETED", "FAILED", "REJECTED", "CANCELLED"]);

function setStatus(status) {
  $("exec-status").textContent = status;
  $("exec-status").className = `v status ${status}`;
}

function renderPlan(snapshot) {
  const card = $("plan-card");
  if (snapshot.status !== "APPROVAL_REQUIRED" || !snapshot.plan) {
    card.classList.add("hidden");
    return;
  }
  card.classList.remove("hidden");
  $("plan-rationale").textContent = snapshot.plan.rationale || "";
  const list = $("plan-steps");
  list.innerHTML = "";
  for (const step of snapshot.plan.steps) {
    const li = document.createElement("li");
    li.textContent = `[${step.action_type}] ${step.description}` +
      (step.command ? ` — ${step.command}` :
       step.path ? ` — ${step.path}` : "");
    li.className = step.requires_approval ? "mutating" : "";
    list.appendChild(li);
  }
}

$("approve-btn").addEventListener("click", () => decide("approve"));
$("reject-btn").addEventListener("click", () => decide("reject"));

async function decide(decision) {
  $("approve-btn").disabled = true;
  $("reject-btn").disabled = true;
  try {
    const resp = await api.decide(activeExecution, decision);
    if (!resp.ok) throw new Error(await resp.text());
  } catch (err) {
    alert(`decision failed: ${err}`);
  }
  $("approve-btn").disabled = false;
  $("reject-btn").disabled = false;
  schedulePoll(300);
}

// --------------------------------------------------------------- events

const EV_LABELS = {
  "task.created": "task created",
  "task.planning_started": "planning started",
  "ai.requested": null, // label built from payload
  "ai.responded": null,
  "plan.generated": null,
  "approval.requested": "approval requested",
  "approval.granted": null,
  "approval.rejected": null,
  "execution.started": "execution started",
  "tool.started": null,
  "tool.completed": null,
  "tool.failed": null,
  "artifact.created": null,
  "observation.recorded": null,
  "task.completed": "task completed",
  "task.failed": null,
  "task.cancelled": "task cancelled",
};

function describe(ev) {
  const p = ev.payload || {};
  switch (ev.event_type) {
    case "ai.requested": return `ai.requested (${p.purpose}, model=${p.model})`;
    case "ai.responded": return `ai.responded (${p.purpose}, tokens=${(p.usage||{}).total_tokens ?? "?"}, ${p.latency_ms}ms)`;
    case "plan.generated": return `plan.generated — ${p.plan?.steps?.length ?? "?"} steps`;
    case "approval.granted": return `approval.granted by ${p.decider}`;
    case "approval.rejected": return `approval.rejected by ${p.decider}`;
    case "tool.started": return `tool.started ${p.action_type}${p.path ? " " + p.path : p.command ? " `" + p.command + "`" : ""}`;
    case "tool.completed": return `tool.completed — ${p.summary ?? ""}`;
    case "tool.failed": return `tool.failed — ${p.error ?? ""}`;
    case "artifact.created": return `artifact.created ${p.path} (${p.bytes} bytes)`;
    case "observation.recorded": return p.ok === false ? `observation: FAILED — ${p.summary ?? ""}` : null;
    case "task.failed": return `task.failed — ${p.error ?? ""}`;
    default: return EV_LABELS[ev.event_type] || ev.event_type;
  }
}

async function renderEvents() {
  const events = await api.events(activeExecution);
  const list = $("timeline");
  for (; renderedEventCount < events.length; renderedEventCount++) {
    const ev = events[renderedEventCount];
    const text = describe(ev);
    if (!text) continue;
    const li = document.createElement("li");
    li.className = `ev-${ev.event_type.replace(".", "-")}`;
    const time = document.createElement("span");
    time.className = "tl-time";
    time.textContent = (ev.timestamp || "").slice(11, 19);
    li.appendChild(time);
    li.appendChild(document.createTextNode(text));
    list.appendChild(li);
  }
  list.scrollTop = list.scrollHeight;
}

function showResult(status, error) {
  const banner = $("result-banner");
  banner.classList.remove("hidden");
  const ok = status === "COMPLETED";
  banner.className = ok ? "ok" : "bad";
  banner.innerHTML = ok
    ? `Task <b>completed</b>. <button class="ghost" onclick="backToForm()">← new task</button>`
    : `Task <b>${status}</b>${error ? ": " + escapeHtml(error) : ""}. ` +
      `<button class="ghost" onclick="backToForm()">← new task</button>`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
window.backToForm = backToForm;

// -------------------------------------------------------------- history

async function refreshHistory() {
  let rows = [];
  try { rows = await api.executions(); } catch {}
  const tbody = $("history-rows");
  tbody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.className = `st-${row.status}`;
    tr.innerHTML = `
      <td class="mono">${row.execution_id}</td>
      <td>${row.status}</td>
      <td title="${escapeHtml(row.repo_path || "")}">${escapeHtml((row.description || "").slice(0, 60))}</td>
      <td>${row.event_count}</td>
      <td class="mono">${(row.started_at || "").slice(11, 19)}</td>
      <td><button class="ghost">replay →</button></td>`;
    tr.querySelector("button").addEventListener("click", () => {
      showExecution(row.execution_id);
      $("task-text") && ($("task-text").value = row.description || "");
    });
    tbody.appendChild(tr);
  }
}
$("refresh-history").addEventListener("click", refreshHistory);

// ------------------------------------------------------------------ boot

refreshBrokerBadge().then(refreshHistory);
if (location.hash.startsWith("#exe_")) showExecution(location.hash.slice(1));
