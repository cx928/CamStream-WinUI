"""
MediaMTX RTSP 服务器：优先从项目 packages 解压安装，无则联网下载。
支持完整 zip 或分割文件（.zip.001, .zip.002 ...）。
"""
import os
import sys
import zipfile
import urllib.request
import subprocess
from pathlib import Path
from typing import Optional, Callable

from .packages_utils import resolve_zip_path

MEDIAMTX_VERSION = "1.16.2"
MEDIAMTX_ZIP_NAME = f"mediamtx_v{MEDIAMTX_VERSION}_windows_amd64.zip"
MEDIAMTX_DOWNLOAD_URL = (
    f"https://github.com/bluenviron/mediamtx/releases/download/v{MEDIAMTX_VERSION}/{MEDIAMTX_ZIP_NAME}"
)
MEDIAMTX_LOCAL_NAMES = [
    MEDIAMTX_ZIP_NAME,
    f"mediamtx_v{MEDIAMTX_VERSION}_windows_amd64.zip",
    "mediamtx.zip",
]


def _packages_dir() -> Path:
    """项目 packages 目录"""
    return Path(__file__).resolve().parent.parent / "packages"


def _local_mediamtx_zip(temp_dir: Optional[Path] = None) -> tuple[Optional[Path], bool]:
    """
    查找本地 MediaMTX 安装包（完整 zip 或分割文件）。
    返回 (zip_path, is_temp)，is_temp 表示由分割文件合并的临时文件，需调用方清理。
    """
    return resolve_zip_path(_packages_dir(), MEDIAMTX_LOCAL_NAMES, temp_dir)


def _install_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")))
    else:
        base = Path.home() / ".local"
    return base / "CamStream" / "mediamtx"


def get_mediamtx_path() -> Optional[Path]:
    """获取 MediaMTX 可执行文件路径"""
    install_path = _install_dir()
    exe = install_path / "mediamtx.exe"
    if exe.exists():
        return exe
    return None


