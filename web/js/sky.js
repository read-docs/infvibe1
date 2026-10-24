const els = {
  status: document.getElementById("status"),
  sky: document.getElementById("sky"),
  kicker: document.getElementById("kicker"),
  headline: document.getElementById("headline"),
  lede: document.getElementById("lede"),
  storyFacts: document.getElementById("story-facts"),
  pano: document.getElementById("pano"),
  panoSub: document.getElementById("pano-sub"),
  panoKey: document.getElementById("pano-key"),
  table: document.getElementById("hours-table"),
  tzNote: document.getElementById("tz-note"),
  planets: document.getElementById("planets"),
  planetsStatus: document.getElementById("planets-status"),
  planetsNote: document.getElementById("planets-note"),
  issCard: document.getElementById("iss-card"),
  forecastParts: document.getElementById("forecast-parts"),
  forecastError: document.getElementById("forecast-error"),
  starlinkCard: document.getElementById("starlink-card"),
  lookSection: document.getElementById("look-section"),
  lookCards: document.getElementById("look-cards"),
  whenGrid: document.getElementById("when-grid"),
};

const dome = createSkyDome(document.getElementById("dome"), document.getElementById("dome-tooltip"));
const LIVE_MS = 30 * 1000;
let domeData = {};
let liveTimer = null;
let issPasses = null;  // next passes over the current location, refreshed with the forecast

const REFRESH_MS = 10 * 60 * 1000;
let current = null;  // location being shown
let refreshTimer = null;

const timeIn = localTime;

const SKY_WORDS = { clear: "Clear", mostly_clear: "Mostly clear", cloudy: "Cloudy", overcast: "Overcast" };
const BODY_COLORS = {
  Moon: "#e9e4d4", Mercury: "#b8a48c", Venus: "#f6d98b", Mars: "#ec7c5a",
  Jupiter: "#e6b98a", Saturn: "#f2c46d", Uranus: "#8fd6d0", Neptune: "#7c9cf5",
};
const bodyColor = (name) => BODY_COLORS[name] || "#f4efe6";

const isGoodHour = (h) => h.dark && (h.sky === "clear" || h.sky === "mostly_clear");

function verdictOf(percent) {
  if (percent == null) return null;
  return percent >= 70 ? "Great night" : percent >= 45 ? "Decent night" : percent >= 20 ? "Poor night" : "Bad night";
}

// Longest run of consecutive clear or mostly clear dark hours, as {from, to} (to = end of the last hour).
function clearWindow(hours) {
  let best = null, start = null;
  hours.forEach((h, i) => {
    const good = isGoodHour(h);
    if (good && start == null) start = i;
    if ((!good || i === hours.length - 1) && start != null) {
      const end = good ? i : i - 1;
      if (!best || end - start > best[1] - best[0]) best = [start, end];
      start = null;
    }
  });
  return best && { from: hours[best[0]].time, to: hours[best[1]].time + 3600, hours: best[1] - best[0] + 1 };
}

function cloudWords(cover) {
  if (cover < 15) return "the sky is clear";
  if (cover < 40) return "there are only a few clouds";
  if (cover < 70) return "it is partly cloudy";
  if (cover < 90) return "it is mostly cloudy";
  return "it is overcast";
}

// "in Warsaw", or "here" when the location is only coordinates.
function placePhrase(loc) {
  return /^[-\d]|^My location/.test(loc.name) ? "here" : `in ${loc.name}`;
}

function el(tag, className, ...children) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  for (const c of children) if (c != null) e.append(c);
  return e;
}

function strong(text) {
  return el("strong", "", text);
}

// --- Headline, lede and the row of big numbers ---

