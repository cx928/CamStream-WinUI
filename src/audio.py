"""
音频采集模块：枚举麦克风设备，供 FFmpeg 使用
"""
import subprocess
import re
import sys
from typing import List
from dataclasses import dataclass


@dataclass
class AudioDeviceInfo:
    """音频设备信息"""
    name: str
    index: int


def enumerate_audio_devices(ffmpeg_path: str = "ffmpeg") -> List[AudioDeviceInfo]:
    """枚举 DirectShow 音频输入设备（麦克风）"""
    devices: List[AudioDeviceInfo] = []
    try:
        result = subprocess.run(
            [ffmpeg_path or "ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        stderr = result.stderr.decode("utf-8", errors="ignore")
        in_audio = False
        for line in stderr.splitlines():
            if "DirectShow audio devices" in line:
                in_audio = True
                continue
            if in_audio and "DirectShow video devices" in line:
                break
            if in_audio:
                m = re.search(r'"([^"]+)"', line)
                if m:
                    name = m.group(1)
                    devices.append(AudioDeviceInfo(name=name, index=len(devices)))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return devices
