"""NASA Astronomy Picture of the Day: https://api.nasa.gov/"""

import re
import time
from dataclasses import dataclass

from skywatch.http.cache import Cache
from skywatch.http.client import HttpError, http_get, parse_json

_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_MONTHS = ("january", "february", "march", "april", "may", "june",
           "july", "august", "september", "october", "november", "december")  # fmt: skip
_ENTITIES = {"amp": "&", "quot": '"', "lt": "<", "gt": ">", "nbsp": " "}


def _nasa_today() -> str:
    """APOD days follow US Eastern time. UTC-5 is close enough: during daylight
    saving it is off by an hour, which at worst asks for yesterday's picture."""
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 5 * 3600))


def _page_url(date: str) -> str:
    """"2026-10-22" -> "https://apod.nasa.gov/apod/ap261022.html" """
    if len(date) != 10:
        return "https://apod.nasa.gov/apod/astropix.html"
    return f"https://apod.nasa.gov/apod/ap{date[2:4]}{date[5:7]}{date[8:10]}.html"


def _decode_entities(s: str) -> str:
    """Decodes the HTML entities that appear in NASA's pages (&amp;, &#8217;, ...)."""

    def replace(m: re.Match) -> str:
        ent = m.group(1)
        if ent in _ENTITIES:
            return _ENTITIES[ent]
        if len(ent) > 1 and ent[0] == "#" and ent[1:].isdigit():
            cp = int(ent[1:])
            if 0 < cp < 0x110000:
                return chr(cp)
        return m.group(0)

    # Up to 7 characters between '&' and ';', like the C++ version.
    return re.sub(r"&([^;&]{0,7});", replace, s)


def _html_to_text(html: str) -> str:
    """Removes HTML tags, decodes entities and collapses whitespace."""
    text: list[str] = []
    in_tag = False
    last_space = True
    for c in html:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            space = c in " \t\n\r\f\v"
            if space and last_space:
                continue
            # Markup like "<a>parties</a> ." leaves a space before punctuation.
            if c in ",.;:!?)" and text and text[-1] == " ":
                text.pop()
            text.append(" " if space else c)
            last_space = space
    return _decode_entities("".join(text).rstrip(" "))


def _between(html: str, open_: str, close: str, start: int = 0) -> str:
    """The text between `open_` and the next `close` after it, or ""."""
    a = html.find(open_, start)
    if a < 0:
        return ""
    a += len(open_)
    b = html.find(close, a)
    return "" if b < 0 else html[a:b]


def _meta_content(html: str, name: str) -> str:
    """The content of <meta property="NAME" content="...">, or ""."""
    return _decode_entities(_between(html, f'property="{name}" content="', '"'))


def _is_article(page: str) -> bool:
    return _meta_content(page, "og:title").startswith("APOD:")


def _clean_title(title: str) -> str:
    """"APOD: 2025 June 1 - UGC 1810: Wildly Interacting Galaxy - NASA Science"
    -> "UGC 1810: Wildly Interacting Galaxy" """
    suffix = " - NASA Science"
    if len(title) > len(suffix) and title.endswith(suffix):
        title = title[: -len(suffix)]
    dash = title.find(" - ")
    if title.startswith("APOD:") and dash >= 0:
        title = title[dash + 3 :]
    return title


@dataclass
class _Article:
    title: str = ""
    image: str = ""
    explanation: str = ""
    credit: str = ""


def _parse_article(page: str) -> _Article:
    a = _Article(title=_clean_title(_meta_content(page, "og:title")), image=_meta_content(page, "og:image"))
    # The explanation paragraph uses <br><br> between paragraphs and ends with a
    # "Tomorrow's picture" teaser, which belongs to the next day.
    body = _between(page, "<strong>Explanation:</strong>", "</p>")
    body = body.split("<strong>Tomorrow", 1)[0]
    paragraphs = (_html_to_text(p) for p in body.split("<br><br>"))
    a.explanation = "\n\n".join(p for p in paragraphs if p)
    # <th>Credit &amp; Copyright:</th> <td>...</td>  (label wording varies, e.g. "Image Credit:")
    meta = page.find("media-detail-hero__meta-row")
    label = page.find("Credit", meta) if meta >= 0 else -1
    if label >= 0:
        cell = page.find("<td", label)
        if cell >= 0:
            a.credit = _html_to_text(_between(page, ">", "</td>", cell))
    # Some cells repeat the label ("Image Credit: NASA, JPL"); drop it.
    credit_at = a.credit.find("Credit")
    if credit_at >= 0:
        colon = a.credit.find(":", credit_at)
        if 0 <= colon < 40:
            a.credit = a.credit[colon + 1 :].removeprefix(" ")
    return a


