"""Arbo MCP -- the tool server. Test setup only.

Speaks MCP (JSON-RPC 2.0, one message per line) over stdin/stdout.
Standard library only. No network code of any kind.

Exactly three tools (see tools.py). No resources, no prompts, no other
capabilities. Every message received is logged before it is acted on; if the
log cannot be written, the call is refused.

How deploy asks Mike: MCP "elicitation" -- the server sends the client an
`elicitation/create` request, and the client shows the question to the person
at the keyboard. Only an explicit "yes" counts.

NO TIME LIMIT (Mike, Sep 26, 2026: "There should be no time limits at all
when it comes to my decision"). The question waits for as long as Mike takes.
While it waits, nothing happens: silence is never approval, and silence
never turns into a decision. Other requests keep being answered meanwhile; only a
second deploy request waits its turn. Decline, cancel, an error, a client that
cannot ask, or a client that disconnects are all "no".

REMINDERS (Mike, Sep 28, 2026: yes to a reminder that decides nothing). While
the question waits, a "still waiting on you" reminder goes out every
--remind-every-minutes (default 60, Mike's to set). A reminder is logged and,
if the client gave a progress token, sent as an MCP progress notification.
It never decides, cancels, or ends the wait.
Whatever the answer, NOTHING is deployed in this build.
"""

import argparse
import json
import os
import queue
import sys
import threading
import time

from . import tools
from .calllog import CallLog

SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18")
DEFAULT_VERSION = "2025-06-18"
DEFAULT_REMIND_EVERY_S = 60 * 60.0  # Mike's to set; a reminder never decides anything
REMINDER_TEXT = "Still waiting on you. No time limit: nothing happens until you answer."

# Recorded on every deploy answer. The client prompt does not prove WHO answered.
IDENTITY_NOTE = "answered at the MCP client prompt; identity not verified (no two-step check in this build)"

_EOF = object()


class LogUnavailable(Exception):
    pass


