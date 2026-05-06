---
name: email-send
description: >-
  Email newsletters
---

# Email send

Send a one-off email campaign from local files. SMTP credentials and limits come
from a local env file.

## Skill files

- Working directory: **the workspace root** (where `AGENTS.md` instruction lives).
- Send script: `.agents/skills/email-send/scripts/local_email_send.py`
- Default env file: `.env` in the script folder (possible to override with `--env <path>`).
- Necessary for email send example files: `.agents/skills/email-send/example_email`
- Human quick-start (no LLM): `.agents/skills/email-send/README.dm`

## Security: do not read `.env` or any user-provided `--env` path

- **Never** open, search, or display `**/.env` or any path the user passes as `--env`.
- Credentials and SMTP host live only in that file; the script loads it.
- It is **acceptable** to quote **public** variable *names* below so the user edits the file **themselves**.

Expected env keys (the user sets these, you don't read them):
`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_ADDRESS`,
`FROM_EMAIL` or `FROM_EMAIL_ADDRESS`, `COPY_ADDRESSES` or `CC` (optional, comma-separated),
`BCC_ADDRESSES` or `BCC` (optional, comma-separated). Optional limits:
`MAX_ATTACHMENT_SIZE_MB`, `MAX_JSON_SIZE_MB`, `MAX_RECIPIENTS`, `MAX_HTML_SIZE_MB`,
`MAX_ATTACHMENTS`, `MAX_SUBJECT_LENGTH`,
`SMTP_RATE_LIMIT_PER_MIN` (0 = unlimited).

## Pre-send checklist (collect from the user)

1. **`.env`**: confirm the user has created/updated it in `.agents/skills/email-send/scripts/.env`; otherwise they pass `--env <path>`.
2. **Change SMTP?** Ask: *Do you need to change SMTP host/port/credentials in `.env` before this send?* If yes, tell them to edit the file and confirm.
3. **Recipients file**: a path to **JSON** or **CSV**.
   - JSON: top level is a **non-empty array** of objects, each must include a valid `email`.
   - CSV: first row is a header; one column must be recognized as email (`email`, `Email`, `E-mail`, `mail`, …).
4. **HTML message file**: the body. Uses `{name}`-style **named placeholders**. Each send substitutes only keys from the recipient object **except** `email`; `{email}` in the body is **not** substituted. Every placeholder in the file must be present on **every** recipient.
5. **Subject line**: non-empty (default max 500 chars).
6. **Attachments (optional)**:
   - None: omit `--attach`.
   - Known paths: one or more `--attach <file>` (repeat the flag), up to `MAX_ATTACHMENTS` (default 10).
   - Folder: list **non-hidden files**; if **more than one** file, **ask the user** whether to attach all or a named subset; pass explicit `--attach` for each.
   - For every candidate file, **show size** (e.g. `ls -l`); warn if it exceeds the per-file limit (default `MAX_ATTACHMENT_SIZE_MB=1`); allowed extensions: `.pdf .doc .docx .xls .xlsx .txt .jpg .jpeg .png .gif .zip`.
7. User may not be able to generate correct **Recipients file** and **HTML message file** and provides you list of email for newsletters and text of the message. In this case generate correct **Recipients file** and **HTML message file** yourself in the **scratch** folder in workspace root. Example files are in `.agents/skills/email-send/example_email`
8. **Recipients file**, **HTML message file** and **Email subject** are required, do not send the email until you have them, insist that the user provide them..
9. If user wants to add attachments say that it is possible and user must provide attachment file(s) or the folder.

## Validation (built into the send command)

`local_email_send.py` runs all validators: JSON size, recipients, HTML size+structure, placeholders vs every row, attachments (size + extension + MIME via `libmagic`). There is no separate validate-only script — run the CLI; fix any `Validation error:` in stderr.

## Sending

Run from the **workspace root** (where `.venv/` is). With a subject string and `--attach` per file. On Windows (Git Bash), use `.venv/Scripts/python.exe` instead of `.venv/bin/python`. All other arguments stay the same.

```bash
.venv/bin/python .agents/skills/email-send/scripts/local_email_send.py \
  --env .agents/skills/email-send/scripts/.env \
  --subject "Subject line here" \
  --recipients <path_to_recipients.{json,csv}> \
  --html <path_to_body.html> \
  --attach <file1> \
  --attach <file2>
```

Call example:
```bash
.venv/bin/python .agents/skills/email-send/scripts/local_email_send.py \
  --subject "Resignation Letter" \
  --recipients scratch/recipients.json \
  --html scratch/resignation_letter.html
```

Omit all `--attach` lines if there are no attachments. `--env` may be omitted only when running from `.agents/skills/email-send/scripts/` where `.env` is located.

Exit codes:
- `0` — sent (no failures)
- `1` — validation error
- `2` — missing/invalid SMTP settings in the env the script loaded
- `3` — at least one recipient failed at SMTP time (others were sent)

Surface stderr to the user.
