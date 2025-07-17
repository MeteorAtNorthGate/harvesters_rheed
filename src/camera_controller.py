# camera_controller.py
# 作用: 提供一个独立于UI的相机控制器，在后台线程中处理图像捕获。

import threading
import time  # <-- 新增导入
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
	new_frame_data = Signal(dict)

	def __init__(self, harvester, device_index=0, fps=30):
		super().__init__()
		self.harvester = harvester
		self.ia = None
		self.device_index = device_index
		self._is_capturing = False
		self.thread = None
		self.fps = fps if fps > 0 else 30  # 确保fps大于0
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

			# --- 核心修改: 动态同步循环 ---
			# 计算单帧的目标周期时长
			target_frame_duration = 1.0 / self.fps

			self.ia.start()
			while self._is_capturing:
				# 在循环开始时记录高精度时间戳
				loop_start_time = time.perf_counter()

				with self.ia.fetch() as buffer:
					component = buffer.payload.components[0]
					bgr_frame = self._process_component(component, pixel_format)

					if bgr_frame is not None:
						with self.lock:
							self.latest_frame = bgr_frame

						frame_payload = {
							'bgr': bgr_frame,
							'raw_component': component
						}
						self.new_frame_data.emit(frame_payload)

				# 计算本次循环处理帧所花费的时间
				processing_time = time.perf_counter() - loop_start_time

				# 计算需要休眠的时间，以将整个循环的耗时补足到一个目标周期
				sleep_duration = target_frame_duration - processing_time

				if sleep_duration > 0:
					time.sleep(sleep_duration)

		except Exception as e:
			if self._is_capturing:
				self.error_occurred.emit(f"捕获过程中发生错误: {e}")
		finally:
			self._cleanup()
			self.capture_stopped.emit()

	def _process_component(self, component, pixel_format):
		width = component.width
		height = component.height
		data = component.data
		try:
			if 'YUV422' in pixel_format or (data.nbytes == width * height * 2 and component.data_format != 'Mono8'):
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
		print("正在清理相机硬件资源 (ia object)...")
		if self.ia:
			try:
				if self.ia.is_acquiring():
					self.ia.stop()
				self.ia.destroy()
			except Exception as e:
				print(f"清理 ia 资源时发生了一个可忽略的错误: {e}")
			finally:
				self.ia = None
		print("相机硬件资源已释放。")
