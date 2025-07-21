# video_preview_widget.py
# 作用: 定义一个基于QLabel的高性能视频预览控件，并实现了鼠标拖拽选择ROI的功能。

from PySide6.QtCore import Qt, Signal, Slot, QRect, QPoint
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor
from PySide6.QtWidgets import QLabel, QApplication, QSizePolicy
#import numpy as np


class VideoPreviewLabel(QLabel):
    """
    一个高性能的视频预览控件，继承自QLabel。
    支持将OpenCV的Numpy图像帧高效显示，并允许用户通过鼠标拖拽来定义一个ROI。
    新版特性: 控件大小会根据第一帧自动固定，以消除缩放带来的CPU开销。
    """
    roi_defined = Signal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #202020")

        self._current_pixmap = None
        self._is_in_selection_mode = False
        self._is_drawing = False
        self._roi_start_pos = None
        self._roi_end_pos = None

        # --- 新增: 用于跟踪尺寸是否已固定的标志 ---
        self._size_is_fixed = False
        # --- 新增: 设置初始尺寸策略为可伸缩 ---
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 设置一个合理的最小尺寸，避免窗口刚启动时过小
        self.setMinimumSize(320, 240)


    @Slot(object)
    def set_frame(self, frame):
        """
        接收一个numpy数组格式的图像帧（应为RGB格式），并更新显示。
        此方法现在会自动调整控件尺寸以匹配第一帧的分辨率。
        """
        if frame is None:
            # --- 新增: 当视频流停止时，重置控件尺寸和策略 ---
            if self._size_is_fixed:
                # 恢复为可伸缩的尺寸策略
                self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                # 解除尺寸限制
                self.setMinimumSize(320, 240)
                self.setMaximumSize(16777215, 16777215) # QWIDGETSIZE_MAX
                self._size_is_fixed = False
                print("VideoPreviewLabel: Size constraint released.")

            self._current_pixmap = None
            self.update()  # 触发重绘以显示提示文字
            return

        try:
            #if not frame.flags['C_CONTIGUOUS']:
            #    frame = np.ascontiguousarray(frame)

            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            self._current_pixmap = QPixmap.fromImage(qt_image)

            # --- 新增: 在接收到第一帧有效图像时，固定控件尺寸 ---
            if not self._size_is_fixed and w > 0 and h > 0:
                self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                self.setFixedSize(w, h)
                self._size_is_fixed = True
                print(f"VideoPreviewLabel: Size fixed to {w}x{h}.")

            self.update() # 触发paintEvent重绘
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
        self.update()
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
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_drawing and event.button() == Qt.MouseButton.LeftButton:
            roi_rect_widget = QRect(self._roi_start_pos, self._roi_end_pos).normalized()
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
        重写绘制事件。现在不再依赖父类的绘制，而是自己完全控制。
        这样可以确保在尺寸固定时，图像以1:1的方式绘制，消除缩放。
        """
        painter = QPainter(self)

        if self._current_pixmap and not self._current_pixmap.isNull():
            # 如果尺寸已固定，直接在左上角(0,0)绘制图像，无缩放
            if self._size_is_fixed:
                painter.drawPixmap(0, 0, self._current_pixmap)
            # 如果尺寸未固定（例如在第一帧到达前），则保持缩放以填充窗口
            else:
                scaled_pixmap = self._current_pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                x = (self.width() - scaled_pixmap.width()) / 2
                y = (self.height() - scaled_pixmap.height()) / 2
                painter.drawPixmap(QPoint(x, y), scaled_pixmap)
        else:
            # 如果没有图像，绘制背景和提示文字
            painter.fillRect(self.rect(), QColor("#202020"))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "视频预览区")

        # 在顶层绘制ROI选择框
        if self._is_drawing:
            pen = QPen(Qt.GlobalColor.yellow, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(QRect(self._roi_start_pos, self._roi_end_pos))

    def _map_widget_rect_to_pixmap_rect(self, widget_rect):
        """
        核心转换函数：将控件坐标系下的矩形，转换为原始图像像素坐标系下的矩形。
        """
        if not self._current_pixmap or self._current_pixmap.isNull():
            return QRect()

        # --- 新增: 如果尺寸已固定，坐标系1:1映射，无需计算 ---
        if self._size_is_fixed:
            # 只需确保ROI在图像边界内
            return widget_rect.intersected(self._current_pixmap.rect())

        # --- 如果尺寸未固定，则使用旧的、带缩放的计算方式 ---
        label_w, label_h = self.width(), self.height()
        pixmap_w, pixmap_h = self._current_pixmap.width(), self._current_pixmap.height()
        if pixmap_w == 0 or pixmap_h == 0: return QRect()

        scale = min(label_w / pixmap_w, label_h / pixmap_h)
        scaled_w, scaled_h = pixmap_w * scale, pixmap_h * scale
        offset_x, offset_y = (label_w - scaled_w) / 2, (label_h - scaled_h) / 2

        if scale == 0: return QRect()
        px = (widget_rect.x() - offset_x) / scale
        py = (widget_rect.y() - offset_y) / scale
        pw = widget_rect.width() / scale
        ph = widget_rect.height() / scale

        # 约束范围
        px = max(0, px)
        py = max(0, py)
        pw = min(pw, pixmap_w - px)
        ph = min(ph, pixmap_h - py)

        return QRect(int(px), int(py), int(pw), int(ph))
