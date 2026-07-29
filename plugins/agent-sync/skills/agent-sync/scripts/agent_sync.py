#!/usr/bin/env python3
"""agent-sync — coordination for concurrent agents over a pluggable knowledge cloud.

Stdlib only. Python 3.9+.

Two planes: git is the record plane, the cloud is the coordination plane.
Leases and id reservations are decided by replaying one append-only log, because
no supported backend offers compare-and-swap. Document order is authoritative;
timestamps only expire leases.

Credentials are read from the environment and never appear in argv, a log line,
a journal entry or a rendered board. HTTP goes through urllib inside this
process — there is no subprocess and nothing for another process to read.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.2.0"

CONFIG_PATH = Path(".claude/agent-sync.json")
ENV_FILE = Path(".env.agent-sync")
STATE_DIR = Path(".agent-sync")
GENERATED_MARKER = "<!-- agent-sync:generated"

LOGS = {
    "claims": "30 Claims",
    "reservations": "40 Reservations",
    "signals": "50 Signals",
    "blockers": "60 Blockers",
}

# Write with "- ", read any bullet. A knowledge base normalises markdown on the way
# in — Outline rewrites "- " to "* " — so a parser anchored to the character we wrote
# rejects every line the server gave back, and the caller sees "lost" instead of
# "unreadable". Be strict in what you emit, liberal in what you accept.
LINE_RE = re.compile(r"^[-*+] `(?P<ts>[^`]+)`(?P<pairs>(?: `[a-z_]+=[^`]*`)+)$")
CANDIDATE_RE = re.compile(r"^[-*+] `")
PAIR_RE = re.compile(r"`([a-z_]+)=([^`]*)`")
MAX_UNPARSEABLE = 0.02

DEFAULT_TTL = 2700
DEFAULT_RENEW = 300


# --------------------------------------------------------------------------- utils

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(ts: str) -> float:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def git(*args: str, cwd: Path | None = None) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def project_root() -> Path:
    top = git("rev-parse", "--show-toplevel")
    return Path(top) if top else Path.cwd()


def head_sha() -> str:
    return git("rev-parse", "--short", "HEAD") or "unknown"


def repo_name() -> str:
    url = git("config", "--get", "remote.origin.url")
    if url:
        return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    return project_root().name


class Fail(Exception):
    """A failure the caller must see. Never swallowed into a success."""


# --------------------------------------------------------------------------- config

def load_config(root: Path) -> dict[str, Any]:
    path = root / CONFIG_PATH
    if not path.exists():
        raise Fail(
            "no .claude/agent-sync.json in this project.\n"
            "Run `init` first — it asks which backend to use and writes the config.\n"
            "  agent_sync.py init --backend outline --url <instance-url>\n"
            "  agent_sync.py init --backend fs")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise Fail(f".claude/agent-sync.json is not valid JSON: {exc}") from exc


def run_id(root: Path) -> str:
    """Stable for the life of one agent session."""
    env = os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("AGENT_SYNC_RUN_ID")
    if env:
        return "r-" + re.sub(r"[^a-z0-9]", "", env.lower())[:12]
    marker = root / STATE_DIR / "run-id"
    if marker.exists():
        return marker.read_text().strip()
    rid = "r-%06x%s" % (random.getrandbits(24), format(int(time.time()) & 0xFFF, "03x"))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(rid)
    return rid


# --------------------------------------------------------------------------- adapters

class Adapter:
    name = "none"
    capabilities = {"atomicAppend": False, "totalOrderRead": False, "search": False}

    def configured(self) -> bool:
        raise NotImplementedError

    def tree_ensure(self, path: str) -> str:
        raise NotImplementedError

    def log_append(self, oid: str, line: str) -> None:
        raise NotImplementedError

    def log_read(self, oid: str) -> str:
        raise NotImplementedError

    def doc_put(self, oid: str, text: str) -> None:
        raise NotImplementedError

    def doc_get(self, oid: str) -> str:
        raise NotImplementedError

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return []

    @property
    def is_lease_authority(self) -> bool:
        return bool(self.capabilities["atomicAppend"]
                    and self.capabilities["totalOrderRead"])


class OutlineAdapter(Adapter):
    """Outline knowledge base. Hosted or self-hosted; the URL is configuration.

    No compare-and-swap exists in this API: documents.update has editMode
    append/replace/prepend/patch and no lastRevision. Coordination state is
    therefore never a document we rewrite.
    """

    name = "outline"
    capabilities = {"atomicAppend": True, "totalOrderRead": True, "search": True}

    def __init__(self) -> None:
        self.url = (os.environ.get("AGENT_SYNC_OUTLINE_URL") or "").rstrip("/")
        self.token = os.environ.get("AGENT_SYNC_OUTLINE_TOKEN") or ""
        self.collection = os.environ.get("AGENT_SYNC_OUTLINE_COLLECTION") or ""
        self._collection_uuid = ""
        self._ids: dict[str, str] = {}

    def configured(self) -> bool:
        return bool(self.url and self.token)

    def _call(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.configured():
            raise Fail("Outline is not configured (URL or token missing from the environment)")
        payload = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.url}/api/{endpoint}", data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        delay = 1.0
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode())
                if not data.get("ok", False):
                    raise Fail(f"outline {endpoint}: {data.get('message') or data.get('error')}")
                return data.get("data") or {}
            except urllib.error.HTTPError as exc:
                # The useful part of an Outline failure is in the body. Dropping it
                # turns "collectionId: Invalid UUID" into a bare 400 and costs a
                # debugging round — never swallow the reason.
                detail = ""
                try:
                    payload_err = json.loads(exc.read().decode())
                    detail = payload_err.get("message") or payload_err.get("error") or ""
                except (ValueError, OSError):
                    pass
                if exc.code in (401, 403):
                    raise Fail(
                        f"outline {endpoint}: {exc.code} — the token is rejected"
                        f"{': ' + detail if detail else ''}. "
                        "A credential does not become valid on retry.") from exc
                if exc.code == 429 and attempt < 4:
                    time.sleep(float(exc.headers.get("Retry-After") or delay))
                    delay *= 2
                    continue
                raise Fail(f"outline {endpoint}: HTTP {exc.code}"
                           f"{' — ' + detail if detail else ''}") from exc
            except urllib.error.URLError as exc:
                if attempt < 2:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise Fail(f"outline {endpoint}: cannot reach the instance ({exc.reason})") from exc
        raise Fail(f"outline {endpoint}: gave up after 5 attempts")

    def resolve_collection(self) -> str:
        """Accept a UUID, a urlId, or the whole `name-urlId` slug from the browser.

        The API takes a UUID, and the value a person copies out of the address bar
        is a slug. Rejecting that with 'Invalid UUID' is technically correct and
        useless, so match it instead."""
        if self._collection_uuid:
            return self._collection_uuid
        value = self.collection.strip()
        if not value:
            raise Fail("AGENT_SYNC_OUTLINE_COLLECTION is not set — run `bootstrap` to create "
                       "the container, then put the id it prints into .env.agent-sync")
        if re.fullmatch(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
            self._collection_uuid = value
            return value

        rows = self._call("collections.list", {"limit": 100})
        rows = rows if isinstance(rows, list) else []
        tail = value.rsplit("-", 1)[-1]
        for c in rows:
            if value in (c.get("urlId"), c.get("name")) or (tail and tail == c.get("urlId")):
                self._collection_uuid = c["id"]
                print(f"note: resolved collection '{c.get('name')}' → {c['id']}\n"
                      f"      put that UUID in AGENT_SYNC_OUTLINE_COLLECTION to skip this lookup",
                      file=sys.stderr)
                return str(c["id"])
        names = ", ".join(repr(c.get("name")) for c in rows) or "none visible to this token"
        raise Fail(f"no collection matches '{value}'. Available: {names}")

    def tree_ensure(self, path: str) -> str:
        if path in self._ids:
            return self._ids[path]
        collection = self.resolve_collection()
        found = self._call("documents.search",
                           {"query": path, "limit": 5, "collectionId": collection})
        for row in (found if isinstance(found, list) else []):
            doc = row.get("document") or {}
            if doc.get("title") == path:
                self._ids[path] = doc["id"]
                return doc["id"]
        doc = self._call("documents.create", {
            "collectionId": collection, "title": path,
            "text": f"{GENERATED_MARKER} container -->\n", "publish": True})
        self._ids[path] = doc["id"]
        return doc["id"]

    def log_append(self, oid: str, line: str) -> None:
        self._call("documents.update",
                   {"id": oid, "text": line.rstrip("\n") + "\n", "editMode": "append"})

    def log_read(self, oid: str) -> str:
        return self._call("documents.info", {"id": oid}).get("text", "")

    def doc_put(self, oid: str, text: str) -> None:
        self._call("documents.update", {"id": oid, "text": text, "editMode": "replace"})

    def doc_get(self, oid: str) -> str:
        return self._call("documents.info", {"id": oid}).get("text", "")

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._call("documents.search", {"query": query, "limit": limit})
        out = []
        for row in (rows if isinstance(rows, list) else []):
            doc = row.get("document") or {}
            out.append({"id": doc.get("id"), "title": doc.get("title"),
                        "snippet": row.get("context", "")})
        return out


class FsAdapter(Adapter):
    """Degraded mode. Files under .agent-sync/, committed and pushed.

    atomicAppend is FALSE on purpose: agents here are separated by git, not by a
    filesystem, so ordering is decided by a merge after the fact — which is not
    when the protocol needs it. This adapter is never the lease authority.
    """

    name = "fs"
    capabilities = {"atomicAppend": False, "totalOrderRead": False, "search": False}

    def __init__(self, root: Path) -> None:
        self.base = root / STATE_DIR
        self.base.mkdir(parents=True, exist_ok=True)

    def configured(self) -> bool:
        return True

    def _p(self, path: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", path).strip("-").lower()
        return self.base / f"{safe}.md"

    def tree_ensure(self, path: str) -> str:
        p = self._p(path)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("")
        return str(p)

    def log_append(self, oid: str, line: str) -> None:
        with open(oid, "a") as fh:
            fh.write(line.rstrip("\n") + "\n")

    def log_read(self, oid: str) -> str:
        p = Path(oid)
        return p.read_text() if p.exists() else ""

    def doc_put(self, oid: str, text: str) -> None:
        Path(oid).write_text(text)

    def doc_get(self, oid: str) -> str:
        p = Path(oid)
        return p.read_text() if p.exists() else ""


def make_adapter(cfg: dict[str, Any], root: Path) -> Adapter:
    backend = os.environ.get("AGENT_SYNC_BACKEND") or cfg.get("backend") or "fs"
    if backend == "outline":
        ad = OutlineAdapter()
        if not ad.configured():
            return FsAdapter(root)
        return ad
    return FsAdapter(root)


# --------------------------------------------------------------------------- log

def fmt_line(op: str, key: str, rid: str, **extra: Any) -> str:
    pairs = [f"`op={op}`", f"`key={key}`", f"`run={rid}`"]
    pairs += [f"`{k}={v}`" for k, v in extra.items() if v not in (None, "")]
    return f"- `{now_iso()}` " + " ".join(pairs)


def parse_log(text: str) -> tuple[list[dict[str, str]], int]:
    events: list[dict[str, str]] = []
    bad = 0
    for raw in text.splitlines():
        raw = raw.rstrip()
        # Skip only what is plainly not an entry (blank lines, prose, the generated
        # marker). Anything shaped like an entry must reach LINE_RE, or a silent
        # pre-filter hides malformed lines from the very counter meant to expose them.
        if not CANDIDATE_RE.match(raw):
            continue
        m = LINE_RE.match(raw)
        if not m:
            bad += 1
            continue
        ev = dict(PAIR_RE.findall(m.group("pairs")))
        if not {"op", "key", "run"} <= ev.keys():
            bad += 1
            continue
        ev["ts"] = m.group("ts")
        events.append(ev)
    return events, bad


def resolve_holder(events: list[dict[str, str]], key: str, at: float) -> str | None:
    """Replay: the holder is the earliest acquire for key that is, at this point,
    neither released nor expired. Pure function of the log text."""
    live: list[dict[str, Any]] = []
    for ev in events:
        if ev["key"] != key:
            continue
        if ev["op"] == "acquire":
            live.append({"run": ev["run"], "ts": parse_iso(ev["ts"]),
                         "ttl": int(ev.get("ttl") or DEFAULT_TTL)})
        elif ev["op"] == "release":
            live = [h for h in live if h["run"] != ev["run"]]
        elif ev["op"] == "renew":
            for h in live:
                if h["run"] == ev["run"]:
                    h["ts"] = parse_iso(ev["ts"])
    for h in live:
        if at <= h["ts"] + h["ttl"]:
            return str(h["run"])
    return None


def resolve_reservations(events: list[dict[str, str]], reg: str) -> tuple[int, list[int], list[tuple[str, int]]]:
    """Positional allocation over the log. Returns (base, free_list, assignments)."""
    base = None
    free: list[int] = []
    served = 0
    assignments: list[tuple[str, int]] = []
    for ev in events:
        if ev["key"] != reg:
            continue
        if ev["op"] == "base":
            base = int(ev.get("value") or 0)
            continue
        if base is None:
            continue
        if ev["op"] == "release_id":
            try:
                free.append(int(ev.get("value") or 0))
            except ValueError:
                pass
        elif ev["op"] == "reserve":
            if free:
                assignments.append((ev["run"], free.pop(0)))
            else:
                assignments.append((ev["run"], base + served))
                served += 1
    return (base or 0), free, assignments


# --------------------------------------------------------------------------- coordinator

class Sync:
    def __init__(self) -> None:
        self.root = project_root()
        os.chdir(self.root)
        self.cfg = load_config(self.root)
        self.adapter = make_adapter(self.cfg, self.root)
        self.rid = run_id(self.root)
        self.ttl = int(self.cfg.get("leaseTtlSeconds") or DEFAULT_TTL)

    @property
    def gated(self) -> bool:
        return bool(self.cfg.get("gated", True)) and self.adapter.is_lease_authority

    def log_id(self, which: str) -> str:
        return self.adapter.tree_ensure(LOGS[which])

    def events(self, which: str) -> tuple[list[dict[str, str]], int]:
        return parse_log(self.adapter.log_read(self.log_id(which)))

    # -- leases ------------------------------------------------------------

    def acquire(self, key: str) -> tuple[bool, str | None]:
        if not self.adapter.is_lease_authority:
            return self._fs_lease(key)
        oid = self.log_id("claims")
        holder = None
        for attempt in range(3):
            self.adapter.log_append(oid, fmt_line(
                "acquire", key, self.rid, ttl=self.ttl,
                repo=repo_name(), sha=head_sha()))
            time.sleep(0.25 + random.random() * 0.15)
            events, bad = parse_log(self.adapter.log_read(oid))
            # A log we cannot replay is not a lost race. Reporting "lost" here would
            # be a lie that sends the caller looking for a holder who does not exist.
            total = len(events) + bad
            if total and bad / total > MAX_UNPARSEABLE:
                raise Fail(
                    f"the claims log is {bad}/{total} unparseable — it cannot be replayed, "
                    "so no holder can be determined. This is a read failure, not a lost "
                    "race. Inspect the log before trusting any lease.")
            holder = resolve_holder(events, key, time.time())
            if holder == self.rid:
                self._touch_renew()
                return True, self.rid
            # Lost: withdraw, or the log replays us as a contender forever.
            self.adapter.log_append(oid, fmt_line("release", key, self.rid))
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
        return False, holder

    def _fs_lease(self, key: str) -> tuple[bool, str | None]:
        """Degraded: the remote's fast-forward rule is the only real arbiter."""
        lock = self.root / STATE_DIR / "leases" / f"{re.sub(r'[^A-Za-z0-9_-]', '-', key)}.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        if lock.exists():
            try:
                held = json.loads(lock.read_text())
            except json.JSONDecodeError:
                held = {}
            if held.get("run") != self.rid and \
                    time.time() <= parse_iso(held.get("ts", "")) + int(held.get("ttl", self.ttl)):
                return False, held.get("run")
        lock.write_text(json.dumps(
            {"run": self.rid, "ts": now_iso(), "ttl": self.ttl}))
        self._touch_renew()
        return True, self.rid

    def renew(self, key: str | None = None) -> bool:
        marker = self.root / STATE_DIR / "last-renew"
        interval = int(self.cfg.get("renewIntervalSeconds") or DEFAULT_RENEW)
        if marker.exists() and time.time() - marker.stat().st_mtime < interval:
            return False
        keys = [key] if key else self.held()
        if not keys:
            self._touch_renew()
            return False
        if self.adapter.is_lease_authority:
            oid = self.log_id("claims")
            for k in keys:
                self.adapter.log_append(oid, fmt_line("renew", k, self.rid))
        self._touch_renew()
        return True

    def _touch_renew(self) -> None:
        marker = self.root / STATE_DIR / "last-renew"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(now_iso())

    def release(self, key: str) -> None:
        if self.adapter.is_lease_authority:
            self.adapter.log_append(self.log_id("claims"), fmt_line("release", key, self.rid))
        lock = self.root / STATE_DIR / "leases" / f"{re.sub(r'[^A-Za-z0-9_-]', '-', key)}.lock"
        if lock.exists():
            lock.unlink()

    def held(self) -> list[str]:
        if not self.adapter.is_lease_authority:
            d = self.root / STATE_DIR / "leases"
            out = []
            for p in (d.glob("*.lock") if d.exists() else []):
                try:
                    if json.loads(p.read_text()).get("run") == self.rid:
                        out.append(p.stem)
                except json.JSONDecodeError:
                    continue
            return out
        events, _ = self.events("claims")
        now = time.time()
        keys = {e["key"] for e in events}
        return sorted(k for k in keys if resolve_holder(events, k, now) == self.rid)

    # -- ids ---------------------------------------------------------------

    def reserve(self, reg: str) -> int:
        if not self.adapter.is_lease_authority:
            raise Fail(
                f"backend '{self.adapter.name}' cannot reserve ids safely "
                "(atomicAppend is false). Allocate by hand and record it, or configure a "
                "cloud backend. Pretending would hand two agents the same id.")
        oid = self.log_id("reservations")
        events, _ = parse_log(self.adapter.log_read(oid))
        base, _free, _assign = resolve_reservations(events, reg)
        if not base:
            base = self._seed_base(reg)
            self.adapter.log_append(oid, fmt_line("base", reg, self.rid, value=f"{base:04d}"))
            events, _ = parse_log(self.adapter.log_read(oid))
        self.adapter.log_append(oid, fmt_line("reserve", reg, self.rid))
        time.sleep(0.25 + random.random() * 0.15)
        events, _ = parse_log(self.adapter.log_read(oid))
        _b, _f, assignments = resolve_reservations(events, reg)
        mine = [v for r, v in assignments if r == self.rid]
        if not mine:
            raise Fail(f"reserve {reg}: the append did not read back — retry")
        return mine[-1]

    def _seed_base(self, reg: str) -> int:
        spec = (self.cfg.get("idRegisters") or {}).get(reg)
        if not spec:
            raise Fail(f"register '{reg}' is not declared in .claude/agent-sync.json")
        path = self.root / spec["file"]
        if not path.exists():
            raise Fail(f"register file {spec['file']} does not exist")
        m = re.search(spec["nextFreeIdPattern"], path.read_text())
        if not m:
            raise Fail(f"could not read the next free id out of {spec['file']}")
        return int(m.group(1))

    def release_id(self, reg: str, value: str) -> None:
        if self.adapter.is_lease_authority:
            self.adapter.log_append(self.log_id("reservations"),
                                    fmt_line("release_id", reg, self.rid, value=value))

    # -- journal / signals -------------------------------------------------

    def journal(self, text: str) -> None:
        oid = self.adapter.tree_ensure(f"20 Runs/{self.rid}")
        self.adapter.log_append(oid, fmt_line(
            "journal", self.rid, self.rid, sha=head_sha(),
            note=text.replace("`", "'")[:400]))

    def signal(self, dep: str, state: str) -> None:
        allowed = {"filed", "accepted", "delivered", "closed", "refused"}
        if state not in allowed:
            raise Fail(f"state must be one of {sorted(allowed)}")
        self.adapter.log_append(self.log_id("signals"), fmt_line(
            "signal", dep, self.rid, state=state, repo=repo_name(), sha=head_sha()))

    # -- awareness ---------------------------------------------------------

    def _watermark(self, which: str) -> int:
        p = self.root / STATE_DIR / "seen.json"
        try:
            return int(json.loads(p.read_text()).get(which, 0))
        except (OSError, ValueError, AttributeError):
            return 0

    def _set_watermark(self, which: str, value: int) -> None:
        p = self.root / STATE_DIR / "seen.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            data = {}
        data[which] = value
        p.write_text(json.dumps(data))

    def activity(self, limit: int = 6, mark_read: bool = True) -> dict[str, Any]:
        """What OTHER runs are doing, and what changed since this run last looked.

        Coordination is not only mutual exclusion. An agent that cannot see the
        others is merely blocked by them: it learns a task is taken and nothing
        about who has it, what they are touching, or what landed while it was away.
        """
        others = {k: v for k, v in self.all_holders().items() if v != self.rid}

        signals, _ = self.events("signals")
        seen = self._watermark("signals")
        fresh = signals[seen:] if len(signals) > seen else []
        if mark_read:
            self._set_watermark("signals", len(signals))

        return {"others": others, "signals": signals[-limit:], "new_signals": fresh}

    # -- guard -------------------------------------------------------------

    def guard(self, path: str) -> tuple[bool, str]:
        rel = os.path.relpath(os.path.abspath(path), str(self.root))
        patterns = self.cfg.get("guardedFiles") or []
        if not any(Path(rel).match(p) for p in patterns):
            return True, "not a guarded file"

        # A lease is required in every mode. What differs between backends is how
        # strongly it is arbitrated, and that is what `gated` reports — not whether
        # the check runs. A local lock file is genuine mutual exclusion between
        # agents on one machine; it is only across machines that fs cannot arbitrate.
        held = self.held()
        if held:
            note = "" if self.gated else " (advisory: arbitrated locally only)"
            return True, f"held by this run ({', '.join(held)}){note}"

        other = self._any_other_holder()
        who = f" — {other} holds a lease right now" if other else ""
        return False, (f"{rel} is a guarded registry file and this run holds no lease{who}. "
                       f"Acquire one first: agent_sync.py acquire <TASK-ID>")

    def _any_other_holder(self) -> str | None:
        if self.adapter.is_lease_authority:
            events, _ = self.events("claims")
            now = time.time()
            for key in {e["key"] for e in events}:
                holder = resolve_holder(events, key, now)
                if holder and holder != self.rid:
                    return holder
            return None
        d = self.root / STATE_DIR / "leases"
        for p in (d.glob("*.lock") if d.exists() else []):
            try:
                held = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if held.get("run") != self.rid and \
                    time.time() <= parse_iso(held.get("ts", "")) + int(held.get("ttl", self.ttl)):
                return str(held.get("run"))
        return None

    # -- board -------------------------------------------------------------

    def all_holders(self) -> dict[str, str]:
        """Every key currently held, by whom — from whichever store this backend uses."""
        if self.adapter.is_lease_authority:
            events, _ = self.events("claims")
            now = time.time()
            out = {}
            for key in sorted({e["key"] for e in events}):
                holder = resolve_holder(events, key, now)
                if holder:
                    out[key] = holder
            return out
        out = {}
        d = self.root / STATE_DIR / "leases"
        for p in sorted(d.glob("*.lock") if d.exists() else []):
            try:
                held = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if time.time() <= parse_iso(held.get("ts", "")) + int(held.get("ttl", self.ttl)):
                out[p.stem] = str(held.get("run"))
        return out

    def board(self) -> str:
        events, bad = self.events("claims")
        total = max(len(events) + bad, 1)
        rows = [f"| `{k}` | {h} | held |" for k, h in self.all_holders().items()]
        res_events, _ = self.events("reservations")

        lines = [
            f"{GENERATED_MARKER} source={repo_name()}@{head_sha()} at={now_iso()} "
            "— edit in git, not here -->",
            "",
            f"# Board — {repo_name()}",
            "",
            f"- backend: `{self.adapter.name}` · lease authority: "
            f"**{'yes' if self.adapter.is_lease_authority else 'no'}**",
            f"- runs are recorded as **{'gated' if self.gated else 'ungated'}**",
            f"- unparseable log lines: {bad}/{total}"
            f"{'  ⚠ over 2% — the log cannot be replayed reliably' if bad / total > 0.02 else ''}",
            "",
            "## Live leases",
            "",
            "| Key | Holder | State |",
            "|---|---|---|",
        ]
        lines += rows or ["| — | — | none held |"]

        sig, _ = self.events("signals")
        if sig:
            lines += ["", "## Recent cross-repo signals", "",
                      "| Dependency | State | By | Repo |", "|---|---|---|---|"]
            for ev in sig[-10:]:
                lines.append(f"| `{ev['key']}` | {ev.get('state','?')} | {ev['run']} "
                             f"| {ev.get('repo','—')} |")

        leaks = self._leaks(res_events)
        if leaks:
            lines += ["", "## Reserved ids not found in git", ""]
            lines += [f"- `{r}-{v:04d}` reserved by {run}" for r, v, run in leaks]
        return "\n".join(lines) + "\n"

    def _leaks(self, events: list[dict[str, str]]) -> list[tuple[str, int, str]]:
        out = []
        for reg, spec in (self.cfg.get("idRegisters") or {}).items():
            _b, _f, assignments = resolve_reservations(events, reg)
            path = self.root / spec["file"]
            text = path.read_text() if path.exists() else ""
            for run, value in assignments:
                if f"{reg}-{value:04d}" not in text:
                    out.append((reg, value, run))
        return out

    def put_generated(self, path: str, text: str) -> str:
        oid = self.adapter.tree_ensure(path)
        current = self.adapter.doc_get(oid)
        if current.strip() and not current.lstrip().startswith(GENERATED_MARKER):
            return (f"REFUSED: '{path}' was not written by agent-sync "
                    "(no generated marker on line 1). Someone took it over; "
                    "reporting instead of overwriting.")
        self.adapter.doc_put(oid, text)
        return f"wrote '{path}'"


