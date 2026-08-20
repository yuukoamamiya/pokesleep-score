# Privacy

Box screenshots and scoring CSVs reveal a user's collection and play state. Browser profiles may additionally contain cookies or authenticated sessions.

All runtime data defaults to `workspace/`, which is ignored by Git. Keep these items out of commits and issue attachments unless they have been intentionally cropped and sanitized:

- `workspace/`, `cap/`, `评分结果/`, `box_ocr.csv`
- `pw-profile/` or any Playwright/browser user-data directory
- capture/scoring progress JSON and debug screenshots
- proxy URLs containing credentials, cookies, local device serials, or full personal paths

Run `python scripts/public_release_check.py` before a public push. The check is defensive, not a guarantee; inspect `git diff --cached` as well.