function renderStory(loc, sky, planets, tz) {
  const where = placePhrase(loc);
  const visible = planets ? planets.bodies.filter((b) => b.best) : [];
  els.lede.replaceChildren();

  if (!sky) {
    els.kicker.textContent = "Tonight's sky";
    els.headline.textContent = `Tonight's sky ${where}`;
    els.lede.append("The weather forecast is unavailable, so there is no viewing score right now.");
    els.storyFacts.hidden = true;
    return;
  }

  const q = sky.night_quality, n = sky.night, verdict = verdictOf(q.percent);
  const win = clearWindow(sky.hours);
  els.kicker.textContent = verdict ? `Tonight's sky · ${q.percent}% · ${verdict}` : "Tonight's sky";

  els.headline.replaceChildren();
  if (n.polar === "day") {
    els.headline.textContent = `No night ${where} tonight: the Sun doesn't set.`;
  } else if (!verdict) {
    els.headline.textContent = `The sky never gets properly dark ${where} tonight.`;
  } else {
    const word = verdict.split(" ")[0].toLowerCase();
    const range = win && el("em", "", `${timeIn(win.from, tz)}–${timeIn(win.to, tz)}`);
    if (!win) els.headline.append(`A ${word} night ${where}. Clouds cover the sky all night.`);
    else if (win.hours >= q.dark_hours) els.headline.append(`A ${word} night ${where}: clear all night.`);
    else if (q.percent < 45) els.headline.append(`A ${word} night ${where}, but the sky clears `, range, ".");
    else els.headline.append(`A ${word} night ${where}, clearest `, range, ".");
  }

  if (sky.best) {
    const h = sky.hours.find((x) => x.time === sky.best.time);
    els.lede.append("The best hour is ", strong(timeIn(sky.best.time, tz)), `, when ${cloudWords(h.cloud_cover)}. `);
  } else if (n.polar !== "day") {
    els.lede.append("Clouds or twilight hide the sky for the rest of the night. ");
  }
  if (visible.length) {
    const names = visible.map((b) => b.name);
    els.lede.append("Look for ");
    names.forEach((name, i) => {
      els.lede.append(strong(name));
      if (i < names.length - 2) els.lede.append(", ");
      else if (i === names.length - 2) els.lede.append(" and ");
    });
    els.lede.append(". ");
  }
  els.lede.append(moonSentence(sky, tz));

  const facts = [
    [verdict ? `${q.percent}%` : "–", "Whole night"],
    [sky.best ? timeIn(sky.best.time, tz) : "–", "Best hour"],
    [q.dark_hours ? `${q.clear_hours} of ${q.dark_hours} h` : "–", "Clear dark hours"],
    [`${Math.round(sky.moon.illumination * 100)}%`, "Moon lit"],
  ];
  els.storyFacts.replaceChildren(...facts.map(([value, label]) =>
    el("div", "story-fact", el("div", "sf-value", value), el("div", "sf-label", label))));
  els.storyFacts.hidden = false;
}

function moonSentence(sky, tz) {
  const m = sky.moon, n = sky.night, lit = Math.round(m.illumination * 100);
  if (lit < 25) return `The Moon is only ${lit}% lit, so the sky is properly dark.`;
  const during = (t) => t != null && n.sunset != null && n.sunrise != null && t > n.sunset && t < n.sunrise;
  if (during(m.set)) return `The Moon is ${lit}% lit and sets at ${timeIn(m.set, tz)}, so faint targets get easier after that.`;
  if (during(m.rise)) return `The Moon is ${lit}% lit and rises at ${timeIn(m.rise, tz)}, so catch faint targets before then.`;
  const upAtNight = sky.hours.some((h) => h.dark && h.moon_alt > 0);
  return upAtNight ? `The Moon is ${lit}% lit and up all night, which washes out faint targets.`
    : `The Moon is ${lit}% lit but stays below the horizon after dark.`;
}

// --- The night at a glance: x = hour, y = altitude, cloud haze per hour ---

const SVG_NS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs, text) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}

