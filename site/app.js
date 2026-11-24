/* PlanTrust page: reads data/results.json (written by src/export.py) and renders it. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const usd = (n) => "$" + Math.round(n).toLocaleString("en-US");
  const usd2 = (n) => "$" + n.toFixed(2);
  const pct = (a, b) => (b ? Math.round((100 * a) / b) + "%" : "n/a");
  const share = (f) => Math.round(f * 100) + "%";
  const roomName = (label) => (label === "living" ? "living room" : label);
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const feet = (n) => String(Math.round(n * 10) / 10);
  const SVGNS = "http://www.w3.org/2000/svg";

  let DATA = null;

  fetch("data/results.json")
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(
      (d) => { DATA = d; init(); },
      () => {
        $("#panel").innerHTML = "<p>The results file did not load. Serve this folder over HTTP, for example <code>python -m http.server -d site</code>, then reload.</p>";
      }
    );

  function init() {
    $("#model-name").textContent = DATA.model;
    renderTally();
    renderScores();
    renderFailureFix();
    const sel = $("#house-select");
    DATA.houses.forEach((h) => {
      const o = document.createElement("option");
      o.value = h.id;
      o.textContent = `${h.id}: ${h.triage.status}, ${usd(h.triage.usd_at_risk)} in open items (${h.n_errors} planted error${h.n_errors === 1 ? "" : "s"})`;
      sel.appendChild(o);
    });
    sel.addEventListener("change", () => renderHouse(sel.value));
    renderHouse(DATA.houses[0].id);
    renderPart2();
    renderDashboard();
  }

  /* ---------- plan viewer ---------- */

  function svgEl(name, attrs, text) {
    const el = document.createElementNS(SVGNS, name);
    Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, v));
    if (text != null) el.textContent = text;
    return el;
  }

  const STATUS = {
    clear: "nothing to do",
    fixed: "edit approved by the drafter",
    drafter: "a drafter must look",
    missing: "in the tour, missing from the plan",
  };

  function renderHouse(hid) {
    const house = DATA.houses.find((h) => h.id === hid);
    const svg = $("#plan");
    svg.innerHTML = "";
    const xs = house.rooms.flatMap((r) => r.polygon.map((p) => p[0]));
    const ys = house.rooms.flatMap((r) => r.polygon.map((p) => p[1]));
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    // The plan's y axis points up, the screen's points down, so every y is negated.
    const left = minX - 3, top = -maxY - 1.2, width = maxX - minX + 4.2, height = maxY - minY + 4.2;
    svg.setAttribute("viewBox", `${left} ${top} ${width} ${height}`);

    const defs = svgEl("defs");
    const grid = svgEl("pattern", { id: "grid", width: 5, height: 5, patternUnits: "userSpaceOnUse" });
    grid.appendChild(svgEl("path", { d: "M5 0H0V5", class: "grid-line" }));
    const hatch = svgEl("pattern", { id: "hatch", width: 0.9, height: 0.9, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
    hatch.appendChild(svgEl("rect", { width: 0.3, height: 0.9, fill: "#e5df00", "fill-opacity": 0.9 }));
    defs.append(grid, hatch);
    svg.appendChild(defs);
    svg.appendChild(svgEl("rect", { x: left, y: top, width, height, fill: "url(#grid)" }));

    // Overall size, drawn like the dimension lines on a drawing.
    const dim = svgEl("g", { class: "dim" });
    const by = -minY + 1.3, lx = minX - 1.3;
    dim.append(
      svgEl("line", { x1: minX, y1: by, x2: maxX, y2: by }),
      svgEl("line", { x1: minX, y1: by - 0.4, x2: minX, y2: by + 0.4 }),
      svgEl("line", { x1: maxX, y1: by - 0.4, x2: maxX, y2: by + 0.4 }),
      svgEl("text", { x: (minX + maxX) / 2, y: by + 1.1 }, `${feet(maxX - minX)} ft`),
      svgEl("line", { x1: lx, y1: -minY, x2: lx, y2: -maxY }),
      svgEl("line", { x1: lx - 0.4, y1: -minY, x2: lx + 0.4, y2: -minY }),
      svgEl("line", { x1: lx - 0.4, y1: -maxY, x2: lx + 0.4, y2: -maxY }),
      svgEl("text", { x: lx - 0.5, y: -(minY + maxY) / 2, transform: `rotate(-90 ${lx - 0.5} ${-(minY + maxY) / 2})` }, `${feet(maxY - minY)} ft`)
    );
    svg.appendChild(dim);

    // Missing rooms are drawn last so their dashed outline sits on top.
    const ordered = [...house.rooms].sort((a, b) => a.missing_from_plan - b.missing_from_plan);
    ordered.forEach((r) => {
      const px = r.polygon.map((p) => p[0]), py = r.polygon.map((p) => p[1]);
      const w = Math.max(...px) - Math.min(...px), d = Math.max(...py) - Math.min(...py);
      const cx = (Math.max(...px) + Math.min(...px)) / 2, cy = -(Math.max(...py) + Math.min(...py)) / 2;
      const fs = Math.max(0.72, Math.min(1.15, w / 7));
      const g = svgEl("g", {
        class: `room ${r.status}`, "data-id": r.id, tabindex: 0, role: "button",
        "aria-label": `${cap(roomName(r.label))} ${r.id}: ${STATUS[r.status]}`,
      });
      g.appendChild(svgEl("polygon", { points: r.polygon.map((p) => `${p[0]},${-p[1]}`).join(" ") }));
      g.appendChild(svgEl("text", { x: cx, y: cy, "font-size": fs }, cap(roomName(r.label))));
      g.appendChild(svgEl("text", { x: cx, y: cy + fs * 1.05, "font-size": fs * 0.72, class: "size" }, `${feet(w)} × ${feet(d)} ft`));
      const pick = () => selectRoom(house, r.id);
      g.addEventListener("click", pick);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      svg.appendChild(g);
    });
    const first = house.rooms.find((r) => r.status !== "clear") || house.rooms[0];
    selectRoom(house, first.id);
  }

  const ACTION = {
    set_room_size: "Set the room size from the tour", set_ceiling: "Set the ceiling from the tour",
    add_door: "Add a door", mark_wet: "Mark the room as wet", no_change: "No change", ask_drafter: "Ask the drafter",
  };
  const BY = { code: "code", agent: "agent", "code (note not read)": "code", "agent not run": "agent (not run)" };

  function decisionHtml(i) {
    if (i.decision === "approve") return '<span class="ok">✓ Drafter approved</span>';
    if (i.decision === "reject") return '<span class="flag">✗ Drafter rejected</span>';
    if (i.action === "ask_drafter") return '<span class="flag">Drafter item</span>';
    return '<span class="soft">Nothing for the drafter</span>';
  }

  function itemHtml(i) {
    const change = i.action === "ask_drafter" ? esc(i.after)
      : i.action === "no_change" ? "keep the plan" : `${esc(i.before)} → <strong>${esc(i.after)}</strong>`;
    return `<li class="item"><p><strong>${esc(ACTION[i.action] || i.action)}</strong>
        <span class="soft">proposed by ${esc(BY[i.by] || i.by)}, ${i.kind === "doors" ? "door question" : i.kind === "wet" ? "wet question" : "measurements"}</span></p>
      <p>${change}</p>
      ${i.evidence && i.evidence !== i.after ? `<p class="evidence">${i.by === "agent" && i.action !== "ask_drafter" ? "Quote" : "Evidence"}: “${esc(i.evidence)}”</p>` : ""}
      <p>${decisionHtml(i)} <span class="soft">${usd(i.usd)} at risk</span></p>${stepsHtml(i.steps)}</li>`;
  }

  function walls(a) { return a ? a.map((x) => Number(x).toFixed(1)).join(" / ") : "n/a"; }

  function stepsHtml(steps) {
    if (!steps || !steps.length) return "";
    const items = steps.map((s) => {
      if (s.type === "tool_call") return `<li class="call"><span class="kind">tool call</span><code>${esc(s.name)}(${esc(JSON.stringify(s.args))})</code></li>`;
      if (s.type === "tool_result") return `<li><span class="kind">result of ${esc(s.name)}</span><code>${esc(s.text)}</code></li>`;
      return `<li><span class="kind">model</span>${esc(s.text)}</li>`;
    });
    return `<details><summary>Agent steps (${steps.length})</summary><ol class="steps">${items.join("")}</ol></details>`;
  }

  function selectRoom(house, rid) {
    document.querySelectorAll("#plan .room").forEach((g) => g.classList.toggle("selected", g.dataset.id === rid));
    const r = house.rooms.find((x) => x.id === rid);
    const n = r.numbers || {};
    let html = `<p class="room-name">${esc(cap(roomName(r.label)))}</p>
      <p class="room-meta">Room ${esc(r.id)}; the plan says ${r.affected ? "wet" : "not wet"}</p>
      <p>${r.status === "clear" ? '<span class="ok">Nothing to do</span>' : r.status === "fixed" ? '<span class="ok">✓ Fixed</span>' : '<span class="flag">A drafter must look</span>'}</p>`;
    if (r.note) html += `<p class="label">Technician's note</p><p class="evidence">“${esc(r.note)}”</p>`;
    html += r.items.length ? `<p class="label">Proposals and drafter items</p><ul class="items">${r.items.map(itemHtml).join("")}</ul>`
      : `<p class="label">Proposals</p><p class="soft">None: the plan agrees with the tour and the note.</p>`;
    if (r.missing_from_plan) {
      html += `<p class="soft">The dashed outline shows where the room really is (from the answer key), for illustration only. The checker knows the room only from the tour.</p>`;
    } else {
      html += `<table class="compare"><thead><tr><td></td><th>Plan</th><th>Tour</th></tr></thead><tbody>
        <tr><th>Walls (ft)</th><td>${walls(n.plan_walls)}</td><td>${walls(n.tour_walls)}</td></tr>
        <tr><th>Ceiling (ft)</th><td>${esc(n.plan_ceiling)}</td><td>${esc(n.tour_ceiling)}</td></tr>
        <tr><th>Doors</th><td>${esc(n.plan_doors)}</td><td>${esc(n.tour_doors)}</td></tr>
        <tr><th>Label</th><td>${esc(n.plan_label)}</td><td>${esc(n.tour_label)}</td></tr></tbody></table>`;
    }
    const key = r.answer_key
      ? `Planted error <strong>${esc(r.answer_key.code)} ${esc(r.answer_key.name)}</strong>: ${esc(r.answer_key.detail)}. Actual cost at risk ${usd(r.answer_key.actual_cost_at_risk_usd)}.`
      : "No error was planted in this room.";
    html += `<details><summary>Answer key</summary><p>${key}</p></details>`;
    $("#panel").innerHTML = html;
  }

  /* ---------- results ---------- */

  const ROWS = ["v1", "B", "C", "D"];
  const ofN = (a, n) => `${a} of ${n} (${pct(a, n)})`;
  const table = (id, html) => { $(id).className = "data"; $(id).innerHTML = html + "</tbody>"; };

  function renderTally() {
    const d = DATA.scores.rows.D, t = DATA.totals;
    $("#tally").innerHTML =
      `Across all ${t.houses} test houses, with the agent: <strong>${ofN(d.fixed, d.errors)}</strong> planted errors fixed by an approved edit, ` +
      `<strong>${d.missed}</strong> missed, and <strong>${d.manual_items}</strong> items left for a drafter.`;
  }

  // Words that depend on numbers: chosen here from the comparisons export.py computed, never typed.
  const METRIC = {
    fixed: "errors fixed", missed: "errors missed", harmful_edits: "harmful edits proposed",
    manual_items: "drafter items", false_alarm_rooms: "false-alarm rooms", usd_open: "dollars still at risk",
  };
  function verdictHtml() {
    const cmp = DATA.agent_vs_baseline;
    const fmt = (m, v) => (m === "usd_open" ? usd(v) : v);
    const list = (better) => Object.keys(METRIC).filter((m) => cmp[m].agent_better === better && cmp[m].agent !== cmp[m].baseline)
      .map((m) => `${METRIC[m]} (${fmt(m, cmp[m].agent)} against ${fmt(m, cmp[m].baseline)})`);
    const win = list(true), lose = list(false);
    const h = DATA.scores.hard;
    let html = `<p><strong>Agent against the keyword baseline.</strong> ` +
      (win.length ? `The agent is better on ${win.join(", ")}. ` : "The agent is not better on any measure. ") +
      (lose.length ? `<strong>It is worse on ${lose.join(", ")}.</strong>` : "") + `</p>`;
    html += `<p>On ${h.D.cases} hand-written hard notes (negations, notes about another room, tricky archways): agent ${h.D.right} right, keyword rule ${h.C.right} right.</p>`;
    return html;
  }

  function renderScores() {
    const t = DATA.totals, S = DATA.scores;
    $("#results-title").textContent = `Results on ${t.houses} houses`;
    $("#results-intro").textContent =
      `${t.houses} synthetic houses, ${t.rooms} rooms, ${t.errors} planted errors in ${t.houses - t.clean_houses} houses. ` +
      `Code routed ${t.questions} questions to the notes (${t.notes_questions.wet} wet, ${t.notes_questions.doors} doors). ` +
      `Every row is scored on the same rooms and the same answer key; a simulated drafter approves or rejects every edit.`;

    let html = "<thead><tr><th>Approach</th><th>Errors fixed (approved edit)</th><th>Sent to a drafter</th><th>Missed</th>" +
      "<th>Harmful edits proposed</th><th>Drafter items</th><th>False alarms (rooms)</th><th>Dollars still at risk</th></tr></thead><tbody>";
    ROWS.forEach((k) => {
      const s = S.rows[k];
      html += `<tr${k === "D" ? ' class="highlight"' : ""}><td>${esc(S.row_names[k])}</td>
        <td class="num">${ofN(s.fixed, s.errors)}</td><td class="num">${ofN(s.to_drafter, s.errors)}</td>
        <td class="num">${ofN(s.missed, s.errors)}</td><td class="num">${s.harmful_edits}</td><td class="num">${s.manual_items}</td>
        <td class="num">${ofN(s.false_alarm_rooms, s.clean_rooms)}</td><td class="num">${usd(s.usd_open)} of ${usd(s.usd_total)}</td></tr>`;
    });
    table("#score-table", html);
    $("#verdict").innerHTML = verdictHtml();

    const r = S.run_report, c = DATA.constants;
    $("#run-report").textContent =
      `Run report: model called for ${r.model_called} of ${r.questions} questions; ${r.failures} failures (step limit or error); ` +
      `${r.fallback_uses} fallback uses; ${r.tokens.toLocaleString("en-US")} tokens; ${usd2(r.usd)} spent; ${r.avg_seconds} s per question; ` +
      `${c.tools_per_question} tools and at most ${c.max_model_steps} model calls per question.`;

    let wh = "<thead><tr><th>Error type</th><th>How often</th><th>Dollars at risk</th><th>Who fixes it</th><th>Why</th><th>Edits approved</th></tr></thead><tbody>";
    DATA.who_does_what.forEach((w) => {
      wh += `<tr><td>${esc(w.code)} ${esc(w.name)}</td><td class="num">${w.count}</td><td class="num">${usd(w.usd_at_risk)}</td>
        <td>${esc(w.who)}</td><td>${esc(w.why)}</td><td class="num">${w.edits ? ofN(w.approved, w.edits) : "no edits"}</td></tr>`;
    });
    table("#who-table", wh);

    $("#ladder-intro").textContent =
      `A fix type may skip the drafter only after the drafter approved at least ${share(c.ladder_rate)} of at least ${c.ladder_min_n} cases. ` +
      `Everything else keeps the drafter check.`;
    let lh = "<thead><tr><th>Fix type</th><th>Proposed by</th><th>Approved</th><th>Decision</th></tr></thead><tbody>";
    S.ladder.forEach((l) => {
      lh += `<tr><td>${esc(ACTION[l.action] || l.action)}</td><td>${esc(l.by)}</td><td class="num">${ofN(l.approved, l.n)}</td><td>${esc(l.status)}</td></tr>`;
    });
    table("#ladder-table", lh);

    const tri = S.triage.reduce((a, h) => ((a[h.status] = (a[h.status] || 0) + 1), a), {});
    $("#ladder-intro").textContent += ` Triage of the ${t.houses} houses with the agent: ` +
      ["ready", "quick review", "full review"].map((k) => `${tri[k] || 0} ${k}`).join(", ") + ".";
  }

  function renderFailureFix() {
    const f = DATA.failure_fix;
    if (!f) return;
    if (f.variance) {
      $("#variance-note").textContent = `The numbers come from one cached run of a model that is not fully repeatable: ` +
        `on the last rerun, ${f.variance.changed} of ${f.variance.of} answers that no fix targeted came out different.`;
    }
    $("#failure-section").hidden = false;
    // Short on the page: the summary and the result; the full story opens on request.
    const last = f.steps[f.steps.length - 1];
    $("#failure-fix").innerHTML = `<p class="measure">${esc(f.summary)}</p><p class="measure"><strong>${esc(last.title)}:</strong> ${esc(last.text)}</p>` +
      `<details><summary>The full story (${f.steps.length} steps)</summary><dl class="story">` +
      f.steps.map((s) => `<div><dt>${esc(s.title)}</dt><dd>${esc(s.text)}</dd></div>`).join("") + "</dl></details>";
  }

  /* ---------- dashboard: two interactions, state in memory only (a reload starts again) ---------- */

  function renderDashboard() {
    document.querySelectorAll("#dash-approach button").forEach((b) => b.addEventListener("click", () => showRow(b.dataset.row)));
    showRow("D");
    const budget = $("#dash-budget");
    budget.max = DATA.scores.triage.length;
    budget.addEventListener("input", () => showBudget(+budget.value));
    showBudget(+budget.value);
    const sel = $("#dash-house");
    DATA.houses.forEach((h) => {
      const n = h.rooms.reduce((a, r) => a + r.items.filter((i) => i.decision).length, 0);
      const o = document.createElement("option");
      o.value = h.id;
      o.textContent = `${h.id}: ${n} edit${n === 1 ? "" : "s"} to decide`;
      sel.appendChild(o);
    });
    sel.addEventListener("change", () => showHouse(sel.value));
    showHouse(sel.value);
  }

  // 1. Approach switch: four tiles and one bar per error type for the chosen row.
  function showRow(k) {
    const s = DATA.scores.rows[k];
    document.querySelectorAll("#dash-approach button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.row === k)));
    $("#tile-fixed").textContent = ofN(s.fixed, s.errors);
    $("#tile-harmful").textContent = String(s.harmful_edits);
    $("#tile-manual").textContent = String(s.manual_items);
    $("#tile-usd").textContent = `${usd(s.usd_open)} of ${usd(s.usd_total)}`;
    $("#dash-bars").innerHTML = Object.entries(s.per_type).map(([code, t]) => {
      const w = (n) => (t.total ? (100 * n) / t.total : 0).toFixed(1) + "%";
      return `<li data-code="${esc(code)}"><span>${esc(code)} ${esc(DATA.error_types[code])}</span>
        <span class="bar" aria-hidden="true"><span class="fixed" style="width:${w(t.fixed)}"></span><span class="drafter" style="width:${w(t.to_drafter)}"></span><span class="missed" style="width:${w(t.missed)}"></span></span>
        <span class="counts">✓ ${t.fixed} fixed · ${t.to_drafter} to a drafter · ✗ ${t.missed} missed, of ${t.total}</span></li>`;
    }).join("");
  }

  // 2. A drafter's day: review the first k houses in triage order (row D, sorted by dollars at risk).
  function showBudget(k) {
    const tri = DATA.scores.triage, top = tri.slice(0, k);
    const sum = (hs, f) => hs.reduce((a, h) => a + f(h), 0);
    const covered = sum(top, (h) => h.usd_at_risk), total = sum(tri, (h) => h.usd_at_risk);
    $("#dash-budget-out").textContent = `${k} of ${tri.length} houses: ${usd(covered)} of ${usd(total)} in open items reviewed ` +
      `(${pct(covered, total)}), ${sum(top, (h) => h.edits + h.manual)} items to check.`;
  }

  // 3. The drafter's job: decide each edit of one house; compare with the simulated drafter at the end.
  let job = null;

  function showHouse(hid) {
    const house = DATA.houses.find((h) => h.id === hid);
    const items = house.rooms.flatMap((r) => r.items.map((i) => ({ ...i, room: r })));
    job = { edits: items.filter((i) => i.decision), asks: items.filter((i) => i.action === "ask_drafter"), mine: [] };
    const line = (i) => `<p><strong>${esc(cap(roomName(i.room.label)))}</strong> ${esc(i.room.id)} · ${i.action === "ask_drafter" ? esc(i.after)
      : i.action === "no_change" ? "keep the plan" : `${esc(i.before)} → ${esc(i.after)}`}</p>
      <p class="soft">by ${esc(BY[i.by] || i.by)}${i.evidence && i.evidence !== i.after ? ` · ${i.by === "agent" && i.action !== "ask_drafter" ? "quote" : "evidence"}: “${esc(i.evidence)}”` : ""} · ${usd(i.usd)}</p>`;
    let n = 0;
    $("#dash-items").innerHTML = items.map((i) => {
      if (!i.decision) {
        const what = i.action === "ask_drafter" ? "drafter item: needs a person" : "nothing to approve";
        return `<li>${line(i)}<p class="soft">${what}</p></li>`;
      }
      return `<li data-edit="${n++}">${line(i)}<div class="decide">
        <button type="button" data-decide="approve" aria-pressed="false">✓ Approve</button>
        <button type="button" data-decide="reject" aria-pressed="false">✗ Reject</button></div><p class="sim soft"></p></li>`;
    }).join("");
    document.querySelectorAll("#dash-items [data-edit]").forEach((li) => {
      li.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
        job.mine[+li.dataset.edit] = b.dataset.decide;
        li.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        updateJob();
      }));
    });
    updateJob();
  }

  function updateJob() {
    const open = job.edits.filter((_, n) => !job.mine[n]).length;
    // Still at risk: drafter items, plus every edit not decided yet or decided unlike the simulated drafter.
    const risk = job.asks.reduce((a, i) => a + i.usd, 0) +
      job.edits.reduce((a, i, n) => a + (job.mine[n] === i.decision ? 0 : i.usd), 0);
    $("#dash-counter").textContent = `This house: $ still at risk: ${usd(risk)} · open items: ${open + job.asks.length}`;
    const done = job.edits.length && !open;
    const agree = job.edits.filter((i, n) => job.mine[n] === i.decision).length;
    document.querySelectorAll("#dash-items [data-edit]").forEach((li) => {
      const i = job.edits[+li.dataset.edit];
      li.querySelector(".sim").textContent = done ? `Simulated drafter: ${i.decision === "approve" ? "✓ approved" : "✗ rejected"}` : "";
    });
    $("#dash-result").textContent = !job.edits.length ? "No edit to decide in this house; its items need a person."
      : done ? `You agreed with the simulated drafter on ${agree} of ${job.edits.length}.` : "";
  }

  /* ---------- part 2: draft estimate ---------- */

  function renderPart2() {
    const p2 = DATA.part2 || {};
    const ing = p2.ingest, est = p2.estimate;
    if (!ing || !est) return;
    $("#part2").hidden = false;

    const sel = $("#estimate-select");
    est.demos.forEach((d, i) => {
      const o = document.createElement("option");
      o.value = i;
      o.textContent = `${cap(roomName(d.room_type))} ${d.room_id}, ${d.size}`;
      sel.appendChild(o);
    });
    sel.addEventListener("change", () => renderEstimateRoom(est.demos[+sel.value]));
    if (est.demos.length) renderEstimateRoom(est.demos[0]);

    const layers = [["exact", "Exact match to a catalog description"], ["fuzzy", "Fuzzy match (rapidfuzz), one clear winner"],
                    ["model", "Model, only for what is left"], ["review", "Still unsure: goes on the review list"]];
    $("#ingest-intro").textContent =
      `${ing.all_lines} past line items (${ing.unique_texts} distinct wordings) from made-up jobs, phrased the way different estimators would write them. ` +
      `Scored on ${ing.holdout_lines} held-out lines with a known correct code.` +
      (ing.model_ran ? ` The model answered in ${ing.model_calls} batched calls.` : " The model layer has not run yet, so its share sits in review.");
    let t = `<thead><tr><th>Layer</th><th>Lines settled (of ${ing.holdout_lines})</th><th>Correct</th><th>Distinct wordings settled</th></tr></thead><tbody>`;
    layers.forEach(([k, name]) => {
      const v = ing.per_layer[k];
      const correct = k === "review" ? "goes to a human" : (v.settled ? `${v.correct} of ${v.settled}` : "n/a");
      t += `<tr><td>${esc(name)}</td><td class="num">${v.settled}</td><td class="num">${correct}</td><td class="num">${ing.unique_by_layer[k]}</td></tr>`;
    });
    $("#ingest-table").className = "data";
    $("#ingest-table").innerHTML = t + "</tbody>";

    const s = est.scores;
    $("#estimate-intro").textContent =
      `${s.holdout_jobs} past jobs held out of the history. For each one, the draft is compared with the items the estimator really wrote. ` +
      `The plain-code baseline includes every item seen in at least ${share(s.freq_rule_threshold)} of similar past jobs; it cannot read the scope notes.`;
    const row = (name, v, ready) => ready
      ? `<tr><td>${esc(name)}</td><td class="num">${v.found} of ${v.true_items} (${pct(v.found, v.true_items)})</td><td class="num">${v.missed}</td><td class="num">${v.extra}</td><td class="num">${share(v.precision)}</td><td class="num">${v.often_missed_caught} of ${v.often_missed_total}</td></tr>`
      : `<tr><td>${esc(name)}</td><td colspan="5" class="pending">Agent run pending (${s.agent_jobs_run} of ${s.holdout_jobs} jobs drafted).</td></tr>`;
    $("#estimate-table").className = "data";
    $("#estimate-table").innerHTML = "<thead><tr><th>Approach</th><th>Real items found</th><th>Missed</th><th>Extra</th><th>Precision (drafted items that are right)</th><th>Often-missed items caught</th></tr></thead><tbody>" +
      row("Frequency rule (plain code)", s.frequency_rule, true) + row("Estimation agent", s.agent, s.agent_complete) + "</tbody>";
  }

  function renderEstimateRoom(d) {
    const kind = roomName(d.room_type);
    let html = `<p><strong>Scope notes:</strong> ${esc(d.notes)}</p>
      <p class="soft">${esc(d.size)}, region ${esc(d.region)}, ${esc(d.month)}, drafted by the ${esc(d.drafted_by)}</p>
      <div class="table-wrap"><table class="data"><thead><tr><th>Item</th><th>Quantity (from plan)</th><th>Unit price (mock)</th><th>Total</th><th>History</th></tr></thead><tbody>`;
    d.lines.forEach((l) => {
      html += `<tr><td>${esc(l.description)}${l.often_missed ? ' <span class="flag">often missed</span>' : ""}
          <span class="item-code">${esc(l.code)}</span>${l.reason ? `<span class="item-reason">${esc(l.reason)}</span>` : ""}</td>
        <td class="num">${l.quantity} ${esc(l.unit)}</td><td class="num">${usd2(l.unit_price_usd)}</td><td class="num">${usd2(l.total_usd)}</td>
        <td>in ${share(l.share_of_similar)} of similar past ${esc(kind)} jobs (${l.source_jobs} of ${l.similar_jobs})</td></tr>`;
    });
    html += `</tbody></table></div><p class="total"><strong>Draft total:</strong> ${usd2(d.total_usd)} <span class="soft">(example prices)</span></p>`;
    if (d.check_often_missed.length) {
      html += `<p><strong>Often missed, worth a check:</strong> ${d.check_often_missed.map((c) => `${esc(c.description)} (in ${share(c.share_of_similar)} of similar jobs)`).join("; ")}</p>`;
    }
    html += stepsHtml(d.steps);
    $("#estimate-room").innerHTML = html;
  }
})();
