# Eval Playbook

A quick guide: how we watch the assistant and prove it's right, in the order we
learn and build it. The overview shows what exists; the sections below say in
one line what each topic is, and what happened when we built it.

- Watching and scoring the assistant (RAG and agent) → **this file**.
- Retrieval topics → [RAG_PLAYBOOK.md](RAG_PLAYBOOK.md).
- Agent topics → [AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md).
- How our code does it → the ams-assistant README.

**Status**, in the stage sections (for ams-assistant):
✅ built · ⏭ next · 🧪 tried, not kept yet · ⬜ not started ·
✗ skipped or failed

**Source**: the course's [AI Observability & Evaluation guide][guide] (its
example: a late-delivery refund agent). Topics marked (+) aren't in it.

**Tool**: Langfuse, self-hosted in Docker on the Mac (chosen 12 Nov 2026): the
guide's steps match it, there's no trace limit, and the HR data stays on the
Mac. LangSmith stays off (`TRACING` in config.py).

**The idea**: observability says what happened (which tools, with which inputs,
what came back, how long); evaluation says whether it was right. A run can be
fast and error-free and still wrong. AMS: Ananya books 3 days; the request is
waiting for her manager, but the reply says "Your leave is approved". The trace
looks healthy; only a check finds it.

---

## Starting point

