# Deep Agents Playbook

A quick guide: agents that work through one long job, and several agents
working together, in the order we learn and build them. The overview shows what
exists; the sections below say in one line what each topic is, and what
happened when we built it.

- A long job, MCP, several agents → **this file**.
- Agent basics (the loop, middleware, LangGraph, approval, memory) →
  [AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md); this file recaps the ones a long job
  builds on, and links there for the rest.
- Tracing and scoring → [EVAL_PLAYBOOK.md](EVAL_PLAYBOOK.md).
- How our code does it → the ams-assistant README.

**Status**, in the stage sections (for ams-assistant):
✅ built or learned · ⏭ next · 🧪 tried, not kept yet · ⬜ not started ·
✗ skipped or failed

**Source**: the course's [Deep Agents, MCP and Multi-Agent Systems
reference][guide] (its example: a research assistant with a lead, two
researchers and a reviewer). Topics marked (+) aren't in it; topics marked
(recap) we covered before, here to revise, each saying where.

**The idea**: our chat agent answers in 2–3 tool calls. A job that reads every
employee's records can't work that way: everything it reads piles up in one
conversation until the model loses track. A deep agent keeps the work outside
the conversation: a to-do list for the plan, helper agents that each read one
part and send back a summary, files for the details, a reviewer that checks the
draft, and a person who approves before anything goes out.

---

## Starting point

What we already have:

- The agent ([AGENT_PLAYBOOK](AGENT_PLAYBOOK.md) A–K): `create_agent` with
  middleware (limits, retries, fallback, reflection), LangGraph's checkpointer,
  store and pauses, approval before saving, our MCP server (J1, tools only)
