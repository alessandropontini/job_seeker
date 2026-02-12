# Troubleshooting


## `candidates_count=0` in `out/run_summary.json`

Quando `fetched_count > 0` ma `candidates_count=0`, significa che **tutti** i job sono stati bloccati dagli hard filter.
In questo caso il digest può restare vuoto solo con `reason_when_zero="no_candidates_after_hard_filters"`.

Controlli consigliati:
- `hard_block_count`: se alto, verifica filtri location/salary hard.
- `exclude_countries` e match su `excluded_country` / `excluded_country_text` (UK escluso esplicitamente).
- Regole salary (`minimum_eur`) e reject `salary_below_minimum`.
- Hard negative blocks (`negative_hard_block`).

Nota: in PR1 `title_not_targeted` è trattato come soft gate per il candidate pool, quindi non deve da solo azzerare `candidates_count`.

## Ho ricevuto `Mode: LOW_CONFIDENCE (anti-zero)` su Telegram

Significa che la selezione ha provato prima i match ad alta qualità (`TOP`) e poi il rilassamento soglia (`ADAPTIVE`), ma non ha raggiunto `min_results`.
Per evitare digest vuoti quando `fetched_count > 0`, il sistema ha inviato i migliori job disponibili per punteggio.

### Cosa controllare in `out/run_summary.json`

- `digest_mode`: deve risultare `LOW_CONFIDENCE`.
- `anti_zero_triggered`: `true` indica che è stato usato il fallback top-K.
- `threshold_initial` / `threshold_final`: mostrano quanto la soglia è stata abbassata.
- `min_results`: target minimo richiesto.
- `selected_count`: quanti job sono stati inviati davvero.
- `fetched_count`, `candidates_count`, `matches_count`: aiutano a capire se il problema è a monte (raccolta/candidati) o solo di soglia.

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
