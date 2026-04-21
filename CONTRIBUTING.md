# Contributing to the Design Token Repository

This document explains how to work safely with the tokens in this repository and what automated checks keep them clean.

---

## Table of contents

1. [Repository layout](#repository-layout)
2. [How to add or edit a token](#how-to-add-or-edit-a-token)
3. [Naming conventions](#naming-conventions)
4. [What is generated vs. what is hand-edited](#what-is-generated-vs-what-is-hand-edited)
5. [Local guardrails (pre-commit)](#local-guardrails-pre-commit)
6. [CI drift checks](#ci-drift-checks)
7. [Troubleshooting CI failures](#troubleshooting-ci-failures)

---

## Repository layout

```
token-bt/
├── tokens/                   ← single source of truth for all design tokens
│   ├── $metadata.json        ← Tokens Studio: ordered list of all token sets
│   ├── $themes.json          ← Tokens Studio: theme configurations
│   ├── Primitive/            ← raw values (no references to other tokens)
│   │   ├── Color.json
│   │   ├── Spacing.json
│   │   ├── Border.json
│   │   ├── Size.json
│   │   ├── Opacity.json
│   │   ├── Shadow.json
│   │   └── Typography.json
│   ├── Semantic/             ← aliases that reference Primitive tokens
│   │   ├── color mode/
│   │   │   ├── light.json
│   │   │   └── dark.json
│   │   ├── Border.json
│   │   ├── Elevation.json
│   │   ├── Opacity.json
│   │   ├── Size.json
│   │   ├── Spacing.json
│   │   └── Typography.json
│   └── Component/            ← component-level overrides referencing Semantic tokens
│       ├── color mode/
│       │   ├── light.json
│       │   └── dark.json
│       ├── Border radius.json
│       ├── Size.json
│       └── Spacing.json
├── scripts/
│   ├── validate-tokens.js    ← drift-check agent (run by CI and pre-commit)
│   └── format-tokens.js      ← auto-formatter
├── .github/
│   └── workflows/
│       └── validate-tokens.yml  ← CI workflow
├── .githooks/
│   └── pre-commit            ← local pre-commit hook
├── .editorconfig             ← editor formatting rules
└── package.json
```

### Layering rules

Token references must flow in **one direction only**:

```
Primitive  →  Semantic  →  Component
```

- **Primitive** tokens hold raw values (hex colors, px values, rem sizes). They must **never** reference other tokens.
- **Semantic** tokens give meaning to primitives (`background.primary`, `text.error`). They reference Primitive tokens.
- **Component** tokens describe component-specific behavior. They reference Semantic (or Primitive) tokens but **never** reference other Component tokens.

Circular references will break any Style Dictionary / token-transformer build.

---

## How to add or edit a token

### 1. Edit via Tokens Studio (Figma plugin) — recommended

Open the Figma file, make changes in Tokens Studio, and sync/push to this repository.  The plugin handles JSON serialization.

### 2. Edit JSON files directly

1. Open the appropriate JSON file for the layer you are working in (`Primitive/`, `Semantic/`, or `Component/`).
2. Follow the existing token shape:
   ```json
   "tokenName": {
     "value": "<raw value or {Reference.Path}>",
     "type": "<token type>"
   }
   ```
3. Do **not** add raw values to Semantic or Component layers — use references (`{Primitive.tokenName}`).
4. Run `npm run format` to normalize JSON formatting.
5. Run `npm run validate` to check for drift before committing.

### Adding a new token set

1. Create the JSON file in the correct layer folder (e.g., `tokens/Semantic/NewSet.json`).
2. Add the token set name to `$metadata.json` `tokenSetOrder` **in the correct position** (Primitive before Semantic before Component).
3. If the set should be included in a theme, add it to the relevant theme in `$themes.json`.
4. Run `npm run validate` — check 4 will confirm the file is reachable from `$metadata.json`.

---

## Naming conventions

| Layer | Folder | File naming |
|---|---|---|
| Primitive | `tokens/Primitive/` | PascalCase, no leading spaces (`Color.json`, `Spacing.json`) |
| Semantic | `tokens/Semantic/` | PascalCase, no leading spaces (`Border.json`) |
| Component | `tokens/Component/` | PascalCase, no leading spaces |

**Token names** inside JSON files should use `camelCase` or `kebab-case` consistently within a file. Avoid spaces in token names.

**References** use `{Group.SubGroup.tokenName}` syntax — curly braces, dot-separated path, no spaces inside braces.

---

## What is generated vs. what is hand-edited

| Path | Status | Edit? |
|---|---|---|
| `tokens/**/*.json` | **Hand-edited / Tokens Studio** | ✅ Yes — this is the source of truth |
| `tokens/$metadata.json` | **Tokens Studio managed** | Only via Tokens Studio or when adding/removing sets |
| `tokens/$themes.json` | **Tokens Studio managed** | Only via Tokens Studio |
| `scripts/` | **Hand-edited** | When adding new validation rules |
| `.github/workflows/` | **Hand-edited** | When changing CI configuration |

If your project generates CSS/JS from these tokens (e.g., via Style Dictionary or token-transformer), **never edit the generated output files manually** — they will be overwritten. Put generated files in a separate directory (e.g., `dist/`) and add it to `.gitignore`.

---

## Local guardrails (pre-commit)

After cloning the repo, run once:

```sh
npm install
```

This triggers the `prepare` script which sets `core.hooksPath` to `.githooks/`.  From then on, every `git commit` automatically runs `scripts/validate-tokens.js`.  If validation fails the commit is blocked.

To bypass the hook in an emergency:

```sh
git commit --no-verify -m "..."
```

> Use `--no-verify` only when absolutely necessary. CI will still catch the issue.

To run validation manually at any time:

```sh
npm run validate    # check for drift
npm run format      # auto-fix formatting
```

---

## CI drift checks

Every pull request that touches `tokens/**`, `scripts/**`, or `package.json` triggers the **Validate Design Tokens** GitHub Actions workflow (`.github/workflows/validate-tokens.yml`).

The workflow runs `node scripts/validate-tokens.js` and fails the PR if any errors are found.

### What the validator checks

| Check | Error code | Description |
|---|---|---|
| JSON syntax | `[invalid-json]` | File must be valid parseable JSON |
| Formatting | `[formatting]` | File must use 2-space indentation + trailing newline |
| Empty value | `[empty-value]` | Token leaf `value` must not be `""`, `null`, or `undefined` |
| Unknown type | `[unknown-type]` | Token `type` must be in the known type list |
| Invalid color | `[invalid-color]` | Colors must not be bare `"#"` or start with `"#rgb("` |
| Empty reference | `[empty-ref]` | `{…}` references inside a value must not be empty |
| Metadata drift | `[metadata-drift]` | Every entry in `$metadata.json` must map to an existing file |
| Themes drift | `[themes-drift]` | Every token set referenced in `$themes.json` must exist in `$metadata.json` |

---

## Troubleshooting CI failures

### `[formatting]` — "File is not formatted with 2-space indentation"

Run locally:

```sh
npm run format
git add tokens/
git commit --amend --no-edit   # or a new commit
```

### `[invalid-color]` — bare `"#"` or `"#rgb(…)"`

The color value is either empty or malformed.

- If it was supposed to be an empty/transparent value, use `rgba(0,0,0,0)` or reference the `{transparent}` primitive token.
- If it's a copy-paste error of `#rgb(r g b / a%)`, remove the leading `#` so it reads `rgb(r g b / a%)`.

### `[metadata-drift]` — file not found

The name in `$metadata.json` `tokenSetOrder` does not match any file on disk.  Common causes:

- A file was renamed but `$metadata.json` was not updated.
- A leading space in the file name (`" Size.json"`) differs from the metadata entry (`"Size"`).

Fix: make the file path and the metadata entry identical (including any spaces).

### `[themes-drift]` — token set not in metadata

A theme in `$themes.json` references a token set that is not listed in `$metadata.json`.  Add the missing set name to `tokenSetOrder` in `$metadata.json`.

### `[unknown-type]` — unrecognised token type

If you intentionally added a new token type (e.g., from a Tokens Studio update), add it to the `VALID_TYPES` set in `scripts/validate-tokens.js`.

### `[empty-ref]` — empty reference `{}`

A token value contains `{}`.  This is almost always a copy-paste mistake.  Replace `{}` with a valid reference like `{Primitive.color.value}`.