class Server:
    def __init__(self, data_dir, log_path, write, remind_every_s=DEFAULT_REMIND_EVERY_S):
        if not remind_every_s > 0:
            raise ValueError("remind_every_s must be positive")
        self.data_dir = data_dir
        self.remind_every_s = remind_every_s
        self.log = CallLog(log_path)
        self.write = write  # function(dict) -> sends one message to the client
        self.inbox = queue.Queue()
        self.deferred = []
        self.client_can_ask = False
        self._elicit_counter = 0

    # --- logging -----------------------------------------------------------
    def _log(self, event, **fields):
        try:
            return self.log.append(event, **fields)
        except Exception as exc:  # any failure to log means the call must not run
            raise LogUnavailable(str(exc)) from exc

    # --- main loop ---------------------------------------------------------
    def run(self):
        while True:
            msg = self.deferred.pop(0) if self.deferred else self.inbox.get()
            if msg is _EOF:
                return
            self.handle(msg)

    def handle(self, msg):
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            self._safe_log("invalid_message")
            self._send({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}})
            return
        method = msg.get("method")
        msg_id = msg.get("id")
        if method is None:
            # A response we were not waiting for (e.g. a late elicitation answer).
            self._safe_log("unexpected_response", id=msg_id)
            return
        try:
            self._log("received", method=method, id=msg_id)
        except LogUnavailable as exc:
            if msg_id is not None:
                self._send({"jsonrpc": "2.0", "id": msg_id,
                            "error": {"code": -32000, "message": f"call refused: could not write the call log ({exc})"}})
            return
        if msg_id is None:
            return  # notifications (e.g. notifications/initialized) need no reply
        try:
            if method == "initialize":
                result = self._initialize(msg.get("params") or {})
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": tools.TOOL_DEFINITIONS}
            elif method == "tools/call":
                result = self._call_tool(msg.get("params") or {})
            else:
                self._reply_error(msg_id, -32601, f"method not available: {method}", log_event="refused_method")
                return
        except LogUnavailable as exc:
            self._send({"jsonrpc": "2.0", "id": msg_id,
                        "error": {"code": -32000, "message": f"call refused: could not write the call log ({exc})"}})
            return
        self._send({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _initialize(self, params):
        caps = params.get("capabilities") or {}
        self.client_can_ask = isinstance(caps.get("elicitation"), dict)
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else DEFAULT_VERSION
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "arbo-mcp", "version": "0.1.0"},
            "instructions": "Test setup only. Synthetic data. The deploy tool deploys nothing.",
        }

    # --- tools -------------------------------------------------------------
    def _call_tool(self, params):
        meta = params.get("_meta")
        progress_token = meta.get("progressToken") if isinstance(meta, dict) else None
        name = params.get("name")
        args = params.get("arguments")
        if name not in tools.TOOL_NAMES:
            self._log("tool_refused", tool=name, reason="tool_not_granted")
            return _tool_result({"error": "tool_not_granted", "tool": name}, is_error=True)
        try:
            args = tools.validate(name, args)
        except tools.BadArguments as exc:
            self._log("tool_refused", tool=name, reason=f"bad arguments: {exc}")
            return _tool_result({"error": "bad_arguments", "detail": str(exc)}, is_error=True)

        self._log("tool_called", tool=name, arguments=args)
        if name == "read_logs":
            out = tools.read_logs(self.data_dir, args)
        elif name == "read_errors":
            out = tools.read_errors(self.data_dir, args)
        else:
            out = self._deploy(args, progress_token)
        self._log("tool_finished", tool=name)
        return _tool_result(out)

    def _deploy(self, args, progress_token=None):
        self._log("deploy_requested", target=args["target"], reason=args["reason"])
        if not self.client_can_ask:
            answer, why = None, "client cannot show a question (no elicitation support)"
        else:
            answer, why = self._ask_mike(args, progress_token)
        decision, decision_why = tools.decide(answer)
        if answer is None:
            decision_why = why
        self._log(
            "deploy_decision",
            target=args["target"],
            decision=decision,
            why=decision_why,
            answered_by=IDENTITY_NOTE,
            deployed=False,
        )
        return {
            "decision": decision,
            "why": decision_why,
            "deployed": False,
            "note": "Recorded only. This build cannot deploy anything, whatever the answer.",
        }

    def _ask_mike(self, args, progress_token=None):
        """Send elicitation/create and wait for the answer, with no time limit.

        The only thing the passage of time ever does here is send a reminder.
        """
        self._elicit_counter += 1
        elicit_id = f"arbo-elicit-{self._elicit_counter}"
        self._log("deploy_question_sent", elicit_id=elicit_id, time_limit="none")
        self._send({
            "jsonrpc": "2.0",
            "id": elicit_id,
            "method": "elicitation/create",
            "params": {
                "message": (
                    f"Arbo deploy request (TEST SETUP -- nothing will be deployed).\n"
                    f"Target: {args['target']}\nReason: {args['reason']}\n"
                    f"No time limit: nothing happens until you answer."
                ),
                "requestedSchema": tools.ELICIT_SCHEMA,
            },
        })
        reminders = 0
        next_reminder = time.monotonic() + self.remind_every_s
        while True:
            try:
                msg = self.inbox.get(block=True, timeout=max(0.0, next_reminder - time.monotonic()))
            except queue.Empty:
                reminders += 1
                self._remind(elicit_id, reminders, progress_token)
                next_reminder += self.remind_every_s
                continue  # keep waiting: no time limit, the reminder decides nothing
            if msg is _EOF:
                self.deferred.append(_EOF)
                return None, "client disconnected before answering"
            if isinstance(msg, dict) and msg.get("id") == elicit_id and "method" not in msg:
                if "error" in msg:
                    return None, "client returned an error instead of an answer"
                return msg.get("result"), "answered"
            if _is_deploy_call(msg):
                self.deferred.append(msg)  # one deploy question at a time
            else:
                self.handle(msg)  # everything else is answered while Mike decides

    def _remind(self, elicit_id, count, progress_token):
        self._safe_log("deploy_reminder", elicit_id=elicit_id, count=count, decided=False)
        if progress_token is not None:
            self._send({
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {"progressToken": progress_token, "progress": count, "message": REMINDER_TEXT},
            })

    # --- output ------------------------------------------------------------
    def _send(self, message):
        self.write(message)

    def _reply_error(self, msg_id, code, message, log_event):
        self._safe_log(log_event, id=msg_id, detail=message)
        if msg_id is not None:
            self._send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})

    def _safe_log(self, event, **fields):
        try:
            self._log(event, **fields)
        except LogUnavailable:
            pass  # nothing is executed on this path, so there is nothing to refuse


def _is_deploy_call(msg):
    return (isinstance(msg, dict) and msg.get("method") == "tools/call"
            and isinstance(msg.get("params"), dict) and msg["params"].get("name") == "deploy")


def _tool_result(payload, is_error=False):
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": is_error}


def _reader(stream, inbox):
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            inbox.put(json.loads(line))
        except ValueError:
            inbox.put({"jsonrpc": "invalid"})
    inbox.put(_EOF)


def main(argv=None):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description="Arbo test MCP server (stdio). Synthetic data only.")
    parser.add_argument("--data-dir", default=os.path.join(here, "data"))
    parser.add_argument("--log", default=os.path.join(here, "logs", "calls.jsonl"))
    parser.add_argument("--remind-every-minutes", type=float, default=DEFAULT_REMIND_EVERY_S / 60,
                        help="how often to remind Mike while a decision waits (reminders never decide)")
    opts = parser.parse_args(argv)
    if not opts.remind_every_minutes > 0:
        parser.error("--remind-every-minutes must be positive")

    out_lock = threading.Lock()

    def write(message):
        with out_lock:
            sys.stdout.write(json.dumps(message) + "\n")
            sys.stdout.flush()

    server = Server(opts.data_dir, opts.log, write, opts.remind_every_minutes * 60)
    threading.Thread(target=_reader, args=(sys.stdin, server.inbox), daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
