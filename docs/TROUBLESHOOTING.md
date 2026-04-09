# Troubleshooting


## `candidates_count=0` in `out/run_summary.json`

Quando `fetched_count > 0` ma `candidates_count=0`, significa che **tutti** i job sono stati bloccati dagli hard filter.
In questo caso il digest può restare vuoto solo con `reason_when_zero="no_candidates_after_hard_filters"`.

Controlli consigliati:
- `hard_rejected_count`: se alto, verifica reject hard reali (`excluded_country*`, `missing_url`).
- `exclude_countries` e match su `excluded_country` / `excluded_country_text` (UK escluso esplicitamente).
- Regole salary (`minimum_eur`): in scheduled `salary_below_minimum` è hard reject, in manual è soft penalty.
- `top_penalties` e `top_hard_rejects` in `out/run_summary.json` per capire cosa sta abbassando la qualità.

Nota PR3: in manual `title_not_targeted` e `location_not_allowed` sono penalità soft; usa `report.csv` colonne `hard_reject_reasons`, `penalties_applied`, `score`, `why` per leggere il motivo reale del ranking.

## Ho ricevuto `Mode: LOW_CONFIDENCE (anti-zero)` su Telegram

Significa che la selezione ha provato prima i match ad alta qualità (`TOP`) e poi il rilassamento soglia (`ADAPTIVE`), ma non ha raggiunto `min_results`.
Per evitare digest vuoti quando `fetched_count > 0`, il sistema ha inviato i migliori job disponibili per punteggio.

### Cosa controllare in `out/run_summary.json`

- `digest_mode`: deve risultare `LOW_CONFIDENCE`.
- `anti_zero_triggered`: `true` indica che è stato usato il fallback top-K.
- `threshold_initial` / `threshold_final`: mostrano quanto la soglia è stata abbassata.
- `min_results`: target minimo richiesto.
- `selection_pool_count`: quanti job sono entrati nella selezione digest dopo gli hard filter.
- `selected_count`: quanti job hanno passato la soglia digest prima dello split canali.
- `digest_count`: quanti job sono finiti davvero nel digest finale.
- `fetched_count`, `candidates_count`, `accepted_count`, `strict_matches_count`: aiutano a capire se il problema è a monte (raccolta/candidati), nel matching, o solo di soglia/canali.

### Azioni consigliate

1. Verifica che il giorno in questione abbia abbastanza job in target (EU/Italy/New York, no UK).
2. Controlla se i punteggi sono sistematicamente bassi (molti sotto `high_threshold`).
3. Se necessario, regola `digest.selection` in config (`min_results`, `high_threshold`, `low_threshold`, `step`) mantenendo invariati scoring e fonti.

## Se non ricevi nulla alle 08:00 Europe/Rome

Controlli rapidi (ordine consigliato):
1. GitHub Actions deve essere abilitato nel repository.
2. Il workflow `live-daily-telegram` deve essere presente nel branch `main` (default branch).
3. Il workflow deve avere trigger `on.schedule` attivo con doppio cron UTC (`55 6 * * *` + `5 7 * * *`).
4. Apri l'ultimo artifact `out/run_summary.json` e verifica `reason`:
   - `sent`: digest inviato.
   - `no_matches`: nessun job selezionato, ma è stato inviato un messaggio diagnostico.
   - `time_gate_skip`: run fuori finestra locale (`08:00-08:10 Europe/Rome`), skip atteso (con ping Telegram `Scheduled run skipped (time gate)`).

Perché doppio cron + gate: il passaggio CET/CEST sposta l'equivalenza UTC delle 08:00 locali. Due run ravvicinati garantiscono che almeno uno cada nella finestra locale corretta, mentre l'altro produce comunque diagnostica osservabile (`time_gate_skip`).

## Se vedi `feedback non valido` su Telegram

Controlli rapidi per distinguere i casi più comuni:
- Verifica `close_at` della sessione nel KV e assicurati che la finestra sia 24h (`FEEDBACK_WINDOW_MINUTES=1440`).
- Se la sessione non esiste più per quel `run_id`, il Worker risponde con `Session missing (expired). request_id=<id>`.
- Se `callback_data` è malformato, il Worker risponde con `Invalid callback data. request_id=<id>`.
- Filtra i Workers Logs per `request_id` (header `X-Request-Id`) e cerca `event=feedback_callback`.

Esempi diagnostici (`event=feedback_callback`):
- `outcome=ok, reason=feedback_recorded`
- `outcome=session_missing, reason=session_expired`
- `outcome=session_missing, reason=no_session_for_run_id`
- `outcome=invalid_callback, reason=bad_format`
- `outcome=invalid_callback, reason=bad_action`
- `outcome=invalid_callback, reason=missing_fields`
