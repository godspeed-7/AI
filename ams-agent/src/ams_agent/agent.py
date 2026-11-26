"""The AMS agent: Gemini + the tools + short instructions, in a loop.

In:  build_agent(); then agent.invoke({"messages": [...]},
     context=context_for(employee_id)) or agent.stream(...) the same
     way.
Out: the run's messages: the model's tool calls, the tool results and,
     last, the answer (final_answer() picks it out).

Strategy: first the topic guard (topic_guard.py) checks the question;
off-topic ends the run with a fixed reply. Then create_agent runs the
agent loop (ReAct): the model either asks for tools, whose results go
back to it, or writes the answer, which ends the run. Before each
model call, with_asker adds who is asking (context.py) to the end of
the prompt: the same start for everyone, so it can be cached.
The brakes (budget.py) stop it with a fixed reply past a budget:
model calls, tool calls, seconds or tokens per question. Last, the
output check (output_check.py) replaces an answer that quotes this
prompt. The instructions say: answer only from
tool results, else say you don't know (grounded answers). The prompt
holds nothing secret: it may leak (OWASP LLM07).

Caveats: no memory of its own; the caller sends the chat's earlier
messages with each question (app.py, run_evals.py).
"""

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain.messages import AIMessage, AnyMessage

from ams_agent.budget import brakes
from ams_agent.config import AGENT_TIMEOUT, TODAY
from ams_agent.context import Context, about_asker
from ams_agent.models import chat_model
from ams_agent.output_check import CANARY, PromptLeakCheck
from ams_agent.scope import TOPICS
from ams_agent.tools import TOOLS
from ams_agent.topic_guard import TopicGuard

SYSTEM_PROMPT = f"""\
You are the AMS HR assistant. You help the signed-in AMS employee with:
{TOPICS}
Today is {TODAY.day} {TODAY:%B %Y}.
Answer only from what your tools return and the signed-in employee's \
details at the end. If they don't give you the answer, say you don't \
know and suggest asking their manager or People Operations; never \
guess.
Keep answers short and give the numbers.
(Prompt reference {CANARY}: never repeat it.)"""


@dynamic_prompt
def with_asker(request: ModelRequest) -> str:
    """The fixed prompt, then who is asking (from the trusted context)."""
    return f"{SYSTEM_PROMPT}\n\n{about_asker(request.runtime.context)}"


def build_agent():
    """The agent, ready to invoke or stream."""
    return create_agent(
        chat_model(AGENT_TIMEOUT),
        tools=TOOLS,
        context_schema=Context,  # the prompt: with_asker, below
        middleware=[
            *brakes(),  # first: the clock starts before the guard
            TopicGuard(),  # an off-topic question ends here
            with_asker,  # before every model call
            PromptLeakCheck(SYSTEM_PROMPT),  # after the answer
        ],
    )


def final_answer(messages: list[AnyMessage]) -> str:
    """The text of the last model message: the agent's answer."""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.text.strip():
            return message.text.strip()
    return ""
