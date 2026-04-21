#!/usr/bin/env node
/**
 * Token drift-check agent.
 *
 * Checks performed:
 *   1. Every JSON file in tokens/ is valid JSON.
 *   2. Every JSON file is formatted with 2-space indentation + trailing newline.
 *   3. Every token leaf node (object with "value" + "type") has:
 *        a. A non-empty "value" field.
 *        b. A recognised "type" field.
 *        c. A valid color value when type === "color" (no bare "#", no "#rgb(…)").
 *        d. Well-formed reference syntax — "{Token.Path}" must not be empty.
 *   4. Every token-set name listed in $metadata.json tokenSetOrder resolves
 *      to an actual file on disk (tokens/<name>.json).
 *   5. Every token-set name referenced inside $themes.json selectedTokenSets
 *      is also listed in $metadata.json.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const TOKENS_DIR = path.resolve(__dirname, '..', 'tokens');

/**
 * Exhaustive list of Tokens Studio / W3C DTCG token types used in this repo.
 * Add new types here as needed.
 */
const VALID_TYPES = new Set([
  'color',
  'spacing',
  'sizing',
  'borderRadius',
  'borderWidth',
  'dimension',
  'opacity',
  'fontFamilies',
  'fontSizes',
  'fontWeights',
  'lineHeights',
  'textDecoration',
  'strokeStyle',
  'x', 'y', 'blur', 'spread',
  // 'type' is a valid Tokens Studio type for the "type" property of shadow tokens
  // (e.g., elevation tokens use { "value": "dropShadow", "type": "type" })
  'type',
  'typography',
  'boxShadow',
  'border',
  'composition',
  'letterSpacing',
  'paragraphSpacing',
  'paragraphIndent',
  'textCase',
]);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Recursively collect every *.json path under a directory. */
function findJsonFiles(dir) {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...findJsonFiles(full));
    } else if (entry.name.endsWith('.json')) {
      results.push(full);
    }
  }
  return results;
}

/**
 * Walk a parsed token JSON object and validate every leaf token.
 *
 * A "leaf token" is any object whose direct properties include both
 * "value" (any non-object) and "type" (string).
 */
function validateTokenTree(node, tokenPath, errors) {
  if (typeof node !== 'object' || node === null) return;

  // Detect a leaf token: has both "value" and "type" as own properties,
  // and "type" is a string (not a nested group that happens to have "type").
  if (
    Object.prototype.hasOwnProperty.call(node, 'value') &&
    Object.prototype.hasOwnProperty.call(node, 'type') &&
    typeof node.type === 'string'
  ) {
    const { value, type } = node;

    // 3a. Non-empty value
    if (value === '' || value === null || value === undefined) {
      errors.push(`[empty-value]    "${tokenPath}" has an empty value`);
    }

    // 3b. Recognised type
    if (!VALID_TYPES.has(type)) {
      errors.push(`[unknown-type]   "${tokenPath}" has unrecognised type "${type}" — add it to VALID_TYPES if intentional`);
    }

    if (type === 'color' && typeof value === 'string') {
      // 3c-i. Bare "#" is not a valid color
      if (value.trim() === '#') {
        errors.push(`[invalid-color]  "${tokenPath}" value is bare "#" (empty hex color)`);
      }
      // 3c-ii. "#rgb(…)" is a common copy-paste mistake; should be "rgb(…)"
      if (/^#rgb\(/.test(value.trim())) {
        errors.push(`[invalid-color]  "${tokenPath}" value "${value}" starts with "#rgb(" — remove the leading "#"`);
      }
    }

    // 3d. Reference syntax — every {…} must be non-empty
    if (typeof value === 'string') {
      for (const match of value.matchAll(/\{([^}]*)\}/g)) {
        if (match[1].trim() === '') {
          errors.push(`[empty-ref]      "${tokenPath}" contains an empty reference "{}"`);
        }
      }
    }

    // Do not recurse further into a leaf token's own children
    return;
  }

  // Recurse into group nodes; skip private/meta keys
  for (const [key, child] of Object.entries(node)) {
    if (key === '$extensions' || key === '$figmaStyleReferences') continue;
    if (typeof child === 'object' && child !== null && !Array.isArray(child)) {
      validateTokenTree(child, tokenPath ? `${tokenPath}.${key}` : key, errors);
    }
  }
}

