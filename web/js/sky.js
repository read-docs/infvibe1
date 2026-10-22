const els = {
  status: document.getElementById("status"),
  sky: document.getElementById("sky"),
  bestTime: document.getElementById("best-time"),
  bestDetail: document.getElementById("best-detail"),
  night: document.getElementById("night"),
  moon: document.getElementById("moon"),
  chart: document.getElementById("chart"),
  table: document.getElementById("hours-table"),
  tzNote: document.getElementById("tz-note"),
  planets: document.getElementById("planets"),
  planetsStatus: document.getElementById("planets-status"),
  planetsNote: document.getElementById("planets-note"),
  issCard: document.getElementById("iss-card"),
  forecastParts: document.getElementById("forecast-parts"),
  forecastError: document.getElementById("forecast-error"),
  starlinkCard: document.getElementById("starlink-card"),
};

const dome = createSkyDome(document.getElementById("dome"), document.getElementById("dome-tooltip"));
const LIVE_MS = 30 * 1000;
let domeData = {};
let liveTimer = null;
let issPasses = null;  // next passes over the current location, refreshed with the forecast

const REFRESH_MS = 10 * 60 * 1000;
let current = null;  // location being shown
let refreshTimer = null;
let lastRender = null;  // [data, tz] of the chart on screen, for redrawing on resize

const timeIn = localTime;

