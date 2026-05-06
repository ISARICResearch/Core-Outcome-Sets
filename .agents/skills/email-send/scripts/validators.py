"""Validation utilities for the email-send skill.

Validates JSON, HTML, attachments, and recipient/template fields. Uses the
standard library and ``python-magic`` only. ``MAX_*`` limits are read from
``os.environ`` lazily on each call, so any ``.env`` loaded before validation
is picked up.
"""
from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import magic


class ValidationError(Exception):
    """Validation failed for user-supplied data (recipients, html, attachments, …)."""


# Mapping of allowed extensions to their accepted MIME types (magic-bytes check).
# Multiple MIME types per extension handle format variants (e.g. Office Open XML).
ALLOWED_MIME_TYPES: dict[str, set[str]] = {
    ".pdf":  {"application/pdf"},
    ".doc":  {"application/msword"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "application/zip"},
    ".xls":  {"application/vnd.ms-excel",
              "application/msexcel"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              "application/zip"},
    ".txt":  {"text/plain"},
    ".jpg":  {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png":  {"image/png"},
    ".gif":  {"image/gif"},
    ".zip":  {"application/zip", "application/x-zip-compressed"},
}

ALLOWED_EXTENSIONS = set(ALLOWED_MIME_TYPES.keys())

# Email validation regex (RFC 5322 simplified).
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Merge fields in HTML: same token shape as apply_template ("{" + keyword + "}").
_PLACEHOLDER_FIELD_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _env_int(key: str, default: str) -> int:
    return int(os.getenv(key, default))


def _env_mb_bytes(key: str, default_mb: str) -> int:
    return _env_int(key, default_mb) * 1024 * 1024


class _SimpleHTMLValidator(HTMLParser):
    """Best-effort check for balanced HTML tags."""

    SELF_CLOSING_TAGS = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr",
    })

    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []
        self.tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag not in self.SELF_CLOSING_TAGS:
            self.tag_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SELF_CLOSING_TAGS:
            return
        if tag in self.tag_stack:
            while self.tag_stack and self.tag_stack[-1] != tag:
                self.tag_stack.pop()
            if self.tag_stack:
                self.tag_stack.pop()
        else:
            self.errors.append(f"Mismatched closing tag: {tag}")


def validate_email(email: str) -> bool:
    """Return True if ``email`` looks like a valid address."""
    if not email or not isinstance(email, str):
        return False
    return EMAIL_REGEX.match(email.strip()) is not None


def validate_subject(subject: str) -> None:
    """Check subject length against ``MAX_SUBJECT_LENGTH`` (default 500)."""
    max_length = _env_int("MAX_SUBJECT_LENGTH", "500")
    if len(subject) > max_length:
        raise ValidationError(
            f"Email subject exceeds maximum length of {max_length} characters (got {len(subject)})"
        )


def validate_json_size(json_str: str) -> None:
    """Check encoded JSON byte size against ``MAX_JSON_SIZE_MB`` (default 10)."""
    max_size = _env_mb_bytes("MAX_JSON_SIZE_MB", "10")
    size = len(json_str.encode("utf-8"))
    if size > max_size:
        raise ValidationError(
            f"JSON size ({size / (1024 * 1024):.2f}MB) "
            f"exceeds maximum allowed ({max_size / (1024 * 1024):.0f}MB)"
        )


def validate_recipients_data(recipients_data: list[dict[str, Any]]) -> None:
    """Validate recipients structure: array, count, each row has a valid ``email``."""
    if not isinstance(recipients_data, list):
        raise ValidationError("Recipients data must be a JSON array")

    max_recipients = _env_int("MAX_RECIPIENTS", "10000")
    if len(recipients_data) > max_recipients:
        raise ValidationError(
            f"Number of recipients ({len(recipients_data)}) "
            f"exceeds maximum allowed ({max_recipients})"
        )

    if not recipients_data:
        raise ValidationError("Recipients list cannot be empty")

    for idx, recipient in enumerate(recipients_data):
        if not isinstance(recipient, dict):
            raise ValidationError(f"Recipient at index {idx} must be an object")
        if "email" not in recipient:
            raise ValidationError(f"Recipient at index {idx} must have an 'email' field")
        email = recipient["email"]
        if not validate_email(email):
            raise ValidationError(f"Invalid email format at index {idx}: {email}")


def validate_html(html: str) -> None:
    """Check HTML byte size and basic tag balance."""
    max_size = _env_mb_bytes("MAX_HTML_SIZE_MB", "5")
    size = len(html.encode("utf-8"))
    if size > max_size:
        raise ValidationError(
            f"HTML size ({size / (1024 * 1024):.2f}MB) "
            f"exceeds maximum allowed ({max_size / (1024 * 1024):.0f}MB)"
        )

    parser = _SimpleHTMLValidator()
    try:
        parser.feed(html)
    except Exception as e:  # noqa: BLE001
        raise ValidationError(f"HTML parsing error: {e}") from e
    if parser.errors:
        raise ValidationError(
            f"Invalid HTML structure: {'; '.join(parser.errors[:3])}"
        )


def validate_recipient_fields_for_template(
    recipients_data: list[dict[str, Any]], template_content: str
) -> None:
    """For each ``{field}`` in the HTML, ensure every recipient row supplies ``field``.

    The literal ``{email}`` is rejected: only keys other than ``'email'`` are
    substituted into the template (see ``apply_template`` in
    ``local_email_send.py``).
    """
    fields = set(_PLACEHOLDER_FIELD_RE.findall(template_content))
    if not fields:
        return
    if "email" in fields:
        raise ValidationError(
            "HTML template contains {email}, but the recipient address is not merged into the "
            "body (only keys other than 'email' are substituted). Use another key or remove the "
            "placeholder."
        )
    for idx, recipient in enumerate(recipients_data):
        to_email = recipient.get("email", "")
        for field in fields:
            if field not in recipient:
                raise ValidationError(
                    f"Template uses {{{field}}} but recipient at index {idx} "
                    f"(email: {to_email!r}) has no {field!r} key"
                )


def _validate_one_binary(filename: str | None, file_size: int, header: bytes) -> None:
    """Shared check: size, extension, magic MIME on a (size, header) pair."""
    max_size = _env_mb_bytes("MAX_ATTACHMENT_SIZE_MB", "1")
    if file_size > max_size:
        name = filename or "file"
        raise ValidationError(
            f"File '{name}' exceeds maximum size of {max_size / (1024 * 1024):.0f} MB"
        )

    file_ext = Path(filename or "").suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"File type '{file_ext}' is not allowed. "
            f"Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    detected_mime = magic.from_buffer(header, mime=True)
    allowed_mimes = ALLOWED_MIME_TYPES[file_ext]
    if detected_mime not in allowed_mimes:
        name = filename or "file"
        raise ValidationError(
            f"File '{name}' content does not match its extension. "
            f"Detected: {detected_mime}, expected one of: {', '.join(sorted(allowed_mimes))}"
        )


def validate_local_attachment_paths(paths: list[Path]) -> list[Path]:
    """Validate local attachment files: count, size, extension, magic MIME."""
    valid = [p for p in paths if p.name.strip()]
    max_count = _env_int("MAX_ATTACHMENTS", "10")
    if len(valid) > max_count:
        raise ValidationError(
            f"Number of attachments ({len(valid)}) exceeds maximum allowed ({max_count})"
        )
    for p in valid:
        if not p.is_file():
            raise ValidationError(f"Attachment not found: {p}")
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(0)
            header = f.read(2048)
        _validate_one_binary(p.name, size, header)
    return valid