function renderPanorama(sky, planets, tz) {
  const svg = els.pano, H = sky.hours, n = sky.night;
  svg.replaceChildren();
  els.panoKey.replaceChildren();
  const darkness = n.twilight.astronomical.dusk == null ? "never fully dark"
    : `full darkness ${timeIn(n.twilight.astronomical.dusk, tz)}–${timeIn(n.twilight.astronomical.dawn, tz)}`;
  els.panoSub.textContent = n.polar === "day" ? "The Sun stays up all night here."
    : `Sunset ${timeIn(n.sunset, tz)} · ${darkness} · sunrise ${timeIn(n.sunrise, tz)}`;
  if (!H.length) { svg.hidden = true; return; }
  svg.hidden = false;

  const W = 1060, L = 52, R = W - 10, T = 36, B = 330;
  svg.setAttribute("viewBox", `0 0 ${W} ${B + 66}`);
  const colW = (R - L) / H.length;
  const x = (i) => L + colW * (i + 0.5);
  const y = (alt) => B - (Math.max(0, alt) / 90) * (B - T);
  const label = (attrs, text) => svg.append(svgEl("text", { class: "pano-label", ...attrs }, text));

  // Background per hour: darker as the Sun sinks, hazed over by clouds.
  H.forEach((h, i) => {
    const d = Math.max(0, Math.min(1, -h.sun_alt / 18)), light = Math.round(70 * (1 - d));
    const rect = { x: L + colW * i, y: T, width: colW + 0.5, height: B - T };
    svg.append(svgEl("rect", { ...rect, fill: `rgb(${30 + light},${Math.round(26 + light * 0.6)},${Math.round(60 + light * 0.4)})` }));
    svg.append(svgEl("rect", { ...rect, fill: "rgb(200,200,215)", opacity: (h.cloud_blocking / 100 * 0.45).toFixed(2) }));
  });
  for (const a of [0, 30, 60, 90]) {
    svg.append(svgEl("line", { x1: L, x2: R, y1: y(a), y2: y(a), class: "pano-grid" }));
    label({ x: L - 8, y: y(a) + 4, "text-anchor": "end" }, `${a}°`);
  }

  const win = clearWindow(H);
  if (win) {
    const i0 = H.findIndex((h) => h.time === win.from);
    svg.append(svgEl("rect", { x: L + colW * i0, y: T - 14, width: colW * win.hours, height: 4, rx: 2, class: "pano-gold" }));
    label({ x: L + colW * i0, y: T - 20, class: "pano-label gold" }, "clear window");
  }

  // One curve per body that gets above the horizon, solid where it has a best hour.
  const labels = [];
  const bodies = planets ? planets.bodies : [];
  for (const b of bodies) {
    const pts = H.map((h, i) => {
      const p = b.hours.find((bh) => bh.time === h.time);
      return p && [x(i), y(p.alt), p.alt];
    }).filter(Boolean);
    if (!pts.some((p) => p[2] > 0)) continue;
    const c = bodyColor(b.name);
    const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
    svg.append(svgEl("path", { d, fill: "none", stroke: c, "stroke-width": b.best ? 2.5 : 1.2, opacity: b.best ? 1 : 0.45, "stroke-dasharray": b.best ? "" : "4 4" }));
    const i = b.best ? H.findIndex((h) => h.time === b.best.time) : -1;
    if (i >= 0) {
      svg.append(svgEl("circle", { cx: x(i), cy: y(b.best.alt), r: b.name === "Moon" ? 9 : 5.5, fill: c, class: "pano-dot" }));
      labels.push({ name: b.name, c, x: x(i), y: y(b.best.alt) });
    }
    const key = el("span", "", el("i", ""), b.name);
    key.firstChild.style.background = c;
    if (!b.best) key.firstChild.style.opacity = 0.45;
    els.panoKey.append(key);
  }
  // Spread labels apart when several bodies peak at the same hour.
  labels.sort((a, b) => a.y - b.y);
  labels.forEach((l, k) => { l.ly = k && labels[k - 1].x === l.x ? Math.max(l.y, labels[k - 1].ly + 15) : l.y; });
  for (const l of labels) {
    if (Math.abs(l.ly - l.y) > 2) svg.append(svgEl("line", { x1: l.x + 6, y1: l.y, x2: l.x + 14, y2: l.ly - 4, stroke: l.c, opacity: 0.5 }));
    svg.append(svgEl("text", { x: l.x + 16, y: l.ly, fill: l.c, class: "pano-name" }, l.name));
  }
  if (bodies.length) els.panoKey.append(el("span", "", el("i", "haze"), "Clouds"));

  // Past hours fade out, with a line at "now".
  const nowI = H.findIndex((h) => sky.now < h.time + 3600);
  if (nowI > 0 || (nowI === 0 && sky.now > H[0].time)) {
    const nx = L + colW * nowI + colW * ((sky.now - H[nowI].time) / 3600);
    svg.append(svgEl("rect", { x: L, y: T, width: nx - L, height: B - T, class: "pano-past" }));
    svg.append(svgEl("line", { x1: nx, x2: nx, y1: T, y2: B, class: "pano-now" }));
    label({ x: nx + 4, y: B - 6, class: "pano-label" }, "now");
  }

  // Rows under the chart: hour, cloud %, score bar. Each column has a hover tooltip.
  label({ x: L - 8, y: B + 36, "text-anchor": "end" }, "cloud");
  label({ x: L - 8, y: B + 56, "text-anchor": "end" }, "score");
  H.forEach((h, i) => {
    const best = sky.best && h.time === sky.best.time;
    label({ x: x(i), y: B + 18, "text-anchor": "middle", class: best ? "pano-label gold strong" : "pano-label" }, timeIn(h.time, tz).slice(0, 2));
    label({ x: x(i), y: B + 36, "text-anchor": "middle", class: isGoodHour(h) ? "pano-label gold" : "pano-label" }, `${h.cloud_blocking}%`);
    const bw = colW - 14;
    svg.append(svgEl("rect", { x: x(i) - bw / 2, y: B + 48, width: bw, height: 6, rx: 3, class: "pano-track" }));
    if (h.dark && h.score > 0) {
      svg.append(svgEl("rect", { x: x(i) - bw / 2, y: B + 48, width: bw * h.score / 100, height: 6, rx: 3, class: "pano-gold", opacity: (0.4 + 0.6 * h.score / 100).toFixed(2) }));
    }
    const hit = svgEl("rect", { x: L + colW * i, y: T, width: colW, height: B + 60 - T, class: "pano-hit" });
    hit.append(svgEl("title", {}, [
      `${timeIn(h.time, tz)} · ${h.dark ? SKY_WORDS[h.sky] : h.sun_alt > 0 ? "Daylight" : "Twilight"}, score ${h.score}`,
      `Clouds block ${h.cloud_blocking}% of the sky (low ${h.cloud_low}%, mid ${h.cloud_mid}%, high ${h.cloud_high}%)`,
      `Visibility ${h.visibility_km} km · humidity ${h.humidity}% · rain chance ${h.precip_probability}%`,
      `Sun ${h.sun_alt}° · Moon ${h.moon_alt > 0 ? `${h.moon_alt}° up` : "down"}`,
    ].join("\n")));
    svg.append(hit);
  });
}

