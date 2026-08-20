# Data sources

## pokeSleepCalc

The structured calculator snapshot in `score/data/` and the source snapshot in `data_src/pokedex.js` originate from or were converted from:

- Repository: https://github.com/bennyhe/pokeSleepCalc
- Author/account: bennyhe
- Snapshot commit: `332967486d840f72a02fdbcd591a55ed9d7c6c64`

`score/convert_pc_data.js` records part of the conversion process from copied `pc_*.js` source modules into JSON consumed by Python. `score/build_species_map.py` and `build_ingredients.py` generate supporting mappings.

The small portrait/ingredient images used for recognition are reference assets tied to Pokémon/game content. They are not relicensed by this project. See `THIRD_PARTY_NOTICES.md`.

## Other sources

`box-exporter/pokemon_data.json` and `box-exporter/index.html` are local lookup/export support files assembled for this workflow. Daifuku (`pokemonsleepdaifuku.com`) is queried only when the user explicitly supplies `--with-daifuku`; no Daifuku responses or browser profiles are included in the repository.

When updating any data snapshot, record the upstream URL, exact commit/date, conversion command, and affected tests in the pull request and changelog.
