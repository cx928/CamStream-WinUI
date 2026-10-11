#!/usr/bin/env python3
"""
将 packages 目录中大于 40MB 的 zip 分割成多个不超过 40MB 的分片，便于纳入 Git。
小于 40MB 的 zip（如 mediamtx）不分割。
"""
import argparse
import sys
import tempfile
import urllib.request
from pathlib import Path

PACKAGES_DIR = Path(__file__).parent / "packages"
CHUNK_SIZE = 40 * 1024 * 1024  # 40MB

DOWNLOADS = {
    "ffmpeg-release-essentials.zip": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
}


def _download(url: str, dest: Path) -> bool:
    """下载文件"""
    print(f"正在下载: {dest.name} ...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CamStream/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 256 * 1024
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = 100 * downloaded / total
                        mb = downloaded / 1024 / 1024
                        total_mb = total / 1024 / 1024
                        print(f"\r  {mb:.1f} / {total_mb:.1f} MB ({pct:.0f}%)", end="")
            print()
        return True
    except Exception as e:
        print(f"  失败: {e}")
        return False


def _delete_split_parts(base_name: str, dir_path: Path) -> None:
    """删除某文件的所有分片"""
    for p in dir_path.iterdir():
        if p.is_file() and p.name.startswith(base_name + ".") and p.suffix[1:].isdigit():
            p.unlink()
            print(f"  已删除: {p.name}")


def main():
    parser = argparse.ArgumentParser(description="分割 packages 中的 zip（每片不超过 40MB）")
    parser.add_argument("--force", action="store_true", help="删除已有分片并重新下载、分割")
    args = parser.parse_args()

    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("CamStream 安装包分割（每片 ≤40MB）")
    print("=" * 50)

    # 需要下载的，先确保有完整 zip
    for filename, url in DOWNLOADS.items():
        dest = PACKAGES_DIR / filename
        first_part = PACKAGES_DIR / f"{filename}.001"
        if dest.exists() and not args.force:
            continue
        if first_part.exists() and not args.force:
            print(f"分片已存在，跳过: {filename}（使用 --force 重新下载并分割）")
            continue
        if first_part.exists() and args.force:
            print(f"删除旧分片: {filename}")
            _delete_split_parts(filename, PACKAGES_DIR)
        # 下载到临时文件再替换，避免占用时无法删除
        with tempfile.NamedTemporaryFile(dir=PACKAGES_DIR, delete=False, suffix=".zip") as tmp:
            tmp_path = Path(tmp.name)
        try:
            if not _download(url, tmp_path):
                tmp_path.unlink(missing_ok=True)
                sys.exit(1)
            if dest.exists():
                dest.unlink()
            tmp_path.rename(dest)
            print(f"  下载完成")
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            print(f"  失败: {e}")
            sys.exit(1)

    for f in sorted(PACKAGES_DIR.iterdir()):
        if not f.is_file() or f.suffix.lower() != ".zip":
            continue
        # 跳过已是分片的文件（如 xxx.zip.001）
        if f.name.count(".") > 1 and f.suffix[1:].isdigit():
            continue

        size = f.stat().st_size
        if size <= CHUNK_SIZE:
            print(f"跳过（≤40MB）: {f.name} ({size / 1024 / 1024:.1f} MB)")
            continue

        first_part = PACKAGES_DIR / f"{f.name}.001"
        if first_part.exists() and not args.force:
            print(f"分片已存在，跳过: {f.name}")
            continue
        if first_part.exists() and args.force:
            print(f"删除旧分片: {f.name}")
            _delete_split_parts(f.name, PACKAGES_DIR)

        print(f"分割: {f.name} ({size / 1024 / 1024:.1f} MB)")
        try:
            part_num = 1
            with open(f, "rb") as src:
                while True:
                    chunk = src.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    part_path = PACKAGES_DIR / f"{f.name}.{part_num:03d}"
                    with open(part_path, "wb") as out:
                        out.write(chunk)
                    print(f"  已生成: {part_path.name}")
                    part_num += 1
            f.unlink()
            print(f"  完成，共 {part_num - 1} 个分片")
        except Exception as e:
            print(f"  失败: {e}")

    print("=" * 50)


if __name__ == "__main__":
    main()