// --- What to look for: a card per body with a best hour, one card for the rest ---

const LIMIT_WORDS = { too_bright: "twilight", clouds: "some cloud", moonlight: "moonlight", too_low: "its low altitude" };

function whyNotTonight(b) {
  const up = b.hours.filter((h) => h.alt >= 10);
  if (up.some((h) => h.limit === "clouds")) return "clouded out";
  if (up.some((h) => h.limit === "too_bright")) return "only up during twilight";
  if (up.some((h) => h.limit === "moonlight")) return "washed out by the Moon";
  return b.hours.some((h) => h.alt > 0) ? "too low after dark" : "below the horizon after dark";
}

function renderLookCards(planets, tz) {
  els.lookCards.replaceChildren();
  const dot = (name) => {
    const d = el("span", "dot");
    d.style.background = bodyColor(name);
    return d;
  };
  for (const b of planets.bodies.filter((x) => x.best)) {
    const note = b.best.limit ? `Held back by ${LIMIT_WORDS[b.best.limit]}.` : "High, dark and clear.";
    const span = b.tonight.length ? ` Visible ${b.tonight.map((w) => `${timeIn(w.from, tz)}–${timeIn(w.to, tz)}`).join(", ")}.` : "";
    els.lookCards.append(el("div", "look-card",
      el("h3", "", dot(b.name), b.name),
      el("div", "look-when", timeIn(b.best.time, tz)),
      el("p", "", `${Math.round(b.best.alt)}° up in the ${b.best.direction}. ${note}${span}${b.naked_eye ? "" : " Needs binoculars or a telescope."}`)));
  }
  const off = planets.bodies.filter((x) => !x.best);
  if (off.length) {
    const list = el("p", "");
    off.forEach((b, i) => {
      if (i) list.append(el("br"));
      list.append(dot(b.name), strong(b.name), `: ${whyNotTonight(b)}`);
    });
    els.lookCards.append(el("div", "look-card off", el("h3", "", "Not tonight"), list));
  }
}

