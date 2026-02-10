# E2E Telegram reale (`e2e-telegram-real`)

Workflow manual-only per validare pipeline con offerte **fixture** + invio **reale** Telegram + callback feedback verso Worker.

## Garanzie
- Solo `workflow_dispatch` (nessun cron/schedule).
- Nessun nuovo secret richiesto: usa quelli già presenti (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `JOB_SCOUT_WEBHOOK_BASE_URL`, `JOB_SCOUT_WEBHOOK_SECRET`, `ALLOWED_TELEGRAM_USER_ID`).
- No leak di segreti: il workflow non stampa token/chat id/webhook secret in chiaro.
- Fixture deterministiche: `tests/fixtures/e2e_fake_jobs.json`.

## Modalità Telegram reale (sicura)
Il workflow abilita invio reale con:
- `JOB_SCOUT_TELEGRAM_MODE=real`
- `JOB_SCOUT_E2E_REAL_TELEGRAM=1`
- CLI `--telegram-real`

Il codice mantiene default safety-first (`send_mode: fake`) e accetta `real` solo con il gate E2E esplicito.

## Callback test
Sono disponibili due modalità:

1. **manual** (default)
   - Il workflow invia il digest reale con pulsanti inline.
   - Nei log viene richiesto di premere il primo bottone entro il timeout (`manual_wait_seconds`, default 120s).
   - A fine attesa, il workflow verifica che il feedback sia stato registrato dal Worker.

2. **automatic** (opzionale)
   - Il workflow estrae `callback_data` dal payload salvato in `out/telegram_payload.json`.
   - Invia una request Telegram-like a `${JOB_SCOUT_WEBHOOK_BASE_URL}/telegram/feedback`
     con header `X-Telegram-Bot-Api-Secret-Token`.
   - Verifica HTTP `200` e body `{"ok":true}`.

## Verifiche E2E
- registration feedback window con `ok=true` in `out/feedback_registration_result.log`.
- callback_data presente e `<=64` byte.
- assenza di errori noti: `Session missing`, `Invalid callback data`.
- stato run coerente (`out/last_run.json` con `digest.run_id` e `digest.jobs`).

## Artifacts
Il workflow pubblica l’intera directory `out/` come artifact `job-scout-e2e-telegram-real`.

## Troubleshooting
- **401/403 webhook**: controllare `JOB_SCOUT_WEBHOOK_SECRET` e validazione header `X-Telegram-Bot-Api-Secret-Token`.
- **callback_data troppo lungo**: verificare formato compatto `fb|run|short|action|hash`.
- **chat id errato / bot non autorizzato**: verificare `TELEGRAM_CHAT_ID`, che il bot sia presente nella chat e abbia i permessi necessari.
- **nessun feedback in manual mode**: assicurarsi di premere il bottone entro la finestra e che `ALLOWED_TELEGRAM_USER_ID` corrisponda all’utente che clicca.
