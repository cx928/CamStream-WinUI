"""
packages 目录工具：支持完整 zip 与分割文件（.zip.001, .zip.002 ...）
"""
import tempfile
from pathlib import Path
from typing import Optional, Tuple


def _find_split_parts(base_name: str, dir_path: Path) -> list[Path]:
    """查找某 zip 的分割文件，按序号排序返回"""
    parts = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        if p.name.startswith(base_name + ".") and p.suffix[1:].isdigit():
            try:
                num = int(p.suffix[1:])
                parts.append((num, p))
            except ValueError:
                pass
    return [p for _, p in sorted(parts)] if parts else []


def _join_split_parts(parts: list[Path], out_path: Path) -> bool:
    """将分割文件合并为完整 zip"""
    try:
        with open(out_path, "wb") as out:
            for part in parts:
                with open(part, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
        return True
    except Exception:
        return False


def resolve_zip_path(
    packages_dir: Path,
    base_names: list[str],
    temp_dir: Optional[Path] = None,
) -> Tuple[Optional[Path], bool]:
    """
    解析可用的 zip 路径。支持完整 zip 或分割文件。
    返回 (zip_path, is_temp)。若为分割文件合并所得，is_temp=True，调用方需负责清理。
    """
    for name in base_names:
        full_path = packages_dir / name
        if full_path.exists() and full_path.is_file():
            return full_path, False
        parts = _find_split_parts(name, packages_dir)
        if parts:
            dest_dir = temp_dir or Path(tempfile.gettempdir())
            dest_dir.mkdir(parents=True, exist_ok=True)
            joined = dest_dir / name
            if _join_split_parts(parts, joined):
                return joined, True
    return None, False
