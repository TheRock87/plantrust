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
      o.textContent = `${h.id}: ${h.rooms.length} rooms, ${h.n_errors} planted error${h.n_errors === 1 ? "" : "s"}`;
      sel.appendChild(o);
    });
    sel.addEventListener("change", () => renderHouse(sel.value));
    renderHouse(DATA.houses[0].id);
    renderPart2();
  }

  /* ---------- plan viewer ---------- */

  function svgEl(name, attrs, text) {
    const el = document.createElementNS(SVGNS, name);
    Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, v));
    if (text != null) el.textContent = text;
    return el;
  }

  function verdictClass(r) {
    if (r.missing_from_plan) return "missing";
    return r.verdict === "accept" ? "accept" : "drafter";
  }

  function verdictText(r) {
    if (r.missing_from_plan) return "missing from the plan";
    return r.verdict === "accept" ? "accept" : "send to drafter";
  }

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
    hatch.appendChild(svgEl("rect", { width: 0.3, height: 0.9, fill: "#ffd23a", "fill-opacity": 0.85 }));
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
        class: `room ${verdictClass(r)}`, "data-id": r.id, tabindex: 0, role: "button",
        "aria-label": `${cap(roomName(r.label))} ${r.id}: ${verdictText(r)}`,
      });
      g.appendChild(svgEl("polygon", { points: r.polygon.map((p) => `${p[0]},${-p[1]}`).join(" ") }));
      g.appendChild(svgEl("text", { x: cx, y: cy, "font-size": fs }, cap(roomName(r.label))));
      g.appendChild(svgEl("text", { x: cx, y: cy + fs * 1.05, "font-size": fs * 0.72, class: "size" }, `${feet(w)} × ${feet(d)} ft`));
      const pick = () => selectRoom(house, r.id);
      g.addEventListener("click", pick);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      svg.appendChild(g);
    });
    const firstFlag = house.rooms.find((r) => r.verdict !== "accept") || house.rooms[0];
    selectRoom(house, firstFlag.id);
  }

  const DECIDED_BY = {
    code: "decided by the code checks",
    "code (unclear)": "unclear in the code checks",
    agent: "decided by the agent",
    "agent not run": "unclear; the agent has not run yet, so a drafter checks it",
  };

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
    const verdict = r.verdict === "accept" ? '<span class="ok">Accept</span>' : '<span class="flag">Send to drafter</span>';
    let html = `<p class="room-name">${esc(cap(roomName(r.label)))}</p>
      <p class="room-meta">Room ${esc(r.id)}, ${r.affected ? "water-affected" : "not water-affected"}</p>
      <p>${verdict} <span class="soft">${esc(DECIDED_BY[r.decided_by] || r.decided_by)}</span></p>`;
    if (r.agent_reason) html += `<p><strong>Agent:</strong> ${esc(r.agent_reason)}</p>`;
    html += `<p class="label">Code check findings</p><ul class="reasons">${r.check_reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    if (r.missing_from_plan) {
      html += `<p class="soft">The dashed outline shows where the room really is (from the answer key), for illustration only. The checker knows the room only from the tour.</p>`;
    } else {
      html += `<table class="compare"><thead><tr><td></td><th>Plan</th><th>Tour</th></tr></thead><tbody>
        <tr><th>Walls (ft)</th><td>${walls(n.plan_walls)}</td><td>${walls(n.tour_walls)}</td></tr>
        <tr><th>Ceiling (ft)</th><td>${esc(n.plan_ceiling)}</td><td>${esc(n.tour_ceiling)}</td></tr>
        <tr><th>Doors</th><td>${esc(n.plan_doors)}</td><td>${esc(n.tour_doors)}</td></tr>
        <tr><th>Label</th><td>${esc(n.plan_label)}</td><td>${esc(n.tour_label)}</td></tr></tbody></table>`;
    }
    html += `<p><strong>Estimated cost at risk:</strong> ${usd(r.est_cost_at_risk_usd)} <span class="soft">(plan against tour, illustrative prices)</span></p>`;
    html += stepsHtml(r.agent_steps);
    const key = r.answer_key
      ? `Planted error <strong>${esc(r.answer_key.code)} ${esc(r.answer_key.name)}</strong>: ${esc(r.answer_key.detail)}. Actual cost at risk ${usd(r.answer_key.actual_cost_at_risk_usd)}.`
      : "No error was planted in this room.";
    html += `<details><summary>Answer key</summary><p>${key}</p></details>`;
    $("#panel").innerHTML = html;
  }

  /* ---------- results ---------- */

  function agentReady() { return DATA.scores.agent_complete; }

  function renderTally() {
    const t = DATA.totals;
    const s = agentReady() ? DATA.scores.code_plus_agent : DATA.scores.code_only;
    const how = agentReady() ? "" : " (code checks only; the agent run is pending)";
    $("#tally").innerHTML =
      `Across all ${t.houses} test houses${how}: <strong>${s.caught} of ${s.errors}</strong> planted errors went to a drafter, ` +
      `and a drafter has to check <strong>${s.sent_to_drafter} of ${s.rooms}</strong> rooms instead of every one.`;
  }

  // One square per room: yellow when it was sent to a drafter, a dot when it held a planted error.
  function unitChart(name, s) {
    const missed = s.errors - s.caught;
    const groups = [["sent error", s.caught], ["sent", s.false_alarms], ["error", missed], ["", s.rooms - s.sent_to_drafter - missed]];
    const squares = groups.map(([cls, n]) => `<span class="unit ${cls}"></span>`.repeat(n)).join("");
    const label = `${name}: ${s.sent_to_drafter} of ${s.rooms} rooms sent to a drafter, ${s.caught} of ${s.errors} planted errors among them, ${missed} missed`;
    return `<div class="units-row"><p><strong>${esc(name)}</strong> <span class="soft">${s.sent_to_drafter} rooms to a drafter</span></p>
      <div class="units" role="img" aria-label="${esc(label)}">${squares}</div></div>`;
  }

  function renderScores() {
    const t = DATA.totals;
    const c = t.check_counts;
    const code = DATA.scores.code_only, both = DATA.scores.code_plus_agent;
    $("#results-title").textContent = `Results on ${t.houses} houses`;
    $("#results-intro").textContent =
      `${t.houses} synthetic houses, ${t.rooms} rooms, ${t.errors} planted errors. ` +
      `Code checks settled ${c.pass + c.fail} rooms (${c.pass} pass, ${c.fail} fail); ${c.unclear} were unclear.`;

    $("#unit-charts").innerHTML = unitChart("Code checks only", code) +
      (agentReady() ? unitChart("Code checks + agent", both) : "") +
      `<ul class="units-key"><li><span class="unit"></span>Accepted</li><li><span class="unit sent"></span>Sent to a drafter</li>
       <li><span class="unit sent error"></span>Held a planted error</li></ul>`;

    const rows = [["Code checks only (unclear rooms go to a drafter)", code, false],
                  ["Code checks + agent for unclear rooms", both, true]];
    let html = "<thead><tr><th>Approach</th><th>Errors caught</th><th>False alarms</th><th>Rooms sent to drafter</th><th>Cost at risk caught</th><th>Model use</th></tr></thead><tbody>";
    rows.forEach(([name, s, isAgent]) => {
      if (isAgent && !agentReady()) {
        html += `<tr><td>${esc(name)}</td><td colspan="5" class="pending">Agent run pending (${s.agent_rooms_run} of ${s.agent_rooms_needed} unclear rooms reviewed).</td></tr>`;
        return;
      }
      const model = isAgent ? `about ${s.tokens_per_house.toLocaleString("en-US")} tokens per house (free tier)` : "none";
      html += `<tr><td>${esc(name)}</td>
        <td class="num">${s.caught} of ${s.errors} (${pct(s.caught, s.errors)})</td>
        <td class="num">${s.false_alarms} of ${s.clean_rooms} (${pct(s.false_alarms, s.clean_rooms)})</td>
        <td class="num">${s.sent_to_drafter} of ${s.rooms} (${pct(s.sent_to_drafter, s.rooms)})</td>
        <td class="num">${usd(s.usd_at_risk_caught)} of ${usd(s.usd_at_risk_total)}</td>
        <td class="num">${model}</td></tr>`;
    });
    $("#score-table").className = "data";
    $("#score-table").innerHTML = html + "</tbody>";

    let th = "<thead><tr><th>Error type</th><th>Code checks only</th><th>Code checks + agent</th></tr></thead><tbody>";
    Object.entries(DATA.error_types).forEach(([id, name]) => {
      const a = code.per_type[id], b = both.per_type[id];
      const bTxt = agentReady() ? `${b.caught} of ${b.total} (${pct(b.caught, b.total)})` : '<span class="pending">pending</span>';
      th += `<tr><td>${esc(id)} ${esc(name)}</td><td class="num">${a.caught} of ${a.total} (${pct(a.caught, a.total)})</td><td class="num">${bTxt}</td></tr>`;
    });
    $("#type-table").className = "data";
    $("#type-table").innerHTML = th + "</tbody>";
  }

  function renderFailureFix() {
    const f = DATA.failure_fix;
    if (!f) return;
    $("#failure-section").hidden = false;
    $("#failure-fix").innerHTML = `<p class="measure">${esc(f.summary)}</p><dl class="story">` +
      f.steps.map((s) => `<div><dt>${esc(s.title)}</dt><dd>${esc(s.text)}</dd></div>`).join("") + "</dl>";
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
      ? `<tr><td>${esc(name)}</td><td class="num">${v.found} of ${v.true_items} (${pct(v.found, v.true_items)})</td><td class="num">${v.missed}</td><td class="num">${v.extra}</td><td class="num">${v.often_missed_caught} of ${v.often_missed_total}</td></tr>`
      : `<tr><td>${esc(name)}</td><td colspan="4" class="pending">Agent run pending (${s.agent_jobs_run} of ${s.holdout_jobs} jobs drafted).</td></tr>`;
    $("#estimate-table").className = "data";
    $("#estimate-table").innerHTML = "<thead><tr><th>Approach</th><th>Real items found</th><th>Missed</th><th>Extra</th><th>Often-missed items caught</th></tr></thead><tbody>" +
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