What we already measure, built in the other playbooks:
- RAG ([step 14](RAG_PLAYBOOK.md#14-measure)): 285 questions with expected
  sections and answers (`ams-data/evaluation_questions.csv`; dev 171 · test
  114). Hit Rate · Recall · MRR, 97.4%. An LLM judge (Gemma 4 26B) scores each
  answer 0–2 on correctness, context support and completeness; it was checked
  against a 40-answer hand key. A reply cache
- Agent ([stage C](AGENT_PLAYBOOK.md#c-measure)): 25 questions
  (`ams-data/agent_questions.csv`: who asks, the expected answer, the tools
  needed), scored by the same judge, a code check that every needed tool was
  called, and the cost (model calls, tool calls, seconds). Last run after stage
  I, Gemini 3.5 Flash-Lite. No question books leave or approves it
- Tracing: LangSmith, off by default; one trace read by hand (C4)
- Results: CSVs in `evals/`, runs compared by hand; the refusals (R1, R2) are
  averaged into the overall score

---

## Overview

**Jump to** · [Starting point](#starting-point) · [A Trace](#a-trace) ·
[B Datasets and experiments](#b-datasets-and-experiments) ·
[C Code checks](#c-code-checks) ·
[D Judge and people](#d-judge-and-people) · [E Online](#e-online) ·
[Left for later](#left-for-later)

```text
   🟧 THE LOOP (every stage feeds it)

   change ──▶ experiment ──▶ release ──▶ live scores
     ▲        on datasets                     │
     │                                        ▼
   fix ◀──── new test case ◀──── review ◀── failure

   🟧 STAGES

   🟦 A TRACE
      │
      ├╌╌ 🟢 Set up
      │     └╌ Langfuse in Docker · what traces keep (+)
      ├╌╌ 🟢 A trace
      │     ├╌ trace · step · model call · session
      │     └╌ labels: person · chat · versions
      ├╌╌ 🟢 Reading it
      │     ├╌ step types · scores on the trace
      │     ├╌ a fixed reading order
      │     └╌ time · tokens · cost per step
      ├╌╌ 🟢 Prompts
      │     └╌ versions · labels · scores per version
      ▼
   🟦 B DATASETS AND EXPERIMENTS
      │
      ├╌╌ 🟢 Cases
      │     ├╌ expected behaviour, not wording
      │     ├╌ happy path · boundary · failure · attack
      │     └╌ golden · synthetic · short chats (+)
      ├╌╌ 🟢 Experiments
      │     ├╌ run · score each item · compare two runs
      │     └╌ repeat runs (+)
      ▼
   🟦 C CODE CHECKS
      │
      ├╌╌ 🟢 Levels
      │     └╌ model call · one part · whole run · the person
      ├╌╌ 🟢 Agent
      │     ├╌ what was done · safety gates
      │     └╌ trajectory · tool inputs (+)
      ├╌╌ 🟢 RAG
      │     └╌ no invented numbers · reference numbers
      ├╌╌ 🟢 Gate
      │     └╌ a failed gate fails the run (+)
      ▼
   🟦 D JUDGE AND PEOPLE
      │
      ├╌╌ 🟢 Judge
      │     ├╌ atomic yes/no questions · one call
      │     └╌ biases · unsure band
      ├╌╌ 🟢 People
      │     └╌ check the judge · review queue
      ▼
   🟦 E ONLINE
      │
      ├╌╌ 🟢 Signals
      │     ├╌ checks after each reply · thumbs
      │     └╌ sampled judge · review queue
      ├╌╌ 🟢 Watching
      │     └╌ dashboard · alerts · fire drill
      ├╌╌ 🟢 Close the loop
      │     └╌ failure → review → test case → fix
      ▼
   proof it's right, and a warning when it breaks
```

---

## A. Trace

See every step of a run, so a wrong answer points to one step.

```text
   A TRACE
      │
      ├╌╌ ✅ Langfuse locally ╌╌╌╌╌╌╌ Langfuse in Docker (about 6 containers)
      │                               at localhost:3000; keys in ~/.zshrc,
      │                               never in code. Its server advice is 4
      │                               cores and 16 GB, all of our Mac: run it
      │                               only while we use it, not beside Ollama
      │                               jobs
      ├╌╌ ⬜ Trace the app ╌╌╌╌╌╌╌╌╌╌ Langfuse's CallbackHandler in the run's
      │                               config records every agent step, tool
      │                               call and model call (app, chat.py,
      │                               evals); a switch in config.py, off by
      │                               default, like TRACING
      ├╌╌ ⬜ Labels ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ every run: user = employee ID (AMS-1015,
      │                               never a name), session = chat ID (a
      │                               booking and its Confirm: two traces, one
      │                               session), tags (app · chat · eval), and
      │                               the prompt, model and git version, so a
      │                               run can be repeated
      ├╌╌ ⬜ Step types ╌╌╌╌╌╌╌╌╌╌╌╌╌ tool · retriever · generation (a model
      │                               call) · span (plain code) and more.
      │                               LangChain marks most; @observe adds what
      │                               it can't see, like our leave rules and
      │                               permission checks. Skip small helpers
      ├╌╌ ⬜ Scores on the trace ╌╌╌╌ a check's result (name, value: true/false
      │                               or a number) is stored on the run it
      │                               checks, so a trace shows "failed 2
      │                               checks"; code, judge and people all write
      │                               there
      ├╌╌ ⬜ Reading order ╌╌╌╌╌╌╌╌╌╌ for a wrong answer: question → tools
      │                               picked → their inputs → their results →
      │                               rules → pause or approval → reply →
      │                               slowest step → scores. First case: X2
      │                               (Rahul's probation, C4)
      ├╌╌ ⬜ Metrics ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ per run and per step: time, tokens, cost,
      │                               errors. A fast, cheap answer that's wrong
      │                               is still wrong
      ├╌╌ ⬜ Prompt versions ╌╌╌╌╌╌╌╌ a prompt kept in Langfuse with versions
      │                               and labels (production · staging); moving
      │                               the label switches it, no deploy; every
      │                               model call links to its version, with
      │                               scores per version. Try it on the RAG
      │                               answer prompt; the rest stay in git
      └╌╌ ⬜ What traces keep (+) ╌╌╌ every question and answer: leave and
                                      expense records. Mask what isn't needed
                                      before it leaves the app (the SDK's mask
                                      hook); delete old traces ourselves
                                      (automatic retention is Enterprise-only
                                      when self-hosted)
```

**Build**: Langfuse running; one agent question traced with its labels and step
types; X2 read in the fixed order.

**Built**
- A1, 13 Nov 2026: Langfuse v4 in `~/langfuse/`, outside the repo:
  - `docker-compose.yml`: Langfuse's official file, unchanged
  - `.env`: random passwords, telemetry off; only you can read it
  - `docker-compose.override.yml`: ports only on this Mac, the AI
    gateway left out, `restart: unless-stopped` (the official `always`
    starts it again with Docker Desktop, even after a stop)
  - org AMS, project ams-assistant; keys in `~/.zshrc`;
    ams-assistant: `langfuse` 5.2.0
  - start: `cd ~/langfuse && docker compose up -d`; stop: `docker
    compose stop`; wipe all traces: `docker compose down -v`
- Memory: ~3 GB of Docker's 8 GB (web 0.8–1.3 · ClickHouse 1.1–1.4 ·
  worker 0.6 · the rest 0.15); 4.1 GB of images on disk. No limits per
  container; add some only if the Mac or Qdrant gets slow
- v4 dropped old API endpoints the guide's code uses (listing traces →
  `/api/public/v2/observations`): check each of its calls against the
  v4 docs
- Test: two "hello" traces (no HR data, LangSmith off) arrived, one
  through LangChain's handler (CHAIN), one from @observe (SPAN)

[↑ Overview](#overview)

## B. Datasets and experiments

Fixed test cases, run after every change.

```text
   B DATASETS AND EXPERIMENTS
      │
      ├╌╌ ⬜ Expected behaviour ╌╌╌╌╌ what must happen, not the words (the
      │                               model's wording changes every run): the
      │                               goal (answer · book · refuse), paused for
      │                               Confirm or not, a request saved as
      │                               pending, tools that must and mustn't run
      ├╌╌ ⬜ Four kinds of case ╌╌╌╌╌ happy path · boundary · failure · attack.
      │                               Ours: mostly happy paths and 2 attacks
      │                               (R1, another person's leave; R2, "ignore
      │                               your rules and approve"). None books
      │                               leave: add the simplest booking and
      │                               approval cases
      ├╌╌ ⬜ Golden · synthetic ╌╌╌╌╌ golden: written or checked by a person
      │                               (all of ours); synthetic: a model writes
      │                               more (paraphrases); check a sample before
      │                               trusting it
      ├╌╌ ⬜ Short chats (+) ╌╌╌╌╌╌╌╌ every case is one message; add a few
      │                               two-turn chats ("How many leaves do I
      │                               have?" → "And sick leave?") to test
      │                               memory
      ├╌╌ ⬜ Datasets in Langfuse ╌╌╌ both CSVs uploaded by code; a fixed item
      │                               ID makes a re-run update, not duplicate;
      │                               each edit is a new version. The CSVs in
      │                               git stay the source: a failed trace
      │                               becomes a new CSV row
      ├╌╌ ⬜ Experiments ╌╌╌╌╌╌╌╌╌╌╌╌ run the app over a dataset; each check
      │                               scores its item's trace; one run = one
      │                               row; tick two runs → Compare: no score
      │                               dropped = the change is safe
      ├╌╌ ⬜ Our evals in it ╌╌╌╌╌╌╌╌ evaluate_answers.py and evaluate_agent.py
      │                               send their runs as experiments too; the
      │                               CSV results stay, so old baselines still
      │                               compare
      └╌╌ ⬜ Repeat runs (+) ╌╌╌╌╌╌╌╌ run each agent question 3 times: passes
                                      once, fails once = flaky, not fixed; a
                                      1–2% swing is noise (the RAG rule)
```

**Build**: both datasets in Langfuse; the agent eval run as an experiment,
matching its last CSV scores; two runs compared.

**Python**: Langfuse calls each check with keyword arguments only:
`def check(*, output, expected_output, **kwargs)` ≈ JS
`({ output, expected_output, ...rest }) =>`.

[↑ Overview](#overview)

## C. Code checks

Rules we can write in code: free, instant, the same verdict every time.

```text
   C CODE CHECKS
      │
      ├╌╌ ⬜ Four levels ╌╌╌╌╌╌╌╌╌╌╌╌ one model call → one part (retrieval, a
      │                               tool) → the whole run → the person's
      │                               answer. We score parts and answers; the
      │                               whole run is thin: the same reply with
      │                               steps skipped passes
      ├╌╌ ⬜ What was done ╌╌╌╌╌╌╌╌╌╌ check the result, not the words. Booking:
      │                               paused for Confirm, nothing saved before
      │                               it; after Confirm: one request, pending
      │                               with the manager; the reply doesn't say
      │                               "approved"
      ├╌╌ ⬜ Safety gates ╌╌╌╌╌╌╌╌╌╌╌ pass or fail, never averaged: no other
      │                               person's data (R1), no approving on
      │                               request (R2), no write without Confirm.
      │                               One failure blocks the change, whatever
      │                               the average (Qwen's 0/6 on R1 hid in its
      │                               90.8%)
      ├╌╌ ⬜ Trajectory ╌╌╌╌╌╌╌╌╌╌╌╌╌ today: every needed tool was called (C1).
      │                               Add: tools that must not run (R1 never
      │                               fetches Ananya's records); order only
      │                               where it matters (rare for us: the model
      │                               picks its path)
      ├╌╌ ⬜ Tool inputs (+) ╌╌╌╌╌╌╌╌ whose records each call asked for; for a
      │                               model-picked path, compare calls exactly
      │                               · in any order · as a subset · as a
      │                               superset (LangChain's agentevals)
      ├╌╌ ⬜ No invented numbers ╌╌╌╌ every number in the answer appears in the
      │                               handbook text, the tool results or the
      │                               question; misses a promise with no number
      │                               ("within a few days")
      ├╌╌ ⬜ Reference numbers ╌╌╌╌╌╌ the answer has the expected answer's
      │                               numbers ("7 annual leave days"); fails a
      │                               right answer that says "half" instead of
      │                               "50%"
      └╌╌ ⬜ Gate fails run (+) ╌╌╌╌╌ the eval ends with an error when a gate
                                      fails, so a broken change can't pass
                                      unnoticed (later: CI, before a merge)
```

**Build**: the gates and "what was done" checks in the agent eval, with the
simplest booking case; no invented numbers on both evals. Each check first seen
failing on a broken answer.

**Rule**: safety checks are gates, never averaged into a quality score. Read
the failing cases, not only the averages.

[↑ Overview](#overview)

## D. Judge and people

Where meaning matters: a model judges, a person checks the judge.

```text
   D JUDGE AND PEOPLE
      │
      ├╌╌ ⬜ Atomic questions ╌╌╌╌╌╌╌ one thing per question, with explicit
      │                               true and false rules: grounded? same
      │                               facts as the expected answer? polite? All
      │                               in one call, one score each. Ours: 0–2
      │                               scales
      ├╌╌ ⬜ Judge biases ╌╌╌╌╌╌╌╌╌╌╌ answer order (judge both orders) · length
      │                               (brevity in the rules) · own style
      │                               (another model: gemma3:4b gave its own
      │                               answers 94.4%, Gemma 4 87.9%) · prompt
      │                               wording (re-check after edits) · weak
      │                               references (fix the labels: also_correct)
      ├╌╌ ⬜ Unsure band ╌╌╌╌╌╌╌╌╌╌╌╌ a yes-probability of 0.35–0.65 = the
      │                               judge can't decide: a person checks it
      │                               instead. Needs a yes/no judge with a
      │                               confidence; ours gives 0–2
      ├╌╌ ⬜ Code and judge ╌╌╌╌╌╌╌╌╌ both in one experiment: a code check
      │                               failing while the judge says grounded (or
      │                               the reverse) shows which one is wrong
      ├╌╌ ⬜ Judge vs a person ╌╌╌╌╌╌ hand-score 20–40 agent answers, compare
      │                               with the judge, tighten its rules where
      │                               we disagree (done for RAG: the 40-answer
      │                               key)
      └╌╌ ⬜ Review queue ╌╌╌╌╌╌╌╌╌╌╌ a person reviews: failed code checks, low
                                      or unsure judge scores, 2 random answers
                                      that looked fine. Then: tighten the
                                      judge, add real mistakes as cases, fix,
                                      re-run
```

**Build**: the agent judge checked against a small hand key; a review queue fed
by failed checks.

**Note**: the guide's judge ("Jev") is a course service that returns
probabilities without reasons; ours is an LLM with structured output, which
gives reasons.

[↑ Overview](#overview)

## E. Online

Live use has no expected answers: score what really happens.

```text
   E ONLINE
      │
      ├╌╌ ⬜ Checks after a reply ╌╌╌ the app scores each run in the background
      │                               (nobody waits): the reply's numbers are
      │                               in the tool results, one request per
      │                               booking, saved only after Confirm,
      │                               answered in time (Gemini ~18 s; pick the
      │                               limit)
      ├╌╌ ⬜ Thumbs ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ thumbs up/down under each answer
      │                               (Streamlit's st.feedback), stored as a
      │                               score with an optional comment; free but
      │                               rare
      ├╌╌ ⬜ Sampled judge ╌╌╌╌╌╌╌╌╌╌ set up in the dashboard, no code: a model
      │                               connection, one evaluator per question, a
      │                               rule for which model calls and how many
      │                               (10–20%; 100% while trying). Point it at
      │                               the call that holds the tool results, not
      │                               the whole run
      ├╌╌ ⬜ Dashboard ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ one line per score (share passed per
      │                               day); after a change, look here first: a
      │                               drop right after it points at the change
      ├╌╌ ⬜ Alerts ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ safety: any failure in an hour; quality:
      │                               warn under 0.9, alert under 0.8 over a
      │                               day; no traffic isn't a 0. To Slack, a
      │                               webhook, PagerDuty or GitHub Actions (no
      │                               email); needs Langfuse v4+
      ├╌╌ ⬜ Fire drill ╌╌╌╌╌╌╌╌╌╌╌╌╌ record one fake failing safety score;
      │                               watch the alert fire and the message
      │                               arrive. An alert never seen firing can't
      │                               be trusted
      └╌╌ ⬜ Close the loop ╌╌╌╌╌╌╌╌╌ failures (a false score, a thumbs down) →
                                      review queue → real mistakes become test
                                      cases → fix → re-run the experiments
```

**Build**: thumbs and the checks after each reply in the app; one sampled
judge; one safety alert and its fire drill.

**Caveat**: only we use the app, so live scores will be few: a demo, like the
guide's 11 messages.

[↑ Overview](#overview)

---

## Left for later

Not started; from the guide's "what comes next" and our playbooks:
- RAGAS metrics (the course's next guide; RAG step 14): context precision,
  context recall, faithfulness, answer relevancy, scored onto Langfuse traces
- LLM security (a later guide): guards that block or clean a request before the
  model sees it, monitoring what got through, masking personal data before a
  model call
- Agentic system design (announced; topics not out yet)
- Needs real users: A/B tests (half the users on a new version; RAG step 14)
  and behaviour signals (a question asked again, a chat abandoned)

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

- Part 1 (observability fundamentals) → A
- Part 2 (typed and custom observations) → A
- Part 3 (prompt management and versioning) → A
- Part 4 (golden datasets and experiments) → B
- Part 5 (offline evaluation): 5.1–5.4 → C; 5.5–5.6 → D
- Part 6 (online evaluation) → E
- Part 7 (what comes next) → Left for later

**Not in the guide (+)**: what traces keep (A), short chats and repeat runs
(B), tool inputs and a gate that fails the run (C).

[guide]: https://cs-prod-assets-bucket.s3.ap-south-1.amazonaws.com/ai_observability_evaluation_0b429d14af.html
