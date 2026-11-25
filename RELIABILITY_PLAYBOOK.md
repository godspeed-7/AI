# Reliability Playbook

A quick guide: making agents controllable, reliable, secure and affordable,
in the order we learn them. Each topic says what we had before (and where)
and what this guide adds.

- System design, a graph around agents, swarms, failures, security, PII,
  budgets → **this file**.
- Agent basics → [AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md). Tracing and scoring
  → [EVAL_PLAYBOOK.md](EVAL_PLAYBOOK.md). Deep Agents, MCP, several agents →
  [DEEP_AGENTS_PLAYBOOK.md](DEEP_AGENTS_PLAYBOOK.md).
- Later, all playbooks become one step-by-step guide to building the app.

**Status**: ✅ learned · ⬜ not started · ✗ skipped. Learning only: nothing
here is built unless we decide to.

**Source**: the course's [Agentic System Design and Reliability Engineering
reference][guide] (its example: a research desk; a support swarm). Tested by
its author on langgraph 1.2.24, langchain 1.5.2, deepagents 0.7.41: exactly
ours. Topics marked (recap) we covered before, each saying where; (+) aren't
in the guide.

**The idea**: "Agents are responsible for reasoning. The application is
responsible for control, safety and reliability." A good prompt can't make a
long job resume after a crash, stop a refund going out twice, or keep names
away from the model. Code around the agents does that.

It picks up DEEP_AGENTS_PLAYBOOK's "Left for later": graphs built by hand,
Send, retry and recovery, idempotency across a whole job.

---

## Starting point

What we already have:

