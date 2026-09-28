"""Tests required by the handoff, plus the checks that make them trustworthy.

Run:  python3 -m unittest discover -s tests -v
"""

import builtins
import hashlib
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from arbo_mcp import calllog, server, tools  # noqa: E402

WRITE_MODES = ("w", "a", "x", "+")


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def file_fingerprints(directory):
    out = {}
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        with open(path, "rb") as f:
            out[name] = (hashlib.sha256(f.read()).hexdigest(), os.stat(path).st_mtime_ns)
    return out


class Harness:
    """Runs the real Server in a thread and plays the MCP client.

    `answer_elicitation(request)` decides what the "client" does when the
    server asks Mike: return a response dict to send, or None to stay silent.
    """

    def __init__(self, can_ask=True, answer_elicitation=None, log_path=None, remind_every_s=3600.0):
        self.tmp = tempfile.mkdtemp(prefix="arbo-mcp-test-")
        self.data_dir = os.path.join(self.tmp, "data")
        shutil.copytree(os.path.join(ROOT, "data"), self.data_dir)
        self.log_path = log_path or os.path.join(self.tmp, "calls.jsonl")
        self.outbox = queue.Queue()
        self.answer_elicitation = answer_elicitation or (lambda req: None)
        self.srv = server.Server(self.data_dir, self.log_path, self.outbox.put, remind_every_s)
        self.thread = threading.Thread(target=self.srv.run, daemon=True)
        self.thread.start()
        self.elicitations = []
        self._next_id = 0
        caps = {"elicitation": {}} if can_ask else {}
        self.init_result = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": caps,
                                                       "clientInfo": {"name": "test", "version": "0"}})
        self.notify("notifications/initialized")

    def notify(self, method):
        self.srv.inbox.put({"jsonrpc": "2.0", "method": method})

    def send_raw(self, msg):
        self.srv.inbox.put(msg)

    def request(self, method, params=None, timeout=10):
        self._next_id += 1
        msg_id = self._next_id
        self.srv.inbox.put({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + timeout
        while True:
            msg = self.outbox.get(timeout=max(0.01, deadline - time.monotonic()))
            if msg.get("method") == "elicitation/create":
                self.elicitations.append(msg)
                reply = self.answer_elicitation(msg)
                if reply is not None:
                    reply.setdefault("jsonrpc", "2.0")
                    reply["id"] = msg["id"]
                    self.srv.inbox.put(reply)
                continue
            if msg.get("id") == msg_id:
                return msg

    def call(self, name, arguments=None):
        resp = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        result = resp["result"]
        return json.loads(result["content"][0]["text"]), result["isError"]

    def log_entries(self):
        return calllog.CallLog(self.log_path).entries()

    def wait_for(self, predicate, timeout=10):
        """Pull messages from the server until one matches (test-harness patience only)."""
        deadline = time.monotonic() + timeout
        while True:
            msg = self.outbox.get(timeout=max(0.01, deadline - time.monotonic()))
            if predicate(msg):
                return msg

    def close(self):
        self.srv.inbox.put(server._EOF)
        self.thread.join(timeout=5)
        shutil.rmtree(self.tmp, ignore_errors=True)


def accept(decision):
    return lambda req: {"result": {"action": "accept", "content": {"decision": decision}}}


class ExactlyThreeTools(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def test_lists_exactly_the_three_tools(self):
        names = [t["name"] for t in self.h.request("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["read_logs", "read_errors", "deploy"])

    def test_advertises_no_other_capabilities(self):
        self.assertEqual(self.h.init_result["result"]["capabilities"], {"tools": {"listChanged": False}})

    def test_unknown_tool_is_refused_and_logged(self):
        out, is_error = self.h.call("delete_everything", {})
        self.assertTrue(is_error)
        self.assertEqual(out["error"], "tool_not_granted")
        refused = [e for e in self.h.log_entries() if e["event"] == "tool_refused"]
        self.assertEqual(refused[-1]["tool"], "delete_everything")

    def test_other_mcp_methods_are_refused(self):
        for method in ("resources/list", "prompts/list", "resources/read", "sampling/createMessage"):
            resp = self.h.request(method)
            self.assertEqual(resp["error"]["code"], -32601, method)

    def test_bad_arguments_are_refused(self):
        for args in ({"limit": True}, {"limit": 0}, {"limit": 999}, {"path": "/etc/passwd"}, {"level": "LOUD"}):
            out, is_error = self.h.call("read_logs", args)
            self.assertTrue(is_error, args)
            self.assertEqual(out["error"], "bad_arguments")
        out, is_error = self.h.call("deploy", {"target": "x"})  # missing reason
        self.assertTrue(is_error)


class ReadToolsCannotWrite(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def test_read_tools_return_synthetic_data(self):
        out, is_error = self.h.call("read_logs", {"level": "ERROR"})
        self.assertFalse(is_error)
        self.assertEqual(out["count"], 2)
        self.assertTrue(all(e["synthetic"] for e in out["entries"]))
        out, _ = self.h.call("read_errors", {"status": "unresolved"})
        self.assertEqual(out["count"], 3)
        self.assertIn("not Sentry", out["source"])

    def test_data_files_are_unchanged_after_many_reads(self):
        before = file_fingerprints(self.h.data_dir)
        time.sleep(0.01)
        for _ in range(25):
            self.h.call("read_logs", {"contains": "sim"})
            self.h.call("read_errors", {})
        self.assertEqual(before, file_fingerprints(self.h.data_dir))

    def test_read_tools_open_nothing_for_writing_except_the_call_log(self):
        real_open = builtins.open
        opened = []

        def spy(path, mode="r", *a, **kw):
            opened.append((os.path.abspath(str(path)), mode))
            return real_open(path, mode, *a, **kw)

        with mock.patch("builtins.open", spy):
            self.h.call("read_logs", {})
            self.h.call("read_errors", {"id": "SIM-ERR-0001"})
        writes = {p for p, m in opened if any(c in m for c in WRITE_MODES)}
        self.assertEqual(writes, {os.path.abspath(self.h.log_path)})
        data_opens = [(p, m) for p, m in opened if p.startswith(os.path.abspath(self.h.data_dir))]
        self.assertTrue(data_opens)
        self.assertTrue(all(m == "r" for _, m in data_opens))

    def test_read_functions_themselves_refuse_to_write_under_a_guard(self):
        real_open = builtins.open

        def guard(path, mode="r", *a, **kw):
            if any(c in mode for c in WRITE_MODES):
                raise AssertionError(f"read tool tried to write: {path} ({mode})")
            return real_open(path, mode, *a, **kw)

        with mock.patch("builtins.open", guard):
            tools.read_logs(self.h.data_dir, {})
            tools.read_errors(self.h.data_dir, {})


class DeployNeedsMikesYes(unittest.TestCase):
    NOT_YES = {
        "decline": lambda req: {"result": {"action": "decline"}},
        "cancel": lambda req: {"result": {"action": "cancel"}},
        "accept but no": accept("no"),
        "accept but YES in caps": accept("YES"),
        "accept with no content": lambda req: {"result": {"action": "accept"}},
        "accept with garbage": lambda req: {"result": {"action": "accept", "content": "yes"}},
        "error instead of answer": lambda req: {"error": {"code": -1, "message": "boom"}},
        "result is not an object": lambda req: {"result": "yes"},
    }

    def assert_nothing_deployed(self, h, out):
        self.assertFalse(out["deployed"])
        decisions = [e for e in h.log_entries() if e["event"] == "deploy_decision"]
        self.assertEqual(len(decisions), 1)
        self.assertFalse(decisions[0]["deployed"])

    def test_every_answer_other_than_an_explicit_yes_is_no(self):
        for label, answer in self.NOT_YES.items():
            with self.subTest(label):
                h = Harness(answer_elicitation=answer)
                try:
                    before = file_fingerprints(h.data_dir)
                    out, is_error = h.call("deploy", {"target": "test-bundle", "reason": "unit test"})
                    self.assertFalse(is_error)
                    self.assertEqual(out["decision"], "no")
                    self.assert_nothing_deployed(h, out)
                    self.assertEqual(before, file_fingerprints(h.data_dir))
                    self.assertEqual(len(h.elicitations), 1, "Mike must have been asked")
                finally:
                    h.close()

    def test_client_that_cannot_ask_mike_means_no(self):
        h = Harness(can_ask=False)
        try:
            out, _ = h.call("deploy", {"target": "test-bundle", "reason": "unit test"})
            self.assertEqual(out["decision"], "no")
            self.assertIn("cannot show a question", out["why"])
            self.assertEqual(h.elicitations, [])
            self.assert_nothing_deployed(h, out)
        finally:
            h.close()

    def test_explicit_yes_is_recorded_and_still_deploys_nothing(self):
        h = Harness(answer_elicitation=accept("yes"))
        try:
            before = file_fingerprints(h.data_dir)
            out, _ = h.call("deploy", {"target": "test-bundle", "reason": "unit test"})
            self.assertEqual(out["decision"], "yes")
            self.assert_nothing_deployed(h, out)
            self.assertEqual(before, file_fingerprints(h.data_dir))
            decision = [e for e in h.log_entries() if e["event"] == "deploy_decision"][0]
            self.assertIn("identity not verified", decision["answered_by"])
        finally:
            h.close()

    def test_question_shows_target_reason_and_that_there_is_no_time_limit(self):
        h = Harness(answer_elicitation=accept("no"))
        try:
            h.call("deploy", {"target": "bundle-abc", "reason": "try it"})
            message = h.elicitations[0]["params"]["message"]
            self.assertIn("bundle-abc", message)
            self.assertIn("try it", message)
            self.assertIn("No time limit", message)
            self.assertNotIn("seconds", message)
            self.assertIn("nothing will be deployed", message)
        finally:
            h.close()

    def test_deploy_code_cannot_run_programs(self):
        source = read_text(os.path.join(ROOT, "arbo_mcp", "server.py"))
        for forbidden in ("subprocess", "os.system", "os.popen", "os.exec", "os.spawn", "shutil"):
            self.assertNotIn(forbidden, source)


def deploy_msg(msg_id, target="t", progress_token=None):
    params = {"name": "deploy", "arguments": {"target": target, "reason": "r"}}
    if progress_token is not None:
        params["_meta"] = {"progressToken": progress_token}
    return {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call", "params": params}


def is_question(msg):
    return msg.get("method") == "elicitation/create"


def is_reply(msg_id):
    return lambda msg: msg.get("id") == msg_id and "method" not in msg


def answer(h, question, decision):
    h.send_raw({"jsonrpc": "2.0", "id": question["id"],
                "result": {"action": "accept", "content": {"decision": decision}}})


class NoTimeLimitOnMikesDecision(unittest.TestCase):
    """Mike, Sep 26, 2026: "There should be no time limits at all when it comes to my decision."

    The deploy question waits for as long as Mike takes. Nothing happens while
    it waits, and silence never turns into an answer.
    """

    def test_the_only_thing_time_can_do_is_send_a_reminder(self):
        import ast
        src = read_text(os.path.join(ROOT, "arbo_mcp", "server.py"))
        lowered = (src + read_text(os.path.join(ROOT, "arbo_mcp", "tools.py"))).lower()
        for word in ("deadline", "expire", "time.sleep"):
            self.assertFalse(word in lowered, f"'{word}' found in the server code")
        # Every place the wait can wake up on the clock (queue.Empty) must send
        # a reminder and keep waiting: no return, no raise, no decision.
        handlers = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ExceptHandler)
                    and "Empty" in ast.dump(n.type or ast.Name(id=""))]
        self.assertEqual(len(handlers), 1)
        body = ast.dump(ast.Module(body=handlers[0].body, type_ignores=[]))
        self.assertIn("_remind", body)
        self.assertTrue(isinstance(handlers[0].body[-1], ast.Continue))
        for forbidden in ("Return(", "Raise(", "decide", "deploy_decision"):
            self.assertNotIn(forbidden, body)
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            server.main(["--deploy-timeout", "5"])

    def test_waits_as_long_as_it_takes_and_decides_nothing_meanwhile(self):
        h = Harness()
        try:
            h.send_raw(deploy_msg(100))
            question = h.wait_for(is_question)
            time.sleep(1.5)  # far longer than any reply takes; still waiting
            self.assertTrue(h.outbox.empty(), "no reply while Mike hasn't answered")
            events = [e["event"] for e in h.log_entries()]
            self.assertIn("deploy_question_sent", events)
            self.assertNotIn("deploy_decision", events, "nothing is decided while waiting")
            answer(h, question, "yes")
            out = json.loads(h.wait_for(is_reply(100))["result"]["content"][0]["text"])
            self.assertEqual((out["decision"], out["deployed"]), ("yes", False))
        finally:
            h.close()

    def test_other_requests_are_answered_while_mike_decides(self):
        h = Harness()
        try:
            h.send_raw(deploy_msg(100))
            question = h.wait_for(is_question)
            h.send_raw({"jsonrpc": "2.0", "id": 101, "method": "tools/call",
                        "params": {"name": "read_logs", "arguments": {"limit": 1}}})
            reply = h.wait_for(lambda m: "method" not in m)
            self.assertEqual(reply["id"], 101, "read_logs is answered before the deploy decision")
            self.assertEqual(h.srv.inbox.qsize(), 0)
            answer(h, question, "no")
            out = json.loads(h.wait_for(is_reply(100))["result"]["content"][0]["text"])
            self.assertEqual(out["decision"], "no")
        finally:
            h.close()

    def test_a_second_deploy_request_waits_its_turn(self):
        h = Harness()
        try:
            h.send_raw(deploy_msg(100, "first"))
            q1 = h.wait_for(is_question)
            h.send_raw(deploy_msg(101, "second"))
            h.send_raw({"jsonrpc": "2.0", "id": 102, "method": "ping"})
            self.assertEqual(h.wait_for(lambda m: "method" not in m)["id"], 102)
            self.assertTrue(h.outbox.empty(), "only one question at a time")
            answer(h, q1, "no")
            self.assertEqual(h.wait_for(lambda m: "method" not in m)["id"], 100)
            q2 = h.wait_for(is_question)
            self.assertIn("second", q2["params"]["message"])
            answer(h, q2, "yes")
            out = json.loads(h.wait_for(is_reply(101))["result"]["content"][0]["text"])
            self.assertEqual((out["decision"], out["deployed"]), ("yes", False))
        finally:
            h.close()

    def test_a_disconnect_while_waiting_means_nothing_happens(self):
        h = Harness()
        try:
            h.send_raw(deploy_msg(100))
            h.wait_for(is_question)
            h.send_raw(server._EOF)
            out = json.loads(h.wait_for(is_reply(100))["result"]["content"][0]["text"])
            self.assertEqual((out["decision"], out["deployed"]), ("no", False))
            self.assertIn("disconnected", out["why"])
        finally:
            h.close()


class RemindersDecideNothing(unittest.TestCase):
    """Mike, Sep 28, 2026: yes to a "still waiting on you" reminder that decides nothing."""

    def reminders(self, h):
        return [e for e in h.log_entries() if e["event"] == "deploy_reminder"]

    def test_reminders_go_out_while_waiting_and_decide_nothing(self):
        h = Harness(remind_every_s=0.1)
        try:
            h.send_raw(deploy_msg(100, progress_token="tok-1"))
            question = h.wait_for(is_question)
            time.sleep(0.65)
            logged = self.reminders(h)
            self.assertGreaterEqual(len(logged), 4)
            self.assertTrue(all(r["decided"] is False for r in logged))
            self.assertNotIn("deploy_decision", [e["event"] for e in h.log_entries()])
            notes = []
            while not h.outbox.empty():
                notes.append(h.outbox.get())
            self.assertTrue(notes)
            for n in notes:
                self.assertEqual(n["method"], "notifications/progress")
                self.assertEqual(n["params"]["progressToken"], "tok-1")
                self.assertIn("Still waiting on you", n["params"]["message"])
            self.assertEqual([n["params"]["progress"] for n in notes], sorted(n["params"]["progress"] for n in notes))
            answer(h, question, "yes")
            out = json.loads(h.wait_for(is_reply(100))["result"]["content"][0]["text"])
            self.assertEqual((out["decision"], out["deployed"]), ("yes", False))
        finally:
            h.close()

    def test_reminders_keep_their_schedule_during_steady_traffic(self):
        h = Harness(remind_every_s=0.1)
        try:
            h.send_raw(deploy_msg(100))
            question = h.wait_for(is_question)
            for i in range(20):  # a ping every 30 ms, faster than the reminder interval
                h.send_raw({"jsonrpc": "2.0", "id": 500 + i, "method": "ping"})
                time.sleep(0.03)
            self.assertGreaterEqual(len(self.reminders(h)), 3)
            answer(h, question, "no")
            h.wait_for(is_reply(100))
        finally:
            h.close()

    def test_without_a_progress_token_reminders_are_only_logged(self):
        h = Harness(remind_every_s=0.1)
        try:
            h.send_raw(deploy_msg(100))
            question = h.wait_for(is_question)
            time.sleep(0.35)
            self.assertGreaterEqual(len(self.reminders(h)), 2)
            self.assertTrue(h.outbox.empty(), "nothing is sent without a progress token")
            answer(h, question, "no")
            h.wait_for(is_reply(100))
        finally:
            h.close()

    def test_the_reminder_interval_must_be_positive(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                server.Server("d", "l", lambda m: None, bad)
            with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                server.main(["--remind-every-minutes", str(bad)])


class EveryCallIsLogged(unittest.TestCase):
    def test_every_request_and_tool_call_is_in_the_log_and_the_chain_verifies(self):
        h = Harness(answer_elicitation=accept("no"))
        try:
            h.request("tools/list")
            h.call("read_logs", {"limit": 3})
            h.call("read_errors", {})
            h.call("deploy", {"target": "t", "reason": "r"})
            h.call("not_a_tool", {})
            h.call("read_logs", {"bogus": 1})
            h.request("resources/list")
            entries = h.log_entries()
            received_ids = {e["id"] for e in entries if e["event"] == "received" and e["id"] is not None}
            self.assertEqual(received_ids, set(range(1, h._next_id + 1)))
            called = [e["tool"] for e in entries if e["event"] == "tool_called"]
            self.assertEqual(called, ["read_logs", "read_errors", "deploy"])
            refused = [e["tool"] for e in entries if e["event"] == "tool_refused"]
            self.assertEqual(refused, ["not_a_tool", "read_logs"])
            events = [e["event"] for e in entries]
            for needed in ("deploy_requested", "deploy_question_sent", "deploy_decision", "refused_method"):
                self.assertIn(needed, events)
            self.assertIn("notifications/initialized", [e.get("method") for e in entries])
            ok, problem = calllog.verify(h.log_path)
            self.assertTrue(ok, problem)
        finally:
            h.close()

    def test_editing_deleting_or_reordering_the_log_is_detected(self):
        h = Harness()
        try:
            h.call("read_logs", {})
            h.call("read_errors", {})
            lines = read_text(h.log_path).splitlines()
        finally:
            h.close()
        cases = {
            "edited": lines[:1] + [lines[1].replace('"received"', '"receivedX"')] + lines[2:],
            "deleted": lines[:1] + lines[2:],
            "reordered": [lines[1], lines[0]] + lines[2:],
        }
        for label, tampered in cases.items():
            with self.subTest(label), tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
                f.write("\n".join(tampered) + "\n")
            ok, _ = calllog.verify(f.name)
            os.unlink(f.name)
            self.assertFalse(ok, label)

    def test_if_the_log_cannot_be_written_the_call_is_refused_and_nothing_runs(self):
        blocked_dir = tempfile.mkdtemp()
        # A directory where the log file should be: every append fails.
        h = Harness.__new__(Harness)
        h.tmp = blocked_dir
        h.data_dir = os.path.join(ROOT, "data")
        h.log_path = blocked_dir  # opening a directory for append always fails
        h.outbox = queue.Queue()
        h.answer_elicitation = accept("yes")
        h.srv = server.Server(h.data_dir, h.log_path, h.outbox.put)
        h.thread = threading.Thread(target=h.srv.run, daemon=True)
        h.thread.start()
        h.elicitations = []
        h._next_id = 0
        try:
            with mock.patch.object(tools, "read_logs", side_effect=AssertionError("must not run")):
                resp = h.request("tools/call", {"name": "read_logs", "arguments": {}})
            self.assertIn("call refused", resp["error"]["message"])
            resp = h.request("tools/call", {"name": "deploy", "arguments": {"target": "t", "reason": "r"}})
            self.assertIn("call refused", resp["error"]["message"])
            self.assertEqual(h.elicitations, [], "no question may be asked if the call cannot be logged")
        finally:
            h.srv.inbox.put(server._EOF)
            h.thread.join(timeout=5)
            shutil.rmtree(blocked_dir, ignore_errors=True)


class NoNetworkAndSyntheticOnly(unittest.TestCase):
    NETWORK_MODULES = ("socket", "ssl", "http", "urllib", "requests", "httpx", "ftplib", "smtplib",
                       "telnetlib", "xmlrpc", "asyncio", "websocket", "aiohttp", "subprocess")

    def test_no_source_file_imports_network_or_process_modules(self):
        pattern = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z_][\w.]*)", re.M)
        for name in os.listdir(os.path.join(ROOT, "arbo_mcp")):
            if name.endswith(".py"):
                src = read_text(os.path.join(ROOT, "arbo_mcp", name))
                for mod in pattern.findall(src):
                    self.assertNotIn(mod.split(".")[0], self.NETWORK_MODULES, f"{name} imports {mod}")

    def test_no_web_addresses_in_the_code_or_data(self):
        url = re.compile(r"(https?://|wss?://|www\.)", re.I)
        for folder in ("arbo_mcp", "data"):
            for name in os.listdir(os.path.join(ROOT, folder)):
                path = os.path.join(ROOT, folder, name)
                if os.path.isfile(path):
                    self.assertIsNone(url.search(read_text(path)), path)

    def test_data_is_synthetic_with_no_phone_numbers_or_emails(self):
        phone = re.compile(r"\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b")
        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        for name in os.listdir(os.path.join(ROOT, "data")):
            text = read_text(os.path.join(ROOT, "data", name))
            self.assertIsNone(phone.search(text), name)
            self.assertIsNone(email.search(text), name)
        for line in read_text(os.path.join(ROOT, "data", "synthetic_logs.jsonl")).splitlines():
            self.assertTrue(json.loads(line)["synthetic"])
        issues = json.loads(read_text(os.path.join(ROOT, "data", "synthetic_errors.json")))["issues"]
        self.assertTrue(all(i["synthetic"] and i["id"].startswith("SIM-") for i in issues))

    def test_every_tool_works_with_sockets_disabled(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network used")), \
                mock.patch.object(socket, "create_connection", side_effect=AssertionError("network used")):
            h = Harness(answer_elicitation=accept("yes"))
            try:
                self.assertFalse(h.call("read_logs", {})[1])
                self.assertFalse(h.call("read_errors", {})[1])
                self.assertEqual(h.call("deploy", {"target": "t", "reason": "r"})[0]["decision"], "yes")
            finally:
                h.close()


# The end-to-end run: the real program over real stdin/stdout, with the Python
# interpreter itself refusing any network or process-launch event.
AUDIT_WRAPPER = r"""
import sys
BLOCKED = ("socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.fork", "urllib.", "http.")
def hook(event, args):
    if event.startswith(BLOCKED):
        raise RuntimeError("BLOCKED BY TEST: " + event)
sys.addaudithook(hook)
sys.path.insert(0, sys.argv[1])
from arbo_mcp.server import main
main(sys.argv[2:])
"""


class EndToEndOverStdio(unittest.TestCase):
    def run_session(self, messages_and_answers):
        tmp = tempfile.mkdtemp()
        log = os.path.join(tmp, "calls.jsonl")
        proc = subprocess.Popen(
            [sys.executable, "-c", AUDIT_WRAPPER, ROOT, "--log", log],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        replies = []
        try:
            for msg, elicit_answer in messages_and_answers:
                proc.stdin.write(json.dumps(msg) + "\n")
                proc.stdin.flush()
                if "id" not in msg:
                    continue
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        self.fail("server exited early: " + proc.stderr.read())
                    out = json.loads(line)
                    if out.get("method") == "elicitation/create":
                        if elicit_answer is not None:
                            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": out["id"], "result": elicit_answer}) + "\n")
                            proc.stdin.flush()
                        continue
                    replies.append(out)
                    break
        finally:
            proc.stdin.close()
            proc.wait(timeout=10)
            stderr = proc.stderr.read()
            proc.stdout.close()
            proc.stderr.close()
        ok, problem = calllog.verify(log)
        shutil.rmtree(tmp, ignore_errors=True)
        self.assertNotIn("BLOCKED BY TEST", stderr)
        self.assertTrue(ok, problem)
        return replies

    def test_full_session_yes_then_no(self):
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {"elicitation": {}},
                           "clientInfo": {"name": "e2e", "version": "0"}}}
        deploy = lambda i: {"jsonrpc": "2.0", "id": i, "method": "tools/call",
                            "params": {"name": "deploy", "arguments": {"target": "t", "reason": "r"}}}
        replies = self.run_session([
            (init, None),
            ({"jsonrpc": "2.0", "method": "notifications/initialized"}, None),
            ({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, None),
            ({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "read_logs", "arguments": {"limit": 2}}}, None),
            ({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "read_errors", "arguments": {}}}, None),
            (deploy(5), {"action": "accept", "content": {"decision": "yes"}}),
            (deploy(6), {"action": "decline"}),
        ])
        self.assertEqual(len(replies[1]["result"]["tools"]), 3)
        self.assertEqual(json.loads(replies[2]["result"]["content"][0]["text"])["count"], 2)
        yes = json.loads(replies[4]["result"]["content"][0]["text"])
        declined = json.loads(replies[5]["result"]["content"][0]["text"])
        self.assertEqual((yes["decision"], yes["deployed"]), ("yes", False))
        self.assertEqual((declined["decision"], declined["deployed"]), ("no", False))

    def test_the_audit_hook_really_blocks_network(self):
        proc = subprocess.run(
            [sys.executable, "-c", AUDIT_WRAPPER.replace("from arbo_mcp.server import main\nmain(sys.argv[2:])",
                                                          "import socket\nsocket.socket()"), ROOT],
            capture_output=True, text=True, timeout=10,
        )
        self.assertIn("BLOCKED BY TEST", proc.stderr)


if __name__ == "__main__":
    unittest.main()
