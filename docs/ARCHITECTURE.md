# Architecture

The pipeline is deliberately script-oriented so an agent can inspect or rerun one stage without rebuilding a service.

```text
MuMu + ADB
  -> capture.py -> workspace/cap + manifest/progress
  -> extract.py -> workspace/box_ocr.csv
  -> quality_report.py -> workspace/results/OCR质检.csv
  -> score.py -> workspace/results/评分总表.csv
  -> daifuku_compare.py (optional) -> 评分总表_大福对照.csv
  -> personal_adjustment.py -> 评分总表_个人规则.csv
  -> make_box_longshot.py -> annotated long screenshots
```

`pokesleep_score/cli.py` is the stable public entry point. `run_pipeline.py` coordinates the existing stage scripts. `project_config.py` is the single source of truth for public source paths versus private runtime paths.

Scoring code lives under `score/`. Normalized calculator data lives in `score/data/`; OCR mappings and the standalone box viewer live under `box-exporter/`. `workspace/` is created at runtime and ignored by Git, including generated scoring baselines under `workspace/cache/`.

Resumable state includes an algorithm version and/or input fingerprint where applicable. If a change can alter old results, update the version so stale cache entries are not reused.
