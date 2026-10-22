#include "apis/NasaApod.hpp"

#include <cctype>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <optional>
#include <regex>
#include <stdexcept>

#include "http/HttpClient.hpp"

using nlohmann::json;

namespace {

// APOD days follow US Eastern time. UTC-5 is close enough: during daylight
// saving it is off by an hour, which at worst asks for yesterday's picture.
std::string nasaToday() {
    std::time_t t = std::time(nullptr) - 5 * 3600;
    std::tm tm{};
    gmtime_r(&t, &tm);
    char buf[11];
    std::strftime(buf, sizeof buf, "%Y-%m-%d", &tm);
    return buf;
}

// "2026-10-22" -> "https://apod.nasa.gov/apod/ap261022.html"
std::string pageUrl(const std::string& date) {
    if (date.size() != 10) return "https://apod.nasa.gov/apod/astropix.html";
    return "https://apod.nasa.gov/apod/ap" + date.substr(2, 2) + date.substr(5, 2) +
           date.substr(8, 2) + ".html";
}

// Decodes the HTML entities that appear in NASA's pages (&amp;, &#8217;, ...).
std::string decodeEntities(const std::string& in) {
    std::string out;
    for (size_t i = 0; i < in.size(); ++i) {
        auto semi = in.find(';', i);
        if (in[i] != '&' || semi == std::string::npos || semi - i > 8) {
            out += in[i];
            continue;
        }
        std::string ent = in.substr(i + 1, semi - i - 1);
        unsigned long cp = 0;
        if (ent == "amp") cp = '&';
        else if (ent == "quot") cp = '"';
        else if (ent == "lt") cp = '<';
        else if (ent == "gt") cp = '>';
        else if (ent == "nbsp") cp = ' ';
        else if (ent.size() > 1 && ent[0] == '#') cp = std::strtoul(ent.c_str() + 1, nullptr, 10);
        if (cp == 0) {
            out += in[i];
            continue;
        }
        // Encode the code point as UTF-8.
        if (cp < 0x80) {
            out += char(cp);
        } else if (cp < 0x800) {
            out += char(0xC0 | (cp >> 6));
            out += char(0x80 | (cp & 0x3F));
        } else {
            out += char(0xE0 | (cp >> 12));
            out += char(0x80 | ((cp >> 6) & 0x3F));
            out += char(0x80 | (cp & 0x3F));
        }
        i = semi;
    }
    return out;
}

// Removes HTML tags, decodes entities and collapses whitespace.
std::string htmlToText(const std::string& html) {
    std::string text;
    bool inTag = false, lastSpace = true;
    for (char c : html) {
        if (c == '<') {
            inTag = true;
        } else if (c == '>') {
            inTag = false;
        } else if (!inTag) {
            bool space = std::isspace(static_cast<unsigned char>(c));
            if (space && lastSpace) continue;
            // Markup like "<a>parties</a> ." leaves a space before punctuation.
            if (std::strchr(",.;:!?)", c) && !text.empty() && text.back() == ' ') text.pop_back();
            text += space ? ' ' : c;
            lastSpace = space;
        }
    }
    while (!text.empty() && text.back() == ' ') text.pop_back();
    return decodeEntities(text);
}

// Returns the text between `open` and the next `close` after it, or "".
std::string between(const std::string& html, const std::string& open, const std::string& close,
                    size_t from = 0) {
    auto start = html.find(open, from);
    if (start == std::string::npos) return "";
    start += open.size();
    auto end = html.find(close, start);
    if (end == std::string::npos) return "";
    return html.substr(start, end - start);
}

// Returns the content of <meta property="NAME" content="...">, or "".
std::string metaContent(const std::string& html, const std::string& name) {
    return decodeEntities(between(html, "property=\"" + name + "\" content=\"", "\""));
}

bool isArticle(const std::string& page) {
    return metaContent(page, "og:title").rfind("APOD:", 0) == 0;
}

// "APOD: 2025 June 1 - UGC 1810: Wildly Interacting Galaxy - NASA Science" -> "UGC 1810: Wildly Interacting Galaxy"
std::string cleanTitle(std::string title) {
    const std::string suffix = " - NASA Science";
    if (title.size() > suffix.size() &&
        title.compare(title.size() - suffix.size(), suffix.size(), suffix) == 0) {
        title.erase(title.size() - suffix.size());
    }
    auto dash = title.find(" - ");
    if (title.rfind("APOD:", 0) == 0 && dash != std::string::npos) title.erase(0, dash + 3);
    return title;
}

struct Article {
    std::string title, image, explanation, credit;
};

Article parseArticle(const std::string& page) {
    Article a;
    a.title = cleanTitle(metaContent(page, "og:title"));
    a.image = metaContent(page, "og:image");
    // The explanation paragraph uses <br><br> between paragraphs and ends with a
    // "Tomorrow's picture" teaser, which belongs to the next day.
    std::string body = between(page, "<strong>Explanation:</strong>", "</p>");
    body = body.substr(0, body.find("<strong>Tomorrow"));
    for (size_t pos = 0, next; pos < body.size(); pos = next + 8) {
        next = body.find("<br><br>", pos);
        if (next == std::string::npos) next = body.size();
        std::string para = htmlToText(body.substr(pos, next - pos));
        if (para.empty()) continue;
        if (!a.explanation.empty()) a.explanation += "\n\n";
        a.explanation += para;
    }
    // <th>Credit &amp; Copyright:</th> <td>...</td>  (label wording varies, e.g. "Image Credit:")
    auto meta = page.find("media-detail-hero__meta-row");
    auto label = meta == std::string::npos ? meta : page.find("Credit", meta);
    if (label != std::string::npos) {
        auto cell = page.find("<td", label);
        if (cell != std::string::npos) a.credit = htmlToText(between(page, ">", "</td>", cell));
    }
    // Some cells repeat the label ("Image Credit: NASA, JPL"); drop it.
    auto colon = a.credit.find("Credit");
    if (colon != std::string::npos && (colon = a.credit.find(':', colon)) != std::string::npos && colon < 40) {
        a.credit.erase(0, colon + 1);
        if (!a.credit.empty() && a.credit[0] == ' ') a.credit.erase(0, 1);
    }
    return a;
}

// APOD moved to science.nasa.gov and NASA's API can no longer read it: it
// returns a placeholder image and another day's explanation. Recover the real
// data from the article page instead. Old apod.nasa.gov URLs redirect to the
// article for most days; for the newest days they redirect to the APOD index,
// which links to the article.
std::optional<Article> recoverFromWebsite(const std::string& date) {
    static const char* months[] = {"january", "february", "march",     "april",   "may",      "june",
                                   "july",    "august",   "september", "october", "november", "december"};
    try {
        auto page = httpGet(pageUrl(date)).body;
        if (!isArticle(page)) {
            int month = std::stoi(date.substr(5, 2));
            int day = std::stoi(date.substr(8, 2));
            std::string slug = "image-article/apod-" + date.substr(0, 4) + "-" + months[month - 1] + "-" +
                               std::to_string(day) + "-";
            auto pos = page.find(slug);
            if (pos == std::string::npos) return std::nullopt;
            auto end = page.find('"', pos);
            page = httpGet("https://science.nasa.gov/" + page.substr(pos, end - pos)).body;
            if (!isArticle(page)) return std::nullopt;
        }
        auto article = parseArticle(page);
        if (article.image.empty()) return std::nullopt;
        return article;
    } catch (const std::exception&) {
        return std::nullopt;  // best effort: the caller reports the picture as missing
    }
}

}  // namespace

