/* PlanTrust page: reads data/results.json (written by src/export.py) and renders it. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const usd = (n) => "$" + Math.round(n).toLocaleString("en-US");
  const pct = (a, b) => (b ? Math.round((100 * a) / b) + "%" : "n/a");
  const SVGNS = "http://www.w3.org/2000/svg";

  let DATA = null;
  let selected = null;

  fetch("data/results.json")
    .then((r) => r.json())
    .then((d) => { DATA = d; init(); })
    .catch(() => {
      $("#panel").innerHTML = "<p>Could not load data/results.json. Serve the folder over HTTP, for example <code>python -m http.server -d site</code>.</p>";
    });

  function init() {
    $("#model-name").textContent = DATA.model;
    renderHeadline();
    renderScores();
    renderFailureFix();
    const sel = $("#house-select");
    DATA.houses.forEach((h) => {
      const o = document.createElement("option");
      o.value = h.id;
      o.textContent = `${h.id}  (${h.rooms.length} rooms, ${h.n_errors} planted error${h.n_errors === 1 ? "" : "s"})`;
      sel.appendChild(o);
    });
    sel.addEventListener("change", () => renderHouse(sel.value));
    renderHouse(DATA.houses[0].id);
    renderPart2();
  }

  function renderPart2() {
    const p2 = DATA.part2 || {};
    const ing = p2.ingest, est = p2.estimate;
    if (!ing || !est) return;
    $("#part2").hidden = false;

    const sel = $("#estimate-select");
    est.demos.forEach((d, i) => {
      const o = document.createElement("option");
      o.value = i;
      o.textContent = `${d.room_type} (${d.room_id}, ${d.size})`;
      sel.appendChild(o);
    });
    sel.addEventListener("change", () => renderEstimateRoom(est.demos[+sel.value]));
    if (est.demos.length) renderEstimateRoom(est.demos[0]);

    const layers = [["exact", "Exact match to a catalog description"], ["fuzzy", "Fuzzy match (rapidfuzz), one clear winner"],
                    ["model", "Model, only for what is left"], ["review", "Still unsure: please review"]];
    $("#ingest-intro").textContent =
      `${ing.all_lines} past line items (${ing.unique_texts} distinct wordings) from 150 made-up jobs, written "by different estimators". ` +
      `Scored on ${ing.holdout_lines} held-out lines with a known correct code.` +
      (ing.model_ran ? ` Model calls: ${ing.model_calls}.` : " The model layer has not run yet, so its share sits in review.");
    let t = "<thead><tr><th>Layer</th><th>Lines settled (of 100)</th><th>Correct</th><th>Distinct wordings settled</th></tr></thead><tbody>";
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
      `The plain-code baseline includes every item seen in at least ${Math.round(s.freq_rule_threshold * 100)}% of similar past jobs; it cannot read the scope notes.`;
    const row = (name, v, ready) => ready
      ? `<tr><td>${esc(name)}</td><td class="num">${v.found} of ${v.true_items} (${pct(v.found, v.true_items)})</td><td class="num">${v.missed}</td><td class="num">${v.extra}</td><td class="num">${v.often_missed_caught} of ${v.often_missed_total}</td></tr>`
      : `<tr><td>${esc(name)}</td><td colspan="4" class="pending">Agent run pending (${s.agent_jobs_run} of ${s.holdout_jobs} jobs drafted).</td></tr>`;
    $("#estimate-table").className = "data";
    $("#estimate-table").innerHTML = "<thead><tr><th>Approach</th><th>Real items found</th><th>Missed</th><th>Extra</th><th>Often-missed items caught</th></tr></thead><tbody>" +
      row("Frequency rule (plain code)", s.frequency_rule, true) + row("Estimation agent", s.agent, s.agent_complete) + "</tbody>";
  }

  function renderEstimateRoom(d) {
    let html = `<p style="margin-top:12px"><strong>Scope notes:</strong> ${esc(d.notes)}</p>
      <p class="muted">${esc(d.size)} · region ${esc(d.region)} · ${esc(d.month)} · drafted by ${esc(d.drafted_by)}</p>`;
    html += `<div class="table-wrap"><table class="data"><thead><tr><th>Item</th><th>Quantity (from plan)</th><th>Unit price (mock)</th><th>Total</th><th>History</th></tr></thead><tbody>`;
    d.lines.forEach((l) => {
      html += `<tr><td>${esc(l.description)}${l.often_missed ? ' <span class="badge drafter">often missed</span>' : ""}<br><span class="panel-id">${esc(l.code)}</span>${l.reason ? `<br><span class="muted" style="font-size:0.85rem">${esc(l.reason)}</span>` : ""}</td>
        <td class="num">${l.quantity} ${esc(l.unit)}</td><td class="num">$${l.unit_price_usd.toFixed(2)}</td><td class="num">$${l.total_usd.toFixed(2)}</td>
        <td>in ${Math.round(l.share_of_similar * 100)}% of similar past ${esc(d.room_type)}s (${l.source_jobs} of ${l.similar_jobs} jobs)</td></tr>`;
    });
    html += `</tbody></table></div><p style="margin-top:10px"><strong>Draft total:</strong> $${d.total_usd.toFixed(2)} <span class="muted">(example prices)</span></p>`;
    if (d.check_often_missed.length) {
      html += `<p><strong>Often missed, worth a check:</strong> ${d.check_often_missed.map((c) => `${esc(c.description)} (in ${Math.round(c.share_of_similar * 100)}% of similar jobs)`).join("; ")}</p>`;
    }
    if (d.steps && d.steps.length) {
      html += `<details><summary>Agent steps (${d.steps.length})</summary><ol class="steps">` + d.steps.map((s) =>
        s.type === "tool_call" ? `<li class="tool_call"><span class="step-kind">tool call</span><code>${esc(s.name)}(${esc(JSON.stringify(s.args))})</code></li>`
          : s.type === "tool_result" ? `<li><span class="step-kind">result of ${esc(s.name)}</span><code>${esc(s.text)}</code></li>`
          : `<li><span class="step-kind">model</span>${esc(s.text)}</li>`).join("") + "</ol></details>";
    }
    $("#estimate-room").innerHTML = html;
  }

  function agentRowReady() { return DATA.scores.agent_complete; }

  function renderHeadline() {
    const t = DATA.totals;
    const s = agentRowReady() ? DATA.scores.code_plus_agent : DATA.scores.code_only;
    const label = agentRowReady() ? "code checks + agent" : "code checks only";
    const items = [
      [`${s.caught} of ${s.errors}`, `planted errors sent to a drafter (${label})`],
      [`${s.false_alarms} of ${s.clean_rooms}`, "clean rooms sent to a drafter (false alarms)"],
      [`${s.sent_to_drafter} of ${s.rooms}`, "rooms a drafter has to check"],
      [`${t.houses} houses`, `${t.rooms} rooms, ${t.errors} planted errors, ${t.clean_houses} clean houses`],
    ];
    $("#headline-stats").innerHTML = items.map(([b, s2]) => `<div class="stat"><b>${esc(b)}</b><span>${esc(s2)}</span></div>`).join("");
  }

  function renderScores() {
    const t = DATA.totals;
    const c = t.check_counts;
    $("#results-intro").textContent =
      `${t.houses} synthetic houses, ${t.rooms} rooms, ${t.errors} planted errors. ` +
      `Code checks settled ${c.pass + c.fail} rooms (${c.pass} pass, ${c.fail} fail); ${c.unclear} were unclear.`;
    const rows = [["Code checks only (unclear rooms go to a drafter)", DATA.scores.code_only, false],
                  ["Code checks + agent for unclear rooms", DATA.scores.code_plus_agent, true]];
    let html = "<thead><tr><th>Approach</th><th>Errors caught</th><th>False alarms</th><th>Rooms sent to drafter</th><th>Cost at risk caught</th><th>Model cost</th></tr></thead><tbody>";
    rows.forEach(([name, s, isAgent]) => {
      if (isAgent && !agentRowReady()) {
        html += `<tr><td>${esc(name)}</td><td colspan="5" class="pending">Agent run pending (${s.agent_rooms_run} of ${s.agent_rooms_needed} unclear rooms reviewed).</td></tr>`;
        return;
      }
      const cost = isAgent ? `${(s.llm_usd_per_house * 100).toFixed(2)} cents per house` : "0";
      html += `<tr><td>${esc(name)}</td>
        <td class="num">${s.caught} of ${s.errors} (${pct(s.caught, s.errors)})</td>
        <td class="num">${s.false_alarms} of ${s.clean_rooms} (${pct(s.false_alarms, s.clean_rooms)})</td>
        <td class="num">${s.sent_to_drafter} of ${s.rooms} (${pct(s.sent_to_drafter, s.rooms)})</td>
        <td class="num">${usd(s.usd_at_risk_caught)} of ${usd(s.usd_at_risk_total)}</td>
        <td class="num">${cost}</td></tr>`;
    });
    $("#score-table").className = "data";
    $("#score-table").innerHTML = html + "</tbody>";

    let th = "<thead><tr><th>Error type</th><th>Code checks only</th><th>Code checks + agent</th></tr></thead><tbody>";
    Object.entries(DATA.error_types).forEach(([code, name]) => {
      const a = DATA.scores.code_only.per_type[code];
      const b = DATA.scores.code_plus_agent.per_type[code];
      const bTxt = agentRowReady() ? `${b.caught} of ${b.total} (${pct(b.caught, b.total)})` : '<span class="pending">pending</span>';
      th += `<tr><td>${code} ${esc(name)}</td><td class="num">${a.caught} of ${a.total} (${pct(a.caught, a.total)})</td><td class="num">${bTxt}</td></tr>`;
    });
    $("#type-table").className = "data";
    $("#type-table").innerHTML = th + "</tbody>";
  }

  function renderFailureFix() {
    const f = DATA.failure_fix;
    if (!f) return;
    $("#failure-section").hidden = false;
    $("#failure-fix").innerHTML = `<p>${esc(f.summary)}</p><div class="story">` +
      f.steps.map((s) => `<div><h4>${esc(s.title)}</h4><p>${esc(s.text)}</p></div>`).join("") + "</div>";
  }

  function verdictClass(r) {
    if (r.missing_from_plan) return "missing";
    return r.verdict === "accept" ? "accept" : "drafter";
  }

  function renderHouse(hid) {
    const house = DATA.houses.find((h) => h.id === hid);
    const svg = $("#plan");
    svg.innerHTML = "";
    const xs = house.rooms.flatMap((r) => r.polygon.map((p) => p[0]));
    const ys = house.rooms.flatMap((r) => r.polygon.map((p) => p[1]));
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const pad = 1.5;
    svg.setAttribute("viewBox", `${minX - pad} ${-(maxY + pad)} ${maxX - minX + 2 * pad} ${maxY - minY + 2 * pad}`);
    // Draw missing rooms last so their dashed outline sits on top.
    const ordered = [...house.rooms].sort((a, b) => a.missing_from_plan - b.missing_from_plan);
    ordered.forEach((r) => {
      const cls = verdictClass(r);
      const g = document.createElementNS(SVGNS, "g");
      g.setAttribute("class", `room ${cls}`);
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      const vtxt = r.missing_from_plan ? "missing from plan" : r.verdict === "accept" ? "accept" : "send to drafter";
      g.setAttribute("aria-label", `${r.label} ${r.id}: ${vtxt}`);
      const poly = document.createElementNS(SVGNS, "polygon");
      poly.setAttribute("points", r.polygon.map((p) => `${p[0]},${-p[1]}`).join(" "));
      g.appendChild(poly);
      const cx = r.polygon.reduce((s, p) => s + p[0], 0) / r.polygon.length;
      const cy = -r.polygon.reduce((s, p) => s + p[1], 0) / r.polygon.length;
      const w = Math.max(...r.polygon.map((p) => p[0])) - Math.min(...r.polygon.map((p) => p[0]));
      const fs = Math.max(0.75, Math.min(1.2, w / 7));
      const icon = document.createElementNS(SVGNS, "text");
      icon.setAttribute("x", cx); icon.setAttribute("y", cy - fs * 0.2);
      icon.setAttribute("text-anchor", "middle");
      icon.setAttribute("font-size", fs * 1.5);
      icon.setAttribute("class", `icon ${cls}`);
      icon.textContent = cls === "accept" ? "✓" : "⚠";
      g.appendChild(icon);
      const lab = document.createElementNS(SVGNS, "text");
      lab.setAttribute("x", cx); lab.setAttribute("y", cy + fs * 1.1);
      lab.setAttribute("text-anchor", "middle");
      lab.setAttribute("font-size", fs * 0.8);
      lab.textContent = r.label;
      g.appendChild(lab);
      const pick = () => selectRoom(house, r.id);
      g.addEventListener("click", pick);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      svg.appendChild(g);
    });
    const firstFlag = house.rooms.find((r) => r.verdict !== "accept") || house.rooms[0];
    selectRoom(house, firstFlag.id);
  }

  function fmtWalls(a) { return a ? a.map((x) => Number(x).toFixed(1)).join(" / ") : "n/a"; }

  function selectRoom(house, rid) {
    selected = rid;
    document.querySelectorAll("#plan .room").forEach((g) => g.classList.toggle("selected", g.getAttribute("aria-label").includes(rid + ":")));
    const r = house.rooms.find((x) => x.id === rid);
    const n = r.numbers || {};
    const v = r.verdict === "accept" ? '<span class="badge accept">&#10003; Accept</span>' : '<span class="badge drafter">&#9888; Send to drafter</span>';
    const by = { code: "decided by the code checks", "code (unclear)": "unclear in the code checks", agent: "decided by the agent", "agent not run": "unclear; agent not run yet, so a drafter checks it" }[r.decided_by] || r.decided_by;
    let html = `<p class="panel-title">${esc(r.label)}</p><p class="panel-id">${esc(r.id)} · ${r.affected ? "water-affected room" : "not affected"}</p>`;
    html += `<p>${v} <span class="muted">${esc(by)}</span></p>`;
    if (r.agent_reason) html += `<p><strong>Agent:</strong> ${esc(r.agent_reason)}</p>`;
    html += `<p class="muted" style="margin-bottom:0">Code check findings</p><ul class="reasons">${r.check_reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    if (!r.missing_from_plan) {
      html += `<table class="kv"><thead><tr><th></th><th>Plan</th><th>Tour</th></tr></thead><tbody>
        <tr><th>Walls (ft)</th><td>${fmtWalls(n.plan_walls)}</td><td>${fmtWalls(n.tour_walls)}</td></tr>
        <tr><th>Ceiling (ft)</th><td>${esc(n.plan_ceiling)}</td><td>${esc(n.tour_ceiling)}</td></tr>
        <tr><th>Doors</th><td>${esc(n.plan_doors)}</td><td>${esc(n.tour_doors)}</td></tr>
        <tr><th>Label</th><td>${esc(n.plan_label)}</td><td>${esc(n.tour_label)}</td></tr></tbody></table>`;
    } else {
      html += `<p class="muted">The outline shows where the room really is (from the answer key), for illustration only; the checker knows it only from the tour.</p>`;
    }
    html += `<p><strong>Estimated cost at risk:</strong> ${usd(r.est_cost_at_risk_usd)} <span class="muted">(plan vs tour, illustrative prices)</span></p>`;
    if (r.agent_steps && r.agent_steps.length) {
      html += `<details><summary>Agent steps (${r.agent_steps.length})</summary><ol class="steps">` +
        r.agent_steps.map((s) => {
          if (s.type === "tool_call") return `<li class="tool_call"><span class="step-kind">tool call</span><code>${esc(s.name)}(${esc(JSON.stringify(s.args))})</code></li>`;
          if (s.type === "tool_result") return `<li><span class="step-kind">result of ${esc(s.name)}</span><code>${esc(s.text)}</code></li>`;
          return `<li><span class="step-kind">model</span>${esc(s.text)}</li>`;
        }).join("") + "</ol></details>";
    }
    html += `<details><summary>Answer key</summary><p>${r.answer_key
      ? `Planted error <strong>${esc(r.answer_key.code)} ${esc(r.answer_key.name)}</strong>: ${esc(r.answer_key.detail)}. Actual cost at risk ${usd(r.answer_key.actual_cost_at_risk_usd)}.`
      : "No error was planted in this room."}</p></details>`;
    $("#panel").innerHTML = html;
  }
})();