# --------------------------------------------------------------------------- init

ENV_TEMPLATE = """# agent-sync — identity lives here, shape lives in .claude/agent-sync.json
# This file is gitignored on purpose. Never commit it, never paste its contents.
AGENT_SYNC_BACKEND={backend}
{extra}"""


def cmd_init(args: argparse.Namespace) -> int:
    root = project_root()
    os.chdir(root)
    cfg_path = root / CONFIG_PATH
    backend = args.backend

    if backend == "outline" and not args.url:
        raise Fail("--url is required for the outline backend "
                   "(the instance URL, e.g. https://wiki.example.com)")

    if cfg_path.exists() and not args.force:
        print(f"• {CONFIG_PATH} already exists — left untouched (use --force to replace)")
    else:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(default_config(backend), indent=2) + "\n")
        print(f"✓ wrote {CONFIG_PATH}")

    extra = ""
    if backend == "outline":
        extra = (f"AGENT_SYNC_OUTLINE_URL={args.url}\n"
                 "AGENT_SYNC_OUTLINE_TOKEN=\n"
                 "AGENT_SYNC_OUTLINE_COLLECTION=\n")
    env_path = root / ENV_FILE
    if env_path.exists() and not args.force:
        print(f"• {ENV_FILE} already exists — left untouched")
    else:
        env_path.write_text(ENV_TEMPLATE.format(backend=backend, extra=extra))
        os.chmod(env_path, stat.S_IRUSR | stat.S_IWUSR)
        print(f"✓ wrote {ENV_FILE} (mode 600)")

    ensure_gitignored(root, str(ENV_FILE))
    ensure_gitignored(root, f"{STATE_DIR}/")

    print()
    if backend == "outline":
        print("NEXT — two things only you can do:")
        print(f"  1. Create an API token in your Outline instance at {args.url}")
        print("     (Settings → API and access), then put it in this line of "
              f"{ENV_FILE}:")
        print("       AGENT_SYNC_OUTLINE_TOKEN=<paste it here>")
        print(f"  2. Load the file into your shell before running agents:")
        print(f"       set -a && . ./{ENV_FILE} && set +a")
        print()
        print("  Then run `status` again — it will create the cloud layout and print "
              "the collection id to paste into AGENT_SYNC_OUTLINE_COLLECTION.")
        print()
        print("  The token is yours alone: do not paste it into a chat, a commit, "
              "or a command line.")
    else:
        print("Backend 'fs' needs no credentials. It is DEGRADED: it is not the lease")
        print("authority, and every run is recorded as `ungated`. See references/backend-fs.md.")
    return 0


