# incoming/

Drop a raw Tokens Studio export here (single JSON file, sets as top-level keys) on any branch
except `main`, then push. The `Clean Supabase token export` workflow will:

1. keep every description already in `tokens/` and move exporter notes to a report,
2. log every value change to an existing token,
3. quarantine tokens that do not exist in `tokens/` into `tokens/Supabase/` (loaded, never pushed),
4. open a pull request against `main` with the report as its description.

Nothing reaches Tokens Studio or Figma until that pull request is merged.
Files in this folder are inputs only; do not edit `tokens/` by hand in the same branch.
