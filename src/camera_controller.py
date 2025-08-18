# camera_controller.py
# 作用: 提供一个独立于UI的相机控制器。
# 新架构: 控制器在选中相机时被创建，并立即初始化相机硬件(ia)和后台控制线程。
#          这使得在启动视频流之前就可以访问和修改相机参数。
# 修复: 为 ia.fetch() 增加超时以防止关闭时死锁。

import threading
import time
from PySide6.QtCore import QObject, Signal, Slot, QThread
import cv2
import numpy as np


class CameraController(QObject):
	"""
	相机控制器，在新架构下，它的生命周期与选中的相机绑定。
	创建实例时，会自动初始化相机硬件和后台线程。
	"""
	# 信号
	error_occurred = Signal(str)
	capture_stopped = Signal()  # 信号：当控制器及其线程完全停止时发出
	new_frame_data = Signal(dict)

	def __init__(self, harvester, device_index=0, fps=30):
		super().__init__()
		self.harvester = harvester
		self.device_index = device_index
		self.fps = fps if fps > 0 else 30
		print(f"相机控制器已使用帧率进行初始化: {self.fps} FPS")

		# 状态标志
		self._is_running = False  # 控制整个线程的生命周期
		self._is_acquiring = False  # 控制是否进行图像采集 (ia.fetch)

		# 资源
		self.ia = None
		self.thread = None
		self.lock = threading.Lock()
		self.latest_frame = None

		try:
			# 立即创建相机接口 (ia)，这是此架构的核心
			self.ia = self.harvester.create(self.device_index)
			print(f"相机接口(ia)已为设备 {self.device_index} 创建。")

			# 创建并启动后台控制线程
			self._is_running = True
			self.thread = QThread()
			self.moveToThread(self.thread)

			# 连接信号和槽
			self.thread.started.connect(self._capture_loop)
			self.thread.finished.connect(self._cleanup)

			self.thread.start()
			print("相机控制线程已启动。")

		except Exception as e:
			self.error_occurred.emit(f"创建相机控制器失败: {e}")
			self._is_running = False
			self.ia = None

	def start_capture(self):
		"""命令后台线程开始采集图像。"""
		if self.ia and self._is_running:
			print("命令: 开始采集图像。")
			self._is_acquiring = True
			return True
		print("警告: 无法启动采集，控制器未就绪。")
		return False

	def stop_capture(self):
		"""命令后台线程停止采集图像。"""
		print("命令: 停止采集图像。")
		self._is_acquiring = False

	def destroy(self):
		"""
		彻底销毁控制器。此方法会阻塞，直到后台线程完全终止。
		"""
		print("命令: 销毁相机控制器。")
		if not self.thread or not self.thread.isRunning():
			print("线程未运行，直接清理。")
			self._cleanup()
			return

		# 1. 发送停止信号
		self.stop_capture()
		self._is_running = False

		# 2. 请求线程的事件循环退出
		self.thread.quit()

		# 3. 等待线程执行完毕
		print("正在等待相机控制线程终止...")
		if self.thread.wait(3000):  # 3秒超时
			print("相机控制线程已成功终止。")
		else:
			print("警告: 相机控制线程未能正常终止。")

	def _capture_loop(self):
		"""
		在后台线程中运行的主循环。
		它会持续运行，并根据 _is_acquiring 标志决定是否执行图像采集。
		"""
		print("后台捕获循环已进入。")
		try:
			while self._is_running:
				if self._is_acquiring:
					try:
						self.ia.start()
						print("相机硬件流已启动。")

						pixel_format = self.ia.remote_device.node_map.PixelFormat.value
						target_frame_duration = 1.0 / self.fps

						while self._is_acquiring and self._is_running:
							loop_start_time = time.perf_counter()
							try:
								# --- 核心修复: 为fetch增加超时，防止死锁 ---
								with self.ia.fetch(timeout=0.5) as buffer:
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
							except TimeoutError:
								# 超时是正常的，意味着没有新帧。这让循环有机会检查_is_running标志。
								continue

							processing_time = time.perf_counter() - loop_start_time
							sleep_duration = target_frame_duration - processing_time
							if sleep_duration > 0:
								# 使用 QThread.msleep() 替代 time.sleep()
								self.thread.msleep(int(sleep_duration * 1000))

					except Exception as e:
						if self._is_running:
							self.error_occurred.emit(f"捕获过程中发生错误: {e}")
						self._is_acquiring = False
					finally:
						if self.ia and self.ia.is_acquiring():
							self.ia.stop()
							print("相机硬件流已停止。")
				else:
					self.thread.msleep(50)
		finally:
			print("捕获循环已终止。")
			self.capture_stopped.emit()

	def _cleanup(self):
		"""清理Harvester的ia资源。此方法在线程结束时自动调用。"""
		print("正在清理相机硬件资源 (ia object)...")
		if self.ia:
			try:
				self.ia.destroy()
			except Exception as e:
				print(f"清理 ia 资源时发生了一个可忽略的错误: {e}")
			finally:
				self.ia = None
		print("相机硬件资源已释放。")

	def _process_component(self, component, pixel_format):
		"""处理图像帧数据 (此部分逻辑未改变)。"""
		width, height, data = component.width, component.height, component.data
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
					if 'Mono12' in pixel_format: shift = 4
					elif 'Mono10' in pixel_format: shift = 6
					mono_image = (img_16bit >> shift).astype(np.uint8)
				return cv2.cvtColor(mono_image, cv2.COLOR_GRAY2BGR)

			self.error_occurred.emit(f"无法确定或不支持的像素格式: {pixel_format}")
			self.stop_capture()
			return None
		except Exception as e:
			self.error_occurred.emit(f"处理图像帧时出错: {e}")
			self.stop_capture()
			return None
