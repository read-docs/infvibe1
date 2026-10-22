#pragma once

#include <stdexcept>
#include <string>

struct HttpError : std::runtime_error {
    int status;  // HTTP status, or 0 when the request never got a response
    HttpError(int status, const std::string& msg) : std::runtime_error(msg), status(status) {}
};

struct HttpResponse {
    int status;
    std::string body;
};

// Blocking GET over HTTP or HTTPS. Throws HttpError on network failure;
// non-2xx responses are returned so callers can read API error bodies.
HttpResponse httpGet(const std::string& url);

// Percent-encodes a string for use as a URL query parameter value.
std::string urlEncode(const std::string& s);
