// A built model page's own mtoSpec() run on its data, without a browser -> the spec JSON for build_mto.py.
//   node generate-mto/page_mtospec.js PAGE.html DATA.json OUT_SPEC.json
// The function is taken from the page itself, so the workbook always matches what the page's Export gives.
const fs = require('fs');
const [page, dataPath, out] = process.argv.slice(2);
const html = fs.readFileSync(page, 'utf8');
const i0 = html.indexOf('function mtoSpec('), i1 = html.indexOf('function colL(');
if (i0 < 0 || i1 < i0) { console.error('mtoSpec() not found in ' + page); process.exit(1); }
const D = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
const parts = D.parts.map((p, i) => Object.assign({}, p, {i}));
const mtoSpec = new Function('D', 'parts', 'S', html.slice(i0, i1) + '; return mtoSpec;')(D, parts, {sel: []});
const spec = mtoSpec(null);
fs.writeFileSync(out, JSON.stringify(spec));
console.log(`mtoSpec: ${spec.units.length} units -> ${out}`);
