# Troubleshooting

## `doctor` reports missing dependencies

Activate `.venv`, rerun `python -m pip install -e ".[daifuku,dev]"`, then run `playwright install chromium` if Daifuku comparison is needed.

## ADB or MuMu is not found

Set `POKESLEEP_ADB` to the emulator's `adb.exe` and `POKESLEEP_ADB_SERIAL` to its device endpoint. `doctor` treats ADB as optional because demo/offline scoring does not need it.

## OCR rows are incomplete

Open `workspace/results/待复核清单.csv`, inspect the referenced four screenshots, and recapture or correct the affected row. Seasonal/costume forms use portrait and main-skill evidence in addition to OCR name text.

## Daifuku stops working

The integration automates a third-party website and may break when its UI changes. Confirm the site manually, update Playwright selectors, and keep raw third-party results distinct from local/personal scores. Use `DAIFUKU_PROXY` only when required by your network.

## After changing scoring code, old results reappear

Delete the affected progress JSON in your private workspace or, when maintaining the code, increment the relevant algorithm/script version so cached entries invalidate automatically.
