#include "zb/file_windows.h"

#include <fcntl.h>
#include <unistd.h>

#include <atomic>
#include <cerrno>
#include <mutex>
#include <unordered_map>

#include "zb/log.h"

namespace zb {

namespace {

struct Registration {
    std::string backing;
    FileWindow window;
};

std::mutex g_mutex;
std::unordered_map<std::string, Registration> g_paths;  // guarded by g_mutex
std::unordered_map<int, FileWindow> g_fds;              // guarded by g_mutex
// Set once anything is registered: until then every fd lookup is one relaxed load.
std::atomic<bool> g_any{false};

}  // namespace

void register_file_window(const std::string& guest_path, const std::string& backing_path,
                          std::uint64_t offset, std::uint64_t length) {
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        g_paths[guest_path] = Registration{backing_path, FileWindow{offset, length}};
    }
    g_any.store(true, std::memory_order_release);
    log("file window: %s -> %s @%llu +%llu", guest_path.c_str(), backing_path.c_str(),
        static_cast<unsigned long long>(offset), static_cast<unsigned long long>(length));
}

bool open_file_window(const char* guest_path, int flags, std::int32_t& result) {
    if (guest_path == nullptr || !g_any.load(std::memory_order_acquire)) return false;
    Registration found;
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        const auto it = g_paths.find(guest_path);
        if (it == g_paths.end()) return false;
        found = it->second;
    }
    if ((flags & O_ACCMODE) != O_RDONLY || (flags & (O_TRUNC | O_CREAT)) != 0) {
        result = -EROFS;  // the data lives inside a signed APK
        return true;
    }
    // Guest flags are arm32 values; O_CLOEXEC and O_NONBLOCK are the same bits on arm64, the
    // rest (O_LARGEFILE, O_DIRECTORY...) differ or do not apply to a read-only window.
    const int fd = ::open(found.backing.c_str(), O_RDONLY | (flags & (O_CLOEXEC | O_NONBLOCK)));
    if (fd < 0) {
        result = -errno;
        log("file window: cannot open %s for %s: errno %d", found.backing.c_str(), guest_path, errno);
        return true;
    }
    if (::lseek(fd, static_cast<off_t>(found.window.offset), SEEK_SET) < 0) {
        result = -errno;
        ::close(fd);
        return true;
    }
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        g_fds[fd] = found.window;
    }
    result = fd;
    return true;
}

std::optional<FileWindow> file_window_for(int fd) {
    if (!g_any.load(std::memory_order_acquire)) return std::nullopt;
    std::lock_guard<std::mutex> lock(g_mutex);
    const auto it = g_fds.find(fd);
    if (it == g_fds.end()) return std::nullopt;
    return it->second;
}

void forget_file_window(int fd) {
    if (!g_any.load(std::memory_order_acquire)) return;
    std::lock_guard<std::mutex> lock(g_mutex);
    g_fds.erase(fd);
}

void copy_file_window(int from, int to) {
    if (!g_any.load(std::memory_order_acquire) || from == to) return;
    std::lock_guard<std::mutex> lock(g_mutex);
    const auto it = g_fds.find(from);
    if (it == g_fds.end()) {
        g_fds.erase(to);  // dup2 onto a windowed fd replaces it with an ordinary one
    } else {
        g_fds[to] = it->second;
    }
}

}  // namespace zb
