#pragma once

#include <cstdint>
#include <optional>
#include <string>

namespace zb {

// File windows: a guest path served from a byte range of another host file, read-only, so a
// guest can read data that lives inside an APK without a copy on disk. The single-game build
// uses it for the game's OBB, which is stored uncompressed in the launcher APK: the guest opens
// the OBB path it expects, and gets the APK with its offsets shifted and its size cut to the
// entry.
//
// A guest descriptor opened through a window keeps the host file's own file offset, positioned
// inside the range; read/pread/readv/lseek/fstat/mmap on it are translated by the syscall layer
// (core/src/syscalls.cpp), and dup/close keep the table in step.
struct FileWindow {
    std::uint64_t offset = 0;  // where the guest's byte 0 lives in the backing file
    std::uint64_t length = 0;  // the guest-visible file size
};

// Registers `guest_path` (absolute, exact match) as a window into [offset, offset + length) of
// `backing_path`. Replaces an earlier registration of the same path.
void register_file_window(const std::string& guest_path, const std::string& backing_path,
                          std::uint64_t offset, std::uint64_t length);

// openat of a windowed path. Returns false when `guest_path` is not windowed; otherwise fills
// `result` with the new descriptor or a negative errno (writes are refused with -EROFS).
bool open_file_window(const char* guest_path, int flags, std::int32_t& result);

// The window behind a host descriptor, if it was opened through one. Cheap when no window is
// registered at all, which is every guest but a bundled game.
std::optional<FileWindow> file_window_for(int fd);

// Keep the descriptor table in step with close and dup.
void forget_file_window(int fd);
void copy_file_window(int from, int to);

}  // namespace zb
