# video_player_controller.py
# 作用: 提供一个独立于UI的视频播放控制器，在后台线程中处理视频帧读取和播放控制。

import cv2
from PySide6.QtCore import QObject, Signal, Slot, QThread

class VideoPlayerController(QObject):
    """
    视频播放控制器，在独立的QThread中运行。
    """
    new_frame_ready = Signal(object)
    error_occurred = Signal(str)
    playback_stopped = Signal()

    def __init__(self):
        super().__init__()
        self.video_capture = None
        self.thread = None
        self._is_playing = False
        self._is_paused = False
        self.filepath = None
        self.fps = 30

    @Slot(str)
    def load_video(self, filepath):
        """加载视频文件。"""
        self.filepath = filepath
        try:
            self.video_capture = cv2.VideoCapture(self.filepath)
            if not self.video_capture.isOpened():
                raise IOError(f"无法打开视频文件: {self.filepath}")
            self.fps = self.video_capture.get(cv2.CAP_PROP_FPS)
            if self.fps <= 0: self.fps = 30
        except Exception as e:
            self.error_occurred.emit(str(e))
            self._cleanup()

    @Slot()
    def play(self):
        """开始或恢复播放。"""
        if not self.video_capture:
            self.error_occurred.emit("没有加载视频文件。")
            return

        # 如果只是暂停了，就恢复播放
        if self._is_paused:
            self._is_paused = False
            return

        # 如果还没开始播放，就启动新线程
        if not self._is_playing:
            self._is_playing = True
            self.thread = QThread()
            self.moveToThread(self.thread)
            self.thread.started.connect(self._playback_loop)
            self.thread.start()
            print("视频播放线程已启动。")

    @Slot()
    def pause(self):
        """暂停播放。"""
        if self._is_playing:
            self._is_paused = True

    @Slot()
    def stop(self):
        """请求停止播放。"""
        self._is_playing = False

    def _playback_loop(self):
        """在后台线程中运行的播放主循环。"""
        print("视频播放循环开始...")
        if self.fps > 0:
            frame_delay = 1.0 / self.fps
        else:
            frame_delay = 1.0 / 30  # 默认延迟

        while self._is_playing:
            if not self._is_paused:
                ret, frame = self.video_capture.read()
                if ret:
                    self.new_frame_ready.emit(frame)
                else:
                    self._is_playing = False  # 视频播放完毕
                    break

            # 使用QThread的msleep来避免忙等待，并允许事件处理
            self.thread.msleep(int(frame_delay * 1000))

        self._cleanup()
        self.playback_stopped.emit()

    def _cleanup(self):
        """只清理本对象拥有的资源，不处理线程。"""
        print("正在清理 VideoCapture 资源...")
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None

        self._is_playing = False
        self._is_paused = False

