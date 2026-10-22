const els = {
  status: document.getElementById("status"),
  aurora: document.getElementById("aurora"),
  verdict: document.getElementById("verdict"),
  verdictDetail: document.getElementById("verdict-detail"),
  nowFacts: document.getElementById("now-facts"),
  placeFacts: document.getElementById("place-facts"),
  chart: document.getElementById("kp-chart"),
  tonight: document.getElementById("tonight"),
  tzNote: document.getElementById("tz-note"),
};

const REFRESH_MS = 15 * 60 * 1000;
let current = null;
let refreshTimer = null;
let lastData = null;

const CHANCE_TEXT = {
  overhead: "Possible overhead",
  horizon: "Possible, low on the horizon",
  camera: "Camera only",
  none: "Unlikely",
};

// NOAA geomagnetic storm scale: Kp 5 = G1 (minor) ... Kp 9 = G5 (extreme).
function stormLevel(kp) {
  if (kp < 3) return "quiet";
  if (kp < 4) return "unsettled";
  if (kp < 5) return "active";
  const g = Math.min(5, Math.floor(kp) - 4);
  return `storm G${g} (${["minor", "moderate", "strong", "severe", "extreme"][g - 1]})`;
}

function fillFacts(dl, rows) {
  dl.replaceChildren();
  for (const [term, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.append(dt, dd);
  }
}

function renderVerdict(d, tz) {
  const t = d.tonight, dir = d.location.look_towards, need = d.kp_needed.horizon.toFixed(1);
  const best = t.best;
  const when = best ? `around ${localTime(best.time, tz)}` : "";
  const texts = {
    go: [`Worth looking ${dir}`, `${CHANCE_TEXT[best.chance]} ${when}: Kp ${best.kp.toFixed(1)} and ${best.cloud == null ? "no cloud forecast" : `${best.cloud}% cloud`}. Get away from city lights and face ${dir}.`],
    cloudy: ["Aurora possible, but cloudy", `Kp is high enough (up to ${t.max_kp.toFixed(1)}), but clouds cover the sky in the hours it could show.`],
    camera: ["Only a camera might catch it", `Kp up to ${t.max_kp.toFixed(1)} tonight; you need about ${need} to see aurora with your eyes here. A long-exposure photo facing ${dir} might still show a glow.`],
    unlikely: ["Unlikely tonight", `Kp up to ${t.max_kp.toFixed(1)} tonight; here you need about ${need} for aurora low on the ${dir}ern horizon.`],
    no_darkness: ["No dark sky tonight", "The Sun doesn't get far enough below the horizon for aurora to show."],
  };
  const [title, detail] = texts[t.verdict];
  els.verdict.textContent = title;
  els.verdictDetail.textContent = t.weather ? detail : `${detail} (The cloud forecast is unavailable.)`;
}

function renderFacts(d) {
  const now = d.now;
  fillFacts(els.nowFacts, [
    ["Kp now", now.kp == null ? "—" : `${now.kp.toFixed(1)}, ${stormLevel(now.kp)}`],
    ["Here", now.dark ? CHANCE_TEXT[now.chance] : "Too bright to see aurora now"],
  ]);
  const ns = d.location.geomagnetic_lat >= 0 ? "N" : "S";
  fillFacts(els.placeFacts, [
    ["Magnetic latitude", `${Math.abs(d.location.geomagnetic_lat).toFixed(1)}° ${ns}`],
    ["Kp for horizon view", d.kp_needed.horizon.toFixed(1)],
    ["Kp for overhead", d.kp_needed.overhead.toFixed(1)],
    ["Look towards", `the ${d.location.look_towards}`],
  ]);
}

const SVG_NS = "http://www.w3.org/2000/svg";
function svgEl(name, attrs) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

function renderChart(d, tz) {
  const pts = d.forecast;
  const W = Math.max(280, els.chart.clientWidth), H = 220, left = 26, right = 8, top = 14, bottom = 26;
  const plotW = W - left - right, plotH = H - top - bottom;
  const colW = plotW / pts.length;
  const y = (kp) => top + plotH * (1 - kp / 9);
  const svg = svgEl("svg", { width: W, height: H, role: "img", "aria-label": "Kp index by 3-hour block" });

  for (const v of [0, 3, 6, 9]) {
    svg.append(svgEl("line", { x1: left, x2: W - right, y1: y(v), y2: y(v), class: v === 0 ? "axis" : "grid" }));
    const t = svgEl("text", { x: left - 6, y: y(v) + 4, class: "tick", "text-anchor": "end" });
    t.textContent = v;
    svg.append(t);
  }

  const tooltip = document.createElement("div");
  tooltip.className = "tooltip";
  tooltip.hidden = true;

  const nowUnix = Date.now() / 1000;
  pts.forEach((p, i) => {
    const x = left + i * colW, bw = Math.max(1, colW - 2), bx = x + 1;
    // NOAA calls the rest of today "estimated" even before it happens; anything ahead of now is a forecast.
    const future = p.kind === "predicted" || p.time > nowUnix;
    const g = svgEl("g", { class: "hour" });
    if (p.kp > 0) {
      const top_ = y(p.kp), r = Math.min(3, bw / 2, y(0) - top_);
      g.append(svgEl("path", {
        d: `M${bx},${y(0)} V${top_ + r} Q${bx},${top_} ${bx + r},${top_} H${bx + bw - r} Q${bx + bw},${top_} ${bx + bw},${top_ + r} V${y(0)} Z`,
        class: future ? "kp-bar predicted" : "kp-bar",
      }));
    }
    // A date label at each local midnight.
    const hour = Number(localTime(p.time, tz).slice(0, 2));
    if (hour < 3) {
      const t = svgEl("text", { x, y: H - 8, class: "tick" });
      t.textContent = new Date(p.time * 1000).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", timeZone: tz });
      g.append(t);
    }
    const hit = svgEl("rect", { x, y: top, width: colW, height: plotH, class: "hit" });
    hit.addEventListener("pointerenter", () => {
      tooltip.replaceChildren();
      const head = document.createElement("strong");
      const day = new Date(p.time * 1000).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: tz });
      head.textContent = `${day} ${localTime(p.time, tz)}–${localTime(p.time + 3 * 3600, tz)}`;
      const line1 = document.createElement("div");
      line1.textContent = `Kp ${p.kp.toFixed(2)} (${future ? "forecast" : p.kind}), ${stormLevel(p.kp)}`;
      const line2 = document.createElement("div");
      line2.textContent = `Aurora here: ${CHANCE_TEXT[p.chance].toLowerCase()}`;
      tooltip.append(head, line1, line2);
      tooltip.style.left = `${x + colW / 2}px`;
      tooltip.style.transform = x > W * 0.6 ? "translateX(calc(-100% - 12px))" : "translateX(12px)";
      tooltip.hidden = false;
      g.classList.add("hover");
    });
    hit.addEventListener("pointerleave", () => { tooltip.hidden = true; g.classList.remove("hover"); });
    g.append(hit);
    svg.append(g);
  });

  // The threshold that matters for this location, and where "now" is.
  const need = d.kp_needed.horizon;
  svg.append(svgEl("line", { x1: left, x2: W - right, y1: y(need), y2: y(need), class: "threshold" }));
  const label = svgEl("text", { x: W - right, y: y(need) - 5, class: "tick threshold-label", "text-anchor": "end" });
  label.textContent = `Kp ${need.toFixed(1)} needed here`;
  svg.append(label);
  const nowIdx = pts.findIndex((p) => p.time > Date.now() / 1000);
  if (nowIdx > 0) {
    const prev = pts[nowIdx - 1];
    const nx = left + (nowIdx - 1 + (Date.now() / 1000 - prev.time) / (3 * 3600)) * colW;
    svg.append(svgEl("line", { x1: nx, x2: nx, y1: top, y2: y(0), class: "now-line" }));
    const t = svgEl("text", { x: nx + 4, y: top + 8, class: "tick" });
    t.textContent = "now";
    svg.append(t);
  }
  els.chart.replaceChildren(svg, tooltip);
}

