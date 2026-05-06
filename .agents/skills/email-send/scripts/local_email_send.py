#!/usr/bin/env python3
"""Send a one-off email campaign from local files.

Reads recipients (JSON or CSV), an HTML body with optional ``{name}``
placeholders, and SMTP credentials from a local ``.env`` file. Validates
everything, then sends one message per recipient over a single SMTP
connection.

Usage::

  .venv/bin/python .agents/skills/email-send/scripts/local_email_send.py \\
    --env path/to/.env --subject "Hello" \\
    --recipients path/to/list.json --html path/to/body.html \\
    --attach file1.pdf --attach file2.docx
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import smtplib
import sys
import time
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import StringIO
from pathlib import Path
from typing import Any

# Make sibling validators.py importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402
from validators import (  # noqa: E402
    ValidationError,
    validate_html,
    validate_json_size,
    validate_local_attachment_paths,
    validate_recipient_fields_for_template,
    validate_recipients_data,
    validate_subject,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recipients parsing (.json or .csv)
# ---------------------------------------------------------------------------

# Headers that count as the "email" column in CSV uploads.
_EMAIL_HEADER_ALIASES: frozenset[str] = frozenset({
    "email", "e-mail", "e_mail", "mail", "emailaddress",
})


def _normalize_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.strip().lower())


def _header_to_field(h: str) -> str:
    """Map a CSV column header to a recipient-dict key. Email aliases collapse to ``email``."""
    if not h or not h.strip():
        return h
    return "email" if _normalize_header(h) in _EMAIL_HEADER_ALIASES else h.strip()


def _parse_csv(text: str) -> list[dict[str, Any]]:
    """CSV: first row is header; needs a column recognizable as email.

    Delimiter: comma; if no comma in the first non-empty line but a semicolon is
    present, use ';'.
    """
    text = text.strip()
    if not text:
        raise ValidationError("Recipients file is empty")

    first = next((line for line in text.splitlines() if line.strip()), "")
    if not first:
        raise ValidationError("No data in recipients file")
    delimiter = ";" if ("," not in first and ";" in first) else ","

    reader = csv.DictReader(StringIO(text), delimiter=delimiter, skipinitialspace=True)
    if not reader.fieldnames:
        raise ValidationError("CSV has no header row")

    headers = [(raw or "").strip() for raw in reader.fieldnames]
    if not any(_header_to_field(h) == "email" for h in headers if h):
        raise ValidationError("CSV must have an email column (e.g. email, Email, E-mail)")

    out: list[dict[str, Any]] = []
    for row in reader:
        if not row:
            continue
        recipient: dict[str, Any] = {}
        email: str | None = None
        for raw in reader.fieldnames:
            h = (raw or "").strip()
            if not h:
                continue
            value = (row.get(raw) or "").strip()
            key = _header_to_field(h)
            if key == "email":
                email = value
            else:
                recipient[key] = value
        if not email:
            continue
        recipient["email"] = email
        out.append(recipient)

    if not out:
        raise ValidationError("No recipient rows with an email in CSV")
    return out


def _parse_json(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON: {e}") from e
    if not isinstance(data, list):
        raise ValidationError("Recipients JSON must be an array")
    return data


def load_recipients(path: Path) -> list[dict[str, Any]]:
    """Read a recipients file and parse it by extension (.json or .csv)."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    validate_json_size(text)
    if not text.strip():
        raise ValidationError("Recipients data is empty")

    suffix = path.suffix.lower()
    if suffix == ".json":
        return _parse_json(text)
    if suffix == ".csv":
        return _parse_csv(text)
    raise ValidationError(
        f"Unsupported recipients file extension {suffix!r}; expected .json or .csv"
    )


# ---------------------------------------------------------------------------
# Templating
# ---------------------------------------------------------------------------

def apply_template(html: str, params: dict[str, Any]) -> str:
    """Replace ``{key}`` placeholders in ``html`` with values from ``params``."""
    out = html
    for key, value in params.items():
        out = out.replace("{" + key + "}", str(value))
    return out


# ---------------------------------------------------------------------------
# SMTP parser
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SmtpConfig:
    server: str
    port: int
    username: str
    password: str
    from_address: str          # display name used in the From header
    from_email_address: str    # envelope sender address
    copy_addresses: list[str]
    bcc_addresses: list[str]


def _split_csv_env(value: str) -> list[str]:
    return [a.strip() for a in (value or "").split(",") if a.strip()]


def load_smtp_config_from_env() -> SmtpConfig | None:
    """Build a ``SmtpConfig`` from ``os.environ``; return None if SMTP_SERVER/USERNAME missing."""
    server = os.environ.get("SMTP_SERVER", "").strip()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    if not server or not username:
        return None
    from_email = (
        os.environ.get("FROM_EMAIL")
        or os.environ.get("FROM_EMAIL_ADDRESS")
        or username
    ).strip()
    return SmtpConfig(
        server=server,
        port=int(os.environ.get("SMTP_PORT", "587")),
        username=username,
        password=os.environ.get("SMTP_PASSWORD", ""),
        from_address=os.environ.get("FROM_ADDRESS", "").strip() or "Sender",
        from_email_address=from_email,
        copy_addresses=_split_csv_env(
            os.environ.get("COPY_ADDRESSES") or os.environ.get("CC", "")
        ),
        bcc_addresses=_split_csv_env(
            os.environ.get("BCC_ADDRESSES") or os.environ.get("BCC", "")
        ),
    )


