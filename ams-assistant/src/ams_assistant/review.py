"""The review queue in Langfuse: replies a person should check
(EVAL_PLAYBOOK.md, D6 and E7).

In:  a Langfuse client and trace IDs: from the agent eval (every
     question that didn't pass, and a few that did) or the app (a reply
     whose checks failed, or a thumbs down).
Out: add_to_review(client, trace_ids) -> the queue's page in Langfuse
     ("" if there was nothing to add).

Strategy: one Langfuse annotation queue, REVIEW_QUEUE, made on first
use with the person's marks (REVIEW_SCORES): is the reply right, and
what's wrong in their own words ("open coding": notes first, grouped
into kinds of failure later). A person opens it, marks each reply and
clicks Complete.

Caveats:
- Langfuse's API can't edit a queue, so its description stays as it was
  made (edit it in Langfuse's settings).
- Raises httpx.HTTPError or ApiError when Langfuse fails: the caller
  decides whether that matters.
"""

from langfuse import Langfuse
from langfuse.api import (
    AnnotationQueueObjectType,
    ConfigCategory,
    ScoreConfigDataType,
)

REVIEW_QUEUE = "agent review"
REVIEW_SCORES = {
    "pass or fail": {
        "data_type": ScoreConfigDataType.CATEGORICAL,
        "categories": [ConfigCategory(label="Pass", value=1),
                       ConfigCategory(label="Fail", value=0)]},
    "open coding": {"data_type": ScoreConfigDataType.TEXT},
}


def review_queue(client: Langfuse) -> str:
    """The review queue's ID, made on first use with its score
    configs (those too, if missing)."""
    api = client.api
    configs = {c.name: c.id for c in api.score_configs.get(limit=100).data
               if not c.is_archived}
    for name, settings in REVIEW_SCORES.items():
        if name not in configs:
            configs[name] = api.score_configs.create(name=name,
                                                     **settings).id
    queue = next((q for q in api.annotation_queues.list_queues(
        limit=100).data if q.name == REVIEW_QUEUE), None)
    if queue is None:
        queue = api.annotation_queues.create_queue(
            name=REVIEW_QUEUE,
            description="Replies for a person to check: from the agent "
                        "eval, each that didn't pass and a few that did; "
                        "from the app, each whose checks failed or got a "
                        "thumbs down. Pass or fail: is the reply right? "
                        "Open coding: what's wrong, in your words.",
            score_config_ids=[configs[name] for name in REVIEW_SCORES])
    return queue.id


def add_to_review(client: Langfuse, trace_ids: list[str]) -> str:
    """Add these traces to the review queue; return its page (found
    from one of the traces' pages), or "" if there were none."""
    if not trace_ids:
        return ""
    queue_id = review_queue(client)
    for trace_id in trace_ids:
        client.api.annotation_queues.create_queue_item(
            queue_id, object_id=trace_id,
            object_type=AnnotationQueueObjectType.TRACE)
    project = client.get_trace_url(trace_id=trace_ids[0]).rsplit(
        "/traces/", 1)[0]
    return f"{project}/annotation-queues/{queue_id}"
