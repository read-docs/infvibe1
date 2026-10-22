const els = {
  status: document.getElementById("status"),
  sky: document.getElementById("sky"),
  bestTime: document.getElementById("best-time"),
  bestDetail: document.getElementById("best-detail"),
  night: document.getElementById("night"),
  moon: document.getElementById("moon"),
  nightPercent: document.getElementById("night-percent"),
  nightDetail: document.getElementById("night-detail"),
  timeline: document.getElementById("timeline"),
  table: document.getElementById("hours-table"),
  tzNote: document.getElementById("tz-note"),
  planets: document.getElementById("planets"),
  planetsStatus: document.getElementById("planets-status"),
  planetsNote: document.getElementById("planets-note"),
  issCard: document.getElementById("iss-card"),
  forecastParts: document.getElementById("forecast-parts"),
  forecastError: document.getElementById("forecast-error"),
  starlinkCard: document.getElementById("starlink-card"),
  whenPanel: document.getElementById("when-panel"),
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

function renderNightQuality(data) {
  const q = data.night_quality;
  if (q.percent == null) {
    els.nightPercent.textContent = "–";
    els.nightDetail.textContent = "The sky doesn't get dark tonight.";
    return;
  }
  const verdict = q.percent >= 70 ? "Great night" : q.percent >= 45 ? "Decent night" : q.percent >= 20 ? "Poor night" : "Bad night";
  els.nightPercent.textContent = `${q.percent}%`;
  els.nightDetail.textContent = `${verdict}: ${q.clear_hours} of ${q.dark_hours} dark hours are clear or mostly clear.`;
}

const SKY_WORDS = { clear: "Clear", mostly_clear: "Mostly clear", cloudy: "Cloudy", overcast: "Overcast" };

function renderTimeline(data, tz) {
  els.timeline.replaceChildren();
  for (const h of data.hours) {
    const best = data.best && h.time === data.best.time;
    const col = document.createElement("div");
    col.className = ["tl-hour", h.past && "past", best && "tl-top"].filter(Boolean).join(" ");
    col.title = [
      `${timeIn(h.time, tz)} · ${SKY_WORDS[h.sky]}, score ${h.score}%`,
      `Clouds block ${h.cloud_blocking}% of the sky (low ${h.cloud_low}%, mid ${h.cloud_mid}%, high ${h.cloud_high}%)`,
      `Visibility ${h.visibility_km} km · humidity ${h.humidity}% · rain chance ${h.precip_probability}%`,
      `Sun ${h.sun_alt}° · Moon ${h.moon_alt > 0 ? `${h.moon_alt}° up` : "down"}`,
    ].join("\n");

    col.append(cell("div", best ? "Best" : "", "tl-best"));
    col.append(cell("div", timeIn(h.time, tz).slice(0, 2), "tl-time"));
    const sky = cell("div", "", `tl-sky sky-${h.dark ? h.sky : "light"}`);
    sky.append(cell("span", h.dark ? SKY_WORDS[h.sky] : h.sun_alt > 0 ? "Daylight" : "Twilight", "tl-word"));
    sky.append(cell("span", `${h.cloud_blocking}% cloud`, "tl-cloud"));
    col.append(sky);

    const meter = cell("div", "", "tl-meter");
    const fill = cell("div", "", "tl-fill");
    fill.style.height = `${h.score}%`;
    meter.append(fill);
    col.append(meter);
    col.append(cell("div", h.dark ? `${h.score}%` : "–", "tl-score"));
    els.timeline.append(col);
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

// Sequential blue ramp, dark (poor) to light (good), steps 600 → 200 of the reference blue.
const SCORE_RAMP = ["#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5", "#5598e7", "#6da7ec", "#86b6ef", "#9ec5f4"];
const rampIndex = (score) => Math.min(SCORE_RAMP.length - 1, Math.floor((score / 100) * SCORE_RAMP.length));

function limitWords(h) {
  if (h.limit === "too_low") return h.alt < 0 ? "below the horizon" : "too low (under 10°)";
  return { too_bright: "the sky is too bright", clouds: "clouds", moonlight: "moonlight" }[h.limit];
}

// One row per body, one column per hour of tonight, shaded by how well it can be seen.
function renderWhenGrid(data, tz) {
  const hours = data.bodies[0].hours;
  els.whenPanel.hidden = !hours.length;
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
    renderNightQuality(data);
    renderTimeline(data, tz);
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
  els.status.hidden = true;
  els.sky.hidden = false;

  if (planets.status === "fulfilled") {
    renderPlanets(planets.value, tz);
    renderWhenGrid(planets.value, tz);
    els.planetsStatus.hidden = true;
  } else {
    els.planets.replaceChildren();
    els.whenPanel.hidden = true;
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
