"""
RTSP 推流模块：使用 FFmpeg 将视频帧推送到 RTSP 服务器
"""
import subprocess
import threading
import queue
import sys
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class StreamConfig:
    """推流配置"""
    width: int = 1280
    height: int = 720
    fps: int = 30
    bitrate: str = "4000k"
    codec: str = "libx264"
    pixel_format: str = "bgr24"
    audio_device: Optional[str] = None
    dshow_video_device: Optional[str] = None
    rtsp_transport: str = "udp"  # "udp" 低延迟优先（图传推荐），"tcp" 可靠优先


class RtspSender:
    """RTSP 推流器"""
    
    def __init__(
        self,
        rtsp_url: str,
        config: StreamConfig,
        on_log: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        ffmpeg_path: Optional[str] = None,
    ):
        self.rtsp_url = rtsp_url
        self.config = config
        self.ffmpeg_path = (ffmpeg_path or "").strip() or "ffmpeg"
        self.on_log = on_log or (lambda _: None)
        self.on_error = on_error or (lambda _: None)
        self._process: Optional[subprocess.Popen] = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=15)  # 适度缓冲，减少卡顿
        self._worker: Optional[threading.Thread] = None
        self._running = False
    
    def _log(self, msg: str):
        self.on_log(msg)
    
    def _build_ffmpeg_cmd(self) -> list:
        """构建 FFmpeg 命令（低延迟参数）"""
        use_dshow = bool(self.config.dshow_video_device and sys.platform == "win32")

        if use_dshow:
            # 高性能模式：FFmpeg 直接采集摄像头，无 pipe 瓶颈
            video_input = f"video={self.config.dshow_video_device}"
            if self.config.audio_device:
                video_input += f":audio={self.config.audio_device}"
            cmd = [
                self.ffmpeg_path, "-y",
                "-f", "dshow",
                "-video_size", f"{self.config.width}x{self.config.height}",
                "-framerate", str(self.config.fps),
                "-i", video_input,
            ]
            # 时间戳 overlay，Windows 指定字体避免 fontconfig 报错
            vf = "drawtext=text='%{localtime\\:%X}':fontsize=24:fontcolor=white:x=10:y=10"
            if sys.platform == "win32":
                vf += ":fontfile='C\\:/Windows/Fonts/arial.ttf'"
        else:
            # Pipe 模式：从 Python 接收帧
            cmd = [
                self.ffmpeg_path, "-y",
                "-f", "rawvideo",
                "-pix_fmt", self.config.pixel_format,
                "-s", f"{self.config.width}x{self.config.height}",
                "-r", str(self.config.fps),
                "-probesize", "32",
                "-analyzeduration", "0",
                "-i", "pipe:0",
            ]
            if self.config.audio_device:
                cmd.extend(["-f", "dshow", "-i", f"audio={self.config.audio_device}"])
            vf = None

        # 视频编码参数
        cmd.extend(["-c:v", self.config.codec, "-pix_fmt", "yuv420p", "-b:v", self.config.bitrate, "-g", str(self.config.fps)])
        if self.config.codec == "h264_nvenc":
            cmd.extend(["-preset", "p1", "-tune", "ull", "-delay", "0"])
        elif self.config.codec == "libx264":
            cmd.extend(["-preset", "ultrafast", "-tune", "zerolatency", "-x264opts", "rc-lookahead=0"])
        elif self.config.codec == "libx265":
            cmd.extend(["-preset", "ultrafast", "-x265-params", "rc-lookahead=0"])

        if vf:
            cmd.extend(["-vf", vf])
        if self.config.audio_device and not use_dshow:
            cmd.extend(["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k", "-ar", "44100"])
        elif self.config.audio_device and use_dshow:
            cmd.extend(["-map", "0:v", "-map", "0:a", "-c:a", "aac", "-b:a", "128k", "-ar", "44100"])

        cmd.extend([
            "-f", "rtsp",
            "-rtsp_transport", self.config.rtsp_transport,
            self.rtsp_url,
        ])
        return cmd
    
    def push_frame(self, frame_data: bytes):
        """推送一帧（非阻塞，放入队列）"""
        if not self._running:
            return
        try:
            self._frame_queue.put_nowait(frame_data)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()  # 丢弃最旧的一帧
                self._frame_queue.put_nowait(frame_data)
            except (queue.Empty, queue.Full):
                pass
    
    def _worker_loop(self):
        """工作线程：从队列取帧并写入 FFmpeg stdin"""
        while self._running and self._process and self._process.stdin:
            try:
                frame_data = self._frame_queue.get(timeout=0.1)
                self._process.stdin.write(frame_data)
                self._process.stdin.flush()
            except queue.Empty:
                continue
            except (BrokenPipeError, OSError):
                if self._running:
                    self.on_error("推流管道已断开")
                break
            except Exception as e:
                self._log(f"推流写入错误: {e}")
    
    def _use_dshow(self) -> bool:
        return bool(self.config.dshow_video_device and sys.platform == "win32")

    def start(self) -> bool:
        """启动推流"""
        if self._running:
            return True
        try:
            cmd = self._build_ffmpeg_cmd()
            self._log(f"启动 FFmpeg: {' '.join(cmd)}")
            use_dshow = self._use_dshow()
            self._process = subprocess.Popen(
                cmd,
                stdin=None if use_dshow else subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self._running = True
            if not use_dshow:
                self._worker = threading.Thread(target=self._worker_loop, daemon=True)
                self._worker.start()
            threading.Thread(target=self._read_stderr, daemon=True).start()
            self._log("推流已启动" + (" (dshow 直接采集)" if use_dshow else ""))
            return True
        except FileNotFoundError:
            self._log("错误: 未找到 FFmpeg，请确保已安装并加入 PATH")
            return False
        except Exception as e:
            self._log(f"启动推流失败: {e}")
            return False
    
    def _read_stderr(self):
        """读取 FFmpeg stderr 输出，检测错误"""
        if self._process and self._process.stderr:
            for line in iter(self._process.stderr.readline, b""):
                if line:
                    try:
                        text = line.decode("utf-8", errors="ignore").strip()
                        self._log(text)
                        # 检测常见错误
                        if "Connection refused" in text or "Connection timed out" in text:
                            self.on_error("无法连接 RTSP 服务器，请检查地址和端口")
                        elif "could not find" in text.lower() or "Invalid data" in text:
                            self.on_error("推流失败，请检查配置")
                    except Exception:
                        pass
    
    def _check_process_exit(self):
        """定时检查 FFmpeg 进程是否异常退出"""
        if self._process and self._running and self._process.poll() is not None:
            code = self._process.returncode
            if code != 0:
                self.on_error(f"FFmpeg 异常退出 (code={code})")
    
    def stop(self):
        """停止推流（快速退出，避免关闭窗口时卡顿）"""
        self._running = False
        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
            except Exception:
                pass
            try:
                self._process.terminate()
                self._process.wait(timeout=0.5)
            except Exception:
                pass
            if self._process and self._process.poll() is None:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        if self._worker:
            self._worker.join(timeout=0.3)
            self._worker = None
        # 清空队列
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break
        self._log("推流已停止")
    
    @property
    def is_running(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None
