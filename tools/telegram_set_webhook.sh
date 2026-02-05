#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "Missing TELEGRAM_BOT_TOKEN env var." >&2
  exit 1
fi

if [[ -z "${JOB_SCOUT_WEBHOOK_SECRET:-}" ]]; then
  echo "Missing JOB_SCOUT_WEBHOOK_SECRET env var." >&2
  exit 1
fi

if [[ -z "${JOB_SCOUT_WEBHOOK_BASE_URL:-}" ]]; then
  echo "Missing JOB_SCOUT_WEBHOOK_BASE_URL env var." >&2
  exit 1
fi

BASE_URL="${JOB_SCOUT_WEBHOOK_BASE_URL%/}"
WEBHOOK_URL="${BASE_URL}/telegram/feedback"
export WEBHOOK_URL

payload=$(python - <<'PY'
import json
import os

webhook_url = os.environ["WEBHOOK_URL"]
secret = os.environ["JOB_SCOUT_WEBHOOK_SECRET"]

print(json.dumps({"url": webhook_url, "secret_token": secret}))
PY
)

set_response=$(curl -sS -X POST \
  -H "Content-Type: application/json" \
  -d "${payload}" \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook")

python - <<'PY' <<<"${set_response}"
import json
import sys

raw = sys.stdin.read()
try:
  data = json.loads(raw)
except json.JSONDecodeError:
  print("setWebhook: Unable to parse response")
  sys.exit(1)

ok = data.get("ok")
description = data.get("description")
print(f"setWebhook: ok={ok} description={description}")
PY

info_response=$(curl -sS \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo")

python - <<'PY' <<<"${info_response}"
import json
import sys

raw = sys.stdin.read()
try:
  data = json.loads(raw)
except json.JSONDecodeError:
  print("getWebhookInfo: Unable to parse response")
  sys.exit(1)

result = data.get("result", {})
fields = {
  "url": result.get("url"),
  "has_custom_certificate": result.get("has_custom_certificate"),
  "pending_update_count": result.get("pending_update_count"),
  "last_error_message": result.get("last_error_message"),
}
print("getWebhookInfo:")
for key, value in fields.items():
  print(f"  {key}: {value}")
PY

echo "Expected webhook URL: ${WEBHOOK_URL}"