function renderTonight(d, tz) {
  els.tonight.replaceChildren();
  const hours = d.tonight.hours;
  if (!hours.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.textContent = "No hours dark enough for aurora tonight.";
    td.className = "muted";
    tr.append(td);
    els.tonight.append(tr);
    return;
  }
  const head = document.createElement("tr");
  for (const h of ["Time", "Kp", "Aurora here", "Clouds"]) {
    const th = document.createElement("th");
    th.textContent = h;
    head.append(th);
  }
  els.tonight.append(head);
  for (const h of hours) {
    const tr = document.createElement("tr");
    const good = (h.chance === "horizon" || h.chance === "overhead") && (h.cloud == null || h.cloud < 50);
    if (good) tr.className = "visible";
    for (const [text, muted] of [
      [localTime(h.time, tz), false],
      [h.kp < 0 ? "—" : h.kp.toFixed(1), false],
      [CHANCE_TEXT[h.chance], h.chance === "none"],
      [h.cloud == null ? "—" : `${h.cloud}%`, h.cloud >= 50],
    ]) {
      const td = document.createElement("td");
      td.textContent = text;
      if (muted) td.className = "muted";
      tr.append(td);
    }
    els.tonight.append(tr);
  }
}

function render() {
  if (!lastData) return;
  const [d, tz] = lastData;
  renderVerdict(d, tz);
  renderFacts(d);
  renderTonight(d, tz);
  renderChart(d, tz);
}

async function load(loc) {
  current = loc;
  clearTimeout(refreshTimer);
  if (els.aurora.hidden) {
    els.status.textContent = "Loading space weather…";
    els.status.className = "status loading";
    els.status.hidden = false;
  }
  try {
    const d = await fetchJson(`/api/aurora?lat=${loc.lat}&lon=${loc.lon}`);
    if (loc !== current) return;
    const tz = loadLocation()?.timezone;
    lastData = [d, tz];
    els.status.hidden = true;
    els.aurora.hidden = false;
    render();
    els.tzNote.textContent = tz ? `All times are local to the location (${tz}).` : "Times are in your browser's time zone.";
  } catch (err) {
    if (loc !== current) return;
    els.aurora.hidden = true;
    els.status.textContent = `Couldn't load space weather: ${err.message}`;
    els.status.className = "status error";
    els.status.hidden = false;
  }
  refreshTimer = setTimeout(() => load(current), REFRESH_MS);
}

let resizeFrame = 0;
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => lastData && !els.aurora.hidden && renderChart(...lastData));
});

createLocationPicker(document.getElementById("location"), load);
