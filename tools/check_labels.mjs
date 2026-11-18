// 画面に日本語名がない記録の欄・選択肢を数える（okura-gov の版を上げたときに実行する）。
//
//   .work/venvs/records/Scripts/python.exe -I -X utf8 okura_web/bridge/meta_records.py > .work/scratch/meta_records.json
//   node tools/check_labels.mjs .work/scratch/meta_records.json
//
// 足りない名前があれば終了コード 1。tools/labels_vocab.json に足して tools/build_labels.py を実行する。
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const { FIELD, ENUM } = await import(pathToFileURL(join(root, 'frontend', 'src', 'lib', 'labels.js')).href);
const m = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const fields = new Map();
const enums = new Map();
const add = (map, k, where) => { if (!map.has(k)) map.set(k, new Set()); map.get(k).add(where); };

function walk(s, where, seen = new Set()) {
  if (!s || typeof s !== 'object') return;
  if (s.$ref) {
    const n = s.$ref.split('/').pop();
    if (!seen.has(n) && m.defs && m.defs[n]) { seen.add(n); walk(m.defs[n], where, seen); }
  }
  if (s.enum) s.enum.forEach((v) => typeof v === 'string' && add(enums, v, where));
  if (typeof s.const === 'string') add(enums, s.const, where);
  for (const [k, v] of Object.entries(s.properties || {})) { add(fields, k, where); walk(v, where, seen); }
  for (const key of ['items', 'additionalProperties']) if (s[key] && typeof s[key] === 'object') walk(s[key], where, seen);
  for (const key of ['oneOf', 'anyOf', 'allOf']) (s[key] || []).forEach((x) => walk(x, where, seen));
}

for (const r of [...(m.records || []), ...(m.ledger || [])]) {
  const w = r.kind;
  for (const k of Object.keys(r.roles || {})) add(fields, k, w);
  for (const [k, v] of Object.entries(r.subject || {})) { add(fields, k, w); walk(v.schema || v, w); }
  for (const [k, v] of Object.entries(r.attributes || {})) { add(fields, k, w); walk(v.schema || v, w); }
  for (const [k, v] of Object.entries(r.amounts || {})) { add(fields, k, w); walk(v.schema || v, w); }
  if (r.value) walk(r.value, w);
}

const missF = [...fields].filter(([k]) => !FIELD[k] && /[a-z]/.test(k));
const missE = [...enums].filter(([k]) => !ENUM[k] && /^[a-z_0-9]+$/.test(k));
for (const [k, w] of missF) console.log('F', k, [...w].slice(0, 3).join(','));
for (const [k, w] of missE) console.log('E', k, [...w].slice(0, 3).join(','));
console.error(`fields ${fields.size} (missing ${missF.length}), enums ${enums.size} (missing ${missE.length})`);
process.exit(missF.length || missE.length ? 1 : 0);
