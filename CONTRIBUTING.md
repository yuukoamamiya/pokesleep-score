# Contributing

Start with `AGENTS.md`, especially the scoring invariants and privacy rules. Keep pull requests focused and explain whether live MuMu capture was verified.

Before submitting:

```text
python -m unittest discover -s tests -v
python -m pokesleep_score doctor
python -m pokesleep_score demo
python scripts/public_release_check.py
```

Add tests for scoring, OCR constraints, resume behavior, and output schemas when changing them. Data updates must identify an upstream URL and exact snapshot. Never attach real browser profiles or unsanitized collection screenshots to a pull request.
