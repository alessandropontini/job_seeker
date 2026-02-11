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