def download_mediamtx(
    on_progress: Optional[Callable[[int, int], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> Optional[Path]:
    """安装 MediaMTX：优先从 packages 解压，无则联网下载"""
    log = on_log or (lambda _: None)
    install_path = _install_dir()
    exe = install_path / "mediamtx.exe"
    if exe.exists():
        log(f"MediaMTX 已存在: {exe}")
        return exe

    temp_dir = install_path.parent / "mediamtx_download"
    zip_path, zip_is_temp = _local_mediamtx_zip(temp_dir)
    if zip_path:
        log(f"使用本地安装包: {zip_path}")
    else:
        temp_dir.mkdir(parents=True, exist_ok=True)
        zip_path = temp_dir / "mediamtx.zip"
        try:
            log("正在下载 MediaMTX（约 20MB）...")
            req = urllib.request.Request(MEDIAMTX_DOWNLOAD_URL, headers={"User-Agent": "CamStream/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 64 * 1024
                with open(zip_path, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress and total:
                            on_progress(downloaded, total)
        except Exception as e:
            log(f"下载失败: {e}")
            return None

    try:
        if not zip_path or not zip_path.exists():
            log("未找到 MediaMTX 安装包，请将安装包放置到 packages/ 目录")
            return None
        log("正在解压...")
        install_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(install_path)

        if exe.exists():
            log(f"MediaMTX 安装完成: {exe}")
            return exe
        log("解压后未找到 mediamtx.exe")
        return None
    except Exception as e:
        log(f"MediaMTX 安装失败: {e}")
        return None
    finally:
        if zip_path and zip_path.exists() and zip_path.parent == temp_dir:
            try:
                zip_path.unlink()
            except Exception:
                pass
        if temp_dir.exists():
            try:
                for f in temp_dir.iterdir():
                    f.unlink()
                temp_dir.rmdir()
            except Exception:
                pass


RTSP_DEFAULT_PORT = 8554
RTSP_FALLBACK_PORTS = [8554, 18554, 28554, 38554]
FIREWALL_RULE_NAME = "CamStream RTSP"

# 运行时实际使用的端口（start_mediamtx 启动后设置）
_active_rtsp_port = RTSP_DEFAULT_PORT


def get_rtsp_port() -> int:
    """获取当前 MediaMTX 实际使用的 RTSP 端口"""
    return _active_rtsp_port


def _ensure_firewall_rule(port: int, log: Optional[Callable[[str], None]] = None) -> bool:
    """
    Windows 防火墙：放行 RTSP 端口（TCP+UDP），便于局域网设备拉流。
    需要管理员权限，失败时静默继续（用户可手动放行）。
    """
    if sys.platform != "win32":
        return False
    log_fn = log or (lambda _: None)
    cflags = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={FIREWALL_RULE_NAME}"],
            capture_output=True, creationflags=cflags, timeout=5,
        )
        ok = True
        for proto in ("TCP", "UDP"):
            r = subprocess.run(
                [
                    "netsh", "advfirewall", "firewall", "add", "rule",
                    f"name={FIREWALL_RULE_NAME}",
                    "dir=in", "action=allow",
                    f"protocol={proto}",
                    f"localport={port}",
                ],
                capture_output=True, creationflags=cflags, timeout=5,
            )
            if r.returncode != 0:
                ok = False
        if ok:
            log_fn(f"防火墙已放行 RTSP 端口 {port}（TCP+UDP，局域网可拉流）")
        return ok
    except Exception:
        return False


_CAMSTREAM_CONFIG_MARKER = "# CamStream managed config"


def _ensure_config(install_dir: Path, port: int = RTSP_DEFAULT_PORT) -> None:
    """
    写入 CamStream 专用配置：仅启用 RTSP，禁用 WebRTC/HLS/RTMP/SRT 等，
    避免端口冲突导致 MediaMTX 启动失败。
    每次启动都重写，确保端口正确。
    """
    config_path = install_dir / "mediamtx.yml"
    try:
        config_path.write_text(
            f"{_CAMSTREAM_CONFIG_MARKER}\n"
            "logLevel: warn\n"
            "writeQueueSize: 1024\n"
            "rtsp: true\n"
            f"rtspAddress: :{port}\n"
            "rtspTransports: [udp, tcp]\n"
            "rtmp: false\n"
            "hls: false\n"
            "webrtc: false\n"
            "srt: false\n"
            "paths:\n"
            "  all_others:\n",
            encoding="utf-8",
        )
    except Exception:
        pass


def start_mediamtx(on_log: Optional[Callable[[str], None]] = None) -> Optional[subprocess.Popen]:
    """启动 MediaMTX 服务器，自动选择可用端口，返回进程对象"""
    global _active_rtsp_port
    exe = get_mediamtx_path()
    if not exe:
        return None
    log = on_log or (lambda _: None)
    install_dir = exe.parent

    import time

    for port in RTSP_FALLBACK_PORTS:
        if _is_port_occupied(port):
            continue
        _ensure_config(install_dir, port)
        try:
            proc = subprocess.Popen(
                [str(exe)],
                cwd=str(install_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            time.sleep(1.5)
            if proc.poll() is not None:
                stderr = ""
                try:
                    stderr = proc.stderr.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                log(f"端口 {port} 启动失败，尝试下一个...")
                continue
            _active_rtsp_port = port
            _ensure_firewall_rule(port, log)
            log(f"MediaMTX 已启动 (PID: {proc.pid})，RTSP 端口 {port}")
            return proc
        except Exception:
            continue

    log("MediaMTX 启动失败：所有候选端口均不可用")
    return None


def _is_port_occupied(port: int) -> bool:
    """检测端口是否已被其他程序监听（通过尝试连接）"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
        return True
    except (OSError, ConnectionRefusedError):
        return False
