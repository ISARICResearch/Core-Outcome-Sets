# Email send quick start (human guide)

Use this when you want to send one email campaign manually from local files.

## 1) Prepare files

Create files in `scratch/email-send/` (from repository root):

- `scratch/email-send/recipients.json` **or** `scratch/email-send/recipients.csv`
- `scratch/email-send/body.html`
- Optional attachments, for example: `scratch/email-send/attachments/<file>`

Recommended names:

- recipients: `recipients.json` or `recipients.csv`
- html body: `body.html`

Accepted recipients formats:

- `JSON`: top-level array, each item must contain `email`
- `CSV`: header row with an email column (`email`, `Email`, `E-mail`, `mail`, etc.)

## 2) Fill `.env`

Create `.env` in `.agents/skills/email-send/scripts/`:

- Required: `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`
- Sender: `FROM_ADDRESS`, `FROM_EMAIL` (or `FROM_EMAIL_ADDRESS`)
- Optional: `COPY_ADDRESSES`, `BCC_ADDRESSES`, `SMTP_RATE_LIMIT_PER_MIN`

## 3) Run from repository root

```bash
.venv/bin/python .agents/skills/email-send/scripts/local_email_send.py \
  --env .agents/skills/email-send/scripts/.env \
  --subject "Your subject" \
  --recipients scratch/email-send/recipients.json \
  --html scratch/email-send/body.html
```

With attachments (repeat `--attach`):

```bash
.venv/bin/python .agents/skills/email-send/scripts/local_email_send.py \
  --env .agents/skills/email-send/scripts/.env \
  --subject "Your subject" \
  --recipients scratch/email-send/recipients.csv \
  --html scratch/email-send/body.html \
  --attach scratch/email-send/attachments/file1.pdf \
  --attach scratch/email-send/attachments/file2.docx
```
