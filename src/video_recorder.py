# video_recorder.py
# 作用: 提供一个线程化的视频录制器，将耗时的写文件操作放在独立线程中，避免阻塞主程序。
import os
dll_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'third_party'))
os.environ['PATH'] = dll_path + os.pathsep + os.environ['PATH']
import cv2
import queue
from PySide6.QtCore import QObject, Slot, QThread, Signal

class VideoRecorderWorker(QObject):
    """
    一个在独立线程中运行的Worker，负责所有视频写入操作。
    """
    finished = Signal()
    error = Signal(str)

    def __init__(self, filepath, fps, frame_size):
        super().__init__()
        self.filepath = filepath
        self.fps = fps
        self.frame_size = frame_size
        self.writer = None
        self.frame_queue = queue.Queue(maxsize=300)  # 缓冲区，可以容纳约5秒的70fps视频帧
        self._is_running = False

    def run(self):
        """主录制循环，将在独立线程中执行。"""
        self._is_running = True
        print(f"录制线程启动，文件: {self.filepath}")

        try:
            #fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fourcc = cv2.VideoWriter_fourcc(*'avc1')
            self.writer = cv2.VideoWriter(self.filepath, fourcc, self.fps, self.frame_size)
            if not self.writer.isOpened():
                raise IOError(f"无法创建视频写入器，路径: {self.filepath}")

            while self._is_running:
                try:
                    # 阻塞式获取帧，直到队列为空且收到None信号
                    frame = self.frame_queue.get(timeout=1)
                    if frame is None:  # 收到停止信号
                        break
                    self.writer.write(frame)
                except queue.Empty:
                    # 如果1秒内没有新帧，并且录制仍在运行，则继续等待
                    # 这可以防止在帧率低时线程意外退出
                    continue

        except Exception as e:
            self.error.emit(f"录制线程发生错误: {e}")
        finally:
            if self.writer:
                self.writer.release()
            print("录制线程结束，文件已保存。")
            self.finished.emit()

    def add_frame_to_queue(self, frame):
        """非阻塞地将帧添加到队列中。"""
        if not self._is_running:
            return
        try:
            # 使用 non-blocking put，如果队列满了就丢弃帧，防止内存无限增长
            self.frame_queue.put_nowait(frame)
        except queue.Full:
            # 当写入速度跟不上采集速度时，打印警告，这在高性能系统中是正常现象
            print("警告: 录制帧队列已满，丢弃一帧。")

    def stop(self):
        """请求停止录制循环。"""
        print("正在向录制线程发送停止信号...")
        self._is_running = False
        # 发送一个哨兵值来终止阻塞的 get()
        self.frame_queue.put(None)


class VideoRecorder(QObject):
    """
    VideoRecorder 的主控制类。
    它负责创建和管理Worker与线程。
    """
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        self.is_recording = False

    def start_recording(self, filepath, fps, frame_size):
        if self.is_recording:
            print("警告: 录制已在进行中。")
            return False

        self.thread = QThread()
        self.worker = VideoRecorderWorker(filepath, fps, frame_size)
        self.worker.moveToThread(self.thread)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.started.connect(self.worker.run)

        # 将worker的错误信号转发出去
        self.worker.error.connect(self.error)

        self.thread.start()
        self.is_recording = True
        return True

    @Slot(object)
    def add_frame(self, frame):
        """将帧传递给后台worker的队列。"""
        if self.is_recording and self.worker:
            # 必须复制帧，因为我们正在将它从一个线程传递到另一个线程
            # 以避免数据竞争或原始帧被修改/回收
            self.worker.add_frame_to_queue(frame.copy())

    def stop_recording(self):
        if not self.is_recording or not self.worker:
            return

        print("请求停止录制...")
        self.is_recording = False
        # 使用元调用确保stop在worker的线程上被调用
        if self.thread and self.thread.isRunning():
            self.worker.stop()
            self.thread.quit()
            # 等待线程安全退出
            if not self.thread.wait(2000):  # 等待2秒
                print("警告: 录制线程未能正确停止。")

        self.worker = None
        self.thread = None
        print("录制已停止。")
