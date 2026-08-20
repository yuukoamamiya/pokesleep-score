# Agent handoff

Read `README.md`, `docs/ARCHITECTURE.md`, and `docs/SCORING_POLICY.md` before changing behavior.

## Non-negotiable scoring invariants

- Evaluate cultivation ceiling at Lv.70.
- Always evaluate main skill at Lv.5, regardless of its current OCR value.
- Sub-skill unlock levels are 10/25/50/70/80; Lv.70 uses the first four slots.
- Berry specialists are compared by total berry energy.
- Food specialists use the concrete three-slot ingredient distribution. Legal patterns are AAA, AAB, AAC, ABA, ABB, ABC. Only AAA and ABB avoid the extra 0.70 multiplier.
- Treat ジュカイン (Sceptile) as berry-specialty for local rating.
- Preserve the raw Daifuku result. Personal rules belong in separate columns/files.
- Enumerate all Eevee evolution branches.

Every scoring-policy change must update tests and `docs/SCORING_POLICY.md`. Increment `ALGORITHM_VERSION` when cached scoring results could become stale.

## Repository hygiene

- Runtime/private data belongs under `workspace/` or an external `POKESLEEP_WORKSPACE`; never commit it.
- Never commit browser profiles, cookies, screenshots, user CSVs, progress files, emulator identifiers, or proxy credentials.
- Keep a sanitized no-emulator demo working.
- Prefer `python -m unittest discover -s tests -v` for the baseline suite and run `python scripts/public_release_check.py` before release.
- Capture/OCR changes may be tested with fixtures, but explicitly disclose when live MuMu verification was not possible.
- Third-party data provenance must remain documented. Do not imply that third-party data or game assets are MIT-licensed by this repository.

## Entry points

- `pokesleep-score doctor`
- `pokesleep-score demo`
- `pokesleep-score full [--with-daifuku]`
- `pokesleep-score offline [--reuse-ocr] [--with-daifuku]`
- `pokesleep-score report`