def default_config(backend: str) -> dict[str, Any]:
    return {
        "backend": backend,
        "leaseTtlSeconds": DEFAULT_TTL,
        "renewIntervalSeconds": DEFAULT_RENEW,
        "gated": True,
        "idRegisters": {},
        "guardedFiles": [],
        "claimTags": {},
        "gates": [],
        "mirror": {"enabled": False, "sources": []},
    }


def ensure_gitignored(root: Path, entry: str) -> None:
    gi = root / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    if any(line.strip() == entry for line in lines):
        print(f"• .gitignore already ignores {entry}")
        return
    header = "# agent-sync"
    with open(gi, "a") as fh:
        if lines and lines[-1].strip():
            fh.write("\n")
        if header not in lines:
            fh.write(f"{header}\n")
        fh.write(f"{entry}\n")
    print(f"✓ added {entry} to .gitignore")


# --------------------------------------------------------------------------- status

def cmd_status(_args: argparse.Namespace) -> int:
    root = project_root()
    os.chdir(root)
    print(f"agent-sync {VERSION} — {repo_name()}@{head_sha()}")

    if not (root / CONFIG_PATH).exists():
        print("\n✗ not initialised.")
        print("\nNEXT: run init. It asks nothing it can guess and writes nothing secret.")
        print("  agent_sync.py init --backend outline --url <instance-url>")
        print("  agent_sync.py init --backend fs        # local, degraded, no credentials")
        return 1

    s = Sync()
    ad = s.adapter
    print(f"  backend        : {ad.name}")
    print(f"  lease authority: {'yes' if ad.is_lease_authority else 'NO — degraded'}")
    print(f"  runs recorded  : {'gated' if s.gated else 'UNGATED'}")
    print(f"  run id         : {s.rid}")

    if not ad.is_lease_authority:
        print("\n⚠ This backend cannot hold leases exclusively, so nothing here is")
        print("  enforced. Do not describe this project as protected.")

    if ad.name == "outline" and isinstance(ad, OutlineAdapter) and not ad.collection:
        print("\n✗ AGENT_SYNC_OUTLINE_COLLECTION is empty.")
        print("\nNEXT: create the container, then paste the id into "
              f"{ENV_FILE}:")
        print("  agent_sync.py bootstrap")
        return 1

    try:
        held = s.held()
    except Fail as exc:
        print(f"\n✗ {exc}")
        return 1
    print(f"  leases held    : {', '.join(held) if held else 'none'}")

    # Who else is in here, and what landed while this run was away. Without this a
    # lease only tells an agent it is blocked, never who by or on what.
    try:
        act = s.activity()
    except Fail as exc:
        print(f"\n⚠ could not read the coordination plane: {exc}")
        act = {"others": {}, "signals": [], "new_signals": []}

    if act["others"]:
        print("\n  Other runs working this project right now:")
        for key, holder in sorted(act["others"].items()):
            print(f"    · {holder} holds {key}")
        print("    Do not take these on. If one looks abandoned, its lease expires on its own.")
    else:
        print("  other runs     : none holding anything")

    if act["new_signals"]:
        print(f"\n  New since you last looked ({len(act['new_signals'])}):")
        for ev in act["new_signals"][-6:]:
            print(f"    · {ev['key']} → {ev.get('state', '?')} "
                  f"(by {ev['run']}, {ev.get('repo', 'unknown repo')})")
        print("    A dependency that moved may unblock — or invalidate — what you were about to do.")
    elif act["signals"]:
        print(f"  signals        : {len(act['signals'])} recent, nothing new since you last looked")

    if not pipeline_installed():
        print("\n✗ task-pipeline is not installed. agent-sync binds to its stages and")
        print("  will not improvise a substitute flow.")
        print("\nNEXT:\n  npx sshlg-skills install")
        return 1

    print("\nNEXT: acquire a lease before you touch a guarded file —")
    print("  agent_sync.py acquire <TASK-ID>")
    return 0