# ---------------------------------------------------------------------------
# Send messages
# ---------------------------------------------------------------------------

def _open_smtp(cfg: SmtpConfig) -> smtplib.SMTP:
    """Open and authenticate a single reusable SMTP connection."""
    server = smtplib.SMTP(cfg.server, cfg.port)
    server.starttls()
    server.login(cfg.username, cfg.password)
    return server


def _build_mime(
    cfg: SmtpConfig,
    subject: str,
    to_address: str,
    body_html: str,
    attachments: list[Path],
) -> tuple[str, list[str]]:
    """Build a MIME message; returns (raw_message, envelope_recipients)."""
    msg = MIMEMultipart("mixed")
    msg["From"] = f'"{cfg.from_address}" <{cfg.from_email_address}>'
    msg["Subject"] = subject
    msg["To"] = to_address

    envelope = [to_address]
    if cfg.copy_addresses:
        msg["Cc"] = ", ".join(cfg.copy_addresses)
        envelope.extend(cfg.copy_addresses)
    if cfg.bcc_addresses:
        # Bcc is envelope-only and must not appear in headers.
        envelope.extend(cfg.bcc_addresses)

    msg.attach(MIMEText(body_html, "html"))

    for path in attachments:
        try:
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", f'attachment; filename="{path.name}"'
                )
                msg.attach(part)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to attach file %s: %s", path, e)

    return msg.as_string(), envelope


def _send_one_with_retry(
    server: smtplib.SMTP,
    cfg: SmtpConfig,
    envelope: list[str],
    raw_msg: str,
) -> smtplib.SMTP:
    """Send one message; on retryable failure reconnect once and retry.

    Retryable: ``SMTPRecipientsRefused`` with a 4xx code (waits 30s),
    ``SMTPServerDisconnected``. Anything else propagates. Returns the live
    connection (possibly a fresh one after a reconnect).
    """
    try:
        server.sendmail(cfg.from_email_address, envelope, raw_msg)
        return server
    except smtplib.SMTPRecipientsRefused as exc:
        code = next(iter(exc.recipients.values()))[0]
        if not (400 <= code < 500):
            raise
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(30)
    except smtplib.SMTPServerDisconnected:
        pass

    server = _open_smtp(cfg)
    server.sendmail(cfg.from_email_address, envelope, raw_msg)
    return server


def send_campaign(
    cfg: SmtpConfig,
    subject: str,
    template_html: str,
    recipients: list[dict[str, Any]],
    attachments: list[Path],
) -> tuple[int, int]:
    """One SMTP connection: throttle, template, MIME, send. Returns ``(sent, failed)``."""
    rate_limit = int(os.environ.get("SMTP_RATE_LIMIT_PER_MIN", "0"))
    delay = (60.0 / rate_limit) if rate_limit > 0 else 0.0

    sent = 0
    failed = 0
    server: smtplib.SMTP | None = None
    try:
        server = _open_smtp(cfg)
        for i, recipient in enumerate(recipients):
            to_address = str(recipient["email"]).strip()
            if i > 0 and delay:
                time.sleep(delay)
            params = {k: v for k, v in recipient.items() if k != "email"}
            try:
                body = apply_template(template_html, params)
                raw_msg, envelope = _build_mime(cfg, subject, to_address, body, attachments)
                server = _send_one_with_retry(server, cfg, envelope, raw_msg)
                sent += 1
            except Exception as err:  # noqa: BLE001
                failed += 1
                logger.warning("Local send failed for %s: %s", to_address, err)
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
    return sent, failed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local email send (no job in DB).")
    parser.add_argument(
        "--env",
        type=Path,
        default=Path(".env"),
        help="Env file with SMTP and optional MAX_* limits (default: .env)",
    )
    parser.add_argument(
        "--recipients",
        type=Path,
        required=True,
        help="JSON array or CSV with header (column email/Email/...); .csv / .json by extension",
    )
    parser.add_argument(
        "--html", type=Path, required=True, help="HTML body (optional {placeholder})"
    )
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument(
        "--attach",
        type=Path,
        action="append",
        default=[],
        help="Attachment (repeat for multiple files)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.env.exists():
        load_dotenv(args.env, override=True)

    try:
        validate_subject(args.subject)
        recipients = load_recipients(args.recipients)
        validate_recipients_data(recipients)

        template_html = args.html.read_text(encoding="utf-8")
        validate_html(template_html)
        validate_recipient_fields_for_template(recipients, template_html)

        if args.attach:
            validate_local_attachment_paths(args.attach)
    except ValidationError as e:
        print("Validation error:", e, file=sys.stderr)
        return 1

    cfg = load_smtp_config_from_env()
    if cfg is None:
        print("Set SMTP_SERVER and SMTP_USERNAME in the env file.", file=sys.stderr)
        return 2

    sent, failed = send_campaign(cfg, args.subject, template_html, recipients, args.attach)
    print(f"Done. Sent: {sent}, failed: {failed}")
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
