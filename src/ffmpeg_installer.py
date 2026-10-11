"""
FFmpeg 自动安装：优先从项目 packages 目录解压，无则联网下载。
支持完整 zip 或分割文件（.zip.001, .zip.002 ...）。
"""
import os
import sys
import zipfile
import shutil
import urllib.request
from pathlib import Path
from typing import Optional, Callable

from .packages_utils import resolve_zip_path

FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_LOCAL_NAMES = ["ffmpeg-release-essentials.zip", "ffmpeg.zip"]


def _packages_dir() -> Path:
    """项目 packages 目录"""
    return Path(__file__).resolve().parent.parent / "packages"


def _local_ffmpeg_zip(temp_dir: Optional[Path] = None) -> tuple[Optional[Path], bool]:
    """
    查找本地 FFmpeg 安装包（完整 zip 或分割文件）。
    返回 (zip_path, is_temp)，is_temp 表示由分割文件合并的临时文件，需调用方清理。
    temp_dir: 合并分割文件时的输出目录，应与下载临时目录一致以便统一清理。
    """
    return resolve_zip_path(_packages_dir(), FFMPEG_LOCAL_NAMES, temp_dir)


def _install_dir() -> Path:
    """FFmpeg 安装目录"""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")))
    else:
        base = Path.home() / ".local"
    return base / "CamStream" / "ffmpeg"


def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def download_ffmpeg(
    on_progress: Optional[Callable[[int, int], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> Optional[Path]:
    """
    下载并安装 FFmpeg 到本地目录。
    返回 ffmpeg.exe 的完整路径，失败返回 None。
    """
    log = on_log or (lambda _: None)

    install_path = _install_dir()
    ffmpeg_exe = install_path / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if ffmpeg_exe.exists():
        log(f"FFmpeg 已存在于: {ffmpeg_exe}")
        return ffmpeg_exe

    temp_dir = install_path.parent / "ffmpeg_download"
    zip_path, zip_is_temp = _local_ffmpeg_zip(temp_dir)
    if zip_path:
        log(f"使用本地安装包: {zip_path}")
    else:
        _ensure_dir(temp_dir)
        zip_path = temp_dir / "ffmpeg.zip"
        try:
            log("正在下载 FFmpeg（约 70MB），请稍候...")
            req = urllib.request.Request(FFMPEG_DOWNLOAD_URL, headers={"User-Agent": "CamStream/1.0"})
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
        except urllib.error.URLError as e:
            log(f"下载失败: {e}")
            return None
        except Exception as e:
            log(f"下载失败: {e}")
            return None

    extract_to = install_path.parent / "ffmpeg_extract"
    try:
        if not zip_path or not zip_path.exists():
            log("未找到 FFmpeg 安装包，请将安装包放置到 packages/ 目录")
            return None
        log("正在解压...")
        _ensure_dir(extract_to)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_to)

        # 解压后结构: extract/ffmpeg-8.x-essentials_build/bin/ffmpeg.exe
        extracted_root = None
        for d in extract_to.iterdir():
            if d.is_dir():
                extracted_root = d
                break

        if not extracted_root:
            log("解压后目录结构异常")
            return None

        # 移动到标准安装位置
        if install_path.exists():
            shutil.rmtree(install_path)
        shutil.move(str(extracted_root), str(install_path))

        # 查找 ffmpeg.exe
        ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        bin_ffmpeg = install_path / "bin" / ffmpeg_name
        if bin_ffmpeg.exists():
            log(f"安装完成: {bin_ffmpeg}")
            return bin_ffmpeg

        for exe in install_path.rglob(ffmpeg_name):
            if exe.is_file():
                log(f"安装完成: {exe}")
                return exe

        log("解压后未找到 ffmpeg 可执行文件")
        return None

    except zipfile.BadZipFile as e:
        log(f"解压失败（文件可能损坏）: {e}")
        return None
    except Exception as e:
        log(f"安装失败: {e}")
        return None
    finally:
        # 清理临时文件：不删除 packages 目录中的安装包
        if extract_to.exists():
            try:
                shutil.rmtree(extract_to)
            except Exception:
                pass
        if zip_path and zip_path.exists() and zip_path.parent == temp_dir:
            try:
                zip_path.unlink()
            except Exception:
                pass
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
