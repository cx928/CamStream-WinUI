# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CamStream is a Python/PyQt6 Windows desktop application that turns any camera into an RTSP streaming source. It manages FFmpeg (encoding) and MediaMTX (RTSP server) as child processes, connecting camera input to network-accessible RTSP streams.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py

# Split large packages for Git (utility, not part of app)
python split_packages.py --force
```

There are no automated tests, linters, or CI pipelines.

## Architecture

**Streaming pipeline:** Camera (DirectShow) -> FFmpeg (H.264/H.265 encoding) -> MediaMTX (RTSP server at port 8554) -> Clients (VLC, ffplay, etc.)

**Two capture modes:**
- **High-performance (default):** FFmpeg captures directly from DirectShow device (`-f dshow`), no Python pipe overhead
- **Pipe mode (fallback):** OpenCV reads frames, pushes BGR24 raw data to FFmpeg stdin via a `queue.Queue(maxsize=15)`

**Key source files in `src/`:**
- `main_window.py` — PyQt6 GUI, `CaptureThread`, install workers. This is the largest file (~35KB) containing the main application logic
- `rtsp_sender.py` — `StreamConfig` dataclass and `RtspSender` class that builds/manages the FFmpeg subprocess
- `mediamtx_server.py` — MediaMTX lifecycle, port auto-selection (8554 -> 18554 -> 28554 -> 38554), firewall rules, YAML config generation
- `camera.py` — Camera enumeration via pygrabber + OpenCV fallback
- `audio.py` — Audio device enumeration by parsing FFmpeg DirectShow output
- `ffmpeg_installer.py` — Auto-download/install FFmpeg; supports split zip files from `packages/`
- `config.py` — JSON config at `%APPDATA%\CamStream\config.json` for FFmpeg path persistence
- `packages_utils.py` — Merges split zip files (.zip.001, .002, .003) at runtime

**Threading model:** Background threads for camera capture, FFmpeg stderr reading, and frame pushing. PyQt signals (`StreamErrorSignal`, `LogSignal`, `frame_ready`) for thread-safe communication to the GUI thread.

**External binaries** (auto-installed to `%LOCALAPPDATA%\CamStream\`):
- FFmpeg — bundled as split zips in `packages/` or downloaded from gyan.dev
- MediaMTX v1.16.2 — bundled or downloaded from GitHub releases

## Platform Constraints

Windows-only. Uses DirectShow for device enumeration, `ctypes.windll` for admin checks, `netsh` for firewall rules. Not portable to macOS/Linux without significant changes.

## Git Rules

Do not execute `git commit` or `git push` unless the user explicitly requests it (e.g., "commit", "push", "提交").
