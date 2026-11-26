# Building the AMS agent, step by step

The recipe: what we did, in order, from a bare start (the database in
`ams-data/db/` and the handbooks in `ams-data/policies/`). At most ~10
lines per step; the options for each step are in
[AGENT_APP_PLAYBOOK.md](../AGENT_APP_PLAYBOOK.md).

## 1. Design

**Did:** decided the job (an employee asking about their own HR, IT,
pay, projects); wrote it as 27 questions with right answers
([evals/questions.csv](evals/questions.csv)); one agent with tools,
Gemini 3.5 Flash-Lite.
**Why:** right answers first, so every later change is measured
(tests before code; [Anthropic on agent evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).
**Checked:** every answer against the data and a handbook section.
**Next time:** job in two sentences → 20–50 questions with right
answers, easy to hard, every "must not" with a mirror that must pass
→ only then pick the shape and the model.

## 2. Walk 2: Identify (the walking skeleton)

**Did:** every layer, thin: Streamlit with a dev-only ID sign-in
([app.py](app.py)) → the ID in the runtime context → the agent
(Gemini, step limit 5, [agent.py](src/ams_agent/agent.py)) → one tool,
`get_leave_balance` → SQLite, read-only, rebuilt from the 12 CSVs
([load_data.py](load_data.py)). Eval runner grades with code
([evals/run_evals.py](evals/run_evals.py)): new columns `must_include`,
`must_not_include`, `db_change`.
**Why:** bugs hide in the joins between layers, so connect them all first.
**Checked:** tool by code (Ananya 7, Michael 0.5, writes refused);
sign-in by AppTest; baseline **4 / 27** (Q01, Q03; Q23, Q25 only as no
tool shows pay). Found: Q17 printed its instructions (OWASP LLM07).
**Next time:** sign-in, one tool, eval runner together; baseline before any fix.
**Terms:** walking skeleton · trusted context (stops IDOR/BOLA) ·
dev-only sign-in vs SSO (OpenID Connect, `st.login`) · test fixture ·
tool calling · agent loop (ReAct) · step limit · deterministic tools ·
grounded answers · least privilege · parameterised queries + allowlist ·
golden dataset · code-based grader · outcome vs trajectory · baseline ·
system prompt leakage.

## 3. Walk 3: Guard input

**Did:** tests first: Q28–Q34 (attacks and their mirrors). Request
limits in code, before the agent ([limits.py](src/ams_agent/limits.py)):
2,000 characters, 10 questions a minute per person. A topic guard
([topic_guard.py](src/ams_agent/topic_guard.py)): middleware, one cheap
check per question against an allow-list, fixed reply, fail open. An
output check ([output_check.py](src/ams_agent/output_check.py)): code
replaces an answer quoting the prompt (canary + 8-word shingles). The
scope written once ([scope.py](src/ams_agent/scope.py)) for prompt and
guard. Gemini calls paced below 15 a minute ([models.py](src/ams_agent/models.py)).
**Why:** Q34 ("a script for my leave note") got code; Q17 leaked the
prompt on a normal question. A guard checks the topic, never permission.
**Checked:** **11 / 34** (was 6 / 34): Q29, Q30, Q32, Q34 blocked; Q24,
Q31, Q33 let through. Output check: 0 of 102 real answers wrongly
replaced; live Q30 with the guard off → replaced.
**Next time:** write the mirrors (real questions that sound off-topic)
before the guard; pace model calls before the first full run.
**Terms:** defence in depth · input guard (input rail) · allow-list vs
deny-list · fail open vs fail closed · false positive · rate limiting
(sliding window) · client-side throttling (token bucket) · topic vs
permission · red-teaming · output check · canary token · word shingles ·
system prompt leakage (OWASP LLM07).

## 4. Walk 4: Route

**Did:** decided the shape: one entry point (the chat), one agent, no
router. Roles worked out by code at sign-in
([context.py](src/ams_agent/context.py)): everyone is an employee,
someone with direct reports a manager, People Operations staff hr;
they ride in the runtime context with the ID (`context_for()`, used by
the app and the eval runner) and show in the sidebar.
**Why:** a router splits by job, not by data: every question is "look
up my records", about 10 tools. Roles now, so walk 7 can give each role
only its tools (don't offer a door someone can never use).
**Checked:** by code: Ananya → employee; Pooja → employee, manager;
Shruti → employee, hr; Neha → all three; unknown ID refused; context
frozen. Sign-in by AppTest. Live Q01 and Q28 still pass.
**Next time:** add a router or a second agent only when evals show
wrong tool choices, a context too big, or jobs needing other powers.
**Terms:** entry points · router (routing workflow) · single vs
multi-agent (orchestrator–worker, supervisor) · split by capability,
not data source · role-based access control (RBAC) · least privilege ·
tools by role · roles from the identity provider (group claims).

## 5. Walk 5: Context

**Did:** tests first: Q35–Q38 (grade and office; the same for a US
person; "what's my name?"; "I've moved to Austin"). The context now
carries job, department, grade and office; `about_asker()`
([context.py](src/ams_agent/context.py)) turns it into one line, which
`with_asker` (`@dynamic_prompt`, [agent.py](src/ams_agent/agent.py))
adds to the END of the fixed prompt before every model call. Payroll
from the office (`PAYROLL`, config.py). Profile added to the scope.
**Why:** the model knows only what it's sent: it said "I don't know"
to "what's my grade?" though the app knew. Office decides which rules
apply. No name: Gemini never needs it. The rest comes from tools.
**Checked:** baseline 1 / 4 (Q37 only because the guard blocked it);
now **15 / 38** (was 11 / 34): Q35–Q38 pass, no other changes. Prompt
for two people: same start, no name; the header isn't flagged as a leak.
**Next time:** put what every answer needs in the prompt, the rest in
tools; fixed text first, per-person text last.
**Terms:** context engineering · dynamic system prompt · trusted
context · just-in-time context (load late) · data minimisation ·
prompt caching (stable prefix) · context window · context rot.

## 6. Walk 6: Orchestrate

**Did:** kept the agent loop (`create_agent`) and gave it brakes in
code, a budget per question ([budget.py](src/ams_agent/budget.py),
values in config.py): 5 model calls (LangChain's limit, our reply), 8
tool calls (more are refused; the model answers with what it has), 90
seconds and 30,000 tokens (`RunBudget`, ours: no built-in). One fixed
reply for all; the reason goes to the log and the results
(`stopped_by`, plus `tokens` per question).
**Why:** a loop the model controls can fail to stop: one stuck
question could use the whole Gemini minute for everyone (OWASP LLM10).
**Checked:** a fake model that never stops trips each brake (5 calls;
8 tools run, 7 refused; 90 s; tokens); a normal answer passes. Full
run **15 / 38**, no verdict changed, nothing stopped: at most 2 model
calls, 19 s, 1,008 tokens.
**Next time:** measure use first, then set each budget with headroom.
**Later:** a graph (code owns the order) → walks 9–10, leave booking;
loop fingerprint, parallel workers, helpers, supervisor, swarm, A2A,
plan-and-execute, to-dos → the year-end review.
**Terms:** agent loop (ReAct) · orchestration · budgets / guardrails on
the loop (max turns) · unbounded consumption (OWASP LLM10, denial of
wallet) · graceful degradation · fake model (test double).
