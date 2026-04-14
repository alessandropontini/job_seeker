# Live Runbook (Cloudflare 08:00 Europe/Rome)

## Architecture summary

Live scheduling is executed by the Cloudflare Worker (not GitHub Actions). The Worker handles:
1. Cron trigger dispatch at Rome 08:00.
2. Live jobs fetch (Remotive API).
3. Daily digest filtering for **yesterday** in `Europe/Rome`.
4. Telegram `sendMessage` with inline feedback buttons (`callback_data` compact format).
5. Feedback window/session persistence and feedback storage in Cloudflare KV.

## Scheduling at 08:00 Europe/Rome

Cloudflare cron is UTC-based. We configure two UTC schedules:
- `0 6 * * *`
- `0 7 * * *`

Then Worker-side logic checks local Rome hour and runs only when local hour is exactly `08`. This handles CET/CEST without GitHub schedules.

## Live gates and safety

- `JOB_SCOUT_ENV` must be `live` to allow daily sends.
- Telegram callback auth requires `X-Telegram-Bot-Api-Secret-Token`.
- Callback user id must match `ALLOWED_TELEGRAM_USER_ID`.
- Callback format is fixed: `fb|<run_id>|<short_id>|<action>|<job_hash>` and must remain `<=64` bytes.
- No secrets are printed in logs (only run id, counts, reason codes).

## Dedup and daily window

### Dedup
- KV key: `live:last_sent_date`
- Stored as `YYYY-MM-DD` in `Europe/Rome` for the digest date (`yesterday`).
- If key already equals current digest date, Worker logs `live_daily_skipped_already_sent` and does not resend.

### Daily window
- Target digest date is always `yesterday` in `Europe/Rome`.
- Jobs are filtered by publication date converted to Rome timezone.
- If window returns zero jobs, Worker executes fallback (best recent filtered jobs) and marks it in logs/message.

## KV state model (live)

- `live:last_sent_date` → dedup date string.
- `live:run:<run_id>` → run metadata and digest jobs.
- `session:<run_id>` → feedback window + short id/job hash mapping.
- `feedback:<run_id>:<short_id>:<user_id>` → feedback record including `run_id`.

## Required Worker bindings/vars (names only)

- `JOB_SCOUT_KV` (KV namespace)
- `TELEGRAM_BOT_TOKEN` (secret)
- `TELEGRAM_CHAT_ID` (secret)
- `JOB_SCOUT_WEBHOOK_SECRET` (secret)
- `ALLOWED_TELEGRAM_USER_ID` (secret)
- `JOB_SCOUT_SMOKE_TOKEN` (secret, for protected manual trigger route)
- `JOB_SCOUT_ENV` (`live` in production)
- `FEEDBACK_WINDOW_MINUTES`

## Endpoints compatibility

Existing endpoints remain compatible:
- `POST /window/open`
- `POST /telegram/feedback`
- `POST /feedback` (`fetch_feedback` path)

Additional route:
- `POST /run_daily` (manual protected trigger; same live logic as cron)

Telegram command trigger on the same webhook:
- `/jobscout`
- `/jobscout mode=test sources=remotive,wwr,arbeitnow,greenhouse since_days=7`
- `/jobscout mode=github sources=remotive,wwr,arbeitnow,greenhouse since_days=7`
- `/jobscout mode=github sources=remotive,wwr,arbeitnow,greenhouse since_days=30 profession=IT_Solution_Architect location_scope=world`

Interactive operator flow:
1. Send `/jobscout`
2. Reply with the profession/focus text
3. Tap the search area (`Italia`, `Europa`, `USA`, `Mondo`)
4. Tap the day-range button
5. The worker dispatches GitHub with `profession` + `location_scope` + `since_days`

Recommended rollout:
1. Test loop first: Telegram -> Cloudflare -> source probe test -> Cloudflare -> Telegram
2. Then enable GitHub dispatch mode: Telegram -> Cloudflare -> GitHub workflow dispatch -> Telegram acknowledgement
3. If needed later, add a workflow callback/Webhook step so Cloudflare can post final run status back to Telegram

## Troubleshooting

- **No jobs sent**: inspect logs for `live_daily_no_jobs` or `live_daily_send_failed`; verify source availability and filters.
- **Token invalid / send failure**: check Telegram token/chat binding presence and bot permissions.
- **Session missing**: ensure `session:<run_id>` exists and callback occurs inside configured feedback window.
- **Callback invalid**: verify compact callback format and 64-byte max payload.
- **Skipped already sent**: expected dedup behavior when `live:last_sent_date` already matches digest date.
