"""
配置管理：FFmpeg 路径等
"""
import os
import sys
import shutil
import json
from pathlib import Path


def _config_path() -> Path:
    """配置文件路径"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    else:
        base = Path.home() / ".config"
    return base / "CamStream" / "config.json"


def _ensure_config_dir():
    _config_path().parent.mkdir(parents=True, exist_ok=True)


def get_ffmpeg_path() -> str:
    """获取 FFmpeg 可执行文件路径，空字符串表示使用系统 PATH"""
    try:
        path = _config_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("ffmpeg_path", "") or ""
    except Exception:
        pass
    return ""


def set_ffmpeg_path(path: str):
    """保存 FFmpeg 路径"""
    _ensure_config_dir()
    try:
        data = {}
        p = _config_path()
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["ffmpeg_path"] = path.strip()
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def find_ffmpeg() -> str:
    """
    查找 FFmpeg 可执行文件。
    返回完整路径，若未找到返回空字符串。
    """
    # 1. 用户配置的路径
    cfg = get_ffmpeg_path()
    if cfg:
        p = Path(cfg)
        if p.is_file():
            return str(p.resolve())
        # 可能是目录，尝试 bin/ffmpeg.exe
        if p.is_dir():
            for exe in [
                p / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"),
                p / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"),
            ]:
                if exe.exists():
                    return str(exe.resolve())

    # 2. 系统 PATH
    found = shutil.which("ffmpeg")
    if found:
        return found

    # 3. Windows 常见安装位置（含本工具自动安装的路径）
    if sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            local_app_data / "CamStream" / "ffmpeg" / "bin" / "ffmpeg.exe",  # 本工具自动安装
            Path("C:/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/Program Files (x86)/ffmpeg/bin/ffmpeg.exe"),
            local_app_data / "ffmpeg/bin/ffmpeg.exe",
            Path(__file__).resolve().parent.parent / "ffmpeg/bin/ffmpeg.exe",  # 项目目录
        ]
        for c in candidates:
            if c and c.exists():
                return str(c.resolve())

    return ""
