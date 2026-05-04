"""Operator alerts for queue-owned NotebookLM failures."""

from __future__ import annotations

import json
import os
import smtplib
import socket
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from .constants import STATE_DEAD_LETTER, STATE_RETRY_SCHEDULED
from .store import QueueStore, _load_json, _write_json_atomic, utc_now_iso

AUTH_ERROR_TOKENS = (
    "authentication expired",
    "auth expired",
    "auth invalid",
    "invalid authentication",
    "not logged in",
    "run 'notebooklm login'",
    "redirected to",
    "403",
)
RATE_LIMIT_ERROR_TOKENS = (
    "rate limit",
    "quota exceeded",
    "resource_exhausted",
    "429",
    "too many requests",
)

ALERT_KIND_AUTH_STALE = "auth_stale"
ALERT_KIND_RATE_LIMIT_EXHAUSTED = "rate_limit_exhausted"
ALERT_KIND_DEAD_LETTER = "dead_letter"


@dataclass(frozen=True, slots=True)
class AlertDecision:
    kind: str
    fingerprint: str
    summary: str


def _alerts_root(store: QueueStore) -> Path:
    return store.root / "alerts"


def _alerts_state_path(store: QueueStore) -> Path:
    return _alerts_root(store) / "state.json"


def _show_alerts_root(store: QueueStore, show_slug: str) -> Path:
    return _alerts_root(store) / show_slug


def _lowered(text: str | None) -> str:
    return str(text or "").lower()