// ---------------------------------------------------------------------------
// Main validation
// ---------------------------------------------------------------------------

let totalErrors = 0;
const allFiles  = findJsonFiles(TOKENS_DIR);

// Collect all token-set names from $metadata.json for cross-checks
let metadataTokenSets = [];

for (const filePath of allFiles) {
  const relPath = path.relative(TOKENS_DIR, filePath);
  const fileErrors = [];

  // --- 1. Valid JSON ---
  let parsed;
  let raw;
  try {
    raw    = fs.readFileSync(filePath, 'utf8');
    parsed = JSON.parse(raw);
  } catch (err) {
    fileErrors.push(`[invalid-json]   File is not valid JSON: ${err.message}`);
    printFileErrors(relPath, fileErrors);
    totalErrors += fileErrors.length;
    continue;
  }

  // --- 2. Formatting consistency ---
  const expected = JSON.stringify(parsed, null, 2) + '\n';
  if (raw !== expected) {
    fileErrors.push(
      '[formatting]     File is not formatted with 2-space indentation + trailing newline. ' +
      'Run "npm run format" to fix.'
    );
  }

  // --- 3. Token structure / value quality (skip $metadata and $themes) ---
  if (!relPath.startsWith('$')) {
    validateTokenTree(parsed, '', fileErrors);
  }

  // --- Capture $metadata for later cross-checks ---
  if (relPath === '$metadata.json' && Array.isArray(parsed.tokenSetOrder)) {
    metadataTokenSets = parsed.tokenSetOrder;
  }

  printFileErrors(relPath, fileErrors);
  totalErrors += fileErrors.length;
}

// --- 4. $metadata.json tokenSetOrder → file existence ---
{
  const metadataErrors = [];
  for (const tokenSet of metadataTokenSets) {
    const expectedFile = path.join(TOKENS_DIR, `${tokenSet}.json`);
    if (!fs.existsSync(expectedFile)) {
      metadataErrors.push(
        `[metadata-drift] "$metadata.json" tokenSetOrder entry "${tokenSet}" ` +
        `does not resolve to an existing file (expected: tokens/${tokenSet}.json)`
      );
    }
  }
  printFileErrors('$metadata.json [cross-check]', metadataErrors);
  totalErrors += metadataErrors.length;
}

// --- 5. $themes.json selectedTokenSets → $metadata.json membership ---
{
  const themesPath = path.join(TOKENS_DIR, '$themes.json');
  const themesErrors = [];
  if (fs.existsSync(themesPath)) {
    let themes;
    try {
      themes = JSON.parse(fs.readFileSync(themesPath, 'utf8'));
    } catch (_) {
      themes = null; // already caught by the main loop above
    }
    if (Array.isArray(themes)) {
      const metaSet = new Set(metadataTokenSets);
      for (const theme of themes) {
        if (typeof theme.selectedTokenSets !== 'object') continue;
        for (const setName of Object.keys(theme.selectedTokenSets)) {
          if (!metaSet.has(setName)) {
            themesErrors.push(
              `[themes-drift]   Theme "${theme.name}" references token set "${setName}" ` +
              'which is not listed in $metadata.json tokenSetOrder'
            );
          }
        }
      }
    }
  }
  printFileErrors('$themes.json [cross-check]', themesErrors);
  totalErrors += themesErrors.length;
}

// ---------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------

if (totalErrors === 0) {
  console.log('✅  All token checks passed.');
  process.exit(0);
} else {
  console.error(`\n❌  ${totalErrors} error(s) found. Fix the issues above before merging.`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

function printFileErrors(label, errors) {
  if (errors.length === 0) return;
  console.error(`\n  📄  ${label}`);
  for (const e of errors) {
    console.error(`     ${e}`);
  }
}
