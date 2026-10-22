#pragma once

#include <chrono>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>

// Thread-safe in-memory cache where every entry expires after a fixed TTL.
// The HTTP server handles requests on several threads, so access is locked.
template <typename Value>
class Cache {
public:
    explicit Cache(std::chrono::seconds ttl) : ttl_(ttl) {}

    std::optional<Value> get(const std::string& key) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = entries_.find(key);
        if (it == entries_.end()) return std::nullopt;
        if (Clock::now() > it->second.expires) {
            entries_.erase(it);
            return std::nullopt;
        }
        return it->second.value;
    }

    void put(const std::string& key, Value value) {
        std::lock_guard<std::mutex> lock(mutex_);
        entries_[key] = {std::move(value), Clock::now() + ttl_};
    }

private:
    using Clock = std::chrono::steady_clock;
    struct Entry {
        Value value;
        Clock::time_point expires;
    };

    std::chrono::seconds ttl_;
    std::mutex mutex_;
    std::unordered_map<std::string, Entry> entries_;
};
