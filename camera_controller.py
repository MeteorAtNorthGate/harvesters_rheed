# camera_controller.py
# 作用: 提供一个独立于UI的相机控制器，在后台线程中处理图像捕获。

import threading
from PySide6.QtCore import QObject, Signal, Slot, QThread
import cv2
import numpy as np


class CameraController(QObject):
    """
    相机控制器，继承自 QObject 以支持信号和槽。
    它将在一个独立的 QThread 中运行图像采集循环。
    """
    error_occurred = Signal(str)
    capture_stopped = Signal()

    def __init__(self, harvester, device_index=0, fps=30):
        super().__init__()
        self.harvester = harvester
        self.ia = None
        self.device_index = device_index
        self._is_capturing = False
        self.thread = None
        self.fps = fps
        print(f"相机控制器已使用帧率进行初始化: {self.fps} FPS")

        self.latest_frame = None
        self.lock = threading.Lock()

    @Slot()
    def start_capture(self):
        if self._is_capturing:
            self.error_occurred.emit("捕获已经在运行中。")
            return
        if not self.harvester or not self.harvester.device_info_list:
            self.error_occurred.emit("Harvester 未初始化或未找到设备。")
            return

        try:
            self.ia = self.harvester.create(self.device_index)
            self._is_capturing = True
            self.thread = QThread()
            self.moveToThread(self.thread)
            self.thread.started.connect(self._capture_loop)
            self.thread.start()
            print("相机控制器已移至后台线程并启动。")
        except Exception as e:
            self.error_occurred.emit(f"启动捕获失败: {e}")
            self._cleanup()

    def _capture_loop(self):
        print("后台捕获循环开始...")
        try:
            try:
                pixel_format = self.ia.remote_device.node_map.PixelFormat.value
            except Exception:
                pixel_format = 'Unknown'
            print(f"相机像素格式: {pixel_format}")

            self.ia.start()
            while self._is_capturing:
                with self.ia.fetch() as buffer:
                    component = buffer.payload.components[0]
                    frame = self._process_component(component, pixel_format)
                    if frame is not None:
                        with self.lock:
                            self.latest_frame = frame
        except Exception as e:
            # 在循环退出时，Harvester可能已经关闭，此时fetch会抛出异常，这是正常的。
            if self._is_capturing: # 只有在非正常停止时才报告错误
                self.error_occurred.emit(f"捕获过程中发生错误: {e}")
        finally:
            self._cleanup()
            self.capture_stopped.emit()

    def _process_component(self, component, pixel_format):
        width = component.width
        height = component.height
        data = component.data
        try:
            if 'YUV422' in pixel_format or (data.nbytes == width * height * 2):
                yuv_image = data.reshape(height, width, 2)
                return cv2.cvtColor(yuv_image, cv2.COLOR_YUV2BGR_UYVY)

            if 'Mono' in pixel_format or (data.nbytes == width * height) or (data.nbytes == width * height * 2):
                if data.nbytes == (width * height):
                    mono_image = data.reshape(height, width)
                else:
                    img_16bit = data.view(np.uint16).reshape(height, width)
                    shift = 8
                    if 'Mono12' in pixel_format:
                        shift = 4
                    elif 'Mono10' in pixel_format:
                        shift = 6
                    mono_image = (img_16bit >> shift).astype(np.uint8)
                return cv2.cvtColor(mono_image, cv2.COLOR_GRAY2BGR)

            self.error_occurred.emit(f"无法确定或不支持的像素格式: {pixel_format}")
            self._is_capturing = False
            return None
        except Exception as e:
            self.error_occurred.emit(f"处理图像帧时出错: {e}")
            self._is_capturing = False
            return None

    @Slot()
    def stop_capture(self):
        if not self._is_capturing: return
        print("收到停止捕获请求...")
        self._is_capturing = False

    def _cleanup(self):
        """
        只清理本对象拥有的硬件资源 (ia)。
        线程的管理由创建者(MainWindow)负责。
        """
        print("正在清理相机硬件资源 (ia object)...")
        if self.ia:
            try:
                if self.ia.is_acquiring():
                    self.ia.stop()
                self.ia.destroy()
            except Exception as e:
                # 在清理阶段，忽略一些可能发生的异常，因为Harvester可能已被重置
                print(f"清理 ia 资源时发生了一个可忽略的错误: {e}")
            finally:
                self.ia = None
        print("相机硬件资源已释放。")
