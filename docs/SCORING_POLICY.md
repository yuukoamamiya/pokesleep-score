# Scoring policy

This project estimates whether a Pokémon is worth investing in, so it models the configured cultivation ceiling rather than reproducing only the current screen values.

## Fixed evaluation assumptions

| Item | Policy |
|---|---|
| Evaluation level | Lv.70 |
| Main skill | Always Lv.5 |
| Sub-skill unlocks | Lv.10, 25, 50, 70, 80 |
| Active slots at Lv.70 | First four |
| Berry metric | Total berry energy |
| Sceptile | Rated as berry-specialty |
| Eevee | Evaluate every evolution branch |

## Ingredient patterns

Each species has a fixed A ingredient, an A/B second slot, and an A/B/C third slot. The six legal distributions are `AAA`, `AAB`, `AAC`, `ABA`, `ABB`, and `ABC`. The letters are resolved to the species-specific ingredient IDs and per-slot quantities from the calculator data.

For food-specialty scoring, `AAA` and `ABB` keep the calculated result. Every other legal pattern receives an additional `0.70` multiplier. This is a user preference layer reflecting practical investment choices, not a claim about the game's official mechanics.

## Daifuku separation

`评分总表_大福对照.csv` preserves the result returned by Daifuku. `评分总表_个人规则.csv` adds the multiplier, adjusted rank, and suggestion in new columns. Never overwrite or relabel a raw Daifuku rank as if the third-party site produced the adjusted value.
