# main_window.py
# 作用: 定义应用程序的主窗口界面。
# 新架构: 修改了UI事件处理逻辑以适应新的CameraController生命周期。

import os
import subprocess
import sys
from PySide6.QtCore import Qt, Slot, QTimer, QThread, Signal
from PySide6.QtWidgets import (
	QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
	QPushButton, QLabel, QMessageBox, QSplitter, QListWidget, QListWidgetItem,
	QFrame, QFileDialog, QLineEdit, QComboBox, QButtonGroup, QAbstractButton,
	QSlider
)
import numpy as np
import cv2

import config_manager
from camera_setup import setup_harvester, cleanup_harvester
from camera_controller import CameraController  # 使用重构后的控制器
from video_player_controller import VideoPlayerController
from video_recorder import VideoRecorder
from plotting_widgets import MainPlottingWidget
from analysis_controller import AnalysisController
from video_preview_widget import VideoPreviewLabel


class DynamicComboBox(QComboBox):
	"""一个在显示弹出菜单前发射信号的自定义QComboBox。"""
	aboutToShowPopup = Signal()

	def __init__(self, parent=None):
		super().__init__(parent)

	def showPopup(self):
		self.aboutToShowPopup.emit()
		super().showPopup()


class MainWindow(QMainWindow):
	frame_to_analyze = Signal(object)

	def __init__(self):
		super().__init__()
		self.setWindowTitle("Rheed_analyzer")
		self.resize(1600, 900)

		self.load_app_config()

		# 初始化控制器引用
		self.harvester = None
		self.camera_controller = None  # 现在在选择时创建
		self.video_player_controller = None
		self.video_recorder = None

		self.is_first_frame = True
		self.current_frame_for_recording = None

		# 初始化分析线程 (无变化)
		self.analysis_controller = AnalysisController()
		self.analysis_thread = QThread()
		self.analysis_controller.moveToThread(self.analysis_thread)
		self.analysis_thread.start()
		print("分析控制器已移至后台线程。")

		# 初始化预览计时器
		self.camera_preview_timer = QTimer(self)
		self.camera_preview_timer.timeout.connect(self.update_camera_preview)

		# --- UI 创建 (大部分无变化) ---
		main_layout = QVBoxLayout()
		central_widget = QWidget()
		central_widget.setLayout(main_layout)
		self.setCentralWidget(central_widget)
		self._create_top_bar(main_layout)

		main_v_splitter = QSplitter(Qt.Orientation.Vertical)
		top_h_splitter = QSplitter(Qt.Orientation.Horizontal)
		left_v_splitter = QSplitter(Qt.Orientation.Vertical)

		camera_list_panel = self._create_camera_list_panel()
		self.camera_settings_panel = self._create_camera_settings_panel()
		video_panel = self._create_video_list_panel()

		left_v_splitter.addWidget(camera_list_panel)
		left_v_splitter.addWidget(self.camera_settings_panel)
		left_v_splitter.addWidget(video_panel)
		left_v_splitter.setSizes([200, 150, 200])

		center_panel = self._create_preview_panel()
		right_panel = self._create_right_panel()
		bottom_panel = self._create_bottom_interaction_panel()

		top_h_splitter.addWidget(left_v_splitter)
		top_h_splitter.addWidget(center_panel)
		top_h_splitter.addWidget(right_panel)
		top_h_splitter.setSizes([400, 650, 550])

		main_v_splitter.addWidget(top_h_splitter)
		main_v_splitter.addWidget(bottom_panel)
		main_v_splitter.setSizes([650, 250])
		main_layout.addWidget(main_v_splitter)

		self._set_default_values()
		self._connect_signals()  # 信号连接有重要修改

		if self.status_button_group.checkedButton():
			self._on_status_button_changed(self.status_button_group.checkedButton())
		initial_function = self.main_plot_widget.control_output.function_combo.currentText()
		self._on_function_selection_changed(initial_function)

	# ===================================================================
	# 架构重构后的核心逻辑
	# ===================================================================

	def _connect_signals(self):
		"""连接所有UI组件的信号和槽。"""
		self.find_button.clicked.connect(self._on_find_cameras)
		self.start_button.clicked.connect(self._on_start_capture)
		self.stop_button.clicked.connect(self._on_stop_capture)
		self.help_button.clicked.connect(self._on_show_help)

		# *** 核心修改: 当列表选择变化时，触发控制器创建/销毁 ***
		self.camera_list_widget.currentItemChanged.connect(self._on_camera_selection_changed)

		# 相机参数设置信号
		self.exposure_slider.valueChanged.connect(self._on_exposure_changed)
		self.pixel_format_combo.currentTextChanged.connect(self._on_pixel_format_changed)

		# 其他信号连接 (无变化)
		self.add_video_button.clicked.connect(self._on_add_video)
		self.remove_video_button.clicked.connect(self._on_remove_video)
		self.play_video_button.clicked.connect(self._on_play_video)
		self.pause_video_button.clicked.connect(self._on_pause_video)
		self.stop_video_button.clicked.connect(self._on_stop_video)
		self.video_list_widget.currentItemChanged.connect(self._on_video_selected)
		self.browse_path_button.clicked.connect(self._on_browse_save_path)
		self.start_record_button.clicked.connect(self._on_start_recording)
		self.stop_record_button.clicked.connect(self._on_stop_recording)
		self.save_path_edit.editingFinished.connect(self._on_save_path_changed)
		self.main_plot_widget.control_output.select_area_button.clicked.connect(self.image_view.enter_selection_mode)
		self.image_view.roi_defined.connect(self.analysis_controller.set_roi)
		self.main_plot_widget.dynamic_plot.clear_button.clicked.connect(self.analysis_controller.clear_dynamic_data)
		self.frame_to_analyze.connect(self.analysis_controller.process_frame_for_analysis)
		self.analysis_controller.data_cleared.connect(self.main_plot_widget.dynamic_plot.clear_plot)
		self.analysis_controller.data_point_generated.connect(self.main_plot_widget.dynamic_plot.add_point)
		self.analysis_controller.analysis_result_ready.connect(self.main_plot_widget.control_output.set_result_text)
		self.main_plot_widget.static_plot.analysis_requested.connect(self._handle_analysis_request)
		self.main_plot_widget.control_output.function_combo.currentTextChanged.connect(
			self._on_function_selection_changed)
		self.status_button_group.buttonClicked.connect(self._on_status_button_changed)
		self.substrate_combo.aboutToShowPopup.connect(self._populate_substrate_combo)
		self.material_combo.aboutToShowPopup.connect(self._populate_material_combo)
		self.edit_substrate_button.clicked.connect(self._on_edit_substrate_list)
		self.edit_material_button.clicked.connect(self._on_edit_material_list)

	@Slot(QListWidgetItem, QListWidgetItem)
	def _on_camera_selection_changed(self, current, previous):
		"""
		当相机列表中的选择项改变时，此槽被调用。
		它负责销毁旧的相机控制器并为新选项创建新的控制器。
		"""
		# 1. 停止所有活动并销毁旧的控制器
		self._stop_all_sources()
		if self.camera_controller:
			print("相机选择已改变，正在销毁旧的控制器...")
			self.camera_controller.destroy()
			self.camera_controller.deleteLater()  # 请求Qt安全地删除对象
			self.camera_controller = None

		# 2. 如果有新的有效选项，则创建新的控制器
		if current and self.harvester:
			device_index = current.data(Qt.ItemDataRole.UserRole)
			print(f"正在为设备索引 {device_index} 创建新的CameraController...")
			try:
				# 创建新的控制器实例
				self.camera_controller = CameraController(
					harvester=self.harvester,
					device_index=device_index,
					fps=self.camera_fps
				)
				# 为新控制器连接信号
				self.camera_controller.new_frame_data.connect(self.update_camera_preview)
				self.camera_controller.error_occurred.connect(self.show_error_message)
				self.camera_controller.capture_stopped.connect(self._on_camera_controller_fully_stopped)

				# 立即更新相机参数UI
				self._update_camera_settings_controls()

			except Exception as e:
				self.show_error_message(f"初始化相机失败: {e}")
				self.camera_controller = None

		# 3. 更新UI按钮状态
		self._update_ui_state()

	@Slot()
	def _on_start_capture(self):
		"""启动相机图像流。"""
		if self.camera_controller and self.camera_controller.start_capture():
			self._on_source_started()
			self.camera_preview_timer.start(1000 // self.preview_fps)
			self._update_ui_state()
		else:
			self.show_error_message("无法启动相机捕获。控制器可能未就绪。")

	@Slot()
	def _on_stop_capture(self):
		"""停止相机图像流。"""
		if self.camera_controller:
			self.camera_preview_timer.stop()
			self.camera_controller.stop_capture()
			self._update_ui_state()

	def _update_camera_settings_controls(self):
		"""当相机连接时，更新曝光和像素格式控件。"""
		if not self.camera_controller or not self.camera_controller.ia:
			self.camera_settings_panel.setEnabled(False)
			return

		try:
			node_map = self.camera_controller.ia.remote_device.node_map
			self.camera_settings_panel.setEnabled(True)

			# 更新曝光滑块
			self.exposure_slider.blockSignals(True)
			exposure_node = node_map.ExposureTimeAbs
			min_exp, max_exp = int(exposure_node.min), int(exposure_node.max)
			current_exp = int(exposure_node.value)
			self.exposure_slider.setRange(min_exp, max_exp)
			self.exposure_slider.setValue(current_exp)
			self.exposure_label.setText(f"{current_exp}")
			self.exposure_slider.blockSignals(False)
			print(f"曝光时间已更新: 范围 [{min_exp}, {max_exp}], 当前值: {current_exp}")

			# 更新像素格式下拉框
			self.pixel_format_combo.blockSignals(True)
			self.pixel_format_combo.clear()
			pixel_format_node = node_map.PixelFormat
			available_formats = pixel_format_node.symbolics
			current_format = pixel_format_node.value
			self.pixel_format_combo.addItems(available_formats)
			self.pixel_format_combo.setCurrentText(current_format)
			self.pixel_format_combo.blockSignals(False)
			print(f"像素格式已更新: 可用项 {available_formats}, 当前值: {current_format}")

		except Exception as e:
			print(f"无法更新相机参数控件: {e}")
			self.camera_settings_panel.setEnabled(False)
			self.show_error_message(f"无法获取相机参数: {e}")

	@Slot(int)
	def _on_exposure_changed(self, value):
		"""当曝光滑块值改变时，设置相机曝光。"""
		if self.camera_controller and self.camera_controller.ia:
			try:
				self.camera_controller.ia.remote_device.node_map.ExposureTimeAbs.value = float(value)
				self.exposure_label.setText(f"{value}")
			except Exception as e:
				print(f"设置曝光时间失败: {e}")

	@Slot(str)
	def _on_pixel_format_changed(self, format_str):
		"""当像素格式下拉框值改变时，设置相机像素格式。"""
		if self.camera_controller and self.camera_controller.ia and format_str:
			try:
				self.camera_controller.ia.remote_device.node_map.PixelFormat.value = format_str
				print(f"像素格式已成功切换为: {format_str}")
			except Exception as e:
				print(f"设置像素格式失败: {e}")
				self.show_error_message(f"无法将像素格式设置为 {format_str}。\n错误: {e}")
				self._update_camera_settings_controls()

	def _update_ui_state(self):
		"""根据当前程序状态更新所有UI组件的启用/禁用状态。"""
		# 核心状态判断
		is_cam_controller_valid = self.camera_controller is not None and self.camera_controller.ia is not None
		is_cam_acquiring = is_cam_controller_valid and self.camera_controller._is_acquiring
		is_vid_active = self.video_player_controller is not None
		is_vid_paused = is_vid_active and self.video_player_controller._is_paused
		is_media_active = is_cam_acquiring or is_vid_active
		is_recording = self.video_recorder is not None and self.video_recorder.is_recording
		can_change_source = not is_media_active and not is_recording

		# 更新UI元素状态
		self.find_button.setEnabled(can_change_source)
		self.camera_list_widget.setEnabled(can_change_source)

		# 相机控制按钮
		self.start_button.setEnabled(
			is_cam_controller_valid and not is_cam_acquiring and not is_vid_active and not is_recording)
		self.stop_button.setEnabled(is_cam_acquiring and not is_recording)

		# 相机参数面板
		self.camera_settings_panel.setEnabled(is_cam_controller_valid and not is_recording)

		# 视频控制按钮
		self.add_video_button.setEnabled(can_change_source)
		self.remove_video_button.setEnabled(can_change_source)
		self.play_video_button.setEnabled(
			(can_change_source and self.video_list_widget.currentItem() is not None) or is_vid_paused)
		self.pause_video_button.setEnabled(is_vid_active and not is_vid_paused and not is_recording)
		self.stop_video_button.setEnabled(is_vid_active and not is_recording)
		self.video_list_widget.setEnabled(can_change_source)

		# 录制按钮
		self.start_record_button.setEnabled(is_media_active and not is_recording)
		self.stop_record_button.setEnabled(is_recording)

		if not is_media_active:
			self.image_view.set_frame(None)
			self.frame_to_analyze.emit(None)
			self.current_frame_for_recording = None

	def closeEvent(self, event):
		"""在关闭窗口前，确保所有资源被正确释放。"""
		self._on_save_path_changed()
		print("正在关闭窗口并清理所有线程...")
		self._on_stop_recording()

		# 销毁相机和视频控制器
		if self.camera_controller:
			self.camera_controller.destroy()
		if self.video_player_controller:
			self.video_player_controller.stop()

		# 等待线程结束
		if self.camera_controller and self.camera_controller.thread and not self.camera_controller.thread.wait(3000):
			print("警告: 相机线程未能正常终止。")
		if self.video_player_controller and self.video_player_controller.thread and not self.video_player_controller.thread.wait(
				2000):
			print("警告: 视频播放器线程未能正常终止。")

		# 清理分析线程和Harvester
		if self.analysis_thread.isRunning():
			self.analysis_thread.quit()
			if not self.analysis_thread.wait(2000):
				print("警告: 分析线程未能正常终止。")
		if self.harvester:
			cleanup_harvester(self.harvester)

		print("所有资源已清理，程序退出。")
		event.accept()

	# ===================================================================
	# 其余未修改或仅微调的方法
	# ===================================================================

	def _stop_all_sources(self):
		"""停止所有活动的媒体源。"""
		if self.camera_preview_timer.isActive():
			self.camera_preview_timer.stop()
		if self.camera_controller:
			self.camera_controller.stop_capture()  # 只停止采集，不销毁
		if self.video_player_controller:
			self.video_player_controller.stop()

	@Slot()
	def update_camera_preview(self):
		if not self.camera_controller or not self.camera_controller.lock: return
		frame_copy = None
		with self.camera_controller.lock:
			if self.camera_controller.latest_frame is not None:
				frame_copy = self.camera_controller.latest_frame.copy()
		if frame_copy is not None:
			self._display_frame(frame_copy)
			self.frame_to_analyze.emit(frame_copy)

	@Slot(dict)
	def update_video_preview(self, frame_payload):
		bgr_frame = frame_payload.get('bgr')
		if bgr_frame is not None:
			self._display_frame(bgr_frame)
			self.frame_to_analyze.emit(bgr_frame)

	def _display_frame(self, frame):
		try:
			self.current_frame_for_recording = frame
			rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
			self.image_view.set_frame(rgb_frame)
		except Exception as e:
			print(f"显示帧时出错: {e}")

	@Slot()
	def _on_camera_controller_fully_stopped(self):
		"""当相机控制器线程完全结束时调用。"""
		print("主窗口收到信号：相机控制器已完全停止。")
		# 在新架构下，这个槽函数的重要性降低了，
		# 因为控制器的生命周期由_on_camera_selection_changed管理。
		# 我们可以选择在这里清理对控制器的引用，以防万一。
		if self.camera_controller and not self.camera_controller.thread.isRunning():
			self.camera_controller = None
		self._update_ui_state()

	@Slot()
	def _on_playback_fully_stopped(self):
		if self.video_player_controller:
			self.video_player_controller.deleteLater()
			self.video_player_controller = None
		self._update_ui_state()

	@Slot(str)
	def show_error_message(self, message):
		QMessageBox.critical(self, "错误", message)
		self._update_ui_state()

	@Slot()
	def _on_find_cameras(self):
		if self.harvester:
			cleanup_harvester(self.harvester)
		self.camera_list_widget.clear()
		QApplication.processEvents()
		self.harvester = setup_harvester(self.cti_path)
		if self.harvester and self.harvester.device_info_list:
			for i, di in enumerate(self.harvester.device_info_list):
				item = QListWidgetItem(f"相机 {i} ({di.model})")
				item.setData(Qt.ItemDataRole.UserRole, i)
				self.camera_list_widget.addItem(item)
		else:
			QMessageBox.warning(self, "未找到设备", f"在路径 '{self.cti_path}' 未能发现任何相机设备。")

	# --- 以下方法基本无变化 ---

	def _create_camera_settings_panel(self):
		panel = QFrame()
		panel.setFrameShape(QFrame.Shape.StyledPanel)
		layout = QGridLayout(panel)
		layout.setContentsMargins(5, 5, 5, 5)
		layout.setSpacing(8)
		title_label = QLabel("相机参数设置:")
		layout.addWidget(title_label, 0, 0, 1, 2)
		layout.addWidget(QLabel("曝光时间 (µs):"), 1, 0)
		self.exposure_slider = QSlider(Qt.Orientation.Horizontal)
		self.exposure_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
		self.exposure_slider.setTickInterval(10000)
		layout.addWidget(self.exposure_slider, 2, 0)
		self.exposure_label = QLabel("N/A")
		self.exposure_label.setMinimumWidth(60)
		self.exposure_label.setAlignment(Qt.AlignmentFlag.AlignRight)
		layout.addWidget(self.exposure_label, 2, 1)
		layout.addWidget(QLabel("像素格式:"), 3, 0)
		self.pixel_format_combo = DynamicComboBox()
		layout.addWidget(self.pixel_format_combo, 4, 0, 1, 2)
		panel.setEnabled(False)
		return panel

	def load_app_config(self):
		try:
			self.cti_path = config_manager.get_config_value('Paths', 'cti_path')
			self.camera_fps = int(config_manager.get_config_value('Camera', 'fps', '30'))
			home_dir = os.path.expanduser('~')
			default_save_path = os.path.join(home_dir, "Desktop", "GrowthRecordings")
			self.save_path = config_manager.get_config_value('Paths', 'save_path', default_save_path)
			self.preview_fps = int(config_manager.get_config_value('Display', 'preview_fps', '60'))
			self.recording_mode = config_manager.get_config_value('Recording', 'mode', 'Compatibility')
			self.mjpeg_quality = int(config_manager.get_config_value('Recording', 'mjpeg_quality', '95'))
			if self.preview_fps <= 0: self.preview_fps = 60
			if not (0 <= self.mjpeg_quality <= 100): self.mjpeg_quality = 95
		except Exception as e:
			QMessageBox.warning(self, "配置错误", f"加载 config.ini 失败: {e}\n将使用默认设置。")

	# ... (fallback values)

	@Slot()
	def _on_play_video(self):
		if self.video_player_controller and self.video_player_controller._is_paused:
			self.video_player_controller.play()
			self._update_ui_state()
			return
		current_item = self.video_list_widget.currentItem()
		if not current_item: return
		self._stop_all_sources()
		filepath = current_item.data(Qt.ItemDataRole.UserRole)
		self.video_player_controller = VideoPlayerController()
		self.video_player_controller.new_frame_data.connect(self.update_video_preview)
		self.video_player_controller.error_occurred.connect(self.show_error_message)
		self.video_player_controller.playback_stopped.connect(self._on_playback_fully_stopped)
		self.video_player_controller.load_video(filepath)
		self.video_player_controller.play()
		self._on_source_started()

	@Slot()
	def _on_start_recording(self):
		source = None
		if self.camera_controller and self.camera_controller._is_acquiring:
			source = self.camera_controller
		elif self.video_player_controller:
			source = self.video_player_controller

		if not source:
			self.show_error_message("没有正在预览的视频源，无法录制。")
			return
		# ... (rest of recording logic is unchanged)
		base_save_path = self.save_path_edit.text()
		furnace_id = self.furnace_id_edit.text()
		if not base_save_path or not furnace_id:
			self.show_error_message("请填写“炉号”和“保存路径”。")
			return

		recording_format_to_use = 'BGR'
		if self.recording_mode == 'Quality' and isinstance(source, CameraController):
			try:
				cam_pixel_format = source.ia.remote_device.node_map.PixelFormat.value
				if 'YUV' in cam_pixel_format:
					recording_format_to_use = 'YUV'
					print("检测到YUV相机，将使用高质量(YUV)模式录制。")
			except Exception as e:
				print(f"无法获取相机像素格式，将使用兼容模式: {e}")

		file_extension = ".mov" if recording_format_to_use == 'YUV' else ".avi"

		checked_button = self.status_button_group.checkedButton()
		if not checked_button:
			self.show_error_message("请选择一个状态。")
			return
		status_text = checked_button.text()
		if self.other_status_edit.text():
			status_filename = self.other_status_edit.text().strip()
		else:
			status_map = {"脱氧前": "non", "脱氧后": "deo", "开始生长": "start", "生长中": "growth", "结束生长": "end"}
			status_filename = status_map.get(status_text, status_text)
			if status_text in ["脱氧前", "脱氧后"]:
				substrate = self.substrate_combo.currentText()
				if substrate: status_filename += f"_{substrate}"
			elif status_text in ["开始生长", "生长中", "结束生长"]:
				material = self.material_combo.currentText()
				if material: status_filename += f"_{material}"

		furnace_dir = os.path.join(base_save_path, furnace_id)
		os.makedirs(furnace_dir, exist_ok=True)
		base_filepath_part = os.path.join(furnace_dir, status_filename)
		full_filepath = f"{base_filepath_part}{file_extension}"
		counter = 1
		while os.path.exists(full_filepath):
			full_filepath = f"{base_filepath_part}_{counter}{file_extension}"
			counter += 1
		full_filepath = full_filepath.replace("\\", "/")

		fps = source.fps
		if self.current_frame_for_recording is not None:
			h, w, _ = self.current_frame_for_recording.shape
			frame_size = (w, h)
		else:
			self.show_error_message("无法获取预览帧的分辨率。")
			return

		self.video_recorder = VideoRecorder(self)
		self.video_recorder.error.connect(self.show_error_message)

		if isinstance(source, CameraController):
			source.new_frame_data.connect(self.video_recorder.add_frame)
		elif isinstance(source, VideoPlayerController):
			source.new_frame_data.connect(self.video_recorder.add_frame)

		if self.video_recorder.start_recording(full_filepath, fps, frame_size, recording_format_to_use,
											   self.mjpeg_quality):
			self._update_recording_ui(True)
		else:
			self.show_error_message(f"启动录制失败，请检查路径和权限。\n{full_filepath}")
			self.video_recorder = None

	@Slot()
	def _on_stop_recording(self):
		if self.video_recorder:
			source = None
			if self.camera_controller and self.camera_controller._is_acquiring:
				source = self.camera_controller
			elif self.video_player_controller:
				source = self.video_player_controller

			if source:
				try:
					source.new_frame_data.disconnect(self.video_recorder.add_frame)
				except RuntimeError:
					pass  # Signal may already be disconnected
			self.video_recorder.stop_recording()
			self.video_recorder = None
			self._update_recording_ui(False)

	def _create_preview_panel(self):
		self.image_view = VideoPreviewLabel()
		return self.image_view

	def _create_right_panel(self):
		self.main_plot_widget = MainPlottingWidget()
		return self.main_plot_widget

	def _create_top_bar(self, parent_layout):
		top_bar_layout = QHBoxLayout()
		self.help_button = QPushButton("?")
		self.help_button.setToolTip("打开使用说明文件 (usage.txt)")
		self.help_button.setFixedWidth(35)
		top_bar_layout.addWidget(self.help_button)
		top_bar_layout.addStretch()
		parent_layout.addLayout(top_bar_layout)

	def _create_camera_list_panel(self):
		panel = QFrame()
		panel.setFrameShape(QFrame.Shape.StyledPanel)
		layout = QVBoxLayout(panel)
		layout.setContentsMargins(2, 2, 2, 2)
		layout.addWidget(QLabel("可用相机列表:"))
		self.camera_list_widget = QListWidget()
		layout.addWidget(self.camera_list_widget)
		button_layout = QHBoxLayout()
		self.find_button = QPushButton("查找相机")
		self.start_button = QPushButton("启动相机")
		self.stop_button = QPushButton("停止相机")
		self.start_button.setEnabled(False)
		self.stop_button.setEnabled(False)
		for btn in [self.find_button, self.start_button, self.stop_button]:
			btn.setMinimumHeight(30)
		button_layout.addWidget(self.find_button)
		button_layout.addWidget(self.start_button)
		button_layout.addWidget(self.stop_button)
		button_layout.addStretch()
		layout.addLayout(button_layout)
		return panel

	def _create_video_list_panel(self):
		panel = QFrame()
		panel.setFrameShape(QFrame.Shape.StyledPanel)
		layout = QVBoxLayout(panel)
		layout.setContentsMargins(2, 2, 2, 2)
		layout.addWidget(QLabel("视频文件列表:"))
		self.video_list_widget = QListWidget()
		layout.addWidget(self.video_list_widget)
		button_layout = QHBoxLayout()
		self.add_video_button = QPushButton("添加视频")
		self.remove_video_button = QPushButton("移除视频")
		self.play_video_button = QPushButton("▶")
		self.pause_video_button = QPushButton("❚❚")
		self.stop_video_button = QPushButton("■")
		self.add_video_button.setToolTip("添加视频文件")
		self.remove_video_button.setToolTip("移除选中视频")
		self.play_video_button.setToolTip("播放/恢复")
		self.pause_video_button.setToolTip("暂停")
		self.stop_video_button.setToolTip("停止")
		for btn in [self.add_video_button, self.remove_video_button, self.play_video_button, self.pause_video_button,
					self.stop_video_button]:
			btn.setMinimumHeight(30)
		button_layout.addWidget(self.add_video_button)
		button_layout.addWidget(self.remove_video_button)
		button_layout.addStretch()
		button_layout.addWidget(self.play_video_button)
		button_layout.addWidget(self.pause_video_button)
		button_layout.addWidget(self.stop_video_button)
		self.play_video_button.setEnabled(False)
		self.pause_video_button.setEnabled(False)
		self.stop_video_button.setEnabled(False)
		layout.addLayout(button_layout)
		return panel

	def _create_bottom_interaction_panel(self):
		panel = QFrame()
		panel.setFrameShape(QFrame.Shape.StyledPanel)
		layout = QGridLayout(panel)
		layout.setSpacing(10)
		layout.addWidget(QLabel("炉号:"), 0, 0, Qt.AlignmentFlag.AlignRight)
		self.furnace_id_edit = QLineEdit()
		self.furnace_id_edit.setMaximumWidth(200)
		layout.addWidget(self.furnace_id_edit, 0, 1)
		layout.addWidget(QLabel("状态:"), 0, 2, Qt.AlignmentFlag.AlignRight)
		self.status_button_group = QButtonGroup(self)
		self.status_button_group.setExclusive(True)
		deo_layout = QVBoxLayout()
		btn_non = QPushButton("脱氧前")
		btn_non.setMinimumHeight(30)
		btn_deo = QPushButton("脱氧后")
		btn_deo.setMinimumHeight(30)
		for btn in [btn_non, btn_deo]:
			btn.setCheckable(True)
			self.status_button_group.addButton(btn)
			deo_layout.addWidget(btn)
		layout.addLayout(deo_layout, 0, 3, 2, 1)
		substrate_v_layout = QVBoxLayout()
		substrate_v_layout.addSpacing(7)
		self.substrate_combo = DynamicComboBox()
		self.substrate_combo.setToolTip("选择衬底类型 (从substrate.txt读取)")
		self.substrate_combo.setFixedWidth(150)
		substrate_v_layout.addWidget(self.substrate_combo)
		self.edit_substrate_button = QPushButton("编辑衬底列表...")
		substrate_v_layout.addWidget(self.edit_substrate_button)
		substrate_v_layout.addStretch(1)
		layout.addLayout(substrate_v_layout, 0, 4, 2, 1)
		growth_layout = QVBoxLayout()
		btn_start = QPushButton("开始生长")
		btn_start.setMinimumHeight(30)
		btn_growth = QPushButton("生长中")
		btn_growth.setMinimumHeight(30)
		btn_end = QPushButton("结束生长")
		btn_end.setMinimumHeight(30)
		for btn in [btn_start, btn_growth, btn_end]:
			btn.setCheckable(True)
			self.status_button_group.addButton(btn)
			growth_layout.addWidget(btn)
		layout.addLayout(growth_layout, 0, 5, 3, 1)
		material_v_layout = QVBoxLayout()
		material_v_layout.addSpacing(7)
		self.material_combo = DynamicComboBox()
		self.material_combo.setToolTip("选择生长材料 (从epi_layer.txt读取)")
		self.material_combo.setFixedWidth(300)
		material_v_layout.addWidget(self.material_combo)
		self.edit_material_button = QPushButton("编辑外延材料列表...")
		material_v_layout.addWidget(self.edit_material_button)
		material_v_layout.addStretch(1)
		layout.addLayout(material_v_layout, 0, 6, 3, 1)
		btn_non.setChecked(True)
		self.start_record_button = QPushButton("开始录制")
		self.stop_record_button = QPushButton("结束录制")
		self.stop_record_button.setEnabled(False)
		self.start_record_button.setMinimumHeight(35)
		self.stop_record_button.setMinimumHeight(35)
		layout.addWidget(self.start_record_button, 0, 7)
		layout.addWidget(self.stop_record_button, 1, 7)
		self.bottom_status_label = QLabel("备用 (打印机器学习模型预测状态等)")
		self.bottom_status_label.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Sunken)
		self.bottom_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
		layout.addWidget(self.bottom_status_label, 0, 9, 5, 2)
		layout.addWidget(QLabel("其他状态:"), 3, 0, Qt.AlignmentFlag.AlignRight)
		self.other_status_edit = QLineEdit()
		layout.addWidget(self.other_status_edit, 3, 1, 1, 8)
		layout.addWidget(QLabel("保存路径:"), 4, 0, Qt.AlignmentFlag.AlignRight)
		self.save_path_edit = QLineEdit()
		self.browse_path_button = QPushButton("浏览...")
		layout.addWidget(self.save_path_edit, 4, 1, 1, 7)
		layout.addWidget(self.browse_path_button, 4, 8)
		layout.setColumnStretch(10, 1)
		layout.setRowStretch(5, 1)
		return panel

	def _set_default_values(self):
		self.furnace_id_edit.setText("AI2233")
		self.save_path_edit.setText(self.save_path.replace("\\", "/"))

	def _update_recording_ui(self, is_recording):
		self.start_record_button.setEnabled(not is_recording)
		self.stop_record_button.setEnabled(is_recording)
		self._update_ui_state()

	def _on_source_started(self):
		self.is_first_frame = True
		self.analysis_controller.clear_dynamic_data()
		self.main_plot_widget.dynamic_plot.clear_plot()
		self._update_ui_state()

	@Slot()
	def _on_pause_video(self):
		if self.video_player_controller: self.video_player_controller.pause(); self._update_ui_state()

	@Slot()
	def _on_stop_video(self):
		if self.video_player_controller: self.video_player_controller.stop()

	@Slot()
	def _on_video_selected(self, item):
		self._update_ui_state()

	@Slot()
	def _on_add_video(self):
		current_path = self.save_path_edit.text()
		files, _ = QFileDialog.getOpenFileNames(self, "选择视频文件", current_path,
												"视频文件 (*.mp4 *.avi *.mov *.mkv)")
		if files:
			for file_path in files:
				item = QListWidgetItem(os.path.basename(file_path))
				item.setData(Qt.ItemDataRole.UserRole, file_path)
				self.video_list_widget.addItem(item)

	@Slot()
	def _on_remove_video(self):
		current_item = self.video_list_widget.currentItem()
		if current_item: self.video_list_widget.takeItem(self.video_list_widget.row(current_item))

	@Slot()
	def _on_browse_save_path(self):
		current_path = self.save_path_edit.text()
		directory = QFileDialog.getExistingDirectory(self, "选择视频保存文件夹", current_path)
		if directory:
			new_path = directory.replace("\\", "/")
			self.save_path_edit.setText(new_path)
			self._on_save_path_changed()

	@Slot()
	def _on_save_path_changed(self):
		new_path = self.save_path_edit.text()
		config_manager.set_config_value('Paths', 'save_path', new_path)
		print(f"保存路径已更新到 config.ini: {new_path}")

	def _open_file_for_editing(self, filename, default_content=""):
		try:
			if not os.path.exists(filename):
				QMessageBox.information(self, "提示", f"文件 {filename} 未找到。将为您创建一个新文件。")
				with open(filename, 'w', encoding='utf-8') as f:
					f.write(f"# 在此文件中添加条目，每行一个。\n{default_content}")
			if sys.platform == "win32":
				os.startfile(filename)
			elif sys.platform == "darwin":
				subprocess.call(["open", filename])
			else:
				subprocess.call(["xdg-open", filename])
		except Exception as e:
			self.show_error_message(f"无法打开文件 {filename}:\n{e}")

	@Slot()
	def _on_show_help(self):
		self._open_file_for_editing('usage.txt', "使用说明...")

	@Slot()
	def _on_edit_substrate_list(self):
		self.substrate_combo.hidePopup()
		self._open_file_for_editing('substrate.txt', "#请用-连接衬底材料和钼托规格\nInAs\nGaSb\nInAs-1X4\n")

	@Slot()
	def _on_edit_material_list(self):
		self.material_combo.hidePopup()
		self._open_file_for_editing('epi_layer.txt', "#请用下划线而不是斜杠分割超晶格\nInAs\nInAs_GaSb\n")

	def _read_items_from_file(self, file_path):
		items = []
		if not os.path.exists(file_path): return items
		try:
			with open(file_path, 'r', encoding='utf-8') as f:
				for line in f:
					line = line.strip()
					if line and not line.startswith('#'):
						items.append(line)
		except Exception as e:
			print(f"读取文件时出错 {file_path}: {e}")
		return items

	@Slot()
	def _populate_substrate_combo(self):
		current_selection = self.substrate_combo.currentText()
		self.substrate_combo.clear()
		self.substrate_combo.addItem("")
		items = self._read_items_from_file('substrate.txt')
		self.substrate_combo.addItems(items)
		index = self.substrate_combo.findText(current_selection)
		if index != -1: self.substrate_combo.setCurrentIndex(index)

	@Slot()
	def _populate_material_combo(self):
		current_selection = self.material_combo.currentText()
		self.material_combo.clear()
		self.material_combo.addItem("")
		items = self._read_items_from_file('epi_layer.txt')
		self.material_combo.addItems(items)
		index = self.material_combo.findText(current_selection)
		if index != -1: self.material_combo.setCurrentIndex(index)

	@Slot(QAbstractButton)
	def _on_status_button_changed(self, button):
		text = button.text()
		is_deo_step = text in ["脱氧前", "脱氧后"]
		is_growth_step = text in ["开始生长", "生长中", "结束生长"]
		self.substrate_combo.setEnabled(is_deo_step)
		self.material_combo.setEnabled(is_growth_step)
		if not is_deo_step: self.substrate_combo.setCurrentIndex(0)
		if not is_growth_step: self.material_combo.setCurrentIndex(0)

	@Slot(np.ndarray, np.ndarray)
	def _handle_analysis_request(self, x_data, y_data):
		selected_function = self.main_plot_widget.control_output.function_combo.currentText()
		if selected_function == "亮度振荡分析":
			self.analysis_controller.perform_fft_analysis(x_data, y_data)
		else:
			self.main_plot_widget.control_output.set_result_text("")

	@Slot(str)
	def _on_function_selection_changed(self, text):
		if text == "亮度振荡分析":
			self.analysis_controller.set_analysis_enabled(True)
		else:
			self.analysis_controller.set_analysis_enabled(False)
