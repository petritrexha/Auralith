"""Server-side secret scrubbing (defense in depth — the plugin scrubs first).

Keep the patterns in sync with plugin/scripts/learnloop_common.py.
"""
import re

SECRET_FILE_PATTERNS = [
    r"(^|/)\.env(\..*)?$",
    r"\.(pem|key|p12|pfx|jks|keystore|crt|cer|der)$",
    r"(^|/)id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$",
    r"(^|/)\.npmrc$",
    r"(^|/)\.pypirc$",
    r"(^|/)\.netrc$",
    r"(^|/)credentials(\.json)?$",
    r"(^|/)secrets?\.(json|ya?ml|toml)$",
    r"appsettings\.(Production|Development|Staging)?\.?json$",
]

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
    # key = "value" style assignments for obviously secret names
    (
        re.compile(
            r"(?i)((?:api[_-]?key|secret|password|passwd|pwd|token|access[_-]?key|private[_-]?key|client[_-]?secret)"
            r"[\"']?\s*[:=]\s*)([\"'])([^\"'\n]{6,})\2"
        ),
        r"\1\2[REDACTED]\2",
    ),
]

_secret_file_res = [re.compile(p, re.IGNORECASE) for p in SECRET_FILE_PATTERNS]


def is_secret_file(path: str) -> bool:
    norm = path.replace("\\", "/")
    return any(r.search(norm) for r in _secret_file_res)


def scrub_text(text: str) -> str:
    for pattern, repl in SECRET_VALUE_PATTERNS:
        text = pattern.sub(repl, text)
    return text