function cloudWords(cover) {
  if (cover < 15) return "clear skies";
  if (cover < 40) return "a few clouds";
  if (cover < 70) return "partly cloudy";
  if (cover < 90) return "mostly cloudy";
  return "overcast";
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

function renderBest(data, tz) {
  const best = data.best;
  if (best) {
    const hour = data.hours.find((h) => h.time === best.time);
    els.bestTime.textContent = timeIn(best.time, tz);
    const moon = hour.moon_alt > 0 ? `the Moon up (${Math.round(data.moon.illumination * 100)}% lit)` : "no Moon";
    els.bestDetail.textContent = `Score ${best.score}/100: ${cloudWords(hour.cloud_cover)}, ${moon}.`;
  } else if (data.night.polar === "day") {
    els.bestTime.textContent = "No night tonight";
    els.bestDetail.textContent = "The Sun doesn't set here, so the sky never gets dark.";
  } else {
    els.bestTime.textContent = "Not tonight";
    els.bestDetail.textContent = "Clouds or twilight hide the sky for the rest of the night.";
  }
}

function renderNight(data, tz) {
  const n = data.night, astro = n.twilight.astronomical;
  if (n.polar === "day") {
    fillFacts(els.night, [["Sun", "Up all day (midnight Sun)"]]);
    return;
  }
  const rows = n.polar === "night"
    ? [["Sun", "Doesn't rise today (polar night)"]]
    : [["Sunset", timeIn(n.sunset, tz)]];
  // Near midsummer at high latitudes the Sun never gets 18° below the horizon.
  if (astro.dusk == null && astro.dawn == null) rows.push(["Full darkness", "Never: twilight all night"]);
  else rows.push(["Full darkness", `${timeIn(astro.dusk, tz)} – ${timeIn(astro.dawn, tz)}`]);
  if (n.polar !== "night") rows.push(["Sunrise", timeIn(n.sunrise, tz)]);
  fillFacts(els.night, rows);
}

function renderMoon(data, tz) {
  const m = data.moon, pos = m.position;
  fillFacts(els.moon, [
    ["Phase", `${m.phase}, ${Math.round(m.illumination * 100)}% lit`],
    ["Now", pos.alt > 0 ? `${Math.round(pos.alt)}° up, ${pos.direction}` : "Below the horizon"],
    ["Rises", timeIn(m.rise, tz)],
    ["Sets", timeIn(m.set, tz)],
  ]);
}

// Sequential blue ramp, dark (low score) to light (high score), so poor hours
// recede into the dark surface. Steps 600 → 200 of the reference blue ramp.
const SCORE_RAMP = ["#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5", "#5598e7", "#6da7ec", "#86b6ef", "#9ec5f4"];
const scoreColor = (s) => SCORE_RAMP[Math.min(SCORE_RAMP.length - 1, Math.floor((s / 100) * SCORE_RAMP.length))];

const SVG_NS = "http://www.w3.org/2000/svg";
function svgEl(name, attrs) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

// Drawn at the container's real pixel width (not a scaled viewBox) so text
// stays readable on phones; redrawn when the window is resized.
function renderChart(data, tz) {
  const hours = data.hours;
  const W = Math.max(280, els.chart.clientWidth), H = 220, left = 34, right = 8, top = 18, bottom = 26;
  const plotW = W - left - right, plotH = H - top - bottom;
  const colW = plotW / hours.length;
  const y = (pct) => top + plotH * (1 - pct / 100);

  const svg = svgEl("svg", { width: W, height: H, role: "img", "aria-label": "Hourly viewing score and cloud cover" });

  for (const v of [0, 50, 100]) {
    svg.append(svgEl("line", { x1: left, x2: W - right, y1: y(v), y2: y(v), class: v === 0 ? "axis" : "grid" }));
    const label = svgEl("text", { x: left - 6, y: y(v) + 4, class: "tick", "text-anchor": "end" });
    label.textContent = v;
    svg.append(label);
  }

  const tooltip = document.createElement("div");
  tooltip.className = "tooltip";
  tooltip.hidden = true;

  hours.forEach((h, i) => {
    const x = left + i * colW;
    const g = svgEl("g", { class: h.past ? "hour past" : "hour" });
    // 2px gap between neighbours; 4px rounded top anchored on the baseline.
    const bw = colW - 2, bx = x + 1;
    if (h.score > 0) {
      const top = y(h.score), r = Math.min(4, bw / 2, y(0) - top);
      g.append(svgEl("path", {
        d: `M${bx},${y(0)} V${top + r} Q${bx},${top} ${bx + r},${top} H${bx + bw - r} Q${bx + bw},${top} ${bx + bw},${top + r} V${y(0)} Z`,
        fill: scoreColor(h.score),
      }));
    }
    if (data.best && h.time === data.best.time) {
      const t = svgEl("text", { x: x + colW / 2, y: y(h.score) - 5, class: "best-mark", "text-anchor": "middle" });
      t.textContent = "Best";
      g.append(t);
    }
    // Thin out the hour labels so they don't collide on narrow screens.
    if (i % Math.ceil(28 / colW) === 0) {
      const t = svgEl("text", { x: x + colW / 2, y: H - 8, class: "tick", "text-anchor": "middle" });
      t.textContent = timeIn(h.time, tz).slice(0, 2);
      g.append(t);
    }
    // Hit target: the whole column, not just the bar.
    const hit = svgEl("rect", { x, y: top, width: colW, height: plotH, class: "hit" });
    hit.addEventListener("pointerenter", () => {
      tooltip.replaceChildren();
      const head = document.createElement("strong");
      head.textContent = `${timeIn(h.time, tz)}  ·  score ${h.score}`;
      tooltip.append(head);
      for (const line of [
        `Clouds ${h.cloud_cover}% (low ${h.cloud_low}, mid ${h.cloud_mid}, high ${h.cloud_high})`,
        `Visibility ${h.visibility_km} km · humidity ${h.humidity}%`,
        `Rain chance ${h.precip_probability}%`,
        `Sun ${h.sun_alt}° · Moon ${h.moon_alt > 0 ? `${h.moon_alt}° up` : "down"}`,
      ]) {
        const div = document.createElement("div");
        div.textContent = line;
        tooltip.append(div);
      }
      tooltip.hidden = false;
      // Flip to the left of the column near the right edge.
      const px = x + colW / 2;
      tooltip.style.left = `${px}px`;
      tooltip.style.transform = px > W * 0.6 ? "translateX(calc(-100% - 12px))" : "translateX(12px)";
      g.classList.add("hover");
    });
    hit.addEventListener("pointerleave", () => {
      tooltip.hidden = true;
      g.classList.remove("hover");
    });
    g.append(hit);
    svg.append(g);
  });

  // Cloud cover drawn on top of the bars; on the same 0–100 scale, so no second axis.
  const points = hours.map((h, i) => `${left + (i + 0.5) * colW},${y(h.cloud_cover)}`).join(" ");
  svg.append(svgEl("polyline", { points, class: "cloud-line" }));

  els.chart.replaceChildren(svg, tooltip);
}

function renderTable(data, tz) {
  const head = ["Time", "Score", "Clouds %", "Visibility km", "Humidity %", "Rain %", "Moon"];
  const rows = data.hours.map((h) => [
    timeIn(h.time, tz), h.score, h.cloud_cover, h.visibility_km, h.humidity, h.precip_probability,
    h.moon_alt > 0 ? `${h.moon_alt}°` : "down",
  ]);
  els.table.replaceChildren();
  const tr = document.createElement("tr");
  for (const text of head) {
    const th = document.createElement("th");
    th.textContent = text;
    tr.append(th);
  }
  els.table.append(tr);
  for (const row of rows) {
    const r = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      td.textContent = cell;
      r.append(td);
    }
    els.table.append(r);
  }
}

