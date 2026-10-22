const els = {
  date: document.getElementById("date"),
  prev: document.getElementById("prev"),
  next: document.getElementById("next"),
  today: document.getElementById("today"),
  status: document.getElementById("status"),
  apod: document.getElementById("apod"),
  media: document.getElementById("media"),
  title: document.getElementById("title"),
  meta: document.getElementById("meta"),
  explanation: document.getElementById("explanation"),
  source: document.getElementById("source"),
};

const FIRST_DATE = "1995-06-16";
const todayStr = isoDate(new Date());
els.date.max = todayStr;

function shiftDate(dateStr, days) {
  const d = new Date(dateStr + "T12:00:00");
  d.setDate(d.getDate() + days);
  return isoDate(d);
}

function showStatus(text, isError = false, isLoading = false) {
  els.status.textContent = text;
  els.status.className = isError ? "status error" : isLoading ? "status loading" : "status";
  els.status.hidden = false;
  els.apod.hidden = true;
}

function renderMedia(data) {
  els.media.replaceChildren();
  if (data.media_missing) {
    const note = document.createElement("p");
    note.className = "apod-missing";
    note.append("NASA's API couldn't load this day's picture. ");
    const link = document.createElement("a");
    link.href = data.page_url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "See it on apod.nasa.gov";
    note.append(link, ".");
    els.media.append(note);
  } else if (data.media_type === "video" && data.url) {
    const frame = document.createElement("iframe");
    frame.src = data.url;
    frame.allowFullscreen = true;
    els.media.append(frame);
  } else if (data.url || data.thumbnail_url) {
    const link = document.createElement("a");
    link.href = data.hdurl || data.url;
    link.target = "_blank";
    link.rel = "noopener";
    const img = document.createElement("img");
    img.src = data.url || data.thumbnail_url;
    img.alt = data.title;
    link.append(img);
    els.media.append(link);
  }
}

async function load(dateStr) {
  els.date.value = dateStr;
  els.prev.disabled = dateStr <= FIRST_DATE;
  els.next.disabled = dateStr >= todayStr;
  history.replaceState(null, "", `?date=${dateStr}`);
  showStatus("Loading…", false, true);

  try {
    // Ask for "today" without a date so NASA decides, since its day may not have rolled over yet.
    const data = await fetchJson(dateStr === todayStr ? "/api/apod" : `/api/apod?date=${dateStr}`);
    renderMedia(data);
    els.title.textContent = data.title;
    els.meta.textContent = [data.date, data.copyright && `Credit: ${data.copyright.trim()}`]
      .filter(Boolean)
      .join(" · ");
    els.explanation.textContent = data.explanation;
    els.source.href = data.page_url;
    els.status.hidden = true;
    els.apod.hidden = false;
  } catch (err) {
    showStatus(err.message, true);
  }
}

els.prev.addEventListener("click", () => load(shiftDate(els.date.value, -1)));
els.next.addEventListener("click", () => load(shiftDate(els.date.value, 1)));
els.today.addEventListener("click", () => load(todayStr));
els.date.addEventListener("change", () => els.date.value && load(els.date.value));

const requested = new URLSearchParams(location.search).get("date");
load(requested && requested >= FIRST_DATE && requested <= todayStr ? requested : todayStr);
