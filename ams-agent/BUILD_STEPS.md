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
