// The sky dome: a circular chart of the whole sky as seen lying on your back,
// horizon at the edge and the zenith in the centre. North is at the top and
// east on the LEFT, the way a sky map is held up overhead.

const DOME_COLORS = {
  surface: "#120f22",
  ring: "#2c2840",
  label: "#a9a3b8",
  body: "#f4efe6",      // Moon and planets
  iss: "#d95926",       // categorical slot 2
  starlinkLit: "#199e70",  // categorical slot 3
  starlinkDark: "#4b5568",
};

function createSkyDome(canvas, tooltip) {
  const ctx = canvas.getContext("2d");
  let items = [];  // what was drawn, for hover hit-testing: {x, y, r, lines}
  let size = 0;

  function project(alt, az) {
    const R = size / 2 - 26, c = size / 2;
    const r = ((90 - Math.max(alt, 0)) / 90) * R;
    const a = (az * Math.PI) / 180;
    return [c - r * Math.sin(a), c - r * Math.cos(a)];
  }

  function dot(x, y, r, color) {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
  }

  let labelBoxes = [];  // labels drawn so far, to avoid overlaps

  // Labels go right of the dot, or left, or below, whichever doesn't hit an earlier label.
  function label(text, x, y, r, color) {
    ctx.font = "600 11px system-ui, sans-serif";
    ctx.textBaseline = "middle";
    const w = ctx.measureText(text).width, h = 12;
    const spots = [[x + r + 4, y], [x - r - 4 - w, y], [x - w / 2, y + r + 9]];
    const hits = (bx, by) => labelBoxes.some((b) => bx < b.x + b.w && bx + w > b.x && by - h / 2 < b.y + b.h / 2 && by + h / 2 > b.y - b.h / 2);
    const [lx, ly] = spots.find(([bx, by]) => !hits(bx, by)) || spots[0];
    labelBoxes.push({ x: lx, y: ly, w, h });
    ctx.fillStyle = color;
    ctx.textAlign = "left";
    ctx.fillText(text, lx, ly);
  }

  function draw(data) {
    size = Math.min(canvas.parentElement.clientWidth, 520);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);
    items = [];
    labelBoxes = [];

    const c = size / 2, R = size / 2 - 26;
    dot(c, c, R, DOME_COLORS.surface);
    ctx.strokeStyle = DOME_COLORS.ring;
    ctx.lineWidth = 1;
    for (const alt of [30, 60]) {
      ctx.beginPath();
      ctx.arc(c, c, ((90 - alt) / 90) * R, 0, 2 * Math.PI);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(c, c, R, 0, 2 * Math.PI);
    ctx.strokeStyle = DOME_COLORS.label;
    ctx.stroke();

    ctx.fillStyle = DOME_COLORS.label;
    ctx.font = "600 12px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const [text, az] of [["N", 0], ["E", 90], ["S", 180], ["W", 270]]) {
      const a = (az * Math.PI) / 180;
      ctx.fillText(text, c - (R + 14) * Math.sin(a), c - (R + 14) * Math.cos(a));
    }

    // Starlink first so the brighter objects sit on top.
    for (const s of data.starlink || []) {
      const [x, y] = project(s.alt, s.az);
      dot(x, y, s.sunlit ? 2.5 : 1.8, s.sunlit ? DOME_COLORS.starlinkLit : DOME_COLORS.starlinkDark);
      items.push({ x, y, r: 3, lines: [s.name, `${Math.round(s.alt)}° up, az ${Math.round(s.az)}°`,
        s.sunlit ? `Sunlit, about mag ${s.magnitude.toFixed(1)}${s.visible ? " (visible now)" : ""}` : "In Earth's shadow"] });
    }

    for (const b of data.bodies || []) {
      if (b.position.alt <= 0) continue;
      const [x, y] = project(b.position.alt, b.position.az);
      // Brighter objects get bigger dots: the Moon biggest, faint Uranus/Neptune smallest.
      const r = b.name === "Moon" ? 9 : Math.max(2.5, Math.min(6, 4 - b.magnitude * 0.6));
      dot(x, y, r + 2, DOME_COLORS.surface);  // ring so overlapping dots stay distinct
      dot(x, y, r, DOME_COLORS.body);
      label(b.name, x, y, r, DOME_COLORS.body);
      items.push({ x, y, r: r + 2, lines: [b.name, `${Math.round(b.position.alt)}° up, ${b.position.direction}`, `Magnitude ${b.magnitude}`] });
    }

    const iss = data.iss && data.iss.look;
    if (iss && iss.alt > 0) {
      const [x, y] = project(iss.alt, iss.az);
      dot(x, y, 7, DOME_COLORS.surface);
      dot(x, y, 5, DOME_COLORS.iss);
      label("ISS", x, y, 5, DOME_COLORS.iss);
      items.push({ x, y, r: 7, lines: ["ISS", `${Math.round(iss.alt)}° up, ${iss.direction}`, `${iss.range_km.toLocaleString("en")} km away`] });
    }
  }

  canvas.addEventListener("pointermove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    // Nearest item within a forgiving radius; tiny dots are hard to hit exactly.
    let best = null, bestD = 12;
    for (const it of items) {
      const d = Math.hypot(it.x - px, it.y - py) - it.r;
      if (d < bestD) { best = it; bestD = d; }
    }
    if (!best) { tooltip.hidden = true; return; }
    tooltip.replaceChildren();
    best.lines.forEach((line, i) => {
      const el = document.createElement(i === 0 ? "strong" : "div");
      el.textContent = line;
      tooltip.append(el);
    });
    tooltip.style.left = `${best.x + canvas.offsetLeft}px`;
    tooltip.style.top = `${best.y + canvas.offsetTop}px`;
    tooltip.style.transform = best.x > size / 2 ? "translate(calc(-100% - 12px), -50%)" : "translate(12px, -50%)";
    tooltip.hidden = false;
  });
  canvas.addEventListener("pointerleave", () => { tooltip.hidden = true; });

  return { draw };
}
