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

## 2. Walk 1: the walking skeleton

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
