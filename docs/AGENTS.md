# AGENTS.md — Operating Contract for AI Coding Agents

> **STOP. Read this entire file before taking any action — before
> listing directories, before opening any file, before searching.
> This file IS your first read. Do not treat it as optional context.**

This file applies to ANY model/provider operating in this repository
(GPT, Claude, DeepSeek, Gemini, or third-party OpenAI-compatible endpoints),
regardless of which CLI tool is driving it (Codex, Aider, OpenCode, etc).

If you are an AI agent reading this: these rules are not suggestions.
They override your default instincts toward "helpfulness via exploration."

---

## 0. Scope Discipline (read this first)

You were invoked from a specific directory for a specific reason. Before
doing ANYTHING else:

1. Confirm the current working directory matches the task description.
2. If the task references specific files or a specific subfolder
   (e.g. "/backend/xxx"), your FIRST action is to `ls`/`view` that exact
   path — not to search the web, not to explore unrelated directories,
   not to infer the goal from the project name.
3. If the task is ambiguous after reading the named files, STOP and ask
   a clarifying question. Do not fill the ambiguity gap with a web
   search or an assumption.

**Default failure mode to avoid:** treating a narrow, file-scoped task
as an open-ended research problem. If you find yourself about to issue
a web search, a broad recursive grep across the whole monorepo, or a
"let me explore the codebase to understand the architecture" pass —
stop and re-read the task. 90% of the time the task already told you
exactly where to look.

---

## 0.5 Plan Mode vs Execute Mode

You operate in two distinct modes. Default to PLAN MODE unless told otherwise.

**PLAN MODE (default for any non-trivial task):**
- You may READ files, but only the ones named in the task or directly
  imported/referenced by them. No edits, no writes, no shell commands
  that change state.
- Output a plan: files you'll touch, the change you'll make in each,
  and your understood acceptance criteria.
- STOP after the plan. Do not proceed to execution until told "go,"
  "execute," "approved," or equivalent.

**EXECUTE MODE (only after explicit go-ahead):**
- Make exactly the edits described in the approved plan.
- If you discover mid-execution that the plan was wrong or incomplete,
  STOP, explain what you found, and return to plan mode rather than
  improvising a new plan on the fly.

Never skip straight to execute mode on a multi-file or unclear task.
Single-line trivial fixes (typo, one-line config value) are exempt and
may be done directly.

## 0.6 Repo Scanning Limits — Read Narrow, Not Wide

You do NOT need to understand the entire repository to complete a
scoped task. Do not:
- Recursively read every file in the project "to get context."
- Open package.json/requirements.txt/lockfiles unless the task is
  about dependencies.
- Read the whole `src/` or `app/` tree because a file you need lives
  somewhere inside it — use a targeted search (grep/glob for the
  specific filename or symbol) instead of opening directories wholesale.
- Re-read files you already have in context from earlier in the session.

Hard ceiling: if a task requires reading more than ~10 files to
understand scope, stop and tell the human the task is bigger than
expected, rather than silently reading 50+ files to "be thorough."

If you are not sure a file is relevant, do not open it speculatively —
ask, or proceed without it and flag the gap in your plan output.

## 1. Tool-Use Priority Order

For any task, prefer tools in this order. Only escalate to the next
tier if the current tier genuinely cannot answer the question.

1. **Read the files named or implied by the task.** Always first.
2. **Read adjacent files in the same module/folder** if you need context
   the named files don't give you (e.g. a shared type definition).
3. **Grep/search within the repo** for symbol usages, callers, configs.
4. **Read project docs** (README, AGENTS.md, CLAUDE.md, ARCHITECTURE.md)
   if present, for conventions.
5. **Web search** — ONLY for: looking up an external library's API
   surface/version-specific syntax, checking a CVE, or confirming a
   fact you cannot get from the repo. Never use web search to "figure
   out the solution" to a task that is about THIS codebase's logic.
6. **Asking the human** — if scope, intent, or acceptance criteria are
   unclear after 1–4. Better to ask than to guess and produce a large,
   wrong diff.