- Its tools: 5 records tools, the handbook search, booking and approvals; each
  checks permissions in code (`permissions.py`: your own records, or a direct
  report's profile)
- Tracing and evals ([EVAL_PLAYBOOK](EVAL_PLAYBOOK.md) A–E): Langfuse traces,
  code checks, the judge, a review queue
- The data: 40 employees in 6 departments, 198 leave requests (16 pending), 60
  expense claims (6 not paid yet), 6 handbooks; as of 16 Nov 2026
- Installed: `deepagents` 0.7.41 (stage A). Not yet: `langchain-mcp-adapters`

**Our task**: People Operations asks "Prepare the year-end leave and expenses
review for every department." For each department: annual leave and PTO above
the carry-over limit, lost on 31 December 2026 (India: up to 5 days carry over,
to use by 31 March; US: up to 10, by 30 June; Employee Handbook 4.4, 5.4),
pending requests, claims over the Finance Handbook's limits; a short memo for
its head; every number checked against the records; HR approves before the
memos go out. The chat assistant stays as it is: this is a second, longer job,
built from the same tools and data.

**Why this task**: it covers every record of 40 people, it splits into
independent parts (6 departments), it has something worth checking (the
numbers) and something worth approving (memos going out). A manager's team is
at most 3 people: one agent does that in a few calls, the case the guide says
not to split. It does fit one conversation (all the records are about 25K
tokens; Gemini takes 1M): stage A measured what that costs.

**One new rule**: HR may read everyone's leave and claims, a new level in
`permissions.py`; each helper gets only the tools for its part.

---

## Overview

**Jump to** · [Starting point](#starting-point) · [A
Foundations](#a-foundations) · [B Planning](#b-planning) · [C Helper
agents](#c-helper-agents) · [D Files, skills, memory](#d-files-skills-memory) ·
[E Context engineering](#e-context-engineering) · [F Control and
reliability](#f-control-and-reliability) · [G Review and
evaluation](#g-review-and-evaluation) · [H MCP](#h-mcp) · [I Several
agents](#i-several-agents) · [Left for later](#left-for-later)

```text
   🟧 OUR TASK: the HR year-end review

   HR: "year-end review" ──▶ LEAD AGENT: one to-do per department
                                  │
                ┌─────────────────┴─────────────────┐
                ▼                                   ▼
          leave analyst                      expense checker
          lapsing days, pending              claims against the
          requests                           Finance Handbook
                │  details → files                  │
                └─────────────────┬─────────────────┘
                                  ▼ short summaries + file paths
                    LEAD: one memo per department
                                  │
                                  ▼
                    REVIEWER: every number in the records?
                    gaps → more work (2 rounds at most)
                                  │
                                  ▼
                    HR approves ──▶ memos "sent"

   🟧 STAGES

   🟦 A FOUNDATIONS
      │
      ├╌╌ 🟢 Why long jobs fail
      │     └╌ context rot · seven failures · three remedies
      ├╌╌ 🟢 The layers
      │     └╌ LangGraph · LangChain · Deep Agents (the harness)
      ▼
   🟦 B PLANNING
      │
      ├╌╌ 🟢 To-do list
      │     └╌ write_todos · plan vs list vs brief · when it helps
      ▼
   🟦 C HELPER AGENTS
      │
      ├╌╌ 🟢 Delegation
      │     ├╌ the task tool · a clean window · forks
      │     └╌ briefs · parallel · background
      ▼
   🟦 D FILES, SKILLS, MEMORY
      │
      ├╌╌ 🟢 Workspace
      │     └╌ files · backends · offloading · permissions · privacy (+)
      ├╌╌ 🟢 Knowledge
      │     └╌ skills (when needed) · memory (always)
      ▼
   🟦 E CONTEXT ENGINEERING
      │
      ├╌╌ 🟢 What the model sees
      │     └╌ runtime context · state · store · compression · caching
      ▼
   🟦 F CONTROL AND RELIABILITY
      │
      ├╌╌ 🟢 People
      │     └╌ gate by consequence · gates with holes
      ├╌╌ 🟢 Running
      │     ├╌ durable progress · limits · streaming · traces per agent
      │     └╌ long jobs in the app (+)
      ▼
   🟦 G REVIEW AND EVALUATION
      │
      ├╌╌ 🟢 Review loop
      │     └╌ separate reviewer · JSON critique · 2 rounds · gate
      ├╌╌ 🟢 Evaluation (+)
      │     └╌ the end result · per agent · cost per job
      ▼
   🟦 H MCP
      │
      ├╌╌ 🟢 The protocol
      │     └╌ tools · resources · prompts · transports
      ├╌╌ 🟢 Our side
      │     └╌ the agent as a client · login (+) · security (+)
      ▼
   🟦 I SEVERAL AGENTS
      │
      ├╌╌ 🟢 Design
      │     └╌ when · design questions · topologies
      ├╌╌ 🟢 Patterns
      │     └╌ catalogue · choosing · operating · A2A (+)
      ▼
   a long job done in parts, checked, and approved
```

---

## A. Foundations

Why a chat agent breaks on a long job, and what Deep Agents adds.

```text
   A FOUNDATIONS
      │
      ├╌╌ ✅ The loop (recap) ╌╌╌╌╌╌╌ the model asks for a tool → our code runs
      │                               it → the model reads the result → again,
      │                               until it answers (ReAct). A deep agent
      │                               runs the same loop, much longer.
      │                               AGENT_PLAYBOOK A
      ├╌╌ ✅ Workflow or agent ╌╌╌╌╌╌ code picks the steps, or the model does;
      │                               mix both, simplest first. Recap:
      │                               AGENT_PLAYBOOK F and K
      ├╌╌ ✅ Context rot ╌╌╌╌╌╌╌╌╌╌╌╌ the fuller the window, the worse the
      │                               model recalls what's in it: give it the
      │                               smallest set of useful text. Most agent
      │                               failures are missing or buried context,
      │                               not a weak model
      ├╌╌ ✅ Seven failures ╌╌╌╌╌╌╌╌╌ context overflow · plan drift · detail
      │                               flooding · nothing to inspect · grading
      │                               its own work · lost progress · unsafe
      │                               actions. Each has a fix in B–G
      ├╌╌ ✅ Three remedies ╌╌╌╌╌╌╌╌╌ compaction (summarise the chat) · notes
      │                               kept outside it (to-dos, files) · helper
      │                               agents with clean windows
      ├╌╌ ✅ The layers ╌╌╌╌╌╌╌╌╌╌╌╌╌ LangGraph runs it (state, checkpoints,
      │                               pauses) · LangChain builds it
      │                               (create_agent, middleware) · Deep Agents
      │                               adds the harness. Our chat agent stops at
      │                               LangChain
      ├╌╌ ✅ Middleware (recap) ╌╌╌╌╌ hooks around every model and tool call;
      │                               ours add limits, retries, a fallback,
      │                               reflection. The harness is create_agent
      │                               with a stack of them: files, helpers,
      │                               summarising. AGENT_PLAYBOOK E
      └╌╌ ✅ The harness ╌╌╌╌╌╌╌╌╌╌╌╌ create_deep_agent(): files, helpers and
                                      summarising on by default; planning,
                                      skills, memory, approval when asked. A
                                      long built-in prompt only for some
                                      models, not Gemini: ours is all of it
```

**Build**: deepagents installed; HR's new permission level; a first lead agent
with no helpers, run on one department, to see where it struggles.

**Built**
- A1–A7, 18–20 Nov 2026: learned. What landed: who decides the next step (code
  = workflow, the model = agent); the harness is what surrounds the model;
  LangGraph is for steps that must always happen in order, wait for a person
  or resume (a shop's refund: as tools the model may skip the manager; as a
  plain function it can't wait a day; as a graph it waits and resumes);
  middleware is rules around one agent's loop
- A8, 21 Nov 2026: `deepagents` 0.7.41 installed. It upgraded LangChain 1.4.9
  → 1.5.2, langchain-core 1.7.7 → 1.8.4, langgraph 1.2.20 → 1.2.24, langsmith
  0.14.12 → 0.16.0, and added langchain-anthropic (unused). The chat after it:
  D1–D3 replayed from the reply cache give the same answers with no new model
  call; the app's first screen; the MCP server's 6 tools
  - the harness gives the lead `ls`, `read_file`, `write_file`, `edit_file`,
    `delete`, `glob`, `grep`, `execute` (an error without a sandbox) and `task`
    (a general-purpose helper with all the lead's tools). No planning (opt-in
    since 0.7) and no built-in prompt for Gemini: ours is the whole prompt
- `permissions.py`: an "hr" level, People Operations staff (Neha, Aditi,
  Shruti): everyone's profile, leave and claims. Only the year-end tool checks
  it; in the chat nothing changes
- A2 in code: `year_end_tools.py`, `year_end_leave(department)`. Code works
  out each person's days lost on 31 December, days carried over and the date
  to use them by, from their payroll's rule; their pending requests; the
  department's head and totals. Karthik (leaving 24 December) is marked
  "settled on leaving", not "lost". The model only copies and writes
- `year_end.py`: the lead (`create_deep_agent` on Gemini, our tool, our limit
  of 30 model calls and the tool-error middleware, `HRContext`); memos in a
  fixed format to `/memos/<department>.md` (files in the run's state);
  `check_memo()` checks each person's line, every pending request, the total,
  and invented numbers (C6). `year_end_review.py` runs it in the terminal
- Tests, no model call: Sales matches the hand count (6 people, 30.5 days),
  Ananya is refused (not People Operations), all 16 pending requests are in;
  the memo check passes a right memo 6/6 and catches 5 planted mistakes (a
  wrong carry-over, a missing person, a missing request, a wrong total, made-up
  numbers)
- Measured (Gemini 3.5 Flash-Lite, traced in Langfuse):
  - Sales alone: 3 model calls, 31 s, prompt 2,984 → 4,334 tokens; 6/6 people
    right, total right, nothing invented
  - all 6 departments in one conversation: also 3 model calls (6 tool calls
    in one reply, then 6 memos in one reply), 32 s, prompt 2,997 → 13,037
    tokens; 38/38 people right, every total right, nothing invented. It never
    used the helper
- What it shows: with the numbers made by code, one conversation does the
  leave part right; no context rot at 13K tokens. The split of A2 removed the
  failure stage A was looking for. Later stages have to earn their place on
  what the model must judge (claims against the Finance Handbook, C) and on
  control (approval, resuming: F). About 3K tokens of every call are the
  instructions and tool descriptions, before any data

[↑ Overview](#overview)


## B. Planning

Keep a long job on track by writing the plan down.

```text
   B PLANNING
      │
      ├╌╌ ✅ Plan first (recap) ╌╌╌╌╌ plan-and-execute: write the whole plan,
      │                               then do the steps, re-plan when one
      │                               fails. write_todos is the agent keeping
      │                               that plan itself and rewriting it as it
      │                               goes. AGENT_PLAYBOOK I
      ├╌╌ ✅ To-do list ╌╌╌╌╌╌╌╌╌╌╌╌╌ write_todos: the agent writes its plan as
      │                               a list (pending → in progress → done) and
      │                               rewrites it as it learns. The tool does
      │                               nothing; the list keeps the goal in
      │                               recent context
      ├╌╌ ✅ Tracing (recap) ╌╌╌╌╌╌╌╌ every model and tool call of a run, in
      │                               Langfuse, read question → tools → answer;
      │                               the same habit reads a plan.
      │                               AGENT_PLAYBOOK C, EVAL_PLAYBOOK A
      ├╌╌ ✅ Reading the trace ╌╌╌╌╌╌ in Langfuse: is the first call a plan? Do
      │                               updates ride along with real work? Does
      │                               the list change when the data surprises
      │                               it? Does the prompt grow fast?
      ├╌╌ ✅ Plan, list, brief ╌╌╌╌╌╌ a plan says what and why (a file); the
      │                               to-do list says done and next (state); a
      │                               brief tells one helper its job
      └╌╌ ✅ When it helps ╌╌╌╌╌╌╌╌╌╌ many steps, independent parts, a person
                                      following progress; not a single lookup
                                      like our chat's
```

**Build**: planning on, one to-do per department, read in its trace.

**Built**
- B1–B6, 21 Nov 2026: learned, build skipped (fundamentals first, builds
  later). What landed: write_todos is the agent keeping its own plan in recent
  context; it pays off on many steps, not on a lookup. B3 and B4 overlap: both
  are reading the trace

[↑ Overview](#overview)


## C. Helper agents

Hand each part to a helper with a clean window; only a summary comes back.

```text
   C HELPER AGENTS (subagents)
      │
      ├╌╌ ✅ Supervisor (recap) ╌╌╌╌╌ one agent hands work to specialists and
      │                               puts their results together
      │                               (orchestrator-workers). Our lead is one;
      │                               the task tool is how it hands work out.
      │                               AGENT_PLAYBOOK I and J
      ├╌╌ ✅ The task tool ╌╌╌╌╌╌╌╌╌╌ a helper is called like a tool,
      │                               task(name, brief); its last message is
      │                               the result. Recap: agents as tools,
      │                               AGENT_PLAYBOOK J
      ├╌╌ ✅ Context isolation ╌╌╌╌╌╌ a helper sees only its brief and the lead
      │                               only its summary (1–2K tokens), so the
      │                               lead's window stays small. A fork also
      │                               gets the lead's chat, and costs more
      ├╌╌ ✅ Defining a helper ╌╌╌╌╌╌ name, description (the lead picks by it),
      │                               prompt, tools, model. Always list its
      │                               tools: left out, it gets all the lead's,
      │                               approval-gated ones too
      ├╌╌ ✅ Identity (recap) ╌╌╌╌╌╌╌ who's asking comes from the sign-in, in
      │                               code, never from what the model writes.
      │                               The lead writes each brief, so a helper's
      │                               tools still take HR's ID from code.
      │                               AGENT_PLAYBOOK D
      ├╌╌ ✅ A good brief ╌╌╌╌╌╌╌╌╌╌╌ the goal, what to return and how long,
      │                               which tools, what's out of bounds.
      │                               Details into files; back only a summary
      │                               and the paths
      ├╌╌ ✅ Parallel ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ several task calls in one reply run side
      │                               by side: the time is the slowest
      │                               helper's. AMS: 6 departments at once (our
      │                               Gemini pacing slows that)
      ├╌╌ ✅ Background helpers ╌╌╌╌╌ start, check, update or cancel a long job
      │                               while the chat goes on; needs an Agent
      │                               Protocol server
      └╌╌ ✅ When not to ╌╌╌╌╌╌╌╌╌╌╌╌ one lookup, work that needs the lead's
                                      whole chat, parts that depend on each
                                      other
```

**Build**: a leave analyst and an expense checker, each with only its tools;
the lead hands out departments; summaries and file paths come back.

**Built**
- C1–C9, 21 Nov 2026: learned, build skipped. What landed: the lead picks
  helpers at run time from the task tool's description (each helper's name and
  what it does); a helper gets only its brief and sends back a summary; several
  agents cost about 15× a chat

[↑ Overview](#overview)


## D. Files, skills, memory

Details in files, procedures in skills, standing rules in memory.

```text
   D FILES, SKILLS, MEMORY
      │
      ├╌╌ ✅ Memory (recap) ╌╌╌╌╌╌╌╌╌ the checkpointer keeps this chat; the
      │                               store keeps facts across chats (ours:
      │                               preferences, like half days). Files can
      │                               live in either. AGENT_PLAYBOOK G
      ├╌╌ ✅ Files as memory ╌╌╌╌╌╌╌╌ the chat is resent on every call and gone
      │                               afterwards; a file is cheap, read when
      │                               needed, handed over by its path, and a
      │                               person can open it
      ├╌╌ ✅ Backends ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ where files live: the run's state
      │                               (default), a folder on disk (always with
      │                               virtual_mode), the store (across chats),
      │                               or routed by path
      ├╌╌ ✅ Offloading ╌╌╌╌╌╌╌╌╌╌╌╌╌ a tool result over ~20,000 tokens goes to
      │                               a file; the model keeps the path and its
      │                               first 10 lines
      ├╌╌ ✅ Permissions ╌╌╌╌╌╌╌╌╌╌╌╌ ordered rules, the first match wins: the
      │                               reviewer may write only its reviews.
      │                               Built-in file tools only, not our own
      │                               tools
      ├╌╌ ✅ Injection (recap) ╌╌╌╌╌╌ text from records, files and handbooks is
      │                               data, not orders: a claim note saying
      │                               "approve everything" changes nothing.
      │                               Here one agent's file is another's input.
      │                               AGENT_PLAYBOOK D
      ├╌╌ ✅ Running code ╌╌╌╌╌╌╌╌╌╌╌ a sandbox, or a shell on the Mac (risky).
      │                               Learn only: our task doesn't need it
      ├╌╌ ✅ Skills ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ a SKILL.md: a procedure read only when a
      │                               task needs it; just its description is
      │                               always in context. AMS: how to check a
      │                               claim against the Finance Handbook
      ├╌╌ ✅ Memory files ╌╌╌╌╌╌╌╌╌╌╌ AGENTS.md: rules loaded on every call, so
      │                               keep it short; per agent, per user or per
      │                               company; policies read-only
      ├╌╌ ✅ Not to store (recap) ╌╌╌ no secrets, no guesses, no one else's
      │                               data; deleted on request. The same for
      │                               AGENTS.md; the workspace does hold
      │                               others' records: next. AGENT_PLAYBOOK G
      └╌╌ ✅ Workspace privacy (+) ╌╌ the files hold HR data: who may open
                                      them, when they're deleted (as
                                      EVAL_PLAYBOOK A8 does for traces)
```

**Build**: a workspace per run (findings, claims, reviews, memos); the reviewer
may write only its reviews; one skill (checking a claim); a short AGENTS.md.

**Built**
- D1–D11, 21 Nov 2026: learned, build skipped. What landed: the agent picks a
  path, code maps paths to storage (backends); a lasting checkpointer lets a
  run carry on from the step it stopped at; skills aren't needed for a focused
  app like ours

[↑ Overview](#overview)


## E. Context engineering

For every piece of information: what the model sees, and when.

```text
   E CONTEXT ENGINEERING
      │
      ├╌╌ ✅ Three controls ╌╌╌╌╌╌╌╌╌ one model call (prompt, tools, history) ·
      │                               what tools read and write · what runs
      │                               between steps (summarising, guardrails)
      ├╌╌ ✅ Three sources ╌╌╌╌╌╌╌╌╌╌ runtime context: per run, never shown to
      │                               the model (ours: HRContext, the employee
      │                               ID) · state: this chat · store: across
      │                               chats. Recap: AGENT_PLAYBOOK F and G
      ├╌╌ ✅ Summarising (recap) ╌╌╌╌ replace old messages with a summary
      │                               before the chat outgrows the window
      │                               (learned, not built). Compression is
      │                               this, after big results go to files.
      │                               AGENT_PLAYBOOK E
      ├╌╌ ✅ Compression ╌╌╌╌╌╌╌╌╌╌╌╌ first big results go to files; at 85% of
      │                               the window, old messages are summarised
      │                               (a copy kept in a file)
      ├╌╌ ✅ Agentic RAG (recap) ╌╌╌╌ the handbook search is a tool, so
      │                               handbook text comes in only when a
      │                               question needs it: loading late, already
      │                               in our chat. AGENT_PLAYBOOK B
      ├╌╌ ✅ Load late ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ keep detail out until it's needed:
      │                               helpers, skills, files. Prevention beats
      │                               repair
      ├╌╌ ✅ Where it lives ╌╌╌╌╌╌╌╌╌ rule → memory · procedure → skill ·
      │                               evidence → file · next steps → to-dos ·
      │                               preferences → store · IDs and keys →
      │                               runtime context
      └╌╌ ✅ Stable prefix ╌╌╌╌╌╌╌╌╌╌ keep the start of the prompt and the tool
                                      list unchanged so the provider can cache
                                      them; add new material at the end. How
                                      Gemini caches: to check (+)
```

**Build**: measured: the lead's prompt size on every call, with and without
helpers and files.

**Built**
- E1–E8, 21 Nov 2026: learned, build skipped. What landed: for each piece of
  text ask "needed on every call?" and "must it last?"; load the rest late,
  offload big results to files, keep the start of the prompt stable for caching

[↑ Overview](#overview)


## F. Control and reliability

Approve what matters, survive failures, see what each agent did.

```text
   F CONTROL AND RELIABILITY
      │
      ├╌╌ ✅ Gate by consequence ╌╌╌╌ no gate for reads; approve or reject for
      │                               costly steps; approve, edit or reject,
      │                               arguments shown, for ones that can't be
      │                               undone. Tool risk: AGENT_PLAYBOOK D
      ├╌╌ ✅ Approval (recap) ╌╌╌╌╌╌╌ ours asks inside the tool, after its
      │                               checks (interrupt), so nobody confirms
      │                               what the rules refuse; code before
      │                               interrupt() runs again on resume. Deep
      │                               Agents' interrupt_on asks before the
      │                               tool: the middleware we skipped.
      │                               AGENT_PLAYBOOK H
      ├╌╌ ✅ Gates with holes ╌╌╌╌╌╌╌ a gate covers only the tool it names: a
      │                               helper with its own copy of that tool
      │                               walks around it. Gate the effect
      ├╌╌ ✅ Respond ≠ reject ╌╌╌╌╌╌╌ respond answers for a tool without
      │                               running it; to deny, use reject, or the
      │                               model may read it as done
      ├╌╌ ✅ Idempotent (recap) ╌╌╌╌╌ the same request sent twice makes one
      │                               leave request, not two. A resumed job can
      │                               redo a step: "send the memos" must still
      │                               send each once. AGENT_PLAYBOOK D
      ├╌╌ ✅ Durable progress ╌╌╌╌╌╌╌ a long run saved on disk (an SQLite or
      │                               Postgres checkpointer) carries on after a
      │                               crash or a restart instead of starting
      │                               over. Ours is in memory, lost on a
      │                               restart: AGENT_PLAYBOOK F and G
      ├╌╌ ✅ Safe errors (recap) ╌╌╌╌ "I couldn't check that right now", never
      │                               a stack trace; say if a retry could help.
      │                               A helper that fails says so, and the memo
      │                               lists the gap, not a guess.
      │                               AGENT_PLAYBOOK D
      ├╌╌ ✅ Limits and budget ╌╌╌╌╌╌ call limits, retries, fallbacks (ours:
      │                               AGENT_PLAYBOOK E); a budget counted in
      │                               code, since a limit can let a person
      │                               approve a call that will never run
      ├╌╌ ✅ Streaming ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ each event says which agent sent it, so
      │                               the app can show the lead and every
      │                               helper. Recap: streaming modes,
      │                               AGENT_PLAYBOOK F
      ├╌╌ ✅ Per-agent traces ╌╌╌╌╌╌╌ tokens, cost and errors per helper in
      │                               Langfuse. Depth costs tokens: ~4× a chat
      │                               for one agent, ~15× for several
      └╌╌ ✅ Long jobs in app (+) ╌╌╌ a 10-minute job can't block the chat: it
                                      runs in the background, shows progress,
                                      can be cancelled, says when it's done
```

**Build**: HR approves the memos before they go out; a run carries on after a
restart; each helper visible in Langfuse; the review runs in the background in
the app.

**Built**
- F1–F11, 21 Nov 2026: learned, build skipped, as three questions: when must a
  person say yes (F1–F4), what happens when it breaks (F5–F8), can people see
  what's going on (F9–F11)

[↑ Overview](#overview)


## G. Review and evaluation

A separate reviewer challenges the draft; evals measure the whole job.

```text
   G REVIEW AND EVALUATION
      │
      ├╌╌ ✅ Reflection (recap) ╌╌╌╌╌ our agent checks its reply against the
      │                               tool results before answering. Same
      │                               model, same window: it misses what it
      │                               already believes, hence a separate
      │                               reviewer. AGENT_PLAYBOOK I
      ├╌╌ ✅ Separate reviewer ╌╌╌╌╌╌ write, review, revise until approved or
      │                               the budget is spent. The reviewer starts
      │                               fresh, or it agrees with its own
      │                               reasoning. Recap: AGENT_PLAYBOOK I
      ├╌╌ ✅ Judge biases (recap) ╌╌╌ an LLM grader favours longer answers, the
      │                               first one shown and its own model's
      │                               style. The reviewer is a judge too:
      │                               another model, brevity in its rules.
      │                               EVAL_PLAYBOOK D2
      ├╌╌ ✅ Structured critique ╌╌╌╌ the reviewer returns JSON (approved,
      │                               unsupported claims, missing parts,
      │                               follow-up tasks) that code acts on
      ├╌╌ ✅ Checkable evidence ╌╌╌╌╌ each claim in a memo tied to its record
      │                               (a request or claim ID), so review is a
      │                               lookup. Our number check (EVAL C6) fits
      │                               here
      ├╌╌ ✅ Bound the loop ╌╌╌╌╌╌╌╌╌ at most 2 rounds, counted in code, not
      │                               asked for in the prompt; at the limit,
      │                               finish and list the gaps
      ├╌╌ ✅ Gate the follow-up ╌╌╌╌╌ a person approves the extra work the
      │                               reviewer asks for, before it runs:
      │                               approve, edit or reject
      ├╌╌ ✅ Trajectory (recap) ╌╌╌╌╌ task success is the right result; the
      │                               trajectory, the right tools with the
      │                               right inputs. For the job: the right
      │                               memos, and each helper's own path.
      │                               AGENT_PLAYBOOK C, EVAL_PLAYBOOK C
      └╌╌ ✅ Evaluate the job (+) ╌╌╌ ~20 realistic requests, the end result
                                      scored by a rubric, per-agent results,
                                      cost and time per job: EVAL_PLAYBOOK
                                      extended to several agents
```

**Build**: a reviewer helper with a JSON verdict; every memo number tied to a
record; two rounds at most; a small eval of whole reviews.

**Built**
- G1–G9, 21 Nov 2026: learned, build skipped, as three questions: who checks
  the work (G1–G3), how feedback turns into fixes, safely (G4–G7), is the whole
  job good (G8–G9)

[↑ Overview](#overview)


## H. MCP

Tools that live in another program, reached through one standard.

```text
   H MCP
      │
      ├╌╌ ✅ Why a protocol ╌╌╌╌╌╌╌╌╌ N apps × M services becomes N + M pieces:
      │                               a host (the app), one client per server,
      │                               servers
      ├╌╌ ✅ Our server (recap) ╌╌╌╌╌ our 6 read tools over stdio, one copy of
      │                               the code and its permission checks; who's
      │                               asking is set when it starts, never a
      │                               tool input; tools marked read-only.
      │                               AGENT_PLAYBOOK J1
      ├╌╌ ✅ Three primitives ╌╌╌╌╌╌╌ tools (the model calls them) · resources
      │                               (data the app fetches) · prompts
      │                               (templates the user picks). Ours
      │                               publishes tools only
      ├╌╌ ✅ Transports ╌╌╌╌╌╌╌╌╌╌╌╌╌ stdio: the app starts the server (ours) ·
      │                               Streamable HTTP: one shared server many
      │                               apps call
      ├╌╌ ✅ The agent as client ╌╌╌╌ the deep agent takes its HR tools from
      │                               our MCP server (langchain-mcp-adapters),
      │                               not Python imports; each helper gets its
      │                               tools by name
      ├╌╌ ✅ More of MCP (+) ╌╌╌╌╌╌╌╌ sampling (a server borrows the app's
      │                               model) · elicitation (a server asks the
      │                               user) · structured results · tool hints
      │                               like read-only
      ├╌╌ ✅ Real login (+) ╌╌╌╌╌╌╌╌╌ a shared server must know who's asking:
      │                               OAuth, a token for this server only,
      │                               never passed on to another (confused
      │                               deputy). Recap: secrets, identity,
      │                               AGENT_PLAYBOOK D
      └╌╌ ✅ MCP security (+) ╌╌╌╌╌╌╌ hidden instructions in tool descriptions;
                                      a server that changes its tools later;
                                      the lethal trifecta: private data +
                                      untrusted text + a way to send it out
```

**Build**: the helpers take their tools from our ams-hr server; its security
checked against the (+) list.

**Built**
- H1–H8, 21 Nov 2026: learned, build skipped, as three questions: what MCP is
  and why (H1–H2), what a server offers and how to connect (H3–H6), keeping it
  safe (H7–H8). The app speaks MCP, not the model: initialize, tools/list,
  tools/call, tried by hand on ams-hr over stdio

[↑ Overview](#overview)


## I. Several agents

When several agents beat one, how to arrange them, how to run them.

```text
   I SEVERAL AGENTS
      │
      ├╌╌ ✅ One or several ╌╌╌╌╌╌╌╌╌ start with one; several pay off on broad
      │                               work that splits into independent parts
      │                               and won't fit one window, at ~15× the
      │                               tokens of a chat. Recap: AGENT_PLAYBOOK J
      │                               and K
      ├╌╌ ✅ Why they help ╌╌╌╌╌╌╌╌╌╌ separate windows · parallel work ·
      │                               specialists: know which one you're paying
      │                               for
      ├╌╌ ✅ Design questions ╌╌╌╌╌╌╌ who decides next · what each sees · how
      │                               they pass work · what runs at once ·
      │                               what's kept · where a person steps in ·
      │                               when it stops
      ├╌╌ ✅ Topologies ╌╌╌╌╌╌╌╌╌╌╌╌╌ pipeline · hub and spoke (ours) · peers ·
      │                               hierarchy
      ├╌╌ ✅ Handoffs (recap) ╌╌╌╌╌╌╌ an agent passes the whole chat to
      │                               another, which carries on with the user.
      │                               A helper is the opposite: it gets a brief
      │                               and comes back. AGENT_PLAYBOOK J
      ├╌╌ ✅ Patterns ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ chaining · routing · parallel ·
      │                               orchestrator-workers ·
      │                               evaluator-optimiser (these five:
      │                               AGENT_PLAYBOOK I) · handoffs · skills ·
      │                               group chat · plan-driven · hierarchy · a
      │                               custom graph
      ├╌╌ ✅ Choosing ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ LangChain's cost per pattern (calls,
      │                               tokens, a repeated request); a few
      │                               questions give a starting pattern;
      │                               patterns combine
      ├╌╌ ✅ Operating ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ duplicated work, details lost in
      │                               retelling, runaway effort, errors that
      │                               compound: hand over by file, resume,
      │                               trace per agent, roll out slowly, test
      │                               prompts like code
      └╌╌ ✅ A2A (+) ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ Agent2Agent: agents from different apps
                                      or companies talk through one protocol;
                                      MCP is agent-to-tool
```

**Build**: learn; ours is hub and spoke plus a reviewer and a gate. Maybe a
router in front: the chat or the review.

**Built**
- I1–I9, 21 Nov 2026: learned, build skipped, as three questions: do we need
  several agents (I1–I2), how to arrange them (I3–I7), what goes wrong when
  they run (I8–I9)

[↑ Overview](#overview)


---

## Left for later

From the guide's "Beyond this reference", not started:

- Orchestration built by hand: custom graphs and state machines, a supervisor
  from scratch, fan-out with Send ([AGENT_PLAYBOOK F](AGENT_PLAYBOOK.md) has
  the pieces)
- Guarantees: retry and recovery design, idempotency across agents and
  workflows

[↑ Overview](#overview)

---

## How to work through a topic

```text
 1. Learn      the idea, with one AMS example
 2. Build      the smallest version in ams-assistant
 3. Prove      it catches a known failure (break something on purpose)
 4. Record     status + a "Built" or "Tried" line here, win or lose
```

---

## Appendix: guide → stage

- Part I (foundations: 1.1–1.3) and 2.1 (the harness) → A
- 2.2 (planning) → B · 2.3 (subagents) → C · 2.4–2.5 (filesystem, skills,
  memory) → D · 2.6 (context engineering) → E · 2.7–2.8 (human oversight,
  reliability) → F · 2.9 (review loops) → G
- Part III (MCP) → H · Part IV (multi-agent) → I
- Part V: 5.1 (the worked research app) → our task, built across the stages;
  5.2–5.3 (quick reference, sources) → looked up as we go

**Not in the guide (+)**: workspace privacy (D), how Gemini caches (E), long
jobs in the app (F), evaluating the whole job (G), more of MCP, a real login
and MCP security (H), A2A (I).

**Revision (recap)**: 19 topics from AGENT_PLAYBOOK and EVAL_PLAYBOOK, each
placed just before the new topic it leads into.

[guide]: https://cs-prod-assets-bucket.s3.ap-south-1.amazonaws.com/deep_agents_mcp_multi_agent_reference_a2a17c05fb.html
