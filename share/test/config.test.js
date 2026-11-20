// Run with the share Worker's tests: node --test "share/test/*.test.js"

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

// Rate-limit namespaces are the account's, not a Worker's: two bindings on one
// id would share its counters and its settings.
test("no rate limit shares a namespace with another, in either Worker", () => {
  const ids = ['../wrangler.toml', '../../worker/wrangler.toml'].flatMap((file) =>
    [...readFileSync(new URL(file, import.meta.url), 'utf8').matchAll(/^name = "(\w+)".*\nnamespace_id = "(\d+)"/gm)].map((m) => [m[2], `${file} ${m[1]}`]));
  assert.ok(ids.length >= 10, `found ${ids.length}`);
  const seen = new Map();
  for (const [id, what] of ids) {
    assert.ok(!seen.has(id), `${what} and ${seen.get(id)} share namespace_id ${id}`);
    seen.set(id, what);
  }
});
