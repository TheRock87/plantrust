/* v2 step 9: end-to-end check of the #dashboard section, run in the served page (browser console or a browser tool).
   Serve: uv run python -m http.server 8000 -d site, open http://localhost:8000/, paste this, await the result.
   It clicks every approach button and decides every proposal of every house, then compares with results.json.
   Returns {pass, failures, checked}; pass must be true. */
(async () => {
  const d = await fetch("data/results.json", { cache: "reload" }).then((r) => r.json());
  const usd = (n) => "$" + Math.round(n).toLocaleString("en-US");
  const fail = [], q = (s) => document.querySelector(s), qa = (s) => [...document.querySelectorAll(s)];
  const check = (ok, msg) => { if (!ok) fail.push(msg); };
  let checked = 0;

  // 1. Approach switch: tiles and bars match the script numbers for every row.
  for (const k of ["v1", "B", "C", "D"]) {
    q(`#dash-approach button[data-row="${k}"]`).click();
    const s = d.scores.rows[k];
    qa("#dash-approach button").forEach((b) => check(b.getAttribute("aria-pressed") === String(b.dataset.row === k), `${k}: aria-pressed`));
    check(q("#tile-fixed").textContent.includes(`${s.fixed} of ${s.errors}`), `${k}: fixed tile`);
    check(q("#tile-harmful").textContent.trim().startsWith(String(s.harmful_edits)), `${k}: harmful tile`);
    check(q("#tile-manual").textContent.trim().startsWith(String(s.manual_items)), `${k}: manual tile`);
    check(q("#tile-usd").textContent.includes(usd(s.usd_open)), `${k}: usd tile`);
    for (const [code, t] of Object.entries(s.per_type)) {
      const txt = q(`#dash-bars [data-code="${code}"] .counts`).textContent;
      check(txt.includes(`✓ ${t.fixed}`) && txt.includes(`✗ ${t.missed}`), `${k} ${code}: bar counts`);
    }
    checked++;
  }

  // 2. Drafter's job: agreeing with the simulated drafter on every edit leaves only the drafter items open.
  const sel = q("#dash-house");
  for (const opt of [...sel.options]) {
    sel.value = opt.value;
    sel.dispatchEvent(new Event("change"));
    const items = d.houses.find((h) => h.id === opt.value).rooms.flatMap((r) => r.items);
    const edits = items.filter((i) => i.decision), asks = items.filter((i) => i.action === "ask_drafter");
    check(qa("#dash-items [data-edit]").length === edits.length, `${opt.value}: edit rows`);
    qa("#dash-items [data-edit]").forEach((li, n) => li.querySelector(`button[data-decide="${edits[n].decision}"]`).click());
    const result = q("#dash-result").textContent;
    if (edits.length) check(result.includes(`${edits.length} of ${edits.length}`), `${opt.value}: agreed all (${result})`);
    const open = asks.reduce((a, i) => a + i.usd, 0);  // only the drafter items stay open
    check(q("#dash-counter").textContent.includes(usd(open)) && q("#dash-counter").textContent.includes(`open items: ${asks.length}`),
      `${opt.value}: counter after agreeing (${q("#dash-counter").textContent})`);
    checked++;
  }

  // 3. Disagreeing once lowers the agreement count by one.
  const withEdits = [...sel.options].find((o) => d.houses.find((h) => h.id === o.value).rooms.some((r) => r.items.some((i) => i.decision)));
  sel.value = withEdits.value;
  sel.dispatchEvent(new Event("change"));
  const rows = qa("#dash-items [data-edit]");
  const sim = d.houses.find((h) => h.id === withEdits.value).rooms.flatMap((r) => r.items).filter((i) => i.decision);
  rows.forEach((li, n) => li.querySelector(`button[data-decide="${n === 0 ? (sim[0].decision === "approve" ? "reject" : "approve") : sim[n].decision}"]`).click());
  check(q("#dash-result").textContent.includes(`${sim.length - 1} of ${sim.length}`), `disagree once (${q("#dash-result").textContent})`);
  checked++;

  // 4. Review budget slider: K houses in triage order cover the sum of their dollars at risk.
  const slider = q("#dash-budget"), tri = d.scores.triage, total = tri.reduce((a, h) => a + h.usd_at_risk, 0);
  for (const k of [0, 1, 10, tri.length]) {
    slider.value = k;
    slider.dispatchEvent(new Event("input"));
    const covered = tri.slice(0, k).reduce((a, h) => a + h.usd_at_risk, 0);
    const txt = q("#dash-budget-out").textContent;
    check(txt.includes(`${k} of ${tri.length} houses`) && txt.includes(`${usd(covered)} of ${usd(total)}`), `slider ${k} (${txt})`);
  }
  checked++;

  // 5. The main results table shows the script numbers, and the removed "Goal not met" sentence stays removed.
  const mainRows = qa("#score-table tbody tr").map((tr) => [...tr.cells].map((c) => c.textContent.trim()));
  ["v1", "B", "C", "D"].forEach((k, i) => {
    const s = d.scores.rows[k];
    check(mainRows[i][1].startsWith(`${s.fixed} of ${s.errors}`) && mainRows[i][4] === String(s.harmful_edits)
      && mainRows[i][5] === String(s.manual_items), `main table ${k}`);
  });
  check(!document.body.innerText.includes("Goal not met"), "goal sentence removed");
  checked++;

  return { pass: fail.length === 0, failures: fail, checked };
})();
