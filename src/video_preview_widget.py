# video_preview_widget.py
# 作用: 定义一个基于QLabel的高性能视频预览控件，并实现了鼠标拖拽选择ROI的功能。
# 这是对pyqtgraph中自带的ROI选区工具的替代实现。你问我为什么不用现成的？性能不够。

from PySide6.QtCore import Qt, Signal, Slot, QRect, QPoint
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen
from PySide6.QtWidgets import QLabel, QApplication
import numpy as np


class VideoPreviewLabel(QLabel):
    """
    一个高性能的视频预览控件，继承自QLabel。
    支持将OpenCV的Numpy图像帧高效显示，并允许用户通过鼠标拖拽来定义一个ROI。
    """
    # 当用户完成ROI选择后，发射此信号，参数为ROI在原始图像像素坐标系中的QRect。
    roi_defined = Signal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #202020")

        self._current_pixmap = None
        self._is_in_selection_mode = False
        self._is_drawing = False
        self._roi_start_pos = None
        self._roi_end_pos = None

    @Slot(object)
    def set_frame(self, frame):
        """
        接收一个numpy数组格式的图像帧（应为RGB格式），并更新显示。
        """
        if frame is None:
            self.setPixmap(QPixmap())
            self._current_pixmap = None
            self.update()  # 确保清除旧图像
            return

        try:
            # 确保数组是C-连续的
            # 这可以解决 "memoryview: underlying buffer is not C-contiguous" 错误
            if not frame.flags['C_CONTIGUOUS']:
                frame = np.ascontiguousarray(frame)

            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

            # 创建 QPixmap 并存储，然后触发重绘事件
            self._current_pixmap = QPixmap.fromImage(qt_image)
            self.update()  # 调用update()来触发paintEvent
        except Exception as e:
            print(f"设置帧时出错: {e}")

    @Slot()
    def enter_selection_mode(self):
        """
        公开的槽函数，用于启动ROI选择模式。
        """
        self._is_in_selection_mode = True
        QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
        print("VideoPreviewLabel: 已进入ROI选择模式。")

    def _exit_selection_mode(self):
        """
        退出ROI选择模式并清理状态。
        """
        self._is_in_selection_mode = False
        self._is_drawing = False
        self._roi_start_pos = None
        self._roi_end_pos = None
        QApplication.restoreOverrideCursor()
        self.update()  # 清除界面上的ROI框
        print("VideoPreviewLabel: 已退出ROI选择模式。")

    def mousePressEvent(self, event):
        if self._is_in_selection_mode and event.button() == Qt.MouseButton.LeftButton:
            self._is_drawing = True
            self._roi_start_pos = event.position().toPoint()
            self._roi_end_pos = self._roi_start_pos
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_drawing:
            self._roi_end_pos = event.position().toPoint()
            self.update()  # 实时重绘ROI框
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_drawing and event.button() == Qt.MouseButton.LeftButton:
            roi_rect_widget = QRect(self._roi_start_pos, self._roi_end_pos).normalized()

            # 将控件坐标系的ROI转换为图像像素坐标系的ROI
            pixel_rect = self._map_widget_rect_to_pixmap_rect(roi_rect_widget)

            if pixel_rect.width() > 1 and pixel_rect.height() > 1:
                self.roi_defined.emit(pixel_rect)
                print(f"VideoPreviewLabel: 新ROI已定义 (像素坐标): {pixel_rect}")

            self._exit_selection_mode()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        """
        重写绘制事件，先绘制视频帧，再在上面叠加ROI选择框。
        """
        super().paintEvent(event)  # 先调用父类方法绘制背景等
        painter = QPainter(self)

        if self._current_pixmap and not self._current_pixmap.isNull():
            # 计算pixmap在label中实际显示的区域（保持宽高比）
            scaled_pixmap = self._current_pixmap.scaled(self.size(),
                                                        Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled_pixmap.width()) / 2
            y = (self.height() - scaled_pixmap.height()) / 2
            painter.drawPixmap(QPoint(x, y), scaled_pixmap)

            # 如果正在绘制ROI，则在pixmap上层绘制矩形
            if self._is_drawing:
                pen = QPen(Qt.GlobalColor.yellow, 2, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawRect(QRect(self._roi_start_pos, self._roi_end_pos))
        else:
            # 如果没有图像，显示提示文字
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "视频预览区")

    def _map_widget_rect_to_pixmap_rect(self, widget_rect):
        """
        核心转换函数：将QLabel控件坐标系下的矩形，转换为原始图像像素坐标系下的矩形。
        """
        if not self._current_pixmap or self._current_pixmap.isNull():
            return QRect()

        label_w = self.width()
        label_h = self.height()
        pixmap_w = self._current_pixmap.width()
        pixmap_h = self._current_pixmap.height()

        # 计算图像在控件中的缩放比例和偏移
        scale_w = label_w / pixmap_w
        scale_h = label_h / pixmap_h
        scale = min(scale_w, scale_h)  # 保持宽高比，取最小缩放因子

        # 计算图像在控件中实际显示的尺寸和边距（黑边）
        scaled_w = pixmap_w * scale
        scaled_h = pixmap_h * scale
        offset_x = (label_w - scaled_w) / 2
        offset_y = (label_h - scaled_h) / 2

        # 从控件坐标转换到像素坐标
        # 1. 减去黑边偏移
        px = widget_rect.x() - offset_x
        py = widget_rect.y() - offset_y
        # 2. 除以缩放比例
        if scale == 0: return QRect()  # 防止除零错误
        px /= scale
        py /= scale

        pw = widget_rect.width() / scale
        ph = widget_rect.height() / scale

        # 约束范围，确保不会超出图像边界
        px = max(0, px)
        py = max(0, py)
        pw = min(pw, pixmap_w - px)
        ph = min(ph, pixmap_h - py)

        return QRect(int(px), int(py), int(pw), int(ph))
