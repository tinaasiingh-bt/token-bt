# incoming/

Drop a raw Tokens Studio export here on any branch except `main`, then push. Either shape works:
a single JSON file (`incoming/<name>.json`, sets as top-level keys) or a folder
(`incoming/<name>/tokens/**.json` in the multi-file layout, plus any notes you like beside it). The `Clean Supabase token export` workflow will:

1. keep every description already in `tokens/` and move exporter notes to a report,
2. log every value change to an existing token,
3. quarantine tokens that do not exist in `tokens/` into `tokens/Supabase/` (loaded, never pushed),
4. open a pull request against `main` with the report as its description.

Nothing reaches Tokens Studio or Figma until that pull request is merged.
Files in this folder are inputs only; do not edit `tokens/` by hand in the same branch.

## Or let the workflow do it

Actions -> **Export Supabase tokens** -> Run workflow (choose staging or prod). It generates the export
from the Supabase token tables with `scripts/supabase_export.py` and `rules/supabase-export-rules.json`,
writes it to `incoming/supabase/` on the `incoming/supabase` branch (replaced every run), and then runs
the cleaner so the review PR is opened or updated. Secrets it needs: `SUPABASE_STAGING_URL`,
`SUPABASE_STAGING_SERVICE_ROLE_KEY`, `SUPABASE_PROD_URL`, `SUPABASE_PROD_SERVICE_ROLE_KEY`
(the token tables are readable by authenticated roles only).