function renderTable(data, tz) {
  const head = ["Time", "Sky", "Score", "Clouds %", "Visibility km", "Humidity %", "Rain %", "Moon"];
  const rows = data.hours.map((h) => [
    timeIn(h.time, tz), h.dark ? SKY_WORDS[h.sky] : "Too bright", h.score, h.cloud_blocking, h.visibility_km, h.humidity, h.precip_probability,
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

// Sequential gold ramp, dark (poor) to light (good).
const SCORE_RAMP = ["#4a3a22", "#5d4826", "#73582a", "#8b6a2e", "#a57d33", "#bf9139", "#d9a641", "#ebba55", "#f6d27f"];
const rampIndex = (score) => Math.min(SCORE_RAMP.length - 1, Math.floor((score / 100) * SCORE_RAMP.length));

function limitWords(h) {
  if (h.limit === "too_low") return h.alt < 0 ? "below the horizon" : "too low (under 10°)";
  return { too_bright: "the sky is too bright", clouds: "clouds", moonlight: "moonlight" }[h.limit];
}

// One row per body, one column per hour of tonight, shaded by how well it can be seen.
function renderWhenGrid(data, tz) {
  const hours = data.bodies[0].hours;
  els.lookSection.hidden = !hours.length;
  if (!hours.length) return;
  const grid = els.whenGrid;
  grid.replaceChildren();
  grid.style.gridTemplateColumns = `minmax(7.5rem, auto) repeat(${hours.length}, minmax(2.3rem, 1fr))`;

  grid.append(cell("div", "", "wg-corner"));
  const pastAt = hours.map((h) => h.time + 3600 <= data.now);
  hours.forEach((h, i) => grid.append(cell("div", timeIn(h.time, tz).slice(0, 2), pastAt[i] ? "wg-hour past" : "wg-hour")));

  for (const b of data.bodies) {
    const label = cell("div", "", "wg-label");
    label.append(cell("strong", b.name));
    let note;
    if (b.best) note = `best ${timeIn(b.best.time, tz)}, ${Math.round(b.best.alt)}° ${b.best.direction}`;
    else if (b.hours.some((h) => h.limit === "clouds" && h.alt >= 10)) note = "clouded out";
    else note = "not visible tonight";
    if (!b.naked_eye) note += " · telescope";
    label.append(cell("span", note, b.best ? "" : "muted"));
    grid.append(label);

    b.hours.forEach((h, i) => {
      const best = b.best && h.time === b.best.time;
      const c = cell("div", h.score > 0 ? h.score : "", "wg-cell");
      if (h.score > 0) {
        const k = rampIndex(h.score);
        c.style.background = SCORE_RAMP[k];
        if (k >= 5) c.classList.add("light");
      }
      if (best) c.classList.add("best-cell");
      if (pastAt[i]) c.classList.add("past");
      const where = h.alt > 0 ? `${Math.round(h.alt)}° up in the ${h.direction}` : "below the horizon";
      const held = h.limit && h.score < 100 ? ` Held back by ${limitWords(h)}.` : "";
      c.title = `${b.name} at ${timeIn(h.time, tz)}: ${where}, score ${h.score}.${held}`;
      grid.append(c);
    });
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
    els.storyFacts.hidden = true;
    els.kicker.textContent = "Tonight's sky";
    els.headline.textContent = "Tonight's Sky";
    els.lede.textContent = "";
    showStatus(`Couldn't load tonight's sky: ${sky.reason.message}`, "error");
    refreshTimer = setTimeout(() => load(current), REFRESH_MS);
    return;
  }

  let tz = loc.timezone;
  if (sky.status === "fulfilled") {
    const data = sky.value;
    tz = data.location.timezone;
    rememberTimezone(tz);
    renderPanorama(data, planets.status === "fulfilled" ? planets.value : null, tz);
    renderTable(data, tz);
    els.forecastParts.hidden = false;
    els.forecastError.hidden = true;
  } else {
    els.forecastParts.hidden = true;
    els.forecastError.textContent = `The weather forecast is unavailable, so there is no viewing score right now (${sky.reason.message}).`;
    els.forecastError.hidden = false;
  }
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  els.tzNote.textContent = !tz ? "Times are in your browser's time zone."
    : tz === browserTz ? "" : `All times are local to the location (${tz}).`;
  renderStory(loc, sky.status === "fulfilled" ? sky.value : null, planets.status === "fulfilled" ? planets.value : null, tz);
  els.status.hidden = true;
  els.sky.hidden = false;

  if (planets.status === "fulfilled") {
    renderPlanets(planets.value, tz);
    renderWhenGrid(planets.value, tz);
    renderLookCards(planets.value, tz);
    els.planetsStatus.hidden = true;
  } else {
    els.planets.replaceChildren();
    els.lookSection.hidden = true;
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
    dome.draw(domeData);
  });
});

createLocationPicker(document.getElementById("location"), load);
