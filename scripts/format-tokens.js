#!/usr/bin/env node
/**
 * Auto-formatter for token JSON files.
 *
 * Rewrites every *.json file under tokens/ using 2-space indentation
 * and a single trailing newline.  Key order is preserved.
 *
 * Usage:
 *   npm run format
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const TOKENS_DIR = path.resolve(__dirname, '..', 'tokens');

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

let fixed = 0;
let skipped = 0;

for (const filePath of findJsonFiles(TOKENS_DIR)) {
  const raw = fs.readFileSync(filePath, 'utf8');

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    console.error(`⚠️  Skipping invalid JSON: ${path.relative(TOKENS_DIR, filePath)} — ${err.message}`);
    skipped++;
    continue;
  }

  const formatted = JSON.stringify(parsed, null, 2) + '\n';
  if (raw !== formatted) {
    fs.writeFileSync(filePath, formatted, 'utf8');
    console.log(`  ✏️   Formatted: ${path.relative(TOKENS_DIR, filePath)}`);
    fixed++;
  }
}

if (fixed === 0 && skipped === 0) {
  console.log('✅  All token files are already correctly formatted.');
} else {
  if (fixed > 0)   console.log(`\n✅  Formatted ${fixed} file(s).`);
  if (skipped > 0) console.warn(`⚠️  Skipped ${skipped} file(s) with JSON errors — fix them manually.`);
}
