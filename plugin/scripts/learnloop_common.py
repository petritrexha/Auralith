"""Shared helpers for the LearnLoop hook scripts. Standard library only.

Golden rule: nothing in here may ever break a coding session. Every public function
swallows its own errors, and the hook scripts always exit 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "0.1.0"
MAX_DIFF_CHARS = 6000          # per change entry
MAX_BATCH_BYTES = 250_000      # per session batch file
SEND_TIMEOUT = 20              # seconds; the Stop hook itself has a 30s timeout


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def config() -> dict:
    """Plugin options (set in Claude Code's plugin config) win; env vars are the fallback."""
    url = os.environ.get("CLAUDE_PLUGIN_OPTION_SERVER_URL") or os.environ.get("LEARNLOOP_URL") or ""
    token = os.environ.get("CLAUDE_PLUGIN_OPTION_API_TOKEN") or os.environ.get("LEARNLOOP_TOKEN") or ""
    return {
        "url": url.strip().rstrip("/"),
        "token": token.strip(),
        "disabled": os.environ.get("LEARNLOOP_DISABLED", "").lower() in {"1", "true", "yes"},
    }


def state_dir() -> Path:
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(Path.home(), ".learnloop")
    path = Path(base) / "batches"
    path.mkdir(parents=True, exist_ok=True)
    return path


def batch_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", session_id or "default")[:80]
    return state_dir() / f"{safe}.jsonl"


def read_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Secret scrubbing (keep in sync with server/core/services/scrub.py)
# ---------------------------------------------------------------------------
SECRET_FILE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r"(^|/)\.env(\..*)?$",
    r"\.(pem|key|p12|pfx|jks|keystore|crt|cer|der)$",
    r"(^|/)id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$",
    r"(^|/)\.npmrc$",
    r"(^|/)\.pypirc$",
    r"(^|/)\.netrc$",
    r"(^|/)credentials(\.json)?$",
    r"(^|/)secrets?\.(json|ya?ml|toml)$",
    r"appsettings\.(Production|Development|Staging)?\.?json$",
]]

SECRET_VALUE_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"\bll_[A-Za-z0-9_\-]{20,}"), "[REDACTED_LEARNLOOP_TOKEN]"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)\b(mongodb(\+srv)?|postgres(ql)?|mysql|redis|amqp)://[^\s'\"]+"), r"\1://[REDACTED_URL]"),
    (re.compile(
        r"(?i)((?:api[_-]?key|secret|password|passwd|pwd|token|access[_-]?key|private[_-]?key|client[_-]?secret)"
        r"[\"']?\s*[:=]\s*)([\"'])([^\"'\n]{6,})\2"), r"\1\2[REDACTED]\2"),
]


def is_secret_file(path: str) -> bool:
    norm = (path or "").replace("\\", "/")
    return any(p.search(norm) for p in SECRET_FILE_PATTERNS)


def scrub(text: str) -> str:
    for pattern, repl in SECRET_VALUE_PATTERNS:
        text = pattern.sub(repl, text)
    return text


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def api_call(method: str, path: str, body: dict | None = None, timeout: float = SEND_TIMEOUT) -> dict | None:
    """Call the LearnLoop server. Returns parsed JSON, or None on any failure."""
    cfg = config()
    if not cfg["url"] or not cfg["token"] or cfg["disabled"]:
        return None
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        cfg["url"] + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {cfg['token']}",
            "Content-Type": "application/json",
            "User-Agent": f"learnloop-claude-plugin/{VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return {"_status": exc.code, **json.loads(exc.read().decode("utf-8") or "{}")}
        except Exception:
            return {"_status": exc.code}
    except Exception:
        return None


def debug(msg: str) -> None:
    """Opt-in log file for troubleshooting: set LEARNLOOP_DEBUG=1."""
    if os.environ.get("LEARNLOOP_DEBUG"):
        try:
            with open(state_dir().parent / "debug.log", "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        except Exception:
            pass
