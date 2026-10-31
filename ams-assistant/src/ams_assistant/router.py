"""Query routing: pick the policy files a question is about, so the
search only looks inside them.

In:  {"question": "How much PTO do Austin employees get?"}
Out: build_router().invoke(...) -> a Route, e.g. reason="Austin is a US
     office", files=["leave_policy_us.txt"]; route_filter(route) -> a
     Qdrant filter for those files, or None (search everything).

Strategy: the LLM sees a one-line description of each file (written
from the file's own section headings) and picks one or two, or "all"
when unsure. "all" is the safety valve: a wrong filter hides the right
chunk completely, so an unsure router should not filter at all. The
reason comes first so the model thinks before it picks.

Caveats:
- One extra LLM call per question; gemma3:4b can still pick the wrong
  file. An experiment for now; not in chain.py.
- POLICY_FILES must match the file names in ams-data/policies; a new
  file needs a new description here.
- Filters per file, so it can't help when the right file ranks the
  wrong section first.
"""

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel
from qdrant_client import models

from ams_assistant.config import LLM_MODEL, TEMPERATURE


# What each file covers, taken from its section headings.
POLICY_FILES = {
    "benefits_policy.txt": (
        "health and insurance benefits (India and US), learning and "
        "development budget, wellness, connectivity allowance, "
        "retirement benefits, employee referral bonus"
    ),
    "code_of_conduct.txt": (
        "core principles, conflicts of interest, gifts and hospitality, "
        "respectful workplace and anti-harassment, speaking up, "
        "information and data protection, company assets and public "
        "statements, consequences of breaches"
    ),
    "company_overview.txt": (
        "about AMS, offices and payroll, base location, job grades, "
        "departments, systems employees use, working hours, key "
        "contacts, policy library"
    ),
    "holiday_calendar_2026.txt": (
        "2026 public holidays for the Bengaluru, Pune and Austin "
        "offices, restricted holidays (India offices), employees "
        "working away from their base office"
    ),
    "hr_faq.txt": (
        "short answers on leave and time off, pay and payslips, office "
        "and facilities, IT and access, career and learning, getting "
        "help"
    ),
    "leave_policy_india.txt": (
        "leave for the India payroll: annual leave and carry-over, "
        "sick leave, casual leave, parental leave, requests and "
        "approvals, leave balances"
    ),
    "leave_policy_us.txt": (
        "leave for the US payroll: paid time off (PTO), carry-over and "
        "payout, sick leave, floating holidays, parental leave, "
        "bereavement leave, jury duty"
    ),
    "onboarding_exit_policy.txt": (
        "before joining, first weeks, probation, resignation and notice "
        "periods, exit process, final settlement, letters after "
        "leaving, rehiring"
    ),
    "remote_hybrid_work_policy.txt": (
        "hybrid working model, working from another city or from "
        "abroad, fully remote arrangements, equipment and allowances, "
        "security when working remotely, remote work and leave"
    ),
    "travel_expense_policy.txt": (
        "travel approval, travel class, accommodation, daily allowance, "
        "local travel, expense claims, non-reimbursable expenses, "
        "client entertainment, corporate cards"
    ),
}


ROUTE_PROMPT = ChatPromptTemplate.from_template("""\
You route questions about AMS company policies to the policy files
most likely to contain the answer.

AMS offices: Bengaluru and Pune are in India (India payroll); Austin is
in the United States (US payroll).

Policy files:
{files}

Rules:
- Pick the one file most likely to contain the answer. Pick two only
  if the question clearly needs both.
- If the question names an office or a country, never pick a file
  that only covers the other country.
- If you are not sure, or three or more files could answer it, pick
  "all".
- Give a short reason first, then the files.

Question: {question}
""").partial(
    files="\n".join(
        f"- {name}: {about}" for name, about in POLICY_FILES.items()
    )
)


class Route(BaseModel):
    """The router's choice. Literal limits files to the real names
    (plus "all"), so the model can't invent one."""

    reason: str
    files: list[Literal[*POLICY_FILES, "all"]]


def build_router():
    """Return the chain: {"question"} -> Route."""
    llm = ChatOllama(model=LLM_MODEL, temperature=TEMPERATURE)
    return ROUTE_PROMPT | llm.with_structured_output(Route)


def route_filter(route: Route) -> models.Filter | None:
    """Turn a Route into a Qdrant filter on the chunks' source file, or
    None (no filter) when the router said "all" or picked nothing."""
    if not route.files or "all" in route.files:
        return None

    # LangChain stores Document metadata under "metadata" in the
    # payload; MatchAny = the source is any of these files.
    return models.Filter(must=[
        models.FieldCondition(
            key="metadata.source",
            match=models.MatchAny(any=route.files),
        )
    ])
