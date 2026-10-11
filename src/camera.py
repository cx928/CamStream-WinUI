"""
摄像头管理模块：枚举、选择、采集
"""
import cv2
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class CameraInfo:
    """摄像头信息"""
    index: int
    name: str


def enumerate_cameras() -> List[CameraInfo]:
    """枚举系统可用摄像头"""
    cameras: List[CameraInfo] = []
    
    # 尝试使用 pygrabber 获取设备名称（Windows DirectShow）
    try:
        from pygrabber.dshow_graph import FilterGraph
        graph = FilterGraph()
        device_names = graph.get_input_devices()
        for i, name in enumerate(device_names):
            cameras.append(CameraInfo(index=i, name=name or f"摄像头 {i}"))
        if cameras:
            return cameras
    except Exception:
        pass
    
    # 回退：尝试 OpenCV 索引 0-9
    for i in range(10):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            cameras.append(CameraInfo(index=i, name=f"摄像头 {i}"))
            cap.release()
    
    return cameras


class CameraCapture:
    """摄像头采集器"""
    
    def __init__(self, camera_index: int = 0, width: int = 1280, height: int = 720, fps: int = 30):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self._cap: Optional[cv2.VideoCapture] = None
    
    def open(self) -> bool:
        """打开摄像头"""
        self.close()
        self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            return False
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 减少缓冲，降低延迟
        return True
    
    def read(self) -> Tuple[bool, Optional[bytes]]:
        """读取一帧，返回 (成功, BGR 原始数据)"""
        if self._cap is None or not self._cap.isOpened():
            return False, None
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return False, None
        return True, frame.tobytes()
    
    def read_frame(self) -> Tuple[bool, Optional[bytes], int, int]:
        """读取一帧，返回 (成功, BGR 数据, 宽, 高)"""
        if self._cap is None or not self._cap.isOpened():
            return False, None, 0, 0
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return False, None, 0, 0
        h, w = frame.shape[:2]
        return True, frame.tobytes(), w, h
    
    def close(self):
        """关闭摄像头"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
    
    def __del__(self):
        self.close()