function cell(tag, text, className) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}

function renderPlanets(data, tz) {
  els.planets.replaceChildren();
  els.planetsNote.textContent = data.weather
    ? "“Tonight” is when it is at least 10° up in a dark, mostly clear sky."
    : "The weather forecast is unavailable, so “Tonight” ignores clouds: it is when the body is at least 10° up in a dark sky.";
  const head = document.createElement("tr");
  for (const h of ["", "Now", "Brightness", "Rises", "Sets", "Tonight"]) head.append(cell("th", h));
  els.planets.append(head);

  for (const b of data.bodies) {
    const tr = document.createElement("tr");
    if (b.visible_now) tr.className = "visible";

    const name = cell("td", b.name, "body-name");
    if (b.visible_now) name.append(cell("span", "visible now", "badge"));
    tr.append(name);

    const pos = b.position;
    tr.append(cell("td", pos.alt > 0 ? `${Math.round(pos.alt)}° up, ${pos.direction}` : "Below horizon", pos.alt > 0 ? "" : "muted"));
    tr.append(cell("td", `mag ${b.magnitude.toFixed(1).replace("-", "−")}${b.naked_eye ? "" : " (telescope)"}`));
    tr.append(cell("td", timeIn(b.rise, tz)));
    tr.append(cell("td", timeIn(b.set, tz)));
    if (b.tonight.length) {
      tr.append(cell("td", b.tonight.map((w) => `${timeIn(w.from, tz)} – ${timeIn(w.to, tz)}`).join(", ")));
    } else {
      tr.append(cell("td", b.high_tonight ? "Clouded out" : "Not visible", "muted"));
    }
    els.planets.append(tr);
  }
}

// --- Above you now: sky dome, ISS and Starlink, refreshed every 30 s.

function setCard(el, parts) {
  el.replaceChildren();
  for (const [text, className] of parts) {
    const span = document.createElement("span");
    span.textContent = text;
    if (className) span.className = className;
    el.append(span, " ");
  }
}

function renderIssCard(now, tz) {
  const parts = [];
  if (now && now.look) {
    parts.push(now.look.alt > 0
      ? [`Right now it is ${Math.round(now.look.alt)}° up in the ${now.look.direction}${now.sunlit ? "" : " (in Earth's shadow, so dark)"}.`]
      : ["Right now it is below your horizon.", "muted"]);
  }
  // Prefer the next pass under a clear sky; mention a cloudier earlier one.
  const visible = issPasses ? issPasses.filter((p) => p.visible) : [];
  const next = visible.find((p) => p.clear !== false);
  const describe = (p) => {
    const v = p.visible_part;
    const day = new Date(v.start.time * 1000).toLocaleDateString("en-GB", { weekday: "long", timeZone: tz });
    return `${day} ${timeIn(v.start.time, tz)}–${timeIn(v.end.time, tz)}, up to ${Math.round(v.max_alt)}°, ` +
      `appearing in the ${v.start.direction}, magnitude ${v.magnitude.toFixed(1).replace("-", "−")}`;
  };
  if (visible.length && visible[0] !== next) {
    parts.push([`The pass on ${describe(visible[0])} is likely clouded out.`, "muted"]);
  }
  if (next) {
    parts.push([`Next visible pass${next.clear ? " with a clear sky" : ""}: ${describe(next)}.`]);
  } else if (visible.length) {
    parts.push(["Every visible pass in the next 3 days looks cloudy.", "muted"]);
  } else if (issPasses) {
    parts.push(["No visible passes in the next 3 days.", "muted"]);
  }
  setCard(els.issCard, parts.length ? parts : [["Couldn't load the ISS position.", "muted"]]);
}

