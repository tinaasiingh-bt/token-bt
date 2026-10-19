# rules/

`supabase-export-rules.json` tells `scripts/supabase_export.py` how the Supabase token tables map onto this repo's Tokens Studio sets. The generator reads only Supabase plus this file for values; `tokens/` is consulted for set order, token types and key order so review diffs stay small.

Sections:

- `name_map`: Supabase token (table, name, theme) → Figma set and path, where the path is not derivable from the name.
- `families`: `design_token_families` → typography composite path (plus any `textCase` carried from Figma).
- `aliases`: Figma paths served by an existing Supabase token of a different name. Never added to Supabase.
- `figma_only`: Figma tokens with no Supabase source, emitted verbatim (currently the unreferenced primitive colours and `textCase.none`).
- `value_overrides`: places where the two sides deliberately differ. `keep=figma` holds the Figma value while Supabase still has the recorded value and expires on its own once Supabase changes; `keep=supabase` means Figma should adopt the Supabase value.
- `suppress`: Supabase names never exported (deprecated `color-chart-palette-*`).
- `descriptions`, `extensions`: carried verbatim; the cleaner keeps `tokens/` as the owner of both anyway.

Tokens with no mapping land in `supabase-only/<table>` sets, which the cleaner quarantines under `tokens/supabase/` (loaded, in no theme).

The file is regenerated from the SDS-7613 sweep tooling whenever the mapping changes and lands here by PR. Offline test: `python3 scripts/supabase_export.py --fixture <dir of table dumps> --out /tmp/x`.
