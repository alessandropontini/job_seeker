# Troubleshooting

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
