"""The three tools, and nothing else.

read_logs   -- read-only, synthetic test logs.
read_errors -- read-only, synthetic stand-in for error reports. Not Sentry.
deploy      -- asks Mike, records the request and his answer, deploys NOTHING.

The read tools take no file paths from the caller: the files they read are
fixed here, and they are only ever opened with mode "r".
"""

import json
import os

LOG_FILE = "synthetic_logs.jsonl"
ERRORS_FILE = "synthetic_errors.json"

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")
ERROR_STATUSES = ("unresolved", "resolved")

TOOL_DEFINITIONS = [
    {
        "name": "read_logs",
        "description": "Read-only. Returns entries from the SYNTHETIC test logs. No real data. Cannot write anything.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": list(LEVELS)},
                "service": {"type": "string", "maxLength": 64},
                "contains": {"type": "string", "maxLength": 200},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "read_errors",
        "description": "Read-only. Returns issues from a SYNTHETIC stand-in for error reports. Does not connect to Sentry. Cannot write anything.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": list(ERROR_STATUSES)},
                "id": {"type": "string", "maxLength": 64},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "deploy",
        "description": (
            "Asks Mike for a yes or no and waits. No answer counts as no. "
            "In this build it deploys NOTHING: it only records the request and the answer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "minLength": 1, "maxLength": 100},
                "reason": {"type": "string", "minLength": 1, "maxLength": 500},
            },
            "required": ["target", "reason"],
            "additionalProperties": False,
        },
    },
]

TOOL_NAMES = tuple(t["name"] for t in TOOL_DEFINITIONS)


class BadArguments(ValueError):
    pass


def validate(tool_name, args):
    """Strict check against the tool's inputSchema. Unknown keys are refused."""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise BadArguments("arguments must be an object")
    schema = next(t["inputSchema"] for t in TOOL_DEFINITIONS if t["name"] == tool_name)
    props = schema["properties"]
    for key in args:
        if key not in props:
            raise BadArguments(f"unknown argument: {key}")
    for key in schema.get("required", []):
        if key not in args:
            raise BadArguments(f"missing required argument: {key}")
    for key, value in args.items():
        rule = props[key]
        if rule["type"] == "string":
            if not isinstance(value, str):
                raise BadArguments(f"{key} must be a string")
            if len(value) > rule.get("maxLength", 10_000) or len(value) < rule.get("minLength", 0):
                raise BadArguments(f"{key} has the wrong length")
            if "enum" in rule and value not in rule["enum"]:
                raise BadArguments(f"{key} must be one of {rule['enum']}")
        elif rule["type"] == "integer":
            # bool is a subclass of int in Python; refuse it explicitly.
            if not isinstance(value, int) or isinstance(value, bool):
                raise BadArguments(f"{key} must be an integer")
            if not rule["minimum"] <= value <= rule["maximum"]:
                raise BadArguments(f"{key} must be between {rule['minimum']} and {rule['maximum']}")
    return args


def read_logs(data_dir, args):
    level = args.get("level")
    service = args.get("service")
    contains = (args.get("contains") or "").lower()
    limit = args.get("limit", 50)
    out = []
    with open(os.path.join(data_dir, LOG_FILE), "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if level and entry.get("level") != level:
                continue
            if service and entry.get("service") != service:
                continue
            if contains and contains not in entry.get("message", "").lower():
                continue
            out.append(entry)
            if len(out) >= limit:
                break
    return {"source": "synthetic test logs", "count": len(out), "entries": out}


def read_errors(data_dir, args):
    status = args.get("status")
    wanted_id = args.get("id")
    limit = args.get("limit", 50)
    with open(os.path.join(data_dir, ERRORS_FILE), "r", encoding="utf-8") as f:
        issues = json.load(f)["issues"]
    out = [
        i for i in issues
        if (not status or i.get("status") == status) and (not wanted_id or i.get("id") == wanted_id)
    ][:limit]
    return {"source": "synthetic stand-in for error reports (not Sentry)", "count": len(out), "issues": out}


def decide(elicit_result):
    """Turn the client's answer into "yes" or "no".

    ONLY an explicit yes counts: action "accept" AND decision exactly "yes".
    Decline, cancel, a missing or malformed answer, an error, or a timeout
    (passed in as None) are all "no". Silence is never approval.
    """
    if not isinstance(elicit_result, dict):
        return "no", "no answer (timeout, error, or no response)"
    action = elicit_result.get("action")
    if action != "accept":
        return "no", f"answer was '{action}', not an explicit yes"
    content = elicit_result.get("content")
    if not isinstance(content, dict) or content.get("decision") != "yes":
        return "no", "accepted without an explicit 'yes'"
    return "yes", "explicit yes"


ELICIT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "title": "Approve this deploy request?",
            "enum": ["yes", "no"],
        }
    },
    "required": ["decision"],
}