def _recover_from_website(date: str) -> _Article | None:
    """APOD moved to science.nasa.gov and NASA's API can no longer read it: it
    returns a placeholder image and another day's explanation. Recover the real
    data from the article page instead. Old apod.nasa.gov URLs redirect to the
    article for most days; for the newest days they redirect to the APOD index,
    which links to the article."""
    try:
        page = http_get(_page_url(date)).body
        if not _is_article(page):
            month, day = int(date[5:7]), int(date[8:10])
            slug = f"image-article/apod-{date[:4]}-{_MONTHS[month - 1]}-{day}-"
            pos = page.find(slug)
            if pos < 0:
                return None
            end = page.find('"', pos)
            page = http_get("https://science.nasa.gov/" + page[pos : end if end >= 0 else len(page)]).body
            if not _is_article(page):
                return None
        article = _parse_article(page)
        return article if article.image else None
    except Exception:
        return None  # best effort: the caller reports the picture as missing


class NasaApod:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._past_cache = Cache(24 * 3600)
        self._today_cache = Cache(3600)

    def fetch(self, date: str) -> dict:
        """date is "YYYY-MM-DD", or empty for today. Returns the APOD fields the
        frontend uses. Raises ValueError for a malformed date and HttpError when
        NASA rejects the request."""
        if date and not _DATE_PATTERN.fullmatch(date):
            raise ValueError("date must be YYYY-MM-DD")

        # Today's entry can still change (NASA sometimes publishes it late or broken), so cache it briefly.
        is_today = not date or date == _nasa_today()
        cache = self._today_cache if is_today else self._past_cache
        key = "today" if is_today else date
        cached = cache.get(key)
        if cached is not None:
            return cached

        if not date:
            try:
                out = self._request("")
            except HttpError as e:
                # The date-less endpoint fails outright when NASA's scraper chokes; the dated one often still works.
                if e.status < 500:
                    raise
                out = self._request(_nasa_today())
        else:
            out = self._request(date)

        cache.put(key, out)
        return out

    def _request(self, date: str) -> dict:
        url = f"https://api.nasa.gov/planetary/apod?thumbs=true&api_key={self._api_key}"
        if date:
            url += f"&date={date}"

        res = http_get(url)
        body = parse_json(res.body)
        if res.status != 200 or not isinstance(body, dict):
            # NASA error bodies look like {"code":400,"msg":"..."}.
            msg = f"NASA API returned HTTP {res.status}"
            if isinstance(body, dict) and "msg" in body:
                msg = str(body["msg"])
            raise HttpError(res.status, msg)

        actual_date = body.get("date", date)
        out = {
            "date": actual_date,
            "title": body.get("title", ""),
            "explanation": body.get("explanation", ""),
            "media_type": body.get("media_type", "image"),
            "url": body.get("url", ""),
            "hdurl": body.get("hdurl", ""),
            "thumbnail_url": body.get("thumbnail_url", ""),
            "copyright": body.get("copyright", ""),
            "page_url": _page_url(actual_date),
            "media_missing": False,
        }

        # When NASA can't parse the day's page it substitutes its logo, and the
        # explanation it returns belongs to another day, so neither can be trusted.
        if "nasa-logo" in out["url"]:
            out["hdurl"] = ""
            out["thumbnail_url"] = ""
            out["media_type"] = "image"  # og:image is a still even on video days
            article = _recover_from_website(actual_date)
            if article:
                out["title"] = article.title
                out["url"] = article.image
                out["explanation"] = article.explanation
                out["copyright"] = article.credit
            else:
                out["title"] = "Astronomy Picture of the Day"
                out["url"] = ""
                out["explanation"] = ""
                out["copyright"] = ""
                out["media_missing"] = True
        return out
