#include "http/HttpClient.hpp"

#include <httplib.h>

#include <cctype>

HttpResponse httpGet(const std::string& url) {
    // Split "https://host[:port]/path?query" into origin and path.
    auto schemeEnd = url.find("://");
    if (schemeEnd == std::string::npos) throw HttpError(0, "bad url: " + url);
    auto pathStart = url.find('/', schemeEnd + 3);
    std::string origin = url.substr(0, pathStart);
    std::string path = pathStart == std::string::npos ? "/" : url.substr(pathStart);

    httplib::Client client(origin);
    client.set_connection_timeout(10);
    client.set_read_timeout(20);
    client.set_follow_location(true);
    client.set_default_headers({{"User-Agent", "SkyWatch/0.1 (school project)"}});

    auto res = client.Get(path);
    if (!res) {
        throw HttpError(0, "request to " + origin + " failed: " + httplib::to_string(res.error()));
    }
    return {res->status, res->body};
}

std::string urlEncode(const std::string& s) {
    static const char* hex = "0123456789ABCDEF";
    std::string out;
    for (unsigned char c : s) {
        if (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
            out += char(c);
        } else {
            out += '%';
            out += hex[c >> 4];
            out += hex[c & 15];
        }
    }
    return out;
}
