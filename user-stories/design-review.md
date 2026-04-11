# Design Review — hub-se-agent

**Date:** 2026-04-11  
**Reviewer:** Claude Sonnet 4.6 (via Claude Code)  
**Scope:** Architecture, skill design, tool patterns, Teams integration, resilience, observability

---

## Overall Assessment

The architecture is coherent and the design philosophy is consistent. The key patterns — skills-as-config, dynamic tool discovery, async Teams reachability via Redis, and local execution — are all correctly applied. This is production-adjacent thinking, not a prototype. The gaps are mostly in resilience, observability, and the boundary between "what belongs in a prompt" vs "what belongs in a tool."

---

## What Is Done Well

### Skills-first declarative design
The YAML skill structure is well-formed. Using `model`, `queued`, `conversational`, `next_skill`, and `reasoning_effort` as first-class skill attributes is the right call. This mirrors Claude Code's approach where skills describe *intent and behavior*, not imperative code. Dropping a YAML file to add a capability — with no code changes — is the correct extensibility model.

### Tool discovery
Dynamic `importlib` loading from `tools/`, with each tool exporting a `SCHEMA` + `handle()` contract, is the right pattern. No central registry to maintain. It's clean and idiomatic.

### Async Teams + Redis design
The two-part split (desktop agent + cloud relay over Redis streams) is the correct approach for reaching a local agent from mobile/Teams without firewall changes. The XREAD with timeout, outbox trim to 100 entries, and heartbeat TTL refresh are all production-grade details, not afterthoughts.

### Human-in-the-loop confirmation gates
The `[AWAITING_CONFIRMATION]` → active session → re-route pattern for `engagement_briefing` is smart. It correctly solves the problem: a 4-phase chain should not run without a confirmation checkpoint. Injecting multi-turn history so the LLM knows "this is Turn 2, the user said X" is the right mechanism.

### Threading model
WebSocket server, tray icon, task queue, Redis poller, and pywebview each running in their own thread/loop is correct. Mixing these would cause deadlocks or blocking. Daemon threads for non-UI components is the right call.

### Model tier selection
Using mini models for `qa` and `task_status`, full models for multi-phase reasoning — this is the cost/quality tradeoff that mature agent systems use.

---

## Design Concerns

### 1. File-based inter-phase context sharing is fragile

The `engagement_context` tool saves JSON to disk between phases. This works for a single user, but:
- If Phase 2 fails and Phase 3 starts, it reads stale/partial data with no way to detect the inconsistency.
- There is no atomic write — a crash mid-write corrupts the context file.
- Two concurrent engagement runs (e.g., two users via Teams) collide on the same path, keyed only by `customer_name`.

**Recommendation:** Key the context file by `request_id` or `task_id`, not `customer_name`. Use a temp directory under `~/.hub-se-agent/tasks/{task_id}/`. This isolates concurrent runs and ties context to a specific execution.

---

### 2. String markers from LLM output are a reliability risk

Parsing `[AWAITING_CONFIRMATION]` and `[STOP_CHAIN]` out of raw LLM prose is a common pattern, but it's brittle:
- The LLM may paraphrase them (`[Awaiting Confirmation]`, `stop chain`) causing the parser to miss them.
- The LLM may hallucinate them mid-response when they are not appropriate.
- If the markers appear in user-quoted text, false positives fire.

This is the single highest-risk failure mode in the current design.

**Recommendation:** Instruct the LLM to return a structured JSON envelope alongside text:
```json
{"text": "Here are the briefing calls I found...", "action": "await_confirmation"}
```
Parse the envelope, not the prose. Azure OpenAI Responses API supports Structured Outputs — use a JSON schema for the response type on skills that need action signalling.

---

### 3. Conversation history is in-memory and lost on restart

`_conversation_histories[skill_name]` lives in the agent process. If the agent crashes or the machine reboots mid-workflow, the active conversation is lost. The user has to start over with no way to resume.

**Recommendation:** Serialize conversation history to `~/.hub-se-agent/sessions/{skill_name}.json` after each turn. Load on startup. This also enables a future "resume" feature for long-running workflows.

---

### 4. No retry or partial-failure recovery for the skill chain

If Phase 3 (`engagement_agenda_build`) fails, there is no way to re-run just Phase 3 with the already-computed Phase 1+2 context. The user restarts from scratch.

