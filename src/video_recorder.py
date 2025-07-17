# video_recorder.py
# 作用: 提供一个线程化的视频录制器，将耗时的写文件操作放在独立线程中，避免阻塞主程序。
import os

dll_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'third_party'))
os.environ['PATH'] = dll_path + os.pathsep + os.environ['PATH']
import cv2
import queue
from PySide6.QtCore import QObject, Slot, QThread, Signal
import numpy as np


class VideoRecorderWorker(QObject):
	"""
	一个在独立线程中运行的Worker，负责所有视频写入操作。
	"""
	finished = Signal()
	error = Signal(str)

	# --- 修改: 初始化时接收MJPEG质量参数 ---
	def __init__(self, filepath, fps, frame_size, recording_format='BGR', mjpeg_quality=95):
		super().__init__()
		self.filepath = filepath
		self.fps = fps
		self.frame_size = frame_size  # (width, height)
		self.recording_format = recording_format
		self.mjpeg_quality = mjpeg_quality
		self.writer = None
		self.frame_queue = queue.Queue(maxsize=300)
		self._is_running = False

	def run(self):
		"""主录制循环，将在独立线程中执行。"""
		self._is_running = True
		print(f"录制线程启动，文件: {self.filepath}, 格式: {self.recording_format}")

		try:
			if self.recording_format == 'YUV':
				# Quality Mode: 使用 'yuv2' 编码器保存为无压缩的YUV422 .mov 文件
				fourcc = cv2.VideoWriter_fourcc(*'yuv2')
				self.writer = cv2.VideoWriter(self.filepath, fourcc, self.fps, self.frame_size)
			else:  # 默认为 BGR (Compatibility Mode)
				# Compatibility Mode: 使用 MJPEG 编码器保存为 .avi 文件
				fourcc = cv2.VideoWriter_fourcc(*'MJPG')
				# --- 新增: 定义写入参数, 包含MJPEG质量 ---
				#params = [cv2.VIDEOWRITER_PROP_QUALITY, self.mjpeg_quality]
				#self.writer = cv2.VideoWriter(self.filepath, fourcc, self.fps, self.frame_size, params)
				self.writer = cv2.VideoWriter(self.filepath, fourcc, self.fps, self.frame_size)

			if not self.writer.isOpened():
				raise IOError(f"无法创建视频写入器，路径: {self.filepath}")

			while self._is_running:
				try:
					frame_data = self.frame_queue.get(timeout=1)
					if frame_data is None:
						break

					if self.recording_format == 'YUV':
						yuv_frame = frame_data.reshape(self.frame_size[1], self.frame_size[0], 2)
						self.writer.write(yuv_frame)
					else:
						self.writer.write(frame_data)

				except queue.Empty:
					continue

		except Exception as e:
			self.error.emit(f"录制线程发生错误: {e}")
		finally:
			if self.writer:
				self.writer.release()
			print("录制线程结束，文件已保存。")
			self.finished.emit()

	def add_frame_data_to_queue(self, frame_payload):
		"""根据录制格式，从负载字典中提取正确的数据并放入队列。"""
		if not self._is_running:
			return

		try:
			if self.recording_format == 'YUV':
				component = frame_payload.get('raw_component')
				if component:
					self.frame_queue.put_nowait(component.data.copy())
			else:  # BGR
				bgr_frame = frame_payload.get('bgr')
				if bgr_frame is not None:
					self.frame_queue.put_nowait(bgr_frame.copy())

		except queue.Full:
			print("警告: 录制帧队列已满，丢弃一帧。")

	def stop(self):
		"""请求停止录制循环。"""
		print("正在向录制线程发送停止信号...")
		self._is_running = False
		self.frame_queue.put(None)


class VideoRecorder(QObject):
	"""
	VideoRecorder 的主控制类。
	"""
	error = Signal(str)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.thread = None
		self.worker = None
		self.is_recording = False

	# --- 修改: 启动时接收MJPEG质量参数 ---
	def start_recording(self, filepath, fps, frame_size, recording_format, mjpeg_quality=95):
		if self.is_recording:
			print("警告: 录制已在进行中。")
			return False

		self.thread = QThread()
		# --- 修改: 将质量参数传递给Worker ---
		self.worker = VideoRecorderWorker(filepath, fps, frame_size, recording_format, mjpeg_quality)
		self.worker.moveToThread(self.thread)

		self.worker.finished.connect(self.thread.quit)
		self.worker.finished.connect(self.worker.deleteLater)
		self.thread.finished.connect(self.thread.deleteLater)
		self.thread.started.connect(self.worker.run)

		self.worker.error.connect(self.error)

		self.thread.start()
		self.is_recording = True
		return True

	@Slot(dict)
	def add_frame(self, frame_payload):
		"""将包含多种格式帧的字典传递给后台worker。"""
		if self.is_recording and self.worker:
			self.worker.add_frame_data_to_queue(frame_payload)

	def stop_recording(self):
		if not self.is_recording or not self.worker:
			return

		print("请求停止录制...")
		self.is_recording = False
		if self.thread and self.thread.isRunning():
			self.worker.stop()
			self.thread.quit()
			if not self.thread.wait(2000):
				print("警告: 录制线程未能正确停止。")

		self.worker = None
		self.thread = None
		print("录制已停止。")
