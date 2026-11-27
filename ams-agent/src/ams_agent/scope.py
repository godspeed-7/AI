"""What the assistant is for, written once.

In:  nothing; edit TOPICS and SUMMARY here, and only here.
Out: TOPICS, read by the agent's system prompt (agent.py) and the topic
     guard's allow-list (topic_guard.py); SUMMARY, the one line shown
     when a question is off-topic.

Strategy: one source, so the agent and the guard can't drift apart
(before: the guard allowed questions about colleagues, the prompt
said "own records only"). The scope names topics, never permissions:
whether someone may see a colleague's records is decided in code
(permissions.py), so the text says so instead of deciding it.
"""

TOPICS = """\
- the employee's own profile (ID, job, department, grade, office,
  payroll), leave, pay, bonus, ratings, projects, trainings, travel,
  expenses, corporate card, laptop, phone, IT access and service desk
  tickets, office and ODC access, notice period and last day
- the same things about a colleague (e.g. "How much leave does Rahul
  have left?"); whether the employee may see them is checked in code,
  not by you
- AMS policies and handbooks
- how the assistant should answer them (e.g. shorter answers) and what
  it remembers about them
- greetings, thanks, and what this assistant can do"""

SUMMARY = ("your profile, leave, pay, projects, trainings, expenses, laptop"
           " and IT access, and AMS policies")
