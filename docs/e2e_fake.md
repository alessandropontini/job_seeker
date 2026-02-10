# E2E fake-data workflow (`e2e_fake`)

Questo documento descrive il flusso E2E manuale che valida pipeline + notifica Telegram fake + callback su Cloudflare Worker senza usare dati reali.

## Garanzie
- **Manual-only**: il workflow usa solo `workflow_dispatch`.
- **Dati finti**: la pipeline usa `tests/fixtures/e2e_fake_jobs.json`.
- **No segreti in artifact/log applicativi**: vengono salvati solo report, payload Telegram fake, callback fake e risposta HTTP.
- **Nessun cambio pubblico del webhook**: `/telegram/feedback` resta invariato; il test invia un payload callback nel formato reale `fb|...`.

## Come lanciare
1. Vai in **GitHub Actions**.
2. Avvia il workflow **`e2e_fake`**.
3. Verifica che i secrets necessari siano configurati:
   - `JOB_SCOUT_WEBHOOK_BASE_URL`
   - `JOB_SCOUT_WEBHOOK_SECRET`
   - `ALLOWED_TELEGRAM_USER_ID`

## Cosa fa il workflow
1. Esegue `python -m job_scout run` con `config/e2e_fake.yaml` e fixture deterministica.
2. Genera report in `out/` e payload Telegram fake (`out/telegram_payload.json`, `out/digest.md`).
3. Registra la sessione feedback nello stesso storage Worker/KV usato da `/telegram/feedback` (tramite `register_feedback_window` del flusso notifica).
4. Estrae una `callback_data` valida dalla keyboard inline reale.
5. Chiama `/telegram/feedback` con header `X-Telegram-Bot-Api-Secret-Token` e payload Telegram fake.
6. Fallisce se trova `Invalid callback data` o `Session missing`.

## Artifacts attesi
- `out/report.csv`
- `out/report.md`
- `out/last_run.json`
- `out/telegram_payload.json`
- `out/digest.md`
- `out/feedback_request.json`
- `out/feedback_response.txt`
- `out/feedback_result.log`
- `out/callback_data.txt`

## Troubleshooting

### `Invalid callback data`
- Controlla che `out/telegram_payload.json` contenga una keyboard con `callback_data` nel formato `fb|run_id|short_id|action|job_hash`.
- Verifica che il workflow stia leggendo la prima riga della keyboard inline corretta.

### `Session missing`
- Verifica che la registrazione finestra feedback sia abilitata (`feedback.enabled: true` in `config/e2e_fake.yaml`).
- Verifica che il Worker sia raggiungibile con `JOB_SCOUT_WEBHOOK_BASE_URL` e che `JOB_SCOUT_WEBHOOK_SECRET` sia corretto.
- Conferma che la callback sia inviata poco dopo la pipeline (finestra feedback non scaduta).