def pipeline_installed() -> bool:
    home = Path.home()
    if list(home.glob(".claude/plugins/cache/task-pipeline/**/skills/task-pipeline/SKILL.md")):
        return True
    if (home / ".agents/skills/task-pipeline/SKILL.md").exists():
        return True
    return (home / ".claude/skills/task-pipeline/SKILL.md").exists()


def cmd_bootstrap(_args: argparse.Namespace) -> int:
    ad = OutlineAdapter()
    if not ad.configured():
        raise Fail("set AGENT_SYNC_OUTLINE_URL and AGENT_SYNC_OUTLINE_TOKEN first")
    if ad.collection:
        print(f"collection already set: {ad.collection}")
        return 0
    name = f"agent-sync — {repo_name()}"
    data = ad._call("collections.create", {"name": name, "description":
                                           "Coordination plane for agent-sync. Generated pages "
                                           "are stamped; edit sources in git."})
    print(f"✓ created collection '{name}'")
    print(f"\nNEXT: put this in {ENV_FILE}:")
    print(f"  AGENT_SYNC_OUTLINE_COLLECTION={data['id']}")
    return 0


# --------------------------------------------------------------------------- cli

def cmd_acquire(args: argparse.Namespace) -> int:
    s = Sync()
    won, holder = s.acquire(args.key)
    if won:
        print(f"won {args.key} (run {s.rid}, ttl {s.ttl}s)")
        if not s.gated:
            print("⚠ ungated backend — this lease is advisory, not enforced")
        print("Remember: release it on every path, including failure.")
        return 0
    print(f"lost {args.key} — held by {holder or 'another run'}")
    return 1