function renderStarlinkCard(result) {
  if (result.status === "rejected") {
    setCard(els.starlinkCard, [[`Starlink orbits are unavailable right now (${result.reason.message}).`, "muted"]]);
    return;
  }
  const d = result.value, c = d.counts;
  const parts = [[`${c.above_horizon} of ${c.total.toLocaleString("en")} Starlink satellites are above your horizon, ${c.sunlit_above} of them in sunlight.`]];
  parts.push(!d.sky_dark ? ["The sky is too bright to see them now.", "muted"]
    : d.cloudy ? ["Clouds hide them right now.", "muted"]
    : [`${c.visible} ${c.visible === 1 ? "is" : "are"} bright and high enough to spot now.`]);
  const train = d.recent_launches.find((l) => l.train);
  if (train) {
    parts.push([`Launch ${train.launch} (${train.satellites} satellites, ~${train.mean_alt_km} km) is still climbing: look for a “train” of dots in a line after dusk or before dawn.`]);
  }
  setCard(els.starlinkCard, parts);
}

async function loadLive(loc, tz) {
  clearTimeout(liveTimer);
  const q = `lat=${loc.lat}&lon=${loc.lon}`;
  const [planets, iss, starlink] = await Promise.allSettled([
    fetchJson(`/api/planets?${q}`),
    fetchJson(`/api/iss/now?${q}`),
    fetchJson(`/api/starlink?${q}`),
  ]);
  if (loc !== current) return;
  domeData = {
    bodies: planets.status === "fulfilled" ? planets.value.bodies : domeData.bodies,
    iss: iss.status === "fulfilled" ? iss.value : null,
    starlink: starlink.status === "fulfilled" ? starlink.value.satellites : [],
  };
  if (!els.sky.hidden) dome.draw(domeData);
  renderIssCard(iss.status === "fulfilled" ? iss.value : null, tz);
  renderStarlinkCard(starlink);
  liveTimer = setTimeout(() => loadLive(loc, tz), LIVE_MS);
}

async function load(loc) {
  if (loc !== current) issPasses = null;
  current = loc;
  clearTimeout(refreshTimer);
  if (els.sky.hidden) showStatus("Loading tonight's sky…", "loading");
  const query = `lat=${loc.lat}&lon=${loc.lon}`;
  // Only the forecast parts need the weather API; the planets, ISS and
  // Starlink still show when it is down.
  const [sky, planets] = await Promise.allSettled([fetchJson(`/api/sky?${query}`), fetchJson(`/api/planets?${query}`)]);
  if (loc !== current) return;  // the user picked another place meanwhile

  if (sky.status === "rejected" && planets.status === "rejected") {
    els.sky.hidden = true;
    showStatus(`Couldn't load tonight's sky: ${sky.reason.message}`, "error");
    refreshTimer = setTimeout(() => load(current), REFRESH_MS);
    return;
  }

  let tz = loc.timezone;
  if (sky.status === "fulfilled") {
    const data = sky.value;
    tz = data.location.timezone;
    rememberTimezone(tz);
    renderBest(data, tz);
    renderNight(data, tz);
    renderMoon(data, tz);
    renderTable(data, tz);
    lastRender = [data, tz];
    els.forecastParts.hidden = false;
    els.forecastError.hidden = true;
  } else {
    lastRender = null;
    els.forecastParts.hidden = true;
    els.forecastError.textContent = `The weather forecast is unavailable, so there is no viewing score right now (${sky.reason.message}).`;
    els.forecastError.hidden = false;
  }
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  els.tzNote.textContent = !tz ? "Times are in your browser's time zone."
    : tz === browserTz ? "" : `All times are local to the location (${tz}).`;
  els.status.hidden = true;
  els.sky.hidden = false;
  if (lastRender) renderChart(...lastRender);  // after unhiding, so the chart can measure its width

  if (planets.status === "fulfilled") {
    renderPlanets(planets.value, tz);
    els.planetsStatus.hidden = true;
  } else {
    els.planets.replaceChildren();
    els.planetsStatus.textContent = `Couldn't load the planets: ${planets.reason.message}`;
    els.planetsStatus.className = "status error";
    els.planetsStatus.hidden = false;
  }

  // Both report their own failures inside the ISS and Starlink cards.
  fetchJson(`/api/iss/passes?${query}&days=3`)
    .then((d) => { if (loc === current) { issPasses = d.passes; renderIssCard(domeData.iss, tz); } })
    .catch(() => {});
  loadLive(loc, tz);
  refreshTimer = setTimeout(() => load(current), REFRESH_MS);
}

function showStatus(text, kind) {
  els.status.textContent = text;
  els.status.className = `status ${kind}`;
  els.status.hidden = false;
}

let resizeFrame = 0;
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => {
    if (els.sky.hidden) return;
    if (lastRender) renderChart(...lastRender);
    dome.draw(domeData);
  });
});

createLocationPicker(document.getElementById("location"), load);
