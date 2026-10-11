"""
主窗口：预览、配置、推流控制
"""
import sys
import socket
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QLineEdit, QGroupBox, QCheckBox, QTextEdit,
    QSplitter, QMessageBox, QSizePolicy, QFileDialog, QProgressDialog,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QImage, QPixmap, QFont

from .camera import enumerate_cameras, CameraCapture, CameraInfo
from .rtsp_sender import RtspSender, StreamConfig
from .audio import enumerate_audio_devices
from .config import set_ffmpeg_path, find_ffmpeg
from .ffmpeg_installer import download_ffmpeg
from .mediamtx_server import get_mediamtx_path, download_mediamtx, start_mediamtx, get_rtsp_port


class StreamErrorSignal(QObject):
    """用于跨线程发送推流错误信号"""
    error_occurred = pyqtSignal(str)


class LogSignal(QObject):
    """用于跨线程安全地追加日志"""
    log_message = pyqtSignal(str)


class FfmpegInstallWorker(QThread):
    """FFmpeg 下载安装后台线程"""
    progress = pyqtSignal(int, int)  # downloaded, total
    finished_signal = pyqtSignal(object)  # Path or None

    def run(self):
        def on_progress(d, t):
            self.progress.emit(d, t)

        def on_log(msg):
            pass  # 可选：通过 signal 传到主线程

        result = download_ffmpeg(on_progress=on_progress, on_log=on_log)
        self.finished_signal.emit(result)


class MediaMTXInstallWorker(QThread):
    """MediaMTX 下载安装后台线程"""
    progress = pyqtSignal(int, int)
    finished_signal = pyqtSignal(object)

    def run(self):
        def on_progress(d, t):
            self.progress.emit(d, t)
        result = download_mediamtx(on_progress=on_progress, on_log=lambda _: None)
        self.finished_signal.emit(result)