NasaApod::NasaApod(std::string apiKey)
    : apiKey_(std::move(apiKey)), pastCache_(std::chrono::hours(24)), todayCache_(std::chrono::hours(1)) {}

json NasaApod::fetch(const std::string& date) {
    static const std::regex datePattern(R"(\d{4}-\d{2}-\d{2})");
    if (!date.empty() && !std::regex_match(date, datePattern)) {
        throw std::invalid_argument("date must be YYYY-MM-DD");
    }

    // Today's entry can still change (NASA sometimes publishes it late or broken), so cache it briefly.
    bool isToday = date.empty() || date == nasaToday();
    auto& cache = isToday ? todayCache_ : pastCache_;
    std::string key = isToday ? "today" : date;
    if (auto cached = cache.get(key)) return *cached;

    json out;
    if (date.empty()) {
        try {
            out = request("");
        } catch (const HttpError& e) {
            // The date-less endpoint fails outright when NASA's scraper chokes; the dated one often still works.
            if (e.status < 500) throw;
            out = request(nasaToday());
        }
    } else {
        out = request(date);
    }

    cache.put(key, out);
    return out;
}

json NasaApod::request(const std::string& date) {
    std::string url = "https://api.nasa.gov/planetary/apod?thumbs=true&api_key=" + apiKey_;
    if (!date.empty()) url += "&date=" + date;

    auto res = httpGet(url);
    auto body = json::parse(res.body, nullptr, /*allow_exceptions=*/false);
    if (res.status != 200 || !body.is_object()) {
        // NASA error bodies look like {"code":400,"msg":"..."}.
        std::string msg = "NASA API returned HTTP " + std::to_string(res.status);
        if (body.is_object() && body.contains("msg")) msg = body["msg"].get<std::string>();
        throw HttpError(res.status, msg);
    }

    std::string actualDate = body.value("date", date);
    json out = {
        {"date", actualDate},
        {"title", body.value("title", "")},
        {"explanation", body.value("explanation", "")},
        {"media_type", body.value("media_type", "image")},
        {"url", body.value("url", "")},
        {"hdurl", body.value("hdurl", "")},
        {"thumbnail_url", body.value("thumbnail_url", "")},
        {"copyright", body.value("copyright", "")},
        {"page_url", pageUrl(actualDate)},
        {"media_missing", false},
    };

    // When NASA can't parse the day's page it substitutes its logo, and the
    // explanation it returns belongs to another day, so neither can be trusted.
    if (out["url"].get<std::string>().find("nasa-logo") != std::string::npos) {
        out["hdurl"] = "";
        out["thumbnail_url"] = "";
        out["media_type"] = "image";  // og:image is a still even on video days
        if (auto article = recoverFromWebsite(actualDate)) {
            out["title"] = article->title;
            out["url"] = article->image;
            out["explanation"] = article->explanation;
            out["copyright"] = article->credit;
        } else {
            out["title"] = "Astronomy Picture of the Day";
            out["url"] = "";
            out["explanation"] = "";
            out["copyright"] = "";
            out["media_missing"] = true;
        }
    }
    return out;
}
