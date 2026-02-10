# E2E Telegram reale (`e2e-telegram-real`)

Workflow manual-only per validare la catena reale:
1. invio Telegram reale (`sendMessage`)
2. click callback inline
3. persistenza feedback su Cloudflare KV
4. retrieval tramite `fetch_feedback(run_id)`

## Garanzie validate

- trigger solo `workflow_dispatch`
- nessun nuovo secret richiesto
- callback contract compatibile (`fb|run|short|action|hash`, max 64 byte)
- auth callback via `X-Telegram-Bot-Api-Secret-Token`
- allowlist user id (`ALLOWED_TELEGRAM_USER_ID`)

## Cosa verifica l'E2E reale

- Digest inviato in Telegram con pulsanti inline validi.
- `run_id` presente in `out/last_run.json`.
- callback salvato dal Worker su chiave `feedback:<run_id>:<short_id>:<user_id>`.
- risposta `fetch_feedback` coerente con almeno un record.

## Come confrontare un record feedback

Esempio atteso (struttura):

```json
{
  "run_id": "25071008ab12",
  "action": "L",
  "job_short_id": "a1b2c3d4",
  "job_hash": "e5f6a7b8",
  "ts": "2026-02-10T07:05:22.123Z",
  "message_id": 314,
  "user_id": 123456789,
  "source": "remotive"
}
```

Confronti operativi:
- `run_id` deve combaciare con `digest.run_id` di `out/last_run.json`.
- `message_id` deve essere quello del messaggio Telegram su cui è stato cliccato il bottone.
- `ts` deve ricadere nella finestra feedback aperta per la run.

## Modalità callback

- `manual` (default): click umano durante il timeout del workflow.
- `automatic`: replay controllato di payload Telegram-like verso `/telegram/feedback`.

## Troubleshooting rapido

- `401/403`: secret webhook mismatch.
- `Session missing`: sessione scaduta/non registrata.
- `Invalid callback data`: payload non conforme o troppo lungo.
- feedback vuoto: click non avvenuto in tempo o user id non autorizzato.