class CaptureThread(QThread):
    """采集线程：摄像头 -> 预览 + 推流"""
    frame_ready = pyqtSignal(bytes, int, int)  # frame_bytes, width, height

    def __init__(self, camera: CameraCapture, rtsp_sender: Optional[RtspSender] = None):
        super().__init__()
        self.camera = camera
        self.rtsp_sender = rtsp_sender
        self._running = True

    def run(self):
        while self._running:
            ret, frame_bytes, w, h = self.camera.read_frame()
            if not ret or frame_bytes is None:
                continue
            self.frame_ready.emit(frame_bytes, w, h)
            if self.rtsp_sender and self.rtsp_sender.is_running:
                self.rtsp_sender.push_frame(frame_bytes)

    def stop(self):
        self._running = False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CamStream - 摄像头推流助手")
        self.setMinimumSize(920, 680)
        self.resize(1020, 720)

        # 状态
        self.cameras: list[CameraInfo] = []
        self.camera: Optional[CameraCapture] = None
        self.rtsp_sender: Optional[RtspSender] = None
        self.capture_thread: Optional[CaptureThread] = None
        self.stream_config = StreamConfig()
        self._error_signal = StreamErrorSignal()
        self._status_check_timer = QTimer(self)
        self._status_check_timer.timeout.connect(self._check_stream_status)
        self._log_buffer: list[str] = []
        self._pending_stream_after_install = False
        self._pending_stream_after_mediamtx = False
        self._log_signal = LogSignal()
        self._mediamtx_process = None
        self._log_signal.log_message.connect(self._append_log)

        self._setup_ui()
        self._apply_styles()
        self._refresh_cameras()
        self._error_signal.error_occurred.connect(self._on_stream_error)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # 上半部分：预览 + 配置
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 预览区域
        preview_group = QGroupBox("摄像头预览")
        preview_group.setObjectName("previewGroup")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(640, 360)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setText("点击「刷新摄像头」后选择摄像头并开始预览\n（双击预览区可全屏）")
        self.preview_label.mouseDoubleClickEvent = lambda e: self._toggle_preview_fullscreen(e)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_layout.addWidget(self.preview_label)
        top_splitter.addWidget(preview_group)

        # 配置区域
        config_group = QGroupBox("推流配置")
        config_group.setObjectName("configGroup")
        config_layout = QVBoxLayout(config_group)

        config_layout.addWidget(QLabel("推流地址 (RTSP):"))
        self.rtsp_input = QLineEdit()
        self.rtsp_input.setPlaceholderText("rtsp://192.168.1.100:554/live")
        self.rtsp_input.setText("rtsp://127.0.0.1:8554/live")
        config_layout.addWidget(self.rtsp_input)

        config_layout.addWidget(QLabel("分辨率:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["640x480", "1280x720", "1920x1080"])
        self.resolution_combo.setCurrentText("1280x720")
        config_layout.addWidget(self.resolution_combo)

        config_layout.addWidget(QLabel("帧率:"))
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["15", "24", "30", "60"])
        self.fps_combo.setCurrentText("30")
        config_layout.addWidget(self.fps_combo)

        config_layout.addWidget(QLabel("码率:"))
        self.bitrate_input = QLineEdit()
        self.bitrate_input.setText("4000k")
        config_layout.addWidget(self.bitrate_input)

        config_layout.addWidget(QLabel("编码格式:"))
        self.codec_combo = QComboBox()
        self.codec_combo.addItems(["H.264 (NVENC GPU)", "H.264 (libx264 CPU)", "H.265 (libx265 CPU)"])
        self.codec_combo.setCurrentIndex(0)
        self.codec_combo.setToolTip("NVENC 需 NVIDIA 显卡，显著减少卡顿")
        config_layout.addWidget(self.codec_combo)

        config_layout.addWidget(QLabel("传输协议:"))
        self.transport_combo = QComboBox()
        self.transport_combo.addItems(["UDP（低延迟，图传推荐）", "TCP（可靠传输）"])
        self.transport_combo.setCurrentIndex(0)
        self.transport_combo.setToolTip("UDP 延迟低适合实时图传，TCP 更可靠适合录制/监控")
        config_layout.addWidget(self.transport_combo)

        self.dshow_check = QCheckBox("高性能模式 (FFmpeg 直接采集)")
        self.dshow_check.setChecked(True)
        self.dshow_check.setToolTip("勾选时 FFmpeg 直接采集摄像头，无 pipe 瓶颈；若卡住或失败可取消勾选")
        config_layout.addWidget(self.dshow_check)

        config_layout.addStretch()
        top_splitter.addWidget(config_group)

        top_splitter.setSizes([720, 280])
        layout.addWidget(top_splitter)

        # 控制栏
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("摄像头:"))
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(220)
        control_layout.addWidget(self.camera_combo)

        refresh_btn = QPushButton("刷新摄像头")
        refresh_btn.clicked.connect(self._refresh_cameras)
        control_layout.addWidget(refresh_btn)

        self.audio_check = QCheckBox("启用音频")
        self.audio_check.setChecked(False)
        self.audio_check.toggled.connect(self._on_audio_toggled)
        control_layout.addWidget(self.audio_check)

        self.audio_combo = QComboBox()
        self.audio_combo.setMinimumWidth(180)
        self.audio_combo.setEnabled(False)
        control_layout.addWidget(self.audio_combo)

        control_layout.addStretch()

        self.preview_btn = QPushButton("开始预览")
        self.preview_btn.clicked.connect(self._start_preview)
        control_layout.addWidget(self.preview_btn)

        self.start_btn = QPushButton("▶ 开始推流")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self._on_start_stream)
        control_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.clicked.connect(self._on_stop_stream)
        control_layout.addWidget(self.stop_btn)

        layout.addLayout(control_layout)

        # 状态栏
        status_layout = QHBoxLayout()
        self.status_label = QLabel("状态: 就绪")
        self.status_label.setObjectName("statusLabel")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        self.copy_url_btn = QPushButton("复制推流地址")
        self.copy_url_btn.clicked.connect(self._copy_rtsp_url)
        status_layout.addWidget(self.copy_url_btn)
        pull_help_btn = QPushButton("拉流说明")
        pull_help_btn.setToolTip("查看如何用 VLC 等播放器拉流")
        pull_help_btn.clicked.connect(self._show_pull_help)
        status_layout.addWidget(pull_help_btn)
        layout.addLayout(status_layout)

        # 日志区域
        log_group = QGroupBox("日志")
        log_group.setObjectName("logGroup")
        log_layout = QVBoxLayout(log_group)
        log_toolbar = QHBoxLayout()
        export_btn = QPushButton("导出日志")
        export_btn.clicked.connect(self._export_log)
        log_toolbar.addWidget(export_btn)
        log_toolbar.addStretch()
        log_layout.addLayout(log_toolbar)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setObjectName("logText")
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)

    def _apply_styles(self):
        """应用界面样式（确保下拉框文字可见）"""
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #f5f5f5; color: #333; }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ddd;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 12px;
                color: #333;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #333; }
            QLabel { color: #333; }
            #previewLabel { background-color: #1e1e1e; border-radius: 6px; color: #888; }
            #startBtn {
                background-color: #2e7d32;
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            #startBtn:hover { background-color: #388e3c; }
            #startBtn:disabled { background-color: #9e9e9e; }
            #stopBtn {
                background-color: #c62828;
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            #stopBtn:hover { background-color: #d32f2f; }
            #stopBtn:disabled { background-color: #9e9e9e; }
            QPushButton {
                padding: 6px 14px;
                border-radius: 4px;
                background-color: #e0e0e0;
                color: #333;
            }
            QPushButton:hover { background-color: #d0d0d0; }
            QLineEdit, QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
                min-height: 24px;
                background-color: white;
                color: #333;
            }
            QComboBox::drop-down {
                border: none;
                background: transparent;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                color: #333;
                selection-background-color: #e3f2fd;
                selection-color: #333;
            }
        """)

    def _log(self, msg: str):
        """主线程调用，直接追加"""
        self._append_log(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _append_log(self, line: str):
        """实际追加日志（由 signal 调用，保证在主线程）"""
        self._log_buffer.append(line)
        if len(self._log_buffer) > 500:
            self._log_buffer.pop(0)
        self.log_text.append(line)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def _log_from_thread(self, msg: str):
        """供后台线程安全调用：通过 signal 转发到主线程"""
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_signal.log_message.emit(f"[{ts}] {msg}")

    def _on_audio_toggled(self, checked: bool):
        self.audio_combo.setEnabled(checked)
        if checked and self.audio_combo.count() == 0:
            self._refresh_audio_devices()

    def _refresh_audio_devices(self):
        ffmpeg_path = find_ffmpeg() or "ffmpeg"
        devices = enumerate_audio_devices(ffmpeg_path)
        self.audio_combo.clear()
        if devices:
            for d in devices:
                self.audio_combo.addItem(d.name, d.name)
            self._log(f"检测到 {len(devices)} 个音频输入设备")
        else:
            self.audio_combo.addItem("未检测到麦克风", None)
            self._log("未检测到音频输入设备")

    def _refresh_cameras(self):
        self.cameras = enumerate_cameras()
        self.camera_combo.clear()
        if not self.cameras:
            self.camera_combo.addItem("未检测到摄像头", -1)
            self._log("未检测到可用摄像头")
            return
        for cam in self.cameras:
            self.camera_combo.addItem(cam.name, cam.index)
        self._log(f"检测到 {len(self.cameras)} 个摄像头")

    def _toggle_preview_fullscreen(self, event):
        """双击预览区切换全屏"""
        event.accept()
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _do_install_ffmpeg(self):
        """执行 FFmpeg 下载安装"""
        from .ffmpeg_installer import _install_dir
        existing = _install_dir() / "bin" / "ffmpeg.exe"
        if existing.exists():
            path = str(existing)
            set_ffmpeg_path(path)
            self._log(f"FFmpeg 已存在: {path}")
            if self._pending_stream_after_install:
                self._pending_stream_after_install = False
                QTimer.singleShot(100, self._on_start_stream)
            else:
                QMessageBox.information(self, "已安装", f"FFmpeg 已安装。\n\n{path}")
            return

        if not self._pending_stream_after_install:
            reply = QMessageBox.question(
                self, "安装 FFmpeg",
                "是否安装 FFmpeg？\n\n"
                "（约 70MB，优先使用本地包）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._install_progress = QProgressDialog("正在下载 FFmpeg...", "取消", 0, 100, self)
        self._install_progress.setWindowTitle("安装 FFmpeg")
        self._install_progress.setMinimumDuration(0)
        self._install_progress.setValue(0)

        self._install_worker = FfmpegInstallWorker()
        self._install_worker.progress.connect(self._on_install_progress)
        self._install_worker.finished_signal.connect(self._on_install_finished)
        self._install_worker.start()

    def _on_install_progress(self, downloaded: int, total: int):
        if total > 0 and hasattr(self, "_install_progress") and self._install_progress:
            pct = min(100, int(100 * downloaded / total))
            self._install_progress.setValue(pct)
            self._install_progress.setLabelText(f"正在下载 FFmpeg... {downloaded // 1024 // 1024} / {total // 1024 // 1024} MB")

    def _on_install_finished(self, result):
        if hasattr(self, "_install_progress") and self._install_progress:
            self._install_progress.close()
        if result:
            path = str(result)
            set_ffmpeg_path(path)
            self._log(f"FFmpeg 安装完成: {path}")
            if self._pending_stream_after_install:
                self._pending_stream_after_install = False
                QTimer.singleShot(100, self._on_start_stream)
            else:
                QMessageBox.information(self, "安装成功", f"FFmpeg 已安装到:\n{path}")
        else:
            self._log("FFmpeg 安装失败")
            if self._pending_stream_after_install:
                self._pending_stream_after_install = False
            QMessageBox.warning(
                self, "安装失败",
                "下载或安装 FFmpeg 失败。\n\n请检查网络连接。",
            )

    def _check_rtsp_server(self, rtsp_url: str) -> bool:
        """通过发送 RTSP OPTIONS 请求验证对端确实是 RTSP 服务器"""
        try:
            parsed = urlparse(rtsp_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port if parsed.port else 8554
            with socket.create_connection((host, port), timeout=2) as s:
                s.sendall(f"OPTIONS {rtsp_url} RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
                s.settimeout(2)
                resp = s.recv(512).decode("utf-8", errors="ignore")
                return resp.startswith("RTSP/")
        except (OSError, ValueError):
            return False

    def _ensure_rtsp_server(self, rtsp_url: str) -> bool:
        """
        确保 RTSP 服务器可用。若未检测到则尝试启动或安装 MediaMTX。
        返回 True 表示可继续推流，False 表示应中止。
        若需异步安装，会启动安装流程并返回 False，安装完成后自动重试推流。
        """
        if self._check_rtsp_server(rtsp_url):
            return True

        exe = get_mediamtx_path()
        if exe:
            # MediaMTX 已安装，直接启动，不询问
            self._pending_stream_after_mediamtx = True
            if not (self._mediamtx_process and self._mediamtx_process.poll() is None):
                proc = start_mediamtx(on_log=self._log_from_thread)
                if proc:
                    self._mediamtx_process = proc
                    self._update_rtsp_url_port()
                    self._log("MediaMTX 已启动，即将开始推流")
            else:
                self._log("MediaMTX 已运行，等待服务就绪...")
            QTimer.singleShot(2000, self._retry_start_stream)  # 等待 MediaMTX 完全就绪
            return False

        # MediaMTX 未安装，询问是否安装
        reply = QMessageBox.question(
            self, "未检测到 RTSP 服务器",
            "推流目标地址无法连接，拉流端将无法播放。\n\n"
            "是否安装 MediaMTX？\n\n"
            "（约 20MB，安装完成后将自动开始推流）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            QMessageBox.information(
                self, "提示",
                "请先启动 RTSP 服务器（如 MediaMTX）后再推流。\n\n"
                "下载：https://github.com/bluenviron/mediamtx/releases",
            )
            return False

        self._pending_stream_after_mediamtx = True
        self._mtx_progress = QProgressDialog("正在安装 MediaMTX...", None, 0, 100, self)
        self._mtx_progress.setWindowTitle("安装 MediaMTX")
        self._mtx_progress.setMinimumDuration(0)
        self._mtx_worker = MediaMTXInstallWorker()
        self._mtx_worker.progress.connect(
            lambda d, t: self._mtx_progress.setValue(int(100 * d / t)) if t else None
        )
        self._mtx_worker.finished_signal.connect(self._on_mediamtx_installed_for_stream)
        self._mtx_worker.start()
        return False

    def _update_rtsp_url_port(self):
        """MediaMTX 启动后，若使用了非默认端口，自动更新推流地址并弹窗提示"""
        port = get_rtsp_port()
        if port == 8554:
            return
        url = self.rtsp_input.text().strip()
        try:
            p = urlparse(url)
            old_port = p.port or 8554
            if old_port == port:
                return
            if (p.hostname or "").lower() in ("127.0.0.1", "localhost"):
                new_url = f"rtsp://127.0.0.1:{port}{p.path or '/live'}"
                self.rtsp_input.setText(new_url)
                self._log(f"端口 {old_port} 被占用，已切换到 {port}")
                QMessageBox.information(
                    self, "RTSP 端口已更换",
                    f"默认端口 {old_port} 被其他程序占用，\n"
                    f"已自动切换到端口 {port}。\n\n"
                    f"推流地址已更新为：\n{new_url}\n\n"
                    f"拉流时请使用新地址。",
                )
        except Exception:
            pass

    def _retry_start_stream(self):
        """MediaMTX 启动后重试推流"""
        self._pending_stream_after_mediamtx = False
        self._on_start_stream()

    def _on_mediamtx_installed_for_stream(self, result):
        if hasattr(self, "_mtx_progress") and self._mtx_progress:
            self._mtx_progress.close()
        if result:
            proc = start_mediamtx(on_log=self._log_from_thread)
            if proc:
                self._mediamtx_process = proc
                self._update_rtsp_url_port()
                self._log("MediaMTX 已安装并启动")
                self._pending_stream_after_mediamtx = False
                QTimer.singleShot(2000, self._on_start_stream)
            else:
                self._pending_stream_after_mediamtx = False
                QMessageBox.warning(self, "失败", "MediaMTX 启动失败。")
        else:
            self._pending_stream_after_mediamtx = False
            QMessageBox.warning(self, "失败", "MediaMTX 下载失败，请检查网络。")

    def _show_pull_help(self):
        """显示拉流说明"""
        url = self.rtsp_input.text().strip() or "rtsp://127.0.0.1:8554/live"
        msg = (
            "【拉流前请确保】\n"
            "1. 已启动 RTSP 服务器（如 MediaMTX）\n"
            "2. 本程序已开始推流\n\n"
            "【VLC 拉流（UDP，低延迟推荐）】\n"
            "  vlc " + url + "\n\n"
            "【VLC 拉流（TCP，稳定优先）】\n"
            "  vlc --rtsp-tcp " + url + "\n\n"
            "【ffplay 拉流（UDP）】\n"
            "  ffplay " + url + "\n\n"
            "【ffplay 拉流（TCP）】\n"
            "  ffplay -rtsp_transport tcp " + url + "\n\n"
            "提示：UDP 延迟更低，适合无人机图传实时查看；\n"
            "TCP 更稳定，适合网络不佳时使用。\n\n"
            "若无法拉流，请确认 RTSP 服务器已运行且推流地址正确。"
        )
        QMessageBox.information(self, "拉流说明", msg)

    def _copy_rtsp_url(self):
        url = self.rtsp_input.text().strip()
        if url:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(url)
            self._log("已复制推流地址到剪贴板")
            QMessageBox.information(self, "提示", "推流地址已复制到剪贴板")

    def _export_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(self._log_buffer))
                self._log(f"日志已导出到 {path}")
                QMessageBox.information(self, "提示", "日志导出成功")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def _check_stream_status(self):
        """定时检查推流状态，检测 FFmpeg 异常退出"""
        if self.rtsp_sender and not self.rtsp_sender.is_running:
            self._status_check_timer.stop()
            self._error_signal.error_occurred.emit("推流连接已断开")

    def _on_stream_error(self, msg: str):
        """处理推流错误（可能从其他线程调用）"""
        self._status_check_timer.stop()
        self._stop_capture()
        self.preview_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.camera_combo.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ 停止")
        self.status_label.setText("状态: 错误")
        self.status_label.setStyleSheet("color: #c62828; font-weight: bold;")
        self._log(f"错误: {msg}")
        QMessageBox.warning(self, "推流错误", msg)

    def _start_preview(self):
        """仅预览，不推流"""
        idx = self.camera_combo.currentData()
        if idx is None or idx < 0:
            QMessageBox.warning(self, "提示", "请先选择摄像头")
            return

        w, h = map(int, self.resolution_combo.currentText().split("x"))
        fps = int(self.fps_combo.currentText())

        self._stop_capture()
        self.camera = CameraCapture(camera_index=idx, width=w, height=h, fps=fps)
        if not self.camera.open():
            QMessageBox.critical(self, "错误", "无法打开摄像头")
            self._log("无法打开摄像头")
            return

        self.capture_thread = CaptureThread(self.camera, None)
        self.capture_thread.frame_ready.connect(self._on_frame)
        self.capture_thread.start()
        self.preview_btn.setEnabled(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("■ 停止预览")
        self.status_label.setText("状态: 预览中")
        self.status_label.setStyleSheet("color: #1976d2;")
        self._log("预览已启动")

    def _on_start_stream(self):
        rtsp_url = self.rtsp_input.text().strip()
        if not rtsp_url:
            QMessageBox.warning(self, "提示", "请输入推流地址")
            return

        idx = self.camera_combo.currentData()
        if idx is None or idx < 0:
            QMessageBox.warning(self, "提示", "请先选择摄像头")
            return

        w, h = map(int, self.resolution_combo.currentText().split("x"))
        fps = int(self.fps_combo.currentText())
        bitrate = self.bitrate_input.text().strip() or "4000k"
        codec_map = {0: "h264_nvenc", 1: "libx264", 2: "libx265"}
        codec = codec_map.get(self.codec_combo.currentIndex(), "h264_nvenc")
        audio_device = None
        if self.audio_check.isChecked() and self.audio_combo.currentData():
            audio_device = self.audio_combo.currentData()

        cam_name = None
        if self.dshow_check.isChecked():
            cam_name = self.camera_combo.currentText() or None
            # "摄像头 N" 为 OpenCV 回退的通用名，dshow 可能无法识别
            if cam_name and cam_name.startswith("摄像头 ") and cam_name[-1].isdigit():
                cam_name = None
        transport = "udp" if self.transport_combo.currentIndex() == 0 else "tcp"
        self.stream_config = StreamConfig(
            width=w, height=h, fps=fps, bitrate=bitrate,
            codec=codec, audio_device=audio_device,
            dshow_video_device=cam_name,
            rtsp_transport=transport,
        )

        ffmpeg_path = find_ffmpeg()
        if not ffmpeg_path:
            reply = QMessageBox.question(
                self, "未找到 FFmpeg",
                "未检测到 FFmpeg。是否安装？\n\n"
                "（约 70MB，安装完成后将自动开始推流）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._pending_stream_after_install = True
                self._do_install_ffmpeg()
            else:
                QMessageBox.information(
                    self, "未找到 FFmpeg",
                    "请安装 FFmpeg 后再推流。\n\n"
                    "下载：https://ffmpeg.org/download.html",
                )
            return

        # 推流前检测 RTSP 服务器，无则询问是否安装 MediaMTX
        if not self._ensure_rtsp_server(rtsp_url):
            return

        self._stop_capture()

        use_dshow = bool(cam_name and sys.platform == "win32")

        def on_error(msg: str):
            self._error_signal.error_occurred.emit(msg)

        self.rtsp_sender = RtspSender(
            rtsp_url, self.stream_config,
            on_log=self._log_from_thread,
            on_error=on_error,
            ffmpeg_path=ffmpeg_path,
        )
        if not self.rtsp_sender.start():
            return

        if use_dshow:
            # dshow 模式：FFmpeg 直接采集，无预览（摄像头被占用）
            self.preview_label.setText("推流中（FFmpeg 直接采集，无预览）")
            self.camera = None
            self.capture_thread = None
        else:
            # pipe 模式：Python 采集并推流
            self.camera = CameraCapture(camera_index=idx, width=w, height=h, fps=fps)
            if not self.camera.open():
                self.rtsp_sender.stop()
                self.rtsp_sender = None
                QMessageBox.critical(self, "错误", "无法打开摄像头")
                self._log("无法打开摄像头")
                return
            self.capture_thread = CaptureThread(self.camera, self.rtsp_sender)
            self.capture_thread.frame_ready.connect(self._on_frame)
            self.capture_thread.start()

        self.preview_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.camera_combo.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("■ 停止推流")
        self.status_label.setText("状态: ● 推流中")
        self.status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
        self._status_check_timer.start(2000)

    def _on_stop_stream(self):
        self._status_check_timer.stop()
        self._stop_capture()
        self.preview_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.camera_combo.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ 停止")
        self.status_label.setText("状态: 已断开")
        self.status_label.setStyleSheet("color: #666;")
        # 若之前是 dshow 模式，恢复预览区占位文字
        if self.preview_label.text().startswith("推流中"):
            self.preview_label.setText("点击「刷新摄像头」后选择摄像头并开始预览\n（双击预览区可全屏）")

    def _stop_capture(self):
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread.wait(500)  # 缩短等待，避免关闭时卡顿
            self.capture_thread = None
        if self.rtsp_sender:
            self.rtsp_sender.stop()
            self.rtsp_sender = None
        if self.camera:
            self.camera.close()
            self.camera = None

    def _on_frame(self, frame_bytes: bytes, w: int, h: int):
        """处理帧：显示预览 + 叠加时间戳"""
        arr = np.frombuffer(frame_bytes, dtype=np.uint8).reshape((h, w, 3)).copy()
        
        # 叠加时间戳 (HH:MM:SS.mmm)
        ts = datetime.now().strftime("%H:%M:%S.") + f"{datetime.now().microsecond // 1000:03d}"
        cv2.putText(
            arr, ts,
            (10, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        # 转 QImage 显示（必须 copy 否则 QImage 持有 numpy 缓冲区引用，函数返回后内存被回收导致崩溃）
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
        self.preview_label.setPixmap(QPixmap.fromImage(qimg).scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def closeEvent(self, event):
        self._status_check_timer.stop()
        self.hide()  # 立即隐藏窗口，避免关闭时卡顿感
        self._stop_capture()
        if self._mediamtx_process and self._mediamtx_process.poll() is None:
            try:
                self._mediamtx_process.terminate()
                self._mediamtx_process.wait(timeout=0.3)
            except Exception:
                pass
            if self._mediamtx_process and self._mediamtx_process.poll() is None:
                self._mediamtx_process.kill()
        event.accept()


def run_app():
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # 设置支持中文的字体，解决 Windows 下下拉框文字不显示问题
    font = QFont("Microsoft YaHei", 9)
    if not font.exactMatch():
        font = QFont("SimHei", 9)  # 备用：黑体
    app.setFont(font)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
