"""Our HR tools as an MCP server (stage J): any app that speaks MCP
(Claude Code, Claude Desktop, Cursor, another agent) can use them.

In:  AMS_EMPLOYEE_ID, set when the app starts the server: who is
     asking (like the app's sign-in), e.g. AMS-1015; then the app's
     tool calls, over stdin/stdout.
Out: what our agent's tools return, as JSON text.

Strategy: our agent's read tools (RECORD_TOOLS and search_policies),
published as they are: the app sees each one's name, description and
inputs (its LangChain schema, without `runtime`). A call runs the tool
with a runtime holding HRContext(AMS_EMPLOYEE_ID), as our agent does,
so the same permission checks apply. The person never comes from a
tool input, so the app's model can't switch person. The server's
instructions carry what our agent's start with: who is signed in,
their key facts, the data's today, and "name the handbook section".

Caveats:
- Read tools only: booking and approvals ask "Confirm?" with
  LangGraph's interrupt(), which only our agent can carry on.
- The app's own model writes the answers, so they read differently
  from our app's; tool results go to that model's provider.
- Local only (stdio): one person per server process. A shared server
  (HTTP) would need a login to know who is asking (stage K).

Usage (normally started by the app, from its MCP settings):
    AMS_EMPLOYEE_ID=AMS-1015 uv run python mcp_server.py
"""

import json
import logging
import os
import sys

import anyio
import mcp_types as types
from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError

from ams_assistant.agent import RECORD_TOOLS, about, long_date
from ams_assistant.config import TODAY
from ams_assistant.hr_tools import HRContext, get_employee_card
from ams_assistant.policy_tools import search_policies

logger = logging.getLogger(__name__)

# What the app may call: our agent's read tools.
TOOLS = {tool.name: tool for tool in [*RECORD_TOOLS, search_policies]}
# Hints for the app: they only read, and only our own data.
READ_ONLY = types.ToolAnnotations(read_only_hint=True,
                                  open_world_hint=False)

INSTRUCTIONS = (
    "These tools read the AMS HR records of {name}, who is signed in, "
    "and the company handbooks. About {name}:\n{about}\n\n"
    "Today, in this HR data, is {today}. For their own records, leave "
    "out `employee`. When you use a handbook rule, name its handbook "
    "and section."
)
# Any unexpected failure: never a stack trace or SQL (as tool_failed()
# in middleware.py); the details go to the log (stderr).
CANT_RUN = ("Error: {name} couldn't run (a system problem, not the "
            "question). Tell them you couldn't check this right now.")


def describe(tool: BaseTool) -> types.Tool:
    """How the app sees one of our tools: what the model sees in our
    agent (name, description, inputs), never `runtime`."""
    return types.Tool(
        name=tool.name,
        description=tool.description,
        input_schema=tool.tool_call_schema.model_json_schema(),
        annotations=READ_ONLY,
    )


def reply(text: str, error: bool = False) -> types.CallToolResult:
    """A tool's result as the app gets it: one text part."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        is_error=error)


def run_tool(tool: BaseTool, arguments: dict,
             employee_id: str) -> types.CallToolResult:
    """Run one of our tools for `employee_id`, as our agent does."""
    runtime = ToolRuntime(state={}, context=HRContext(employee_id),
                          config={}, stream_writer=lambda _: None,
                          tool_call_id=None, store=None, tools=[])
    try:
        # Ours last: a "runtime" sent by the app can't replace it.
        output = tool.invoke({**arguments, "runtime": runtime})
    except ValidationError as error:  # a bad input: the model can fix it
        return reply(str(error), error=True)
    except Exception:
        logger.exception("Tool %s failed", tool.name)
        return reply(CANT_RUN.format(name=tool.name), error=True)
    if isinstance(output, str):
        return reply(output)
    return reply(json.dumps(output, ensure_ascii=False))


def build_server(employee_id: str) -> Server:
    """The MCP server, signed in as `employee_id` (ValueError if no
    such employee)."""
    card = get_employee_card(employee_id)
    if card is None:
        raise ValueError(f"No employee with ID {employee_id!r}")
    listed = types.ListToolsResult(
        tools=[describe(tool) for tool in TOOLS.values()])

    async def list_tools(ctx: ServerRequestContext,
                         params: types.PaginatedRequestParams | None,
                         ) -> types.ListToolsResult:
        return listed

    async def call_tool(ctx: ServerRequestContext,
                        params: types.CallToolRequestParams,
                        ) -> types.CallToolResult:
        tool = TOOLS.get(params.name)
        if tool is None:
            return reply(f"Unknown tool: {params.name}", error=True)
        # Our tools are plain (blocking) code: a worker thread runs it,
        # so the server keeps answering meanwhile.
        return await anyio.to_thread.run_sync(
            run_tool, tool, params.arguments or {}, employee_id)

    return Server(
        "ams-hr",
        version="0.1.0",
        instructions=INSTRUCTIONS.format(name=card["name"],
                                         about=about(card),
                                         today=long_date(TODAY)),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve(server: Server) -> None:
    """Answer the app over stdin/stdout until it disconnects."""
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    # The log goes to stderr: stdout carries the MCP messages.
    logging.basicConfig(level=logging.WARNING)
    employee_id = os.environ.get("AMS_EMPLOYEE_ID", "").strip().upper()
    try:
        server = build_server(employee_id)
    except ValueError as error:
        sys.exit(f"{error}. Set AMS_EMPLOYEE_ID to who is asking, "
                 "e.g. AMS-1015.")
    anyio.run(serve, server)


if __name__ == "__main__":
    main()
