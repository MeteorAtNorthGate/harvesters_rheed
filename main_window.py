# main_window.py
# 作用: 定义应用程序的主窗口界面，使用新的VideoPreviewLabel替换旧的pyqtgraph预览区。

import os
from PySide6.QtCore import Qt, Slot, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QMessageBox, QSplitter, QListWidget, QListWidgetItem,
    QFrame, QFileDialog, QLineEdit
)

import config_manager
from camera_setup import setup_harvester, cleanup_harvester
from camera_controller import CameraController
from video_player_controller import VideoPlayerController
from video_recorder import VideoRecorder
from status_selector import StatusSelector
from plotting_widgets import MainPlottingWidget
from analysis_controller import AnalysisController
from video_preview_widget import VideoPreviewLabel

PREVIEW_FPS = 30


class MainWindow(QMainWindow):
    frame_to_analyze = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rheed_analyzer_v0.32")
        self.resize(1600, 900)

        self.load_app_config()

        self.harvester = None
        self.camera_controller = None
        self.video_player_controller = None
        self.video_recorder = None
        self.is_first_frame = True
        self.current_frame_for_recording = None

        self.analysis_controller = AnalysisController()
        self.analysis_thread = QThread()
        self.analysis_controller.moveToThread(self.analysis_thread)
        self.analysis_thread.start()
        print("分析控制器已移至后台线程。")

        self.camera_preview_timer = QTimer(self)
        self.camera_preview_timer.timeout.connect(self.update_camera_preview)

        # UI创建
        main_layout = QVBoxLayout()
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        self._create_top_bar(main_layout)
        main_v_splitter = QSplitter(Qt.Vertical)
        top_h_splitter = QSplitter(Qt.Horizontal)
        left_v_splitter = QSplitter(Qt.Vertical)
        camera_panel = self._create_camera_list_panel()
        video_panel = self._create_video_list_panel()
        left_v_splitter.addWidget(camera_panel)
        left_v_splitter.addWidget(video_panel)
        center_panel = self._create_preview_panel()
        right_panel = self._create_right_panel()
        top_h_splitter.addWidget(left_v_splitter)
        top_h_splitter.addWidget(center_panel)
        top_h_splitter.addWidget(right_panel)

        # 使用 setSizes 替换 setStretchFactor 来设置初始像素宽度 ---
        # 这将使中间的预览区以650px的宽度启动（某经典650*450*70CCD的画幅）
        top_h_splitter.setSizes([400, 650, 550])

        bottom_panel = self._create_bottom_interaction_panel()
        main_v_splitter.addWidget(top_h_splitter)
        main_v_splitter.addWidget(bottom_panel)
        # 此处设置上下面板的初始高度，上部（预览区所在行）高度为650
        main_v_splitter.setSizes([650, 250])
        main_layout.addWidget(main_v_splitter)

        self._set_default_values()
        self._connect_signals()

    @Slot()
    def _on_start_capture(self):
        current_item = self.camera_list_widget.currentItem()
        if not current_item or not self.harvester: return
        self._stop_all_sources()
        device_index = current_item.data(Qt.UserRole)

        self.camera_controller = CameraController(harvester=self.harvester, device_index=device_index, fps=self.camera_fps)
        self.camera_controller.error_occurred.connect(self.show_error_message)
        self.camera_controller.capture_stopped.connect(self._on_capture_fully_stopped)

        self.camera_controller.start_capture()
        self._on_source_started()

        self.camera_preview_timer.start(1000 // PREVIEW_FPS)

    def _stop_all_sources(self):
        if self.camera_preview_timer.isActive():
            self.camera_preview_timer.stop()

        if self.camera_controller:
            self.camera_controller.stop_capture()

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

    @Slot(object)
    def update_video_preview(self, frame):
        if frame is not None:
            self._display_frame(frame)
            self.frame_to_analyze.emit(frame)

    def _display_frame(self, frame):
        try:
            if self.video_recorder and self.video_recorder.is_recording:
                self.video_recorder.add_frame(frame)

            self.current_frame_for_recording = frame
            rgb_frame = frame[..., ::-1]
            self.image_view.set_frame(rgb_frame)

        except Exception as e:
            print(f"显示帧时出错: {e}")

    def _connect_signals(self):
        self.find_button.clicked.connect(self._on_find_cameras)
        self.start_button.clicked.connect(self._on_start_capture)
        self.stop_button.clicked.connect(self._on_stop_capture)
        self.camera_list_widget.currentItemChanged.connect(self._on_camera_selected)

        self.add_video_button.clicked.connect(self._on_add_video)
        self.remove_video_button.clicked.connect(self._on_remove_video)
        self.play_video_button.clicked.connect(self._on_play_video)
        self.pause_video_button.clicked.connect(self._on_pause_video)
        self.stop_video_button.clicked.connect(self._on_stop_video)
        self.video_list_widget.currentItemChanged.connect(self._on_video_selected)

        self.browse_path_button.clicked.connect(self._on_browse_save_path)
        self.start_record_button.clicked.connect(self._on_start_recording)
        self.stop_record_button.clicked.connect(self._on_stop_recording)

        self.main_plot_widget.control_output.select_area_button.clicked.connect(self.image_view.enter_selection_mode)
        self.image_view.roi_defined.connect(self.analysis_controller.set_roi)

        self.main_plot_widget.dynamic_plot.clear_button.clicked.connect(self.analysis_controller.clear_dynamic_data)

        self.frame_to_analyze.connect(self.analysis_controller.process_frame_for_analysis)
        self.analysis_controller.data_cleared.connect(self.main_plot_widget.dynamic_plot.clear_plot)
        self.analysis_controller.data_point_generated.connect(self.main_plot_widget.dynamic_plot.add_point)
        self.analysis_controller.analysis_result_ready.connect(self.main_plot_widget.control_output.set_result_text)
        self.main_plot_widget.static_plot.analysis_requested.connect(self.analysis_controller.perform_fft_analysis)

    def closeEvent(self, event):
        print("正在关闭窗口并清理所有线程...")

        self._on_stop_recording()

        if self.camera_controller:
            self.camera_controller.stop_capture()
        if self.video_player_controller:
            self.video_player_controller.stop()

        print("等待数据源线程结束...")
        if self.camera_controller and self.camera_controller.thread:
            if not self.camera_controller.thread.wait(3000):
                print("警告: 相机线程未能正常终止。")

        if self.video_player_controller and self.video_player_controller.thread:
            if not self.video_player_controller.thread.wait(2000):
                print("警告: 视频播放器线程未能正常终止。")

        print("正在停止分析线程...")
        if self.analysis_thread.isRunning():
            self.analysis_thread.quit()
            if not self.analysis_thread.wait(2000):
                print("警告: 分析线程未能正常终止。")

        if self.harvester:
            print("正在清理 Harvester...")
            cleanup_harvester(self.harvester)
            self.harvester = None

        print("所有资源已清理，程序退出。")
        event.accept()

    def _cleanup_controller(self, controller_attr):
        controller = getattr(self, controller_attr)
        if not controller: return

        print(f"开始清理 {controller_attr}...")

        if self.video_recorder: self._on_stop_recording()

        thread = controller.thread

        setattr(self, controller_attr, None)

        if thread and thread.isRunning():
            print(f"正在请求 {controller_attr} 的线程停止...")
            thread.quit()
            if not thread.wait(2000):
                print(f"警告: {controller_attr} 的线程未能正常终止。")

        controller.deleteLater()

        self._update_ui_state()
        self.frame_to_analyze.emit(None)
        print(f"{controller_attr} 已被清理。")

    @Slot()
    def _on_stop_capture(self):
        if self.camera_controller:
            self.stop_button.setEnabled(False)
            print("UI请求停止相机...")
            self.camera_controller.stop_capture()

    def load_app_config(self):
        try:
            self.cti_path = config_manager.get_config_value('Paths', 'cti_path')
            fps_str = config_manager.get_config_value('Camera', 'fps', '30')
            self.camera_fps = int(fps_str)
            print("配置加载成功:")
            print(f"  - CTI Path: {self.cti_path}")
            print(f"  - Camera FPS: {self.camera_fps}")
        except Exception as e:
            print(f"加载config.ini时出错: {e}, 将使用默认值。")
            self.cti_path = ""
            self.camera_fps = 30
            QMessageBox.warning(self, "配置错误", f"加载 config.ini 失败: {e}\n将使用默认设置。")

    def _on_find_cameras(self):
        if self.harvester: cleanup_harvester(self.harvester)
        self.camera_list_widget.clear()
        QApplication.processEvents()
        self.harvester = setup_harvester(self.cti_path)
        if self.harvester and self.harvester.device_info_list:
            for i, di in enumerate(self.harvester.device_info_list):
                item = QListWidgetItem(f"相机 {i} ({di.model})")
                item.setData(Qt.UserRole, i)
                self.camera_list_widget.addItem(item)
        else:
            QMessageBox.warning(self, "未找到设备", f"在路径 '{self.cti_path}' 未能发现任何相机设备。\n请检查 config.ini 中的路径和相机连接。")

    @Slot()
    def _on_play_video(self):
        if self.video_player_controller and self.video_player_controller._is_paused:
            self.video_player_controller.play()
            self._update_ui_state()
            return
        current_item = self.video_list_widget.currentItem()
        if not current_item: return
        self._stop_all_sources()
        filepath = current_item.data(Qt.UserRole)
        self.video_player_controller = VideoPlayerController()
        self.video_player_controller.new_frame_ready.connect(self.update_video_preview)
        self.video_player_controller.error_occurred.connect(self.show_error_message)
        self.video_player_controller.playback_stopped.connect(self._on_playback_fully_stopped)
        self.video_player_controller.load_video(filepath)
        self.video_player_controller.play()
        self._on_source_started()

    @Slot()
    def _on_start_recording(self):
        source = self.camera_controller or self.video_player_controller
        if not source:
            self.show_error_message("没有正在预览的视频源，无法录制。")
            return
        base_save_path = self.save_path_edit.text()
        furnace_id = self.furnace_id_edit.text()
        if not base_save_path or not furnace_id:
            self.show_error_message("请填写“炉号”和“保存路径”。")
            return
        if self.other_status_edit.text():
            status_filename = self.other_status_edit.text().strip()
        else :
            status_filename = {
                "脱氧前": "non","脱氧后": "deo","开始生长": "start","生长中": "growth","结束生长": "end"
            }.get(self.status_selector.currentText(), self.status_selector.currentText())
            # 这里采用了dic.get(key,default_value)的方法，兼顾currentText的选择按钮和自定义两种方式
        furnace_dir = os.path.join(base_save_path, furnace_id)
        try:
            os.makedirs(furnace_dir, exist_ok=True)
        except OSError as e:
            self.show_error_message(f"无法创建保存目录:\n{furnace_dir}\n错误: {e}")
            return
        base_filepath_part = os.path.join(furnace_dir, status_filename)
        full_filepath = f"{base_filepath_part}.mp4"
        counter = 1
        while os.path.exists(full_filepath): full_filepath = f"{base_filepath_part}_{counter}.mp4"; counter += 1
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
        if self.video_recorder.start_recording(full_filepath, fps, frame_size):
            self._update_recording_ui(True)
        else:
            self.show_error_message(f"启动录制失败，请检查路径和权限。\n{full_filepath}")
            self.video_recorder = None

    @Slot()
    def _on_stop_recording(self):
        if self.video_recorder: self.video_recorder.stop_recording(); self.video_recorder = None; self._update_recording_ui(False)

    def _create_preview_panel(self):
        self.image_view = VideoPreviewLabel()
        return self.image_view

    def _create_right_panel(self):
        self.main_plot_widget = MainPlottingWidget()
        return self.main_plot_widget

    def _create_top_bar(self, parent_layout):
        top_bar_layout = QHBoxLayout()
        self.find_button = QPushButton("查找相机")
        self.start_button = QPushButton("启动相机")
        self.stop_button = QPushButton("停止相机")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        top_bar_layout.addWidget(self.find_button)
        top_bar_layout.addWidget(self.start_button)
        top_bar_layout.addWidget(self.stop_button)
        top_bar_layout.addStretch()
        parent_layout.addLayout(top_bar_layout)

    def _create_camera_list_panel(self):
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(QLabel("可用相机列表:"))
        self.camera_list_widget = QListWidget()
        layout.addWidget(self.camera_list_widget)
        return panel

    def _create_video_list_panel(self):
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(QLabel("视频文件列表:"))
        self.video_list_widget = QListWidget()
        layout.addWidget(self.video_list_widget)
        button_layout = QHBoxLayout()
        self.add_video_button = QPushButton("+")
        self.remove_video_button = QPushButton("-")
        self.play_video_button = QPushButton("▶")
        self.pause_video_button = QPushButton("❚❚")
        self.stop_video_button = QPushButton("■")
        self.add_video_button.setToolTip("添加视频文件")
        self.remove_video_button.setToolTip("移除选中视频")
        self.play_video_button.setToolTip("播放/恢复")
        self.pause_video_button.setToolTip("暂停")
        self.stop_video_button.setToolTip("停止")
        for btn in [self.add_video_button, self.remove_video_button, self.play_video_button, self.pause_video_button,
                    self.stop_video_button]: btn.setMinimumHeight(30)
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
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setMinimumHeight(220)
        layout = QGridLayout(panel)
        layout.setSpacing(10)
        layout.addWidget(QLabel("炉号:"), 0, 0, Qt.AlignRight)
        self.furnace_id_edit = QLineEdit()
        self.furnace_id_edit.setMaximumWidth(200)
        layout.addWidget(self.furnace_id_edit, 0, 1)
        layout.addWidget(QLabel("状态:"), 0, 2, Qt.AlignRight)
        status_labels = ["脱氧前", "脱氧后", "开始生长", "生长中", "结束生长"]
        self.status_selector = StatusSelector(status_labels)
        layout.addWidget(self.status_selector, 0, 3)
        self.start_record_button = QPushButton("开始录制")
        self.stop_record_button = QPushButton("结束录制")
        self.stop_record_button.setEnabled(False)
        self.start_record_button.setMinimumHeight(35)
        self.stop_record_button.setMinimumHeight(35)
        layout.addWidget(self.start_record_button, 0, 4)
        layout.addWidget(self.stop_record_button, 0, 5)
        layout.addWidget(QLabel("其他状态:"), 1, 2, Qt.AlignRight)
        self.other_status_edit = QLineEdit()
        layout.addWidget(self.other_status_edit, 1, 3)
        layout.addWidget(QLabel("保存路径:"), 2, 0, Qt.AlignRight)
        self.save_path_edit = QLineEdit()
        self.browse_path_button = QPushButton("浏览...")
        layout.addWidget(self.save_path_edit, 2, 1, 1, 3)
        layout.addWidget(self.browse_path_button, 2, 4)
        self.bottom_status_label = QLabel("备用 (打印机器学习模型预测状态等)")
        self.bottom_status_label.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.bottom_status_label.setAlignment(Qt.AlignCenter)
        self.bottom_status_label.setMinimumHeight(50)
        layout.addWidget(self.bottom_status_label, 3, 0, 1, 8)
        layout.setColumnStretch(7, 1)
        return panel

    def _set_default_values(self):
        self.furnace_id_edit.setText("AI2233")
        home_dir = os.path.expanduser('~')
        default_save_path = os.path.join(home_dir, "Desktop", "GrowthRecordings")
        self.save_path_edit.setText(default_save_path.replace("\\", "/"))

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

    def _update_ui_state(self):
        is_cam_active = self.camera_controller is not None
        is_vid_active = self.video_player_controller is not None
        is_vid_paused = is_vid_active and self.video_player_controller._is_paused
        is_media_active = is_cam_active or is_vid_active
        is_recording = self.video_recorder is not None and self.video_recorder.is_recording
        can_change_source = not is_media_active and not is_recording

        self.find_button.setEnabled(can_change_source)
        self.start_button.setEnabled(can_change_source and self.camera_list_widget.currentItem() is not None)
        self.stop_button.setEnabled(is_cam_active and not is_recording)
        self.camera_list_widget.setEnabled(can_change_source)

        self.add_video_button.setEnabled(can_change_source)
        self.remove_video_button.setEnabled(can_change_source)
        self.play_video_button.setEnabled((
                                                  can_change_source and self.video_list_widget.currentItem() is not None) or is_vid_paused)
        self.pause_video_button.setEnabled(is_vid_active and not is_vid_paused and not is_recording)
        self.stop_video_button.setEnabled(is_vid_active and not is_recording)
        self.video_list_widget.setEnabled(can_change_source)

        self.start_record_button.setEnabled(is_media_active and not is_recording)
        self.stop_record_button.setEnabled(is_recording)

        if not is_media_active:
            self.image_view.set_frame(None)
            self.frame_to_analyze.emit(None)
            self.current_frame_for_recording = None

    @Slot()
    def _on_stop_video(self):
        if self.video_player_controller: self.video_player_controller.stop()

    @Slot()
    def _on_camera_selected(self, item):
        self._update_ui_state()

    @Slot()
    def _on_video_selected(self, item):
        self._update_ui_state()

    @Slot()
    def _on_capture_fully_stopped(self):
        self._cleanup_controller('camera_controller')

    @Slot()
    def _on_playback_fully_stopped(self):
        self._cleanup_controller('video_player_controller')

    @Slot(str)
    def show_error_message(self, message):
        QMessageBox.critical(self, "错误", message)
        self._on_capture_fully_stopped()
        self._on_playback_fully_stopped()

    @Slot()
    def _on_add_video(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mov *.mkv)")
        if files:
            for file_path in files:
                item = QListWidgetItem(os.path.basename(file_path))
                item.setData(Qt.UserRole, file_path)
                self.video_list_widget.addItem(item)

    @Slot()
    def _on_remove_video(self):
        current_item = self.video_list_widget.currentItem()
        if current_item: self.video_list_widget.takeItem(self.video_list_widget.row(current_item))

    @Slot()
    def _on_browse_save_path(self):
        directory = QFileDialog.getExistingDirectory(self, "选择视频保存文件夹")
        if directory: self.save_path_edit.setText(directory.replace("\\", "/"))