def cmd_renew(args: argparse.Namespace) -> int:
    Sync().renew(args.key)
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    Sync().release(args.key)
    print(f"released {args.key}")
    return 0


def cmd_reserve(args: argparse.Namespace) -> int:
    value = Sync().reserve(args.register)
    print(f"{args.register}-{value:04d}")
    return 0


def cmd_release_id(args: argparse.Namespace) -> int:
    Sync().release_id(args.register, args.value)
    print(f"released {args.register}-{args.value}")
    return 0


def cmd_journal(args: argparse.Namespace) -> int:
    Sync().journal(" ".join(args.text))
    return 0


def cmd_signal(args: argparse.Namespace) -> int:
    Sync().signal(args.dep, args.state)
    print(f"{args.dep} → {args.state}")
    return 0


def cmd_guard(args: argparse.Namespace) -> int:
    """Exit 0 = allowed, 2 = denied. Any other code is non-blocking in Claude Code,
    so internal failures must also exit 2 rather than fail open."""
    try:
        allowed, reason = Sync().guard(args.path)
    except Fail as exc:
        print(f"agent-sync guard: {exc}", file=sys.stderr)
        return 2
    if allowed:
        print(reason)
        return 0
    print(f"agent-sync: {reason}", file=sys.stderr)
    return 2


