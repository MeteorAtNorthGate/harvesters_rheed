# analysis_controller.py
# 作用: 负责数据记录、实时计算和最终分析的核心逻辑。

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, QElapsedTimer, QRect

class AnalysisController(QObject):
    """
    一个独立的控制器，用于处理所有数据分析逻辑。
    只要有视频帧和ROI，就持续进行计算。
    """
    data_point_generated = Signal(float, float)
    analysis_result_ready = Signal(str)
    data_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.roi_rect = None
        self.latest_frame = None

        self.dynamic_x = []
        self.dynamic_y = []

        self.time_tracker = QElapsedTimer()

    @Slot(QRect)
    def set_roi(self, roi_rect):
        """仅设置用于分析的图像区域 (ROI)，接收一个QRect对象。"""
        if roi_rect and not roi_rect.isNull() and roi_rect.isValid():
            self.roi_rect = roi_rect
            print(f"AnalysisController: ROI 已更新。Rect=({self.roi_rect.x()}, {self.roi_rect.y()}, {self.roi_rect.width()}, {self.roi_rect.height()})")
        else:
            self.roi_rect = None

    @Slot(object)
    def process_frame_for_analysis(self, frame):
        if frame is None:
            self.time_tracker.invalidate()
            self.latest_frame = None
            return

        if not self.time_tracker.isValid():
            self.time_tracker.start()

        self.latest_frame = frame

        if self.roi_rect is None:
            return

        try:
            # 直接使用Numpy切片，效率更高
            x, y, w, h = self.roi_rect.x(), self.roi_rect.y(), self.roi_rect.width(), self.roi_rect.height()

            # 确保ROI在图像边界内
            frame_h, frame_w = self.latest_frame.shape[:2]
            x_end = min(x + w, frame_w)
            y_end = min(y + h, frame_h)

            selected_region = self.latest_frame[y:y_end, x:x_end]

            if selected_region is None or selected_region.size == 0:
                return

            # 后续分析逻辑保持不变
            if selected_region.ndim == 3:
                # 使用更快的向量化操作进行灰度转换
                gray_region = np.dot(selected_region[..., :3], [0.299, 0.587, 0.114])
                mean_brightness = gray_region.mean()
            else:
                mean_brightness = selected_region.mean()

            elapsed_time = self.time_tracker.elapsed() / 1000.0

            self.dynamic_x.append(elapsed_time)
            self.dynamic_y.append(mean_brightness)

            self.data_point_generated.emit(elapsed_time, mean_brightness)

        except Exception as e:
            print(f"计算数据点时出错: {e}")

    @Slot()
    def clear_dynamic_data(self):
        """清空动态记录的数据，重置计时器，并通知UI。由“清除”按钮触发。"""
        self.dynamic_x.clear()
        self.dynamic_y.clear()

        if self.latest_frame is not None:
            self.time_tracker.restart()
        else:
            self.time_tracker.invalidate()

        print("AnalysisController: 数据和计时器已通过按钮清除。")
        self.data_cleared.emit()

    @Slot(np.ndarray, np.ndarray)
    def perform_fft_analysis(self, x_data, y_data):
        if len(x_data) < 2:
            self.analysis_result_ready.emit("数据点太少，无法分析。")
            return
        try:
            n = len(y_data)
            sampling_interval = (x_data[-1] - x_data[0]) / (n - 1) if n > 1 else 0
            if sampling_interval == 0:
                self.analysis_result_ready.emit("无法计算采样率。")
                return
            fft_result = np.fft.fft(y_data - np.mean(y_data))
            frequencies = np.fft.fftfreq(n, d=sampling_interval)
            positive_freq_mask = frequencies > 0
            freqs = frequencies[positive_freq_mask]
            if len(freqs) == 0:
                self.analysis_result_ready.emit("无法计算有效频率。")
                return
            amplitudes = np.abs(fft_result)[positive_freq_mask]
            dominant_freq_index = np.argmax(amplitudes)
            dominant_frequency = freqs[dominant_freq_index]
            dominant_period = 1 / dominant_frequency
            result_text = f"振荡周期: {dominant_period:.4f} 秒\n"
            result_text += "\n傅里叶级数 (前5项):\n"
            phases = np.angle(fft_result)[positive_freq_mask]
            sorted_indices = np.argsort(amplitudes)[::-1]
            count = 0
            for i in sorted_indices:
                if count >= 5: break
                amp = amplitudes[i] * 2 / n
                freq = freqs[i]
                phase = phases[i]
                result_text += f"  {amp:.3f} * cos(2π * {freq:.3f}t + {phase:.3f})\n"
                count += 1
            self.analysis_result_ready.emit(result_text)
        except Exception as e:
            self.analysis_result_ready.emit(f"分析时发生错误: {e}")

    #def link_image_view(self, image_view):
    #    self.image_view = image_view