def _int_env(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _alert_dedup_seconds() -> int:
    return _int_env("NOTEBOOKLM_QUEUE_ALERT_DEDUP_SECONDS", 21600)


def _rate_limit_alert_attempts() -> int:
    return _int_env("NOTEBOOKLM_QUEUE_RATE_LIMIT_ALERT_ATTEMPTS", 3)


def _command_timeout_seconds() -> int:
    return _int_env("NOTEBOOKLM_QUEUE_ALERT_COMMAND_TIMEOUT_SECONDS", 30)


def _webhook_timeout_seconds() -> int:
    return _int_env("NOTEBOOKLM_QUEUE_ALERT_WEBHOOK_TIMEOUT_SECONDS", 15)


def _smtp_timeout_seconds() -> int:
    return _int_env("NOTEBOOKLM_QUEUE_ALERT_SMTP_TIMEOUT_SECONDS", 15)


def _resend_api_url() -> str:
    return str(os.environ.get("NOTEBOOKLM_QUEUE_RESEND_API_URL") or "").strip() or "https://api.resend.com/emails"


def _looks_like_auth_error(text: str | None) -> bool:
    lowered = _lowered(text)
    return any(token in lowered for token in AUTH_ERROR_TOKENS)


def _looks_like_rate_limit(text: str | None) -> bool:
    lowered = _lowered(text)
    return any(token in lowered for token in RATE_LIMIT_ERROR_TOKENS)


def classify_failure_alert(
    *,
    failed_state: str,
    error_text: str | None,
    job: dict[str, Any],
) -> AlertDecision | None:
    show_slug = str(job.get("show_slug") or "").strip()
    lecture_key = str(job.get("lecture_key") or "").strip()
    attempt_count = int(job.get("attempt_count") or 0)

    if failed_state == STATE_DEAD_LETTER:
        return AlertDecision(
            kind=ALERT_KIND_DEAD_LETTER,
            fingerprint=f"{ALERT_KIND_DEAD_LETTER}:{show_slug}:{lecture_key}",
            summary=f"Queue job moved to dead letter for {show_slug} {lecture_key}",
        )

    if _looks_like_auth_error(error_text):
        return AlertDecision(
            kind=ALERT_KIND_AUTH_STALE,
            fingerprint=f"{ALERT_KIND_AUTH_STALE}:{show_slug}",
            summary=f"NotebookLM auth appears stale for {show_slug} {lecture_key}",
        )

    if (
        failed_state == STATE_RETRY_SCHEDULED
        and _looks_like_rate_limit(error_text)
        and attempt_count >= max(_rate_limit_alert_attempts(), 1)
    ):
        return AlertDecision(
            kind=ALERT_KIND_RATE_LIMIT_EXHAUSTED,
            fingerprint=f"{ALERT_KIND_RATE_LIMIT_EXHAUSTED}:{show_slug}",
            summary=f"NotebookLM rate limits persist for {show_slug} {lecture_key}",
        )

    return None


def emit_failure_alert(
    *,
    store: QueueStore,
    show_slug: str,
    job: dict[str, Any],
    manifest: dict[str, Any],
    failed_state: str,
    error_text: str | None,
    note: str,
) -> dict[str, Any] | None:
    decision = classify_failure_alert(
        failed_state=failed_state,
        error_text=error_text,
        job=job,
    )
    if decision is None:
        return None

    now = datetime.now(tz=UTC)
    occurred_at = now.replace(microsecond=0).isoformat()
    dedup_seconds = max(_alert_dedup_seconds(), 0)

    state = _load_json(_alerts_state_path(store))
    seen = state.get("seen") if isinstance(state.get("seen"), dict) else {}
    last_seen_raw = seen.get(decision.fingerprint) if isinstance(seen, dict) else None
    last_seen_at = None
    if isinstance(last_seen_raw, str):
        try:
            last_seen_at = datetime.fromisoformat(last_seen_raw)
        except ValueError:
            last_seen_at = None
    suppressed = False
    if dedup_seconds > 0 and last_seen_at is not None:
        suppressed = (now - last_seen_at).total_seconds() < dedup_seconds

    alert_payload: dict[str, Any] = {
        "version": 1,
        "occurred_at": occurred_at,
        "kind": decision.kind,
        "summary": decision.summary,
        "fingerprint": decision.fingerprint,
        "suppressed": suppressed,
        "show_slug": show_slug,
        "subject_slug": str(job.get("subject_slug") or ""),
        "job_id": str(job.get("job_id") or ""),
        "lecture_key": str(job.get("lecture_key") or ""),
        "content_types": list(job.get("content_types") or []),
        "state": failed_state,
        "attempt_count": int(job.get("attempt_count") or 0),
        "note": note,
        "error": str(error_text or ""),
        "run_id": str(manifest.get("run_id") or ""),
        "manifest_phase_names": [str(phase.get("name") or "") for phase in list(manifest.get("phases") or [])],
        "manifest_path": str(
            dict(job.get("artifacts") or {}).get("execution", {}).get("latest_run_manifest") or ""
        ),
        "host": socket.gethostname(),
        "deliveries": [],
    }

    if not suppressed:
        alert_payload["deliveries"].extend(_deliver_alert(alert_payload))
        if isinstance(seen, dict):
            seen[decision.fingerprint] = occurred_at
        state["seen"] = seen
        _write_json_atomic(_alerts_state_path(store), state)

    alerts_root = _show_alerts_root(store, show_slug)
    alerts_root.mkdir(parents=True, exist_ok=True)
    filename = f"{occurred_at.replace(':', '').replace('-', '')}-{decision.kind}-{job.get('job_id')}.json"
    alert_path = alerts_root / filename
    _write_json_atomic(alert_path, alert_payload)
    alert_payload["alert_path"] = str(alert_path)
    return alert_payload


def _deliver_alert(payload: dict[str, Any]) -> list[dict[str, Any]]:
    deliveries: list[dict[str, Any]] = []

    webhook_url = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_WEBHOOK_URL") or "").strip()
    if webhook_url:
        deliveries.append(_deliver_webhook(payload, webhook_url))

    email_to = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_EMAIL_TO") or "").strip()
    if email_to:
        deliveries.append(_deliver_email(payload, email_to))

    command = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_COMMAND") or "").strip()
    if command:
        deliveries.append(_deliver_command(payload, command))

    return deliveries


def _deliver_webhook(payload: dict[str, Any], webhook_url: str) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    bearer = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_WEBHOOK_BEARER_TOKEN") or "").strip()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib_request.Request(webhook_url, data=body, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=max(_webhook_timeout_seconds(), 1)) as response:
            return {
                "channel": "webhook",
                "status": "sent",
                "http_status": int(getattr(response, "status", 200)),
            }
    except urllib_error.HTTPError as exc:
        return {"channel": "webhook", "status": "failed", "error": f"HTTP {exc.code}"}
    except urllib_error.URLError as exc:
        return {"channel": "webhook", "status": "failed", "error": str(exc.reason)}


def _deliver_email(payload: dict[str, Any], email_to: str) -> dict[str, Any]:
    resend_key = str(os.environ.get("NOTEBOOKLM_QUEUE_RESEND_API_KEY") or "").strip()
    if resend_key:
        return _deliver_resend_email(payload, email_to, resend_key)

    smtp_host = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_SMTP_HOST") or "").strip()
    if not smtp_host:
        return {
            "channel": "email",
            "status": "skipped",
            "error": "No NOTEBOOKLM_QUEUE_RESEND_API_KEY or NOTEBOOKLM_QUEUE_ALERT_SMTP_HOST configured.",
        }

    smtp_port = int(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_SMTP_PORT") or "587")
    smtp_user = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_SMTP_USER") or "").strip()
    smtp_password = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_SMTP_PASSWORD") or "").strip()
    smtp_use_tls = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_SMTP_USE_TLS") or "1").strip() not in {"0", "false", "False"}
    smtp_use_ssl = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_SMTP_USE_SSL") or "0").strip() in {"1", "true", "True"}
    from_email = (
        str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_EMAIL_FROM") or "").strip()
        or f"notebooklm-queue@{socket.gethostname()}"
    )

    message = EmailMessage()
    message["Subject"] = _email_subject(payload)
    message["From"] = from_email
    message["To"] = email_to
    message.set_content(_email_body(payload))

    try:
        smtp_cls = smtplib.SMTP_SSL if smtp_use_ssl else smtplib.SMTP
        with smtp_cls(smtp_host, smtp_port, timeout=max(_smtp_timeout_seconds(), 1)) as client:
            if smtp_use_tls and not smtp_use_ssl:
                client.starttls()
            if smtp_user or smtp_password:
                client.login(smtp_user, smtp_password)
            client.send_message(message)
    except Exception as exc:  # pragma: no cover - transport-specific failure path
        return {"channel": "email", "status": "failed", "error": str(exc)}
    return {"channel": "email", "status": "sent", "recipient": email_to}


def _deliver_resend_email(payload: dict[str, Any], email_to: str, api_key: str) -> dict[str, Any]:
    from_email = (
        str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_EMAIL_FROM") or "").strip()
        or "noreply@freudd.dk"
    )
    resend_payload = {
        "from": from_email,
        "to": [email_to],
        "subject": _email_subject(payload),
        "text": _email_body(payload),
    }
    req = urllib_request.Request(
        _resend_api_url(),
        data=json.dumps(resend_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=max(_webhook_timeout_seconds(), 1)) as response:
            return {
                "channel": "email",
                "provider": "resend",
                "status": "sent",
                "http_status": int(getattr(response, "status", 200)),
            }
    except urllib_error.HTTPError as exc:
        return {"channel": "email", "provider": "resend", "status": "failed", "error": f"HTTP {exc.code}"}
    except urllib_error.URLError as exc:
        return {"channel": "email", "provider": "resend", "status": "failed", "error": str(exc.reason)}


def _deliver_command(payload: dict[str, Any], command: str) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(
        {
            "NOTEBOOKLM_QUEUE_ALERT_KIND": str(payload.get("kind") or ""),
            "NOTEBOOKLM_QUEUE_ALERT_SUMMARY": str(payload.get("summary") or ""),
            "NOTEBOOKLM_QUEUE_ALERT_SHOW_SLUG": str(payload.get("show_slug") or ""),
            "NOTEBOOKLM_QUEUE_ALERT_LECTURE_KEY": str(payload.get("lecture_key") or ""),
            "NOTEBOOKLM_QUEUE_ALERT_JOB_ID": str(payload.get("job_id") or ""),
            "NOTEBOOKLM_QUEUE_ALERT_STATE": str(payload.get("state") or ""),
        }
    )
    try:
        completed = subprocess.run(
            ["bash", "-lc", command],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=max(_command_timeout_seconds(), 1),
            env=env,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - subprocess failure path
        return {"channel": "command", "status": "failed", "error": str(exc), "command": command}
    result = {
        "channel": "command",
        "status": "sent" if completed.returncode == 0 else "failed",
        "command": command,
        "returncode": int(completed.returncode),
    }
    if completed.stdout.strip():
        result["stdout"] = completed.stdout.strip()
    if completed.stderr.strip():
        result["stderr"] = completed.stderr.strip()
    return result


def _email_subject(payload: dict[str, Any]) -> str:
    prefix = str(os.environ.get("NOTEBOOKLM_QUEUE_ALERT_SUBJECT_PREFIX") or "[NotebookLM Queue]").strip()
    summary = str(payload.get("summary") or "Queue alert").strip()
    return f"{prefix} {summary}"


def _email_body(payload: dict[str, Any]) -> str:
    lines = [
        str(payload.get("summary") or ""),
        "",
        f"Kind: {payload.get('kind') or ''}",
        f"Show: {payload.get('show_slug') or ''}",
        f"Lecture: {payload.get('lecture_key') or ''}",
        f"Job: {payload.get('job_id') or ''}",
        f"State: {payload.get('state') or ''}",
        f"Attempt: {payload.get('attempt_count') or ''}",
        f"Host: {payload.get('host') or ''}",
        f"Occurred at: {payload.get('occurred_at') or ''}",
        "",
        "Error:",
        str(payload.get("error") or ""),
    ]
    return "\n".join(lines).strip() + "\n"