**Recommendation:** Add a checkpoint flag to the context file after each phase completes (e.g., `phase_1_complete: true`). On re-invocation of the chain, detect completed phases and skip them. This is the core idea behind durable execution — lightweight to implement here with the file-based context already in place.

---

### 5. `engagement_agenda_build` instruction complexity crosses the line

The instructions for this skill encode:
- Time-slot arithmetic (continuous scheduling from `start_time`)
- Session-count rules per engagement type (BUSINESS_ENVISIONING vs ADS vs RAPID_PROTOTYPE)
- Speaker assignment fallback logic (briefing participants → catalog → default)
- Multi-day splitting rules (> 6.5 hours → new day)

When a skill instruction is encoding conditional branching and arithmetic, that logic belongs in a tool, not a prompt. The LLM will execute it, but inconsistently — especially as model versions change.

**Recommendation:** Move the structural planning logic into a new tool: `plan_agenda_structure(engagement_type, goals, start_time, speakers)` that returns a structured slot plan (list of `{time, speaker, topic, goal}` dicts). Let the LLM write the narrative description for each slot, which is the task it does reliably. The tool handles the deterministic parts.

---

### 6. No observability layer

There is no logging of LLM calls, token counts, tool execution times, or skill outcomes. When something goes wrong (wrong agenda built, wrong speakers assigned), there is no audit trail beyond what the user saw in the UI.

**Recommendation:** Log structured events to `~/.hub-se-agent/logs/YYYY-MM-DD.jsonl` — at minimum: timestamp, skill name, model, prompt tokens, completion tokens, tool calls made, duration, outcome (success/error). This is invaluable for debugging production failures and tuning prompts.

---

### 7. Redis reconnect is time-based, not event-driven

The 30-minute forced reconnect regardless of connection health causes unnecessary churn on healthy connections and may miss failures in the 30-minute window.

**Recommendation:** Replace the timer-based reconnect with exception-driven reconnect: catch connection errors, attempt immediate reconnect with exponential backoff (1s, 2s, 4s, cap at 60s). Keep the 30-minute timer only for Entra token refresh, which is its appropriate scope.

---

## Skill YAML Complexity — Verdict by Skill

| Skill | Complexity | Verdict |
|---|---|---|
| `qa` | Low | Correct — simple and clear |
| `task_status` | Low | Correct |
| `meeting_invites` | Medium | Justified — email resolution + calendar invite is genuinely complex |
| `engagement_briefing` | High | Justified — multi-turn human-in-the-loop with context extraction is inherently complex |
| `engagement_goals` | Medium | Justified — reasoning over unstructured notes requires specific guidance |
| `engagement_agenda_build` | Very High | **Borderline** — time arithmetic and session-type branching should move to a tool |
| `engagement_agenda_publish` | Low-Medium | Justified |
| `agenda_repurpose` | Medium | Justified |

---

## Summary Ratings

| Dimension | Rating | Note |
|---|---|---|
| Architecture design | Strong | Layered correctly, patterns are sound |
| Skills-as-config philosophy | Strong | Correctly applied |
| Tool discovery | Strong | Clean and idiomatic |
| Teams / Redis async | Strong | Production-ready pattern |
| Multi-phase workflow | Good | Chaining works; resilience is missing |
| Confirmation gates | Good | Mechanism is right; marker parsing is fragile |
| Observability | Weak | No structured audit trail |
| Failure recovery | Weak | No retry, no checkpoint-based resume |
| Skill instruction maintainability | Mixed | Justified for most skills; `agenda_build` crosses the line |

---

## Prioritised Action Items

1. **[High]** Replace `[AWAITING_CONFIRMATION]` / `[STOP_CHAIN]` string parsing with structured JSON response envelope — highest reliability risk.
2. **[High]** Key context files by `task_id`, not `customer_name` — required for multi-user correctness.
3. **[Medium]** Add phase checkpoint flags to context files for partial-failure resume.
4. **[Medium]** Serialize conversation history to disk — enables crash recovery and resume.
5. **[Medium]** Extract time-slot and session-type logic from `engagement_agenda_build` into a `plan_agenda_structure` tool.
6. **[Medium]** Add structured JSONL logging per skill execution.
7. **[Low]** Replace timer-based Redis reconnect with exception-driven exponential backoff.