Web search and "creative exploration" are tier 5 and 6 tools, not tier 1.
A task that says "implement X in file Y" should almost never trigger a
web search before you've even opened file Y.

---

## 2. Diff Discipline

- Make the SMALLEST diff that satisfies the task. Do not refactor
  unrelated code, rename variables for "clarity," reformat untouched
  files, or upgrade dependencies unless explicitly asked.
- Do not delete or rewrite whole files when a targeted edit will do.
- If a fix requires touching more than ~3 files outside what was named,
  stop and explain why before proceeding — this usually signals you've
  misunderstood the scope.
- Never modify CI/CD configs, deployment scripts, environment files
  (.env, secrets, terraform, nginx configs), or infra-as-code unless
  the task explicitly names that file.

---

## 3. Before You Start Coding — Restate the Plan

For any non-trivial task (more than a one-line fix), output a short
plan BEFORE editing:
- What you read
- What you understood the task to be
- Which files you intend to touch
- What you will NOT touch

This is cheap insurance against scope drift and lets a human (or a
review step) catch a misunderstood task before 200 lines of diff happen.

---

## 4. Environment Awareness

- Confirm you're operating in the correct context: local WSL vs. a
  remote OCI/Azure instance. Commands that assume local paths
  (`~/docker/apps/`, SSH key paths, etc.) will not work identically
  across environments — check `pwd`/`hostname` if unsure.
- Never assume network access exists or is desired. Some environments
  (sandboxed runs) intentionally have no/limited egress. If a tool call
  fails due to network restriction, do not retry aggressively — report
  it and stop.
- Do not install global packages, modify system-level config, or touch
  Docker/Nginx configs outside the task's explicit ask.

---

## 5. When in Doubt: Under-react

If you're unsure whether something is in scope, it is not in scope.
If you're unsure whether a destructive action (delete, force-push,
drop table, overwrite config) is wanted, it is not wanted — ask first.
Silence/ambiguity from the human is not consent to expand scope.

---

## 6. Reporting Back

When done, report:
- What you changed (file list, one-line summary per file)
- What you deliberately did NOT change and why (if relevant)
- Any assumptions you made that the human should verify
- Anything you noticed that seems wrong/risky but is OUT of scope for
  this task — flag it, don't fix it unprompted.

---

## Provider-Specific Notes

Different model providers running through this harness need different
amounts of explicit reinforcement. The rules above apply to all of them,
but pay extra attention here based on which model is active:

**GPT-4o / GPT-4o-mini / smaller OpenAI models:** Most prone to
"helpfully" over-exploring — treating narrow tasks as open research
questions, reaching for web search when local file context would
answer the question. Section 0 and Section 1 matter most here.

**DeepSeek (chat/coder models):** Generally good at scoped code edits
when given an OpenAI-compatible tool-calling interface, but can be
less reliable at multi-step tool orchestration (e.g. read → reason →
edit → verify) under harnesses tuned for OpenAI's function-calling
format. Watch for incomplete or partially-applied diffs; verify after
each edit rather than trusting a single large multi-file change.

**Gemini (via OpenAI-compat endpoint):** Tool-calling reliability
varies most here across the four. Treat multi-tool-call sequences with
extra skepticism — confirm each tool result was actually used/read
before the next step, since this is where compatibility-shim failures
are most likely to silently produce wrong behavior.

**Claude (Opus/Sonnet):** Generally most reliable at honoring scope and
asking clarifying questions unprompted, but give it the same explicit
contract anyway — consistency across providers matters more than
relying on any one model's "good instincts," and it keeps behavior
predictable when you're switching providers mid-project.

**Third-party OpenAI-compatible endpoints (unknown base model):**
Treat as the least-trusted tier by default. Don't assume function-
calling schema fidelity, context window honesty, or that the model
follows system prompts as strongly as the major providers. Use Section
3 (plan before coding) especially strictly here, and review diffs from
these endpoints more closely before applying.

---

## Quick Self-Check Before Any Tool Call

Ask yourself: "Did the task explicitly point me here, or am I guessing?"
If guessing — stop, re-read the task, or ask.
