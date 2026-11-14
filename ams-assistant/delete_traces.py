"""Delete traces from Langfuse: the old ones, or one person's
(EVAL_PLAYBOOK.md, stage A).

In:  --older-than DAYS (default TRACE_KEEP_DAYS, config.py) or --user
     EMPLOYEE_ID; --yes to really delete. The LANGFUSE_* keys.
Out: how many traces match; with --yes, those traces deleted, with
     their steps and scores.

Strategy: self-hosted Langfuse deletes nothing by itself (automatic
retention is an Enterprise feature), so this script is our retention:
run it now and then to keep only the last TRACE_KEEP_DAYS. --user is
for a deletion request: every trace is labelled with the employee ID
(tracing.py), so all of theirs can be found. Without --yes it only
counts, so a typo deletes nothing.

Usage (from ams-assistant/):
    uv run python delete_traces.py                   # count old ones
    uv run python delete_traces.py --yes             # delete them
    uv run python delete_traces.py --user AMS-1015 --yes

Caveats:
- Langfuse deletes in the background: they may show for a minute.
- Only traces: a person's questions copied into a dataset (stage B)
  stay there.
"""

import argparse
from datetime import UTC, datetime, timedelta

import httpx
from langfuse.api.core import ApiError

from ams_assistant.config import TRACE_KEEP_DAYS
from ams_assistant.tracing import START_IT, langfuse_client

# The most steps Langfuse returns per page, and trace IDs per delete.
PAGE_SIZE = 1000
DELETE_BATCH = 100


def find_traces(user: str | None = None,
                before: datetime | None = None) -> list[str]:
    """IDs of the traces with a step by `user` or started before
    `before`, read page by page."""
    api = langfuse_client().api
    found, cursor = set(), None
    while True:
        page = api.observations.get_many(
            fields="core", limit=PAGE_SIZE, cursor=cursor, user_id=user,
            to_start_time=before)
        found.update(step.trace_id for step in page.data)
        cursor = page.meta.cursor
        if not cursor:
            return sorted(found)


def delete(trace_ids: list[str]) -> None:
    """Delete the traces, DELETE_BATCH per call."""
    api = langfuse_client().api
    for start in range(0, len(trace_ids), DELETE_BATCH):
        api.trace.delete_multiple(
            trace_ids=trace_ids[start:start + DELETE_BATCH])


def main():
    parser = argparse.ArgumentParser(
        description="Delete old traces, or one person's, from Langfuse.")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--older-than", type=int, metavar="DAYS",
                       default=TRACE_KEEP_DAYS,
                       help=f"traces older than DAYS (default "
                            f"{TRACE_KEEP_DAYS}, config.py)")
    which.add_argument("--user", metavar="EMPLOYEE_ID",
                       help="all traces of one employee, e.g. AMS-1015")
    parser.add_argument("--yes", action="store_true",
                        help="really delete (without it: only count)")
    args = parser.parse_args()

    try:
        if not langfuse_client().auth_check():
            raise SystemExit("Langfuse refused the keys (LANGFUSE_* in "
                             "~/.zshrc)")
        if args.user:
            what = f"of {args.user}"
            trace_ids = find_traces(user=args.user)
        else:
            cutoff = datetime.now(UTC) - timedelta(days=args.older_than)
            what = (f"older than {args.older_than} days (before "
                    f"{cutoff:%-d %B %Y %H:%M} UTC)")
            trace_ids = find_traces(before=cutoff)
        print(f"{len(trace_ids)} traces {what}")
        if not trace_ids:
            return
        if not args.yes:
            print("Nothing deleted: add --yes to delete them.")
            return
        delete(trace_ids)
    except httpx.HTTPError:  # not running: the connection fails
        raise SystemExit(f"Langfuse isn't answering; {START_IT}") from None
    except ApiError as error:  # e.g. 401: wrong keys
        raise SystemExit(f"Langfuse said no: {error.status_code} "
                         f"{error.body}") from None
    print(f"Deleted {len(trace_ids)} traces (Langfuse finishes in the "
          f"background).")


if __name__ == "__main__":
    main()
