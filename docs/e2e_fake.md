# E2E fake-data workflow (`e2e_fake`)

Questo documento descrive il flusso E2E manuale che valida pipeline + notifica Telegram fake + callback su Cloudflare Worker senza usare dati reali.

## Garanzie
- **Manual-only**: il workflow usa solo `workflow_dispatch`.
- **Dati finti**: la pipeline usa `tests/fixtures/e2e_fake_jobs.json`.
- **No segreti in artifact/log applicativi**: vengono salvati report, payload Telegram fake, callback fake, risposta HTTP e log di registration con soli metadati tecnici.
- **Nessun cambio pubblico del webhook**: `/telegram/feedback` resta invariato; il test invia un payload callback nel formato reale `fb|...`.

## Registration feedback window (fake mode)
Nel run con `notifications.telegram.send_mode: fake` la registration della sessione feedback è **obbligatoria**.

Dettagli della chiamata Worker:
- **Endpoint**: `POST <JOB_SCOUT_WEBHOOK_BASE_URL>/window/open`
- **Headers firmati** (senza secret in chiaro):
  - `Content-Type: application/json`
  - `Accept: application/json`
  - `Accept-Language: en-US,en;q=0.9`
  - `User-Agent: Mozilla/5.0 ...` (browser-like, stabile)
  - `X-Webhook-Timestamp`
  - `X-Webhook-Id`
  - `X-Webhook-Signature` (HMAC SHA-256)

Se la registration fallisce (errore rete o `status != 200`), `job_scout run` termina con errore in fake mode e scrive comunque `out/feedback_registration_result.log` con:
- endpoint/metodo/header names
- status code
- primi 200 caratteri del body (`body_excerpt`)
- flag diagnostico `user_agent_sent=true|false`
- esito (`ok=true|false`) e reason.


### Cloudflare 1010 su `/window/open`
In alcuni ambienti CI, Cloudflare può bloccare la registration con `403` e `error code: 1010` sul path `/window/open`.

Mitigazioni:
- il client invia un `User-Agent` browser-like insieme agli header di firma;
- in caso di errore, `out/feedback_registration_result.log` include `status`, `body_excerpt` (max 200 char) e `user_agent_sent=true|false` per diagnosi rapida;
- lato Cloudflare, valutare una bypass rule su `/window/*` condizionata alla presenza di `X-Webhook-Signature` (senza allargare il bypass ad altri path).

## Come lanciare
1. Vai in **GitHub Actions**.
2. Avvia il workflow **`e2e_fake`**.
3. Verifica che i secrets necessari siano configurati:
   - `JOB_SCOUT_WEBHOOK_BASE_URL`
   - `JOB_SCOUT_WEBHOOK_SECRET`
   - `ALLOWED_TELEGRAM_USER_ID`

## Cosa fa il workflow
1. Esegue `python -m job_scout run` con `config/e2e_fake.yaml` e fixture deterministica.
2. Verifica subito `out/feedback_registration_result.log` e fallisce se manca o contiene `ok=false`.
3. Estrae una `callback_data` valida dalla keyboard inline reale.
4. Chiama `/telegram/feedback` con header `X-Telegram-Bot-Api-Secret-Token` e payload Telegram fake.
5. Fallisce se trova `Invalid callback data` o `Session missing`.

## Artifacts attesi
- `out/report.csv`
- `out/report.md`
- `out/last_run.json`
- `out/telegram_payload.json`
- `out/digest.md`
- `out/feedback_registration_result.log`
- `out/feedback_request.json`
- `out/feedback_response.txt`
- `out/feedback_result.log`
- `out/callback_data.txt`

## Troubleshooting

### `Feedback registration failed`
- Apri `out/feedback_registration_result.log` e controlla `status` + `body_excerpt`.
- Verifica `JOB_SCOUT_WEBHOOK_BASE_URL` e `JOB_SCOUT_WEBHOOK_SECRET`.
- Verifica che il Worker esponga il path `/window/open`.

### `Invalid callback data`
- Controlla che `out/telegram_payload.json` contenga una keyboard con `callback_data` nel formato `fb|run_id|short_id|action|job_hash`.
- Verifica che il workflow stia leggendo la prima riga della keyboard inline corretta.

### `Session missing`
- Verifica che la registration sia `ok=true` nel file `out/feedback_registration_result.log`.
- Conferma che callback e registration usino lo stesso `run_id`.
- Conferma che la callback sia inviata poco dopo la pipeline (finestra feedback non scaduta).
