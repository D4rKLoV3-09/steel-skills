function buildWorkbook(spec){
  /* port of generate-mto build_mto.py, function by function: same cells, formulas and styles */
  const wb = new ExcelJS.Workbook(); wb.calcProperties = {fullCalcOnLoad: true};
  const FONT = 'Times New Roman', BLUE = 'FF0000FF', GREEN = 'FF008000';
  const thin = {style: 'thin'}, dbl = {style: 'double'};
  const HDR_B = {left: thin, right: thin, top: thin, bottom: dbl}, SUB_B = {top: thin, bottom: thin}, TOT_B = {top: thin, bottom: dbl};
  const fill = argb => ({type: 'pattern', pattern: 'solid', fgColor: {argb}});
  const RED_FILL = fill('FFFFC7CE'), PURPLE_FILL = fill('FFE4D7F5'), HDR_FILL = fill('FFEDEDED');
  const f = (sz = 11, b = false, color = null, u = null) => { const o = {name: FONT, size: sz, bold: b}; if (color) o.color = {argb: color}; if (u) o.underline = u; return o; };
  const fx = s => ({formula: s.replace(/^=/, '')});
  const q = s => `'${s.replace(/'/g, "''")}'`;
  const setPage = (ws, titles) => { ws.pageSetup = Object.assign(ws.pageSetup || {}, {orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0}); if (titles) ws.pageSetup.printTitlesRow = titles; };
  const titleBlock = (ws, h, vcol) => [["CLIENT'S : ", 'client'], ['PROJECT : ', 'project'], ['DESCRIPTION : ', 'description'], ['CONTRACTOR : ', 'contractor'], ['DATE : ', 'date']].forEach(([lab, key], i) => {
    const a = ws.getCell(i + 1, 1); a.value = lab; a.font = f(11, true); const c = ws.getCell(i + 1, vcol); c.value = h[key] || ''; c.font = f(); });
  const UOMS = ['m2', 'm', 'pcs'];
  const kind = r => r.kind || (r.wid && r.thk && !r.kgm ? 'plate' : (r.len ? 'length' : 'piece'));
  const UNIT_COLS = ['Item', 'Material Section', null, null, null, null, 'Category', 'Grade', 'Description', 'Mark', 'Unit wt. (kg/m, kg/m2) / kg/no', 'Surface area (m2/m)',
    'Length (mm)', 'Width (mm)', 'Thk (mm)', 'Qty (no)', 'Set (no)', 'Weight (kg)', 'Painted area (m2)', 'Run (m)', 'Area (m2)', 'kg/m run', 'Dim source / basis'];
  const UNIT_W = [6, 7, 3, 7, 3, 7, 9, 9, 58, 8, 13, 12, 11, 10, 8, 8, 7, 13, 13, 11, 11, 10, 70];
  const NC = UNIT_COLS.length, SRC = NC;
  const FIELD_COL = {cat: 7, grade: 8, desc: 9, mark: 10, kgm: 11, m2m: 12, len: 13, wid: 14, thk: 15, qty: 16, set: 17};
  const INPUT_COLS = [11, 12, 13, 14, 15, 16, 17];
  const NUMFMT = {11: '0.0##', 12: '0.00#', 13: '#,##0', 14: '#,##0', 15: '0.#', 16: '#,##0', 17: '#,##0', 18: '#,##0.0', 19: '#,##0.0', 20: '#,##0.00', 21: '#,##0.00', 22: '0.0'};
  const CENTER = [1, 7, 8, 10, 16, 17, 19, 20, 21, 22];

  /* only what the drawings show (build_mto.py prune / uses): drop categories with no row in any unit, hide unused quantity columns */
  { const used = spec.categories.filter(c => spec.units.some(u => ((u.rows || {})[c.code] || []).length));
    if (used.length && used.length !== spec.categories.length){ const keep = new Set(used.map(c => c.code));
      spec = Object.assign({}, spec, {categories: used, units: spec.units.map(u => Object.assign({}, u, {rows: Object.fromEntries(Object.entries(u.rows || {}).filter(([k]) => keep.has(k)))}))}); } }
  const allRows = spec.units.flatMap(u => Object.values(u.rows || {}).flat());
  const hasRun = allRows.some(r => r.run || (kind(r) === 'measure' && r.uom === 'm'));
  const hasArea = allRows.some(r => kind(r) === 'area' || (kind(r) === 'measure' && r.uom === 'm2'));
  const codes = spec.categories.map(c => c.code);
  if (new Set(codes).size !== codes.length) throw new Error('duplicate category codes');
  for (const u of spec.units){ const bad = Object.keys(u.rows || {}).filter(k => !codes.includes(k)); if (bad.length) throw new Error(`${u.name}: rows under unknown categories ${bad}`); }

  const summ = wb.addWorksheet('Summary ');
  const links = {};
  for (const unit of spec.units){
    const ws = wb.addWorksheet(unit.name);
    titleBlock(ws, spec.header, 5);
    const note = unit.note ? `   (${unit.note})` : '';
    const h6 = ws.getCell(6, 1); h6.value = `QTY-BREAKDOWN : ${unit.name}${note}`; h6.font = f(12, true);
    const key = ws.getCell(6, SRC); key.value = 'Red fill = ASSUMED   Purple fill = SCALED   Blue font = input'; key.font = f(9, true); key.alignment = {horizontal: 'right'};
    UNIT_COLS.forEach((t, i) => { const cell = ws.getCell(7, i + 1); if (t !== null) cell.value = t; cell.font = f(11, true); cell.border = HDR_B; cell.fill = HDR_FILL;
      cell.alignment = {horizontal: 'center', vertical: 'middle', wrapText: true}; });
    ws.mergeCells('B7:F7'); ws.getRow(7).height = 32;
    setPage(ws, '7:7');
    UNIT_W.forEach((w, i) => ws.getColumn(i + 1).width = w === 9 ? 9.0001 : w);  // ExcelJS omits width 9 (its default)
    ws.views = [{state: 'frozen', xSplit: 0, ySplit: 7, topLeftCell: 'A8'}];
    if (!hasRun){ ws.getColumn(20).hidden = true; ws.getColumn(22).hidden = true; }
    if (!hasArea) ws.getColumn(21).hidden = true;

    let r = 8; const subs = {};
    for (const cat of spec.categories){
      const code = cat.code;
      const a = ws.getCell(r, 1); a.value = code; a.font = f(13, true); a.alignment = {horizontal: 'center'};
      const t = ws.getCell(r, 9); t.value = cat.title; t.font = f(13, true, null, 'single');
      const dwg = (unit.dwg || {})[code] || cat.dwg || '';
      const dl = ws.getCell(r + 1, 9); dl.value = dwg ? `Dwg No: ${dwg}` : 'Dwg No: -'; dl.font = f(11, true);
      r += 2; const first = r;
      ((unit.rows || {})[code] || []).forEach((row, i) => {
        const k = kind(row);
        if (k === 'measure' && !UOMS.includes(row.uom)) throw new Error(`${unit.name} ${code}: measure row needs uom in ${UOMS}`);
        const vals = {1: i + 1, 7: row.cat, 8: row.grade, 9: row.desc, 10: row.mark, 11: row.kgm, 12: row.m2m, 13: row.len, 14: row.wid, 15: row.thk, 16: row.qty ?? 1, 17: row.set ?? 1, [SRC]: row.src};
        if (k === 'length' && row.d !== undefined && row.d !== null){ vals[2] = String(row.d); vals[3] = 'x'; vals[4] = String(row.w ?? '');
          if (row.t !== undefined && row.t !== null && row.t !== ''){ vals[5] = 'x'; vals[6] = String(row.t); } }
        for (const cs in vals){ const c = +cs, v = vals[cs]; if (v === undefined || v === null) continue;
          const cell = ws.getCell(r, c); cell.value = v; cell.font = f(c === SRC ? 9 : 11, false, INPUT_COLS.includes(c) ? BLUE : null);
          if (NUMFMT[c]) cell.numFmt = NUMFMT[c];
          if (CENTER.includes(c)) cell.alignment = {horizontal: 'center', vertical: 'top'};
          else if (c === SRC) cell.alignment = {wrapText: false, vertical: 'top'}; }
        for (const [fk, fl] of [['scaled', PURPLE_FILL], ['assumed', RED_FILL]]) for (const fld of row[fk] || []) ws.getCell(r, FIELD_COL[fld]).fill = fl;
        let fm;
        if (k === 'length') fm = `=K${r}*M${r}/1000*P${r}*Q${r}`;
        else if (k === 'plate') fm = `=M${r}/1000*N${r}/1000*O${r}*${row.dens ?? 7.85}*P${r}*Q${r}`;
        else if (k === 'area') fm = `=K${r}*M${r}/1000*N${r}/1000*P${r}*Q${r}`;
        else if (k === 'measure') fm = null;
        else fm = `=K${r}*P${r}*Q${r}`;
        if (fm){ const p = ws.getCell(r, 18); p.value = fx(fm); p.font = f(); p.numFmt = NUMFMT[18]; p.alignment = {vertical: 'top'}; }
        let pa = null;
        if (k === 'length' && row.m2m !== undefined && row.m2m !== null) pa = `=L${r}*M${r}/1000*P${r}*Q${r}`;
        else if (k === 'plate') pa = `=2*M${r}/1000*N${r}/1000*P${r}*Q${r}`;
        if (pa){ const c = ws.getCell(r, 19); c.value = fx(pa); c.font = f(); c.numFmt = NUMFMT[19]; c.alignment = {horizontal: 'center', vertical: 'top'}; }
        const run = row.run || (k === 'measure' && row.uom === 'm') ? `=M${r}/1000*P${r}*Q${r}` : null;
        const area = k === 'area' || (k === 'measure' && row.uom === 'm2') ? `=M${r}/1000*N${r}/1000*P${r}*Q${r}` : null;
        for (const [c, v] of [[20, run], [21, area]]) if (v){ const cell = ws.getCell(r, c); cell.value = fx(v); cell.font = f(); cell.numFmt = NUMFMT[c]; cell.alignment = {horizontal: 'center', vertical: 'top'}; }
        for (let c = 1; c <= NC; c++){ const cell = ws.getCell(r, c); const al = cell.alignment || {};
          cell.alignment = {horizontal: al.horizontal, vertical: 'top', wrapText: al.wrapText}; }
        r++;
      });
      const last = r - 1;
      ws.getCell(r, 9).value = `Sub-Total ${code}`;
      ['R', 'S', 'T', 'U'].forEach((L, j) => ws.getCell(r, 18 + j).value = last >= first ? fx(`=SUM(${L}${first}:${L}${last})`) : 0);
      ws.getCell(r, 22).value = fx(`=IF(AND(T${r}>0,R${r}>0),R${r}/T${r},"")`);
      for (let c = 1; c <= NC; c++){ const cell = ws.getCell(r, c); cell.border = SUB_B; cell.font = f(11, true); }
      ws.getCell(r, 18).numFmt = ws.getCell(r, 19).numFmt = '#,##0';
      ws.getCell(r, 20).numFmt = ws.getCell(r, 21).numFmt = '#,##0.0';
      ws.getCell(r, 22).numFmt = NUMFMT[22];
      subs[code] = r; r += 2;
    }
    const total = r;
    ws.getCell(r, 9).value = `TOTAL ${unit.name} (kg)`;
    ['R', 'S', 'T', 'U'].forEach((L, j) => ws.getCell(r, 18 + j).value = fx('=' + Object.values(subs).map(x => `${L}${x}`).join('+')));
    for (let c = 1; c <= NC; c++){ const cell = ws.getCell(r, c); cell.border = TOT_B; cell.font = f(12, true); }
    ws.getCell(r, 18).numFmt = ws.getCell(r, 19).numFmt = '#,##0';
    ws.getCell(r, 20).numFmt = ws.getCell(r, 21).numFmt = '#,##0.0';
    ws.pageSetup.printArea = `A1:V${total}`;
    links[unit.name] = [subs, total];
  }

  // summary
  const ws = summ;
  const cur = spec.currency || 'RM', units = spec.units.map(u => u.name), n = units.length;
  const tcol = 3 + n, ucol = 4 + n, rcol = 5 + n, acol = 6 + n, T = colL(tcol), R = colL(rcol), A = colL(acol), last = colL(acol);
  titleBlock(ws, spec.header, 3);
  ['Sl. No.', 'Description', ...units, 'Total (kg)', 'Unit', `Rate (${cur})`, `Amount (${cur})`, 'Painted area (m2)', 'Run (m)', 'Area (m2)', 'kg/m run'].forEach((t, i) => {
    const cell = ws.getCell(7, i + 1); cell.value = t; cell.font = f(11, true); cell.border = HDR_B; cell.fill = HDR_FILL;
    cell.alignment = {horizontal: 'center', vertical: 'middle', wrapText: true}; });
  ws.getRow(7).height = 32;
  setPage(ws, null);
  [7, 80, ...Array(n).fill(13), 14, 7, 11, 13, 16, 11, 11, 10].forEach((w, i) => ws.getColumn(i + 1).width = w === 9 ? 9.0001 : w);  // ExcelJS omits width 9 (its default)
  if (!hasRun){ ws.getColumn(acol + 2).hidden = true; ws.getColumn(acol + 4).hidden = true; }
  if (!hasArea) ws.getColumn(acol + 3).hidden = true;
  const rates = spec.rates || {};
  let r = 8;
  for (const cat of spec.categories){
    const code = cat.code;
    const a = ws.getCell(r, 1); a.value = code; a.font = f(13, true); a.alignment = {horizontal: 'center'};
    const b = ws.getCell(r, 2); b.value = cat.title; b.font = f(11, true); b.alignment = {wrapText: true, vertical: 'middle'};
    units.forEach((u, j) => { const c = ws.getCell(r, 3 + j); c.value = fx(`=${q(u)}!R${links[u][0][code]}`); c.font = f(11, false, GREEN); c.numFmt = '#,##0'; });
    const c = ws.getCell(r, tcol); c.value = fx(`=SUM(C${r}:${colL(2 + n)}${r})`); c.font = f(11, true); c.numFmt = '#,##0';
    ws.getCell(r, ucol).value = 'kg'; ws.getCell(r, ucol).font = f();
    const pc = ws.getCell(r, acol + 1); pc.value = fx('=' + units.map(u => `${q(u)}!S${links[u][0][code]}`).join('+')); pc.font = f(11, false, GREEN); pc.numFmt = '#,##0.0';
    for (const [k, col] of [[2, 'T'], [3, 'U']]){ const cc = ws.getCell(r, acol + k); cc.value = fx('=' + units.map(u => `${q(u)}!${col}${links[u][0][code]}`).join('+')); cc.font = f(11, false, GREEN); cc.numFmt = '#,##0.0'; }
    const rn = colL(acol + 2);
    const km = ws.getCell(r, acol + 4); km.value = fx(`=IF(AND(${rn}${r}>0,${T}${r}>0),${T}${r}/${rn}${r},"")`); km.font = f(11, true); km.numFmt = '0.0';
    if (code in rates){ const rc = ws.getCell(r, rcol); rc.value = rates[code]; rc.font = f(11, false, BLUE);
      const am = ws.getCell(r, acol); am.value = fx(`=${T}${r}*${R}${r}`); am.font = f(); am.numFmt = '#,##0.00'; }
    r++;
  }
  const first = 8, lastcat = r - 1;
  ws.getCell(r, 2).value = spec.unit_label === undefined ? 'Sub-Total per unit (kg)' : `Sub-Total per ${spec.unit_label} (kg)`;
  for (let c = 3; c <= tcol; c++){ const cl = colL(c); const cell = ws.getCell(r, c); cell.value = fx(`=SUM(${cl}${first}:${cl}${lastcat})`); cell.numFmt = '#,##0'; }
  if (Object.keys(rates).length){ const cell = ws.getCell(r, acol); cell.value = fx(`=SUM(${A}${first}:${A}${lastcat})`); cell.numFmt = '#,##0.00'; }
  for (let c = 1; c <= acol + 4; c++){ const cell = ws.getCell(r, c); cell.border = SUB_B; cell.font = f(11, true); }
  const sub = r;
  for (const k of [1, 2, 3]){ const cl = colL(acol + k); const ps = ws.getCell(r, acol + k); ps.value = fx(`=SUM(${cl}${first}:${cl}${lastcat})`); ps.font = f(11, true); ps.numFmt = '#,##0.0'; }
  r++;
  const word = spec.unit_label || 'unit';
  const ck = ws.getCell(r, 2); ck.value = `Check: ${word} sheet total (kg)`; ck.font = f(10);
  units.forEach((u, j) => { const c = ws.getCell(r, 3 + j); c.value = fx(`=${q(u)}!R${links[u][1]}`); c.font = f(10, false, GREEN); c.numFmt = '#,##0'; });
  r++; const pct = r;
  const al = ws.getCell(r, 2); al.value = 'Connection / misc. allowance (%) - 0 when plates and bolts are itemised'; al.font = f();
  const pcc = ws.getCell(r, tcol); pcc.value = spec.allowance || 0; pcc.font = f(11, false, BLUE); pcc.numFmt = '0.0%';
  r++;
  const al2 = ws.getCell(r, 2); al2.value = 'Allowance (kg)'; al2.font = f();
  for (let c = 3; c <= tcol; c++){ const cl = colL(c); const cell = ws.getCell(r, c); cell.value = fx(`=${cl}${sub}*$${T}$${pct}`); cell.font = f(); cell.numFmt = '#,##0'; }
  const allow = r; r += 2;
  const label = spec.grand_total_label || `${n} UNITS`;
  ws.getCell(r, 2).value = `GRAND TOTAL - ${label} (kg)`;
  const g1 = ws.getCell(r, tcol); g1.value = fx(`=${T}${sub}+${T}${allow}`); g1.numFmt = '#,##0';
  ws.getCell(r + 1, 2).value = `GRAND TOTAL - ${label} (tonnes)`;
  const g2 = ws.getCell(r + 1, tcol); g2.value = fx(`=${T}${r}/1000`); g2.numFmt = '#,##0.00';
  for (const rr of [r, r + 1]) for (let c = 1; c <= acol + 4; c++){ const cell = ws.getCell(rr, c); cell.border = TOT_B; cell.font = f(12, true); }
  r += 2;
  const sections = (spec.cautions && spec.cautions.length) ? [['CAUTIOUS', spec.cautions]] : [];
  sections.push(['LEFT OUT OF THIS TAKE-OFF', (spec.left_out && spec.left_out.length) ? spec.left_out : ['Nothing left out.']]);
  if (spec.decisions && spec.decisions.length) sections.push(['DECISIONS FOR YOU', spec.decisions]);
  sections.push(['ASSUMPTIONS / ITEMS TO VERIFY', spec.assumptions || []]);
  for (const [title, items] of sections){
    r += 2;
    const ah = ws.getCell(r, 1); ah.value = title; ah.font = f(12, true);
    for (const a of items){
      r++;
      const d = ws.getCell(r, 1); d.value = '-'; d.font = f(10); d.alignment = {horizontal: 'right', vertical: 'top'};
      const c = ws.getCell(r, 2); c.value = a; c.font = f(10); c.alignment = {wrapText: true, vertical: 'top'};
      ws.mergeCells(`B${r}:${last}${r}`);
      ws.getRow(r).height = 15 * Math.max(2, Math.ceil(a.length / 170));
    }
  }
  return wb;
}