- The year-end review (DEEP_AGENTS A): one deep agent writes a memo per
  department. Its order lives in the prompt ("one department at a time, don't
  hand it to a helper"); `check_memo` checks the numbers in code; 30 model
  calls at most; no checkpointer, no approval, nothing sent
- The chat agent (AGENT_PLAYBOOK): permissions in code, a leave request
  saved once however often it's sent (D3), time limits and retries (D4), a
  fallback model and 5 model calls a question (E), approval inside the tool
  (H), chats in memory
- Langfuse traces of every run, HR names included (EVAL_PLAYBOOK)

**Our example** (learning only): the year-end review as the guide's research
desk. Code runs the steps; agents only write and judge:

```text
   HR: "year-end review"
          │
          ▼
   CODE: one task per department, IDs made in code
          │ Send: 6 workers at once
          ▼
   WORKERS: Deep Agents, one per department, memo → its own file
          │
          ▼
   CODE: every file there? numbers right? (check_memo)
          │
          ▼
   REVIEWER: a separate agent, a JSON verdict, 2 rounds at most
          │
          ▼
   HR approves (interrupt) ──▶ CODE sends each memo once (key + ledger)
```

For the swarm (C), the chat: Ananya's "Can I take Friday off, and has my
Dallas trip been paid?" (AGENT_PLAYBOOK J).

---

## Overview

**Jump to** · [Starting point](#starting-point) · [A System
design](#a-system-design) · [B Graph supervisor](#b-graph-supervisor) · [C
Swarm and handoffs](#c-swarm-and-handoffs) · [D Runtime
reliability](#d-runtime-reliability) · [E Security](#e-security) · [F PII
protection](#f-pii-protection) · [G Operating](#g-operating) · [Left for
later](#left-for-later)

```text
   🟦 A SYSTEM DESIGN
      │
      ├╌╌ 🟢 When and who
      │     └╌ one or several · three families · who decides what
      ├╌╌ 🟢 A way to look
      │     └╌ the map · six questions
      ▼
   🟦 B GRAPH SUPERVISOR
      │
      ├╌╌ 🟢 Code runs the steps
      │     └╌ prompt as engine · the graph · agents as workers
      ├╌╌ 🟢 Checked work
      │     └╌ IDs in code · output contract · check the files · critic
      ▼
   🟦 C SWARM AND HANDOFFS
      │
      ├╌╌ 🟢 Handoffs
      │     └╌ a tool · shared state · allowed map · cap · what to pass
      ▼
   🟦 D RUNTIME RELIABILITY
      │
      ├╌╌ 🟢 Survive
      │     └╌ five layers · three storages · resume · not a transaction
      ├╌╌ 🟢 Fail well
      │     └╌ retries · circuit breaker
      ├╌╌ 🟢 Never twice
      │     └╌ keys · operation ledger · unknown outcome
      ▼
   🟦 E SECURITY
      │
      ├╌╌ 🟢 Threats
      │     └╌ OWASP · injection · excessive agency
      ├╌╌ 🟢 Controls
      │     └╌ every door · auth in code · least privilege · sandbox · risk
      ▼
   🟦 F PII PROTECTION
      │
      ├╌╌ 🟢 Names out, names back
      │     └╌ find and replace · put it back · traces and logs
      ▼
   🟦 G OPERATING
      │
      ├╌╌ 🟢 Bounded
      │     └╌ loop fingerprint · budgets
      ├╌╌ 🟢 Measured and checked
      │     └╌ metrics · failure tests · pitfalls · before you ship
      ▼
   agents that think, inside code that controls
```

---
## A. System design

When to split, who decides, and the questions to ask of any design.

```text
   A SYSTEM DESIGN
      │
      ├╌╌ ✅ Split or not (recap) ╌╌╌ split only when one agent strains: a huge
      │                               prompt, many tools, a long history,
      │                               permissions that can't be separated.
      │                               Split for specialists, clean windows,
      │                               parallel work or a permission line.
      │                               DEEP_AGENTS I1, AGENT_PLAYBOOK J
      ├╌╌ ✅ Three families ╌╌╌╌╌╌╌╌╌ before: patterns by name (DEEP_AGENTS
      │                               I6). New lens, by who decides the next
      │                               step: code (workflow: sequential, router,
      │                               parallel) · a manager (supervisor) · the
      │                               agent in charge (swarm). Parallel work
      │                               and a reviewer loop fit inside any of
      │                               them
      ├╌╌ ✅ More patterns ╌╌╌╌╌╌╌╌╌╌ new names: blackboard (agents watch a
      │                               shared store and act when something
      │                               relevant appears) · debate (several
      │                               answer, a judge or a vote picks) · market
      │                               (agents bid for a task). Network (anyone
      │                               calls anyone): avoid, hard to bound
      ├╌╌ ✅ Who decides what ╌╌╌╌╌╌╌ the model decides what is useful: the
      │                               plan, the judgement. Code decides what is
      │                               allowed and what must happen: the order,
      │                               IDs, checks, limits, gates
      ├╌╌ ✅ The map ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ the parts every LLM app has: model
      │                               access, data, coordination, state,
      │                               failure handling, security, privacy,
      │                               cost, observability. Stages B-G are one
      │                               part each
      └╌╌ ✅ Six questions ╌╌╌╌╌╌╌╌╌╌ is it the simplest that works? model or
                                      code decides? what must outlive a step?
                                      what can fail, and is it safe to repeat?
                                      how bad if the agent is wrong or
                                      hijacked? what does one success cost?
```

**Build**: learning only. Would be: the six questions answered for the year-end
review.

**Learned**
- A1–A6, 23 Nov 2026: learned. What landed: split only when one agent strains
  (ours doesn't: the chat answers in 2–3 calls, the review got 38/38 with one
  agent); three families by who decides the next step; the six questions
  answered for the year-end review. In short: the model thinks, code
  guarantees

[↑ Overview](#overview)

## B. Graph supervisor

Code runs the steps; Deep Agents are the workers inside.

```text
   B GRAPH SUPERVISOR
      │
      ├╌╌ ✅ Prompt as engine ╌╌╌╌╌╌╌ before: our year-end lead is told the
      │                               order in its prompt ("one department at a
      │                               time, don't hand it to a helper"). New: a
      │                               model can skip, repeat or reorder steps,
      │                               so steps that must always happen go in
      │                               code
      ├╌╌ ✅ Workflows (recap) ╌╌╌╌╌╌ sequential, router, parallel: the app
      │                               owns the path, the safest default. A
      │                               router can be one classifying call, not
      │                               an agent. AGENT_PLAYBOOK I
      ├╌╌ ✅ The graph ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ before: listed in AGENT_PLAYBOOK F, build
      │                               deferred. New: used. State (the shared
      │                               data) · nodes and edges · a reducer lets
      │                               parallel workers add to one list · Send
      │                               starts one worker per task · checkpointer
      │                               · interrupt
      ├╌╌ ✅ Agents as workers ╌╌╌╌╌╌ keep Deep Agents' files, permissions,
      │                               skills, offloading and per-worker limits.
      │                               Switch off its built-in helper (a
      │                               HarnessProfile) and its to-do list: the
      │                               graph holds the tasks. Before: stage A's
      │                               lead got that helper and the prompt asked
      │                               it not to use it
      ├╌╌ ✅ IDs in code ╌╌╌╌╌╌╌╌╌╌╌╌ the model never names files: code makes
      │                               each task's ID (a hash of run, worker and
      │                               question) → /findings/<id>.md. Parallel
      │                               workers can't collide; a retry writes the
      │                               same file
      ├╌╌ ✅ Output contract ╌╌╌╌╌╌╌╌ before: a helper returns a summary and
      │                               file paths (DEEP_AGENTS C). New: a fixed
      │                               JSON shape code can check: status,
      │                               summary, paths, limitations
      ├╌╌ ✅ Check the files ╌╌╌╌╌╌╌╌ "I saved it" is not proof. Code checks:
      │                               every task has a result, every file
      │                               exists and matches its shape, no two
      │                               workers wrote the same path. Missing → a
      │                               recovery step, never on to writing. Our
      │                               check_memo is half of this
      ├╌╌ ✅ Critic (recap) ╌╌╌╌╌╌╌╌╌ separate reviewer, JSON verdict, 2 rounds
      │                               (DEEP_AGENTS G). New: the graph's edge
      │                               counts the rounds; at the limit it
      │                               publishes with the gaps listed
      ├╌╌ ✅ Approval node (recap) ╌╌ interrupt() in a node; resume on the same
      │                               thread_id. The node reruns from its first
      │                               line, so side effects go after the
      │                               approval or are safe to repeat.
      │                               DEEP_AGENTS F
      └╌╌ ✅ Hierarchy (recap) ╌╌╌╌╌╌ supervisors of supervisors: only when a
                                      part needs its own breakdown. DEEP_AGENTS
                                      I4
```

**Build**: learning only. Would be: the year-end review as a graph, one worker
per department (Send), check_memo as the checking step, the reviewer capped at
2 rounds, HR's approval as an interrupt.

**Learned**
- B1–B10, 23 Nov 2026: learned. What landed: a graph for fixed steps, the agent
  loop for open-ended work (our chat), code for every guarantee; LangGraph is
  the outer frame, the workers inside are still agents and still pick their own
  next tool. A prompt is fine for guidance, not for what must (or must never)
  happen

[↑ Overview](#overview)

## C. Swarm and handoffs

No manager: the agent in charge passes the chat on.

```text
   C SWARM AND HANDOFFS
      │
      ├╌╌ ✅ Swarm (recap) ╌╌╌╌╌╌╌╌╌╌ one agent active at a time; it hands the
      │                               chat to a specialist when needed.
      │                               Supervisor for planned work, swarm when
      │                               needs show up mid-chat. AGENT_PLAYBOOK J,
      │                               DEEP_AGENTS I5
      ├╌╌ ✅ Handoff as a tool ╌╌╌╌╌╌ new: transfer_to_billing is a tool
      │                               returning a Command: which agent runs
      │                               next, plus a note in the chat. The tool
      │                               call needs a matching tool reply, or the
      │                               chat history is invalid
      ├╌╌ ✅ Shared state ╌╌╌╌╌╌╌╌╌╌╌ every agent reads one state: the
      │                               messages, who is active, how many
      │                               handoffs, what's being handed over. A
      │                               checkpointer and the thread_id carry it
      │                               across turns
      ├╌╌ ✅ Allowed handoffs ╌╌╌╌╌╌╌ new: a map of who may hand to whom
      │                               (billing → account only); any other
      │                               handoff is refused in code
      ├╌╌ ✅ Handoff cap ╌╌╌╌╌╌╌╌╌╌╌╌ at most 5, then a person takes over; also
      │                               catch two agents passing the chat back
      │                               and forth
      ├╌╌ ✅ Pass what's needed ╌╌╌╌╌ not the whole history (cost, and data the
      │                               next agent shouldn't see), but the
      │                               reference (an order or request ID), so
      │                               the user isn't asked again. Who the user
      │                               is travels with the chat
      └╌╌ ✅ Not a group chat ╌╌╌╌╌╌╌ group chat: a manager picks who speaks in
                                      one shared thread. Swarm: the agent
                                      itself hands off
```

**Build**: learning only. Our chat answers in 2–3 tool calls, so no strain and
no swarm. Would be: Ananya's "Friday off, and has my Dallas trip been paid?"
moving between a leave agent and an expenses agent.

**Learned**
- C1–C7, 23 Nov 2026: learned (example: a customer-care call being
  transferred). What landed: the handoff is a tool, the state remembers who has
  the call, code limits who may transfer to whom, how often, and what is
  passed. Not needed for our chat

[↑ Overview](#overview)

## D. Runtime reliability

When something fails mid-run: resume, retry the right things, never act twice.

```text
   D RUNTIME RELIABILITY
      │
      ├╌╌ ✅ Five layers ╌╌╌╌╌╌╌╌╌╌╌╌ prompts and tools are one layer of five:
      │                               harness · orchestration (the graph) ·
      │                               durable runtime (checkpoints, store,
      │                               files) · controls (identity, permissions,
      │                               budgets, approval) · observability
      ├╌╌ ✅ Three storages ╌╌╌╌╌╌╌╌╌ before: checkpointer (one run's progress)
      │                               and store (across chats). AGENT_PLAYBOOK
      │                               G, DEEP_AGENTS D1. New: artefact storage
      │                               for reports and big files (an object
      │                               store, like S3)
      ├╌╌ ✅ Resume (recap) ╌╌╌╌╌╌╌╌╌ a SQLite or Postgres checkpointer, the
      │                               same thread_id: the guide's test resumed
      │                               without rerunning finished workers.
      │                               DEEP_AGENTS F6, AGENT_PLAYBOOK K1
      ├╌╌ ✅ Not a transaction ╌╌╌╌╌╌ new: the checkpointer saves where the run
      │                               was, not what happened outside. A sent
      │                               email stays sent; a resumed step can send
      │                               it again
      ├╌╌ ✅ Failure → response ╌╌╌╌╌ time-out: time limit, a few retries · bad
      │                               JSON: check it, return an error, no blind
      │                               retry · 429: back off · crash: resume ·
      │                               one worker failed: keep the good result,
      │                               redo only that task · loop: budgets (G)
      ├╌╌ ✅ Retries (recap) ╌╌╌╌╌╌╌╌ a time limit on every call; retry only
      │                               what waiting can fix (time-outs, 429,
      │                               5xx), never a bad input, key or
      │                               permission. AGENT_PLAYBOOK D4. New: a
      │                               RetryPolicy on a graph step
      ├╌╌ ✅ Circuit breaker ╌╌╌╌╌╌╌╌ new: a service that keeps failing gets no
      │                               more calls for a while; the task goes to
      │                               a fallback or says "unavailable". Like a
      │                               fuse. AGENT_PLAYBOOK E3 left it for later
      │                               (Gemini down: ~3 min a call)
      ├╌╌ ✅ Keys (recap) ╌╌╌╌╌╌╌╌╌╌╌ the same request twice → one leave
      │                               request: AGENT_PLAYBOOK D3, and K3 (a
      │                               unique key in the database). New: send
      │                               the key to the outside service too
      │                               (tenant:workflow:action), so it refuses a
      │                               repeat
      ├╌╌ ✅ Operation ledger ╌╌╌╌╌╌╌ new: our own table of every action: its
      │                               ID, status, and the service's reference.
      │                               Check it before any retry
      └╌╌ ✅ Unknown outcome ╌╌╌╌╌╌╌╌ new: a time-out isn't a failure. Four
                                      states: pending, confirmed, failed,
                                      unknown. Unknown: ask the service by key,
                                      retry only if it says no, escalate if it
                                      can't say. For payments, bookings,
                                      messages
```

**Build**: learning only. Would be: "send the memos" with a key and a ledger
row per memo; a time-out marks it unknown and is checked before anything is
resent.

**Learned**
- D1–D10, 23 Nov 2026: learned, in a simpler retelling (paying 6 bills online):
  remember where you stopped; retry only what waiting can fix, and a fuse for a
  service that keeps failing; never do an important action twice: keep your own
  list and check first (a UPI payment stuck on "pending")

[↑ Overview](#overview)

## E. Security

Stop an agent doing harm: limits in code, not rules in the prompt.

```text
   E SECURITY
      │
      ├╌╌ ✅ OWASP LLM Top 10 ╌╌╌╌╌╌╌ the standard list of LLM app risks. The
      │                               four used here: prompt injection,
      │                               sensitive data disclosure, unsafe output
      │                               handling, excessive agency
      ├╌╌ ✅ Injection (recap) ╌╌╌╌╌╌ direct: the user types "ignore your
      │                               rules" (AGENT_PLAYBOOK D5). Indirect: the
      │                               attack hides in fetched text, a page, a
      │                               file or an email (DEEP_AGENTS D, H8).
      │                               Design for indirect: leave nothing
      │                               dangerous to be talked into
      ├╌╌ ✅ Excessive agency ╌╌╌╌╌╌╌ new name: more tools or permissions than
      │                               the job needs, like a researcher that can
      │                               also send email and delete files
      ├╌╌ ✅ Every door ╌╌╌╌╌╌╌╌╌╌╌╌╌ new: checks at 8 points: user input ·
      │                               before the model · fetched text · before
      │                               a tool (allowlist, arguments) · agent to
      │                               agent · tool reply (format, size) · final
      │                               answer · afterwards (audit). Before: only
      │                               some of them
      ├╌╌ ✅ Auth in code (recap) ╌╌╌ the model never decides whether it may
      │                               call a tool; code checks the permission
      │                               and the limits (permissions.py).
      │                               AGENT_PLAYBOOK D
      ├╌╌ ✅ Least privilege ╌╌╌╌╌╌╌╌ (recap) each agent gets the smallest tool
      │                               set: a critic reads, never rewrites the
      │                               evidence; a publisher publishes only
      │                               after the gate. DEEP_AGENTS C
      ├╌╌ ✅ Sandbox (recap) ╌╌╌╌╌╌╌╌ read-only by default, a restricted shell,
      │                               a list of allowed sites, separate
      │                               credentials per agent: limits the damage,
      │                               not only the chance. DEEP_AGENTS D
      └╌╌ ✅ Risk levels (recap) ╌╌╌╌ before: three (DEEP_AGENTS F1). Now four:
                                      low (read) none · medium (internal draft)
                                      maybe · high (refund, outside email)
                                      required · critical (delete data, change
                                      permissions) strong approval plus more.
                                      Show the real action, never a bare
                                      "Approve?"
```

**Build**: learning only. Would be: the 8 doors checked for the chat and the
year-end review.

**Learned**
- E1–E8, 23 Nov 2026: learned (example: a new intern who believes what they
  read). Mostly recap. New: the OWASP names, excessive agency, the 8
  checkpoints, a fourth risk level

[↑ Overview](#overview)

## F. PII protection

Keep personal data from the model, the traces and the logs.

```text
   F PII PROTECTION
      │
      ├╌╌ ✅ What PII is ╌╌╌╌╌╌╌╌╌╌╌╌ data that identifies a person: names,
      │                               emails, phones, addresses, ID and card
      │                               numbers. Text sent to Gemini leaves our
      │                               app
      ├╌╌ ✅ Middleware (recap) ╌╌╌╌╌ before: PIIMiddleware finds emails,
      │                               cards, IPs and URLs by pattern
      │                               (AGENT_PLAYBOOK E), left out as our data
      │                               has none; trace masking skipped
      │                               (EVAL_PLAYBOOK A). New: names are PII
      │                               too, and our tool results are full of
      │                               them
      ├╌╌ ✅ Find and replace ╌╌╌╌╌╌╌ new: Microsoft Presidio. Its analyzer
      │                               finds names (with a language model),
      │                               emails, phones; its anonymizer swaps
      │                               them: "Varun Malhotra" → <PERSON>
      ├╌╌ ✅ Put it back ╌╌╌╌╌╌╌╌╌╌╌╌ new: encrypt the name before the model,
      │                               decrypt after, so the memo still names
      │                               the real person. The key in a secrets
      │                               store, never in code
      ├╌╌ ✅ Four words ╌╌╌╌╌╌╌╌╌╌╌╌╌ redaction: removed · masking: hidden
      │                               (****) · pseudonymisation: replaced, can
      │                               be restored · anonymisation: can never be
      │                               traced back. Reversible is
      │                               pseudonymisation
      ├╌╌ ✅ Misses (+) ╌╌╌╌╌╌╌╌╌╌╌╌╌ detection misses some and flags others:
      │                               measure both. Our IDs (AMS-1040) need a
      │                               recogniser of our own
      └╌╌ ✅ Copies too (recap) ╌╌╌╌╌ a clean model call isn't enough: Langfuse
                                      and the logs keep copies. DEEP_AGENTS D
                                      (hidden copies), EVAL_PLAYBOOK A
```

**Build**: learning only. Would be: HR names replaced before Gemini in the
year-end review and put back in the memo; Langfuse shows stand-ins.

**Learned**
- F1–F7, 23 Nov 2026: learned (example: blood samples sent to a lab with a
  code, not a name). Asked: why not keep names in Langfuse, since they
  help debugging? Kept for now (local, one reader, made-up data: EVAL_PLAYBOOK
  A8). In production: hide names, keep employee IDs (readable and safe), limit
  who opens traces, delete after 30 days. Gemini never needs the name

[↑ Overview](#overview)

## G. Operating

Keep runs bounded, see whether they work, check before shipping.

```text
   G OPERATING
      │
      ├╌╌ ✅ Loop fingerprint ╌╌╌╌╌╌╌ before: a call limit stops a loop, but
      │                               only at the limit (AGENT_PLAYBOOK E).
      │                               New: a hash of tool name + inputs; the
      │                               same failing call again with nothing
      │                               changed → stop early. A rule of thumb:
      │                               reading pages repeats legitimately
      ├╌╌ ✅ Budgets (recap) ╌╌╌╌╌╌╌╌ in code, per run and per agent: model
      │                               calls 30, tool calls per worker 20,
      │                               critic rounds 2, handoffs 5, parallel
      │                               workers 4, 5 minutes, tokens and cost.
      │                               Ours: 5 a question, 30 a review
      ├╌╌ ✅ Metrics ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ before: time, tokens, cost per step
      │                               (EVAL_PLAYBOOK A). New: completion rate,
      │                               duplicate calls, handoffs, critic rounds,
      │                               p95 time, cost per success, retries,
      │                               approvals rejected, permissions denied
      ├╌╌ ✅ Cost per success ╌╌╌╌╌╌╌ don't just cut model calls: 20 useful
      │                               calls beat 5 wrong ones
      ├╌╌ ✅ Failure tests ╌╌╌╌╌╌╌╌╌╌ six scenarios with what should happen: a
      │                               repeated failing search · a crash before
      │                               writing · a time-out after an email went
      │                               · a malicious page · two agents passing a
      │                               request back and forth · a request with
      │                               an email and a phone number
      ├╌╌ ✅ Pitfalls ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ ten: prompt as engine · the model names
      │                               files · trusting "I saved it" · an
      │                               endless critic · side effects before
      │                               interrupt() · retrying a timed-out write
      │                               · rules in the prompt · the whole history
      │                               on handoff · approving everything ·
      │                               fewest calls
      └╌╌ ✅ Before you ship ╌╌╌╌╌╌╌╌ 10 checks: order, limits, gates in code ·
                                      resume works · time limits, retry only
                                      what can pass · a key and ledger row per
                                      action · auth in code · untrusted text,
                                      sandbox · PII replaced · hard budgets ·
                                      real-action approval · metrics and
                                      failure tests
```

**Build**: learning only. Would be: the 10 checks run on the chat and the year-
end review.

**Learned**
- G1–G7, 23 Nov 2026: learned (example: a long car trip). What landed: the 6
  failure tests are the whole playbook tested, each one a stage: loop (G),
  crash and timed-out email (D), hidden instructions (E), ping-pong (C),
  personal data (F)

[↑ Overview](#overview)

---

## Left for later

- Not in the guide (its own list): RAG, MCP, Deep Agents basics, evaluation
  and tracing (our other playbooks have them); model serving, fine-tuning;
  queues and microservices, beyond where agents need them
- Not run by the guide's author: any live model call, a handoff with a real
  model, the Presidio analyzer, a database checkpointer. Treat those parts
  as documentation, not observation

[↑ Overview](#overview)

---

## How to work through a topic

```text
 1. Before     what we already had, and where
 2. New        what this guide adds, in plain words
 3. Example    one small real case
 4. Record     status + a "Learned" line here
```

---

## Appendix: guide → stage

- Part I: 1.1 (one or several), 1.5 (system design) → A · 1.2–1.3
  (workflows, supervisor) → A and B · 1.4 (swarm) → C
- Part II (building a supervisor) → B · Part III (swarm) → C
- Part IV (runtime reliability) → D · Part V: 5.1–5.2 (threats, guardrails)
  → E · 5.3 (PII) → F
- Part VI (budgets, monitoring) and Part VII (failure scenarios, pitfalls,
  checklist) → G

**Not in the guide (+)**: a recogniser for our own IDs (F).

[guide]: https://cs-prod-assets-bucket.s3.ap-south-1.amazonaws.com/agentic_system_design_reliability_reference_f9e68be3c7.html
