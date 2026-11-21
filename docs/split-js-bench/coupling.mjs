// How tangled a page's script is, section by section (its
// `/* ---------- Name ---------- */` markers): the top-level names each uses
// from other sections, the names they use from it, and assignments across
// sections, which a module couldn't take (imports are read-only). With a
// list of sections, the interface those would need as one module.
//
// It needs acorn and eslint-scope, which the repo doesn't install: copy this
// file to a scratch directory, run `npm i acorn@8.14.0 eslint-scope@8.2.0`
// there, then
//
//   node coupling.mjs path/to/letterfield.html
//   node coupling.mjs path/to/letterfield.html "Sound,Music"
//
// It reads the page's first <script> or <script type="module"> holding `(() => {`.
import { readFileSync } from 'node:fs';
import * as acorn from 'acorn';
import * as eslintScope from 'eslint-scope';

const [file, groupArg] = process.argv.slice(2);
const lines = readFileSync(file, 'utf8').split('\n');
const start = lines.findIndex((l, i) => /^<script( type="module")?>$/.test(l) && lines.slice(i + 1, i + 12).includes('(() => {'));
const end = lines.findIndex((l, i) => i > start && l === '</script>');
const src = lines.slice(start + 1, end).join('\n');
const marks = [];
src.split('\n').forEach((l, i) => {
  const m = /^\/\* -{10} (.+?) -{10} \*\/$/.exec(l);
  if (m) marks.push([i + 1, m[1]]);
});
const sectionOf = (line) => marks.reduce((s, [l, n]) => (l <= line ? n : s), '(top)');
const ast = acorn.parse(src, { ecmaVersion: 'latest', sourceType: 'module', locations: true, ranges: true });
const scopes = eslintScope.analyze(ast, { ecmaVersion: 2022, sourceType: 'module' });
const main = scopes.scopes.find((s) => s.type === 'function' && s.upper && ['global', 'module'].includes(s.upper.type));
const vars = main.variables.filter((v) => v.defs.length);
const lineOf = (node) => node.loc.start.line;

if (groupArg) {
  const group = new Set(groupArg.split(','));
  const imports = new Map(), exports = new Map(), writes = [];
  for (const v of vars) {
    const inside = group.has(sectionOf(lineOf(v.defs[0].name)));
    for (const r of v.references) {
      if (group.has(sectionOf(lineOf(r.identifier))) === inside) continue;
      const m = inside ? exports : imports;
      m.set(v.name, (m.get(v.name) || 0) + 1);
      if (r.isWrite() && !r.init) writes.push(`${v.name} (line ${lineOf(r.identifier) + start + 1})`);
    }
  }
  const list = (m) => [...m].sort((a, b) => b[1] - a[1]).map(([n, c]) => `${n}×${c}`).join(' ');
  console.log(`imports (${imports.size}): ${list(imports)}\n\nexports (${exports.size}): ${list(exports)}\n\nassigned across (${writes.length}): ${writes.join('; ')}`);
} else {
  const stats = new Map();
  const of = (n) => {
    if (!stats.has(n)) stats.set(n, { lines: 0, uses: new Set(), usedBy: new Set(), refs: 0, assignedBy: [] });
    return stats.get(n);
  };
  marks.forEach(([l, n], i) => { of(n).lines = (marks[i + 1]?.[0] ?? src.split('\n').length) - l; });
  for (const v of vars) {
    const home = sectionOf(lineOf(v.defs[0].name));
    for (const r of v.references) {
      const at = sectionOf(lineOf(r.identifier));
      if (at === home) continue;
      of(at).uses.add(v.name);
      of(at).refs++;
      of(home).usedBy.add(v.name);
      if (r.isWrite() && !r.init) of(home).assignedBy.push(`${v.name}@${at}`);
    }
  }
  console.table([...stats].map(([section, s]) => ({ section, lines: s.lines, fromOthers: s.uses.size, usedByOthers: s.usedBy.size, refsOut: s.refs, assignedByOthers: s.assignedBy.length })));
  for (const [section, s] of stats) if (s.assignedBy.length) console.log(`${section}: ${s.assignedBy.join(' ')}`);
}