def cmd_board(_args: argparse.Namespace) -> int:
    s = Sync()
    result = s.put_generated("10 Board", s.board())
    print(result)
    # A refusal must be visible to a gate, not just to a reader.
    return 1 if result.startswith("REFUSED") else 0


def cmd_whoami(_args: argparse.Namespace) -> int:
    s = Sync()
    print(f"run {s.rid} · backend {s.adapter.name} · "
          f"{'gated' if s.gated else 'ungated'}")
    print(f"holds: {', '.join(s.held()) or 'nothing'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent_sync.py", description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="ask where to store, write config and env file")
    i.add_argument("--backend", required=True, choices=["outline", "fs"])
    i.add_argument("--url", help="instance URL (required for outline)")
    i.add_argument("--force", action="store_true")
    i.set_defaults(fn=cmd_init)

    sub.add_parser("status", help="inspect, repair, report, one next action").set_defaults(fn=cmd_status)
    sub.add_parser("bootstrap", help="create the cloud container").set_defaults(fn=cmd_bootstrap)
    sub.add_parser("whoami", help="this run and its leases").set_defaults(fn=cmd_whoami)
    sub.add_parser("board", help="regenerate the read-only board").set_defaults(fn=cmd_board)

    for name, fn, arg in (("acquire", cmd_acquire, "key"), ("release", cmd_release, "key")):
        q = sub.add_parser(name)
        q.add_argument(arg)
        q.set_defaults(fn=fn)

    r = sub.add_parser("renew")
    r.add_argument("key", nargs="?")
    r.set_defaults(fn=cmd_renew)

    rv = sub.add_parser("reserve", help="reserve the next id in a register")
    rv.add_argument("register")
    rv.set_defaults(fn=cmd_reserve)

    ri = sub.add_parser("release-id", help="return an id you did not write to git")
    ri.add_argument("register")
    ri.add_argument("value")
    ri.set_defaults(fn=cmd_release_id)

    j = sub.add_parser("journal")
    j.add_argument("text", nargs="+")
    j.set_defaults(fn=cmd_journal)

    sg = sub.add_parser("signal")
    sg.add_argument("dep")
    sg.add_argument("state")
    sg.set_defaults(fn=cmd_signal)

    g = sub.add_parser("guard", help="may this run write that path? exit 2 = no")
    g.add_argument("path")
    g.set_defaults(fn=cmd_guard)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except Fail as exc:
        print(f"agent-sync: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
