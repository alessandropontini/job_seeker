# Job Scout

Minimal, offline-first job scouting pipeline for Sprint 1.

## Requirements
- Python 3.11
- Dependencies in `requirements.txt`

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration
- Edit `config/config.yaml` to adjust defaults (location rules, salary rules, and notifications).
- Missing fields fall back to sane defaults in `job_scout/config.py`.

## Usage
Run the pipeline:
```bash
python -m job_scout run
python -m job_scout run --since-days 7
```

Inspect sources:
```bash
python -m job_scout sources --list
python -m job_scout sources --test
```

## Outputs
The pipeline writes reports to `out/`:
- `out/report.csv` (all postings)
- `out/report.md` (sorted by posted date, newest first)

## Notes
- The dummy source provides realistic, offline job postings scoped to EU/Italy/New York.
- Missing salaries are tagged with `missing_salary` in outputs when configured.
