# plotting_widgets.py
# 作用: 定义用于显示和控制数据曲线的自定义控件。

import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame,
                               QLabel, QGridLayout, QComboBox, QTextEdit, QApplication)
from PySide6.QtCore import Signal, Slot, Qt


class DynamicPlotWidget(QFrame):
    """
    动态记录区
    - 新增: “选择范围”按钮和相关逻辑
    - 修改: 按钮布局
    """
    range_selected = Signal(np.ndarray, np.ndarray)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QGridLayout(self)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setTitle("动态记录区")
        #self.plot_widget.setLabel('left', '平均亮度')
        #self.plot_widget.setLabel('bottom', '时间 (s)')
        #self.plot_widget.showGrid(x=True, y=True)
        self.dynamic_curve = self.plot_widget.plot(pen='y', name='实时亮度')

        self.x_data = []
        self.y_data = []

        self.selection_region = pg.LinearRegionItem()
        self.selection_region.setZValue(10)
        self.plot_widget.addItem(self.selection_region, ignoreBounds=True)
        self.selection_region.hide()

        # 变量记录用户是否已经手动调整过参考线，调整过之后不再重置参考线坐标
        self.user_has_interacted_with_guides = False
        self._is_programmatic_change = False

        self.select_range_button = QPushButton("选择范围")
        self.select_range_button.setToolTip("选择用于计算的时间段")
        self.clear_button = QPushButton("清除")
        self.clear_button.setToolTip("清除当前记录的曲线")

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.select_range_button)
        button_layout.addWidget(self.clear_button)

        layout.addWidget(self.plot_widget, 0, 0)
        layout.addLayout(button_layout, 1, 0)

        self.select_range_button.clicked.connect(self._activate_and_set_range)
        self.selection_region.sigRegionChangeFinished.connect(self._on_region_selection_finished)

    @Slot()
    def _activate_and_set_range(self):
        """
        处理“选择范围”按钮点击事件。
        如果用户在本轮录制中还未动过参考线，则自动定位；否则，仅显示。
        """
        if not self.x_data:
            print("动态记录区没有数据，无法选择范围。")
            return

        # 只有在用户尚未交互过的情况下，才自动定位参考线
        if not self.user_has_interacted_with_guides:
            latest_time = self.x_data[-1]
            start_time = max((latest_time - self.x_data[0])/3, latest_time - 5.0)

            self._is_programmatic_change = True
            self.selection_region.setRegion([start_time, latest_time])
            self._is_programmatic_change = False

            print(f"首次选择：已自动定位范围 [{start_time:.2f}s, {latest_time:.2f}s]。")
        else:
            print("用户已调整过，在上次位置显示参考线。")

        self.selection_region.show()

        # 无论如何，都根据当前参考线位置进行一次分析
        min_x, max_x = self.selection_region.getRegion()
        x_data_np = np.array(self.x_data)
        y_data_np = np.array(self.y_data)
        mask = (x_data_np >= min_x) & (x_data_np <= max_x)
        self.range_selected.emit(x_data_np[mask], y_data_np[mask])

    @Slot()
    def _on_region_selection_finished(self):
        """
        当用户手动在图上拖动完范围选择区域后调用。
        """
        if self._is_programmatic_change:
            return

        if not self.selection_region.isVisible():
            return

        self.user_has_interacted_with_guides = True

        min_x, max_x = self.selection_region.getRegion()

        x_data_np = np.array(self.x_data)
        y_data_np = np.array(self.y_data)
        mask = (x_data_np >= min_x) & (x_data_np <= max_x)

        self.range_selected.emit(x_data_np[mask], y_data_np[mask])

        print(f"手动调整范围至 [{min_x:.2f}s, {max_x:.2f}s]，分析完成。")

    @Slot(float, float)
    def add_point(self, x, y):
        self.x_data.append(x)
        self.y_data.append(y)
        self.dynamic_curve.setData(self.x_data, self.y_data)

    @Slot()
    def clear_plot(self):
        """清除数据时，也重置用户交互状态"""
        self.x_data.clear()
        self.y_data.clear()
        self.dynamic_curve.setData([], [])
        self.selection_region.hide()

        self.user_has_interacted_with_guides = False
        self.selection_region.hide()
        print("DynamicPlotWidget: 绘图区已清除，交互状态已重置。")


class StaticPlotWidget(QFrame):
    """
    静态捕获区
    """
    analysis_requested = Signal(np.ndarray, np.ndarray)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QGridLayout(self)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setTitle("分析计算用")
        #self.plot_widget.showGrid(x=True, y=True)
        self.static_curve = self.plot_widget.plot(pen='r', name='捕获曲线')

        self.line1 = pg.InfiniteLine(angle=90, movable=True, pen='g')
        self.line2 = pg.InfiniteLine(angle=90, movable=True, pen='g')
        self.plot_widget.addItem(self.line1)
        self.plot_widget.addItem(self.line2)
        self.line1.hide()
        self.line2.hide()

        layout.addWidget(self.plot_widget, 0, 0)

        self.line1.sigPositionChanged.connect(self._request_analysis)
        self.line2.sigPositionChanged.connect(self._request_analysis)

    def _request_analysis(self):
        if not self.line1.isVisible() or self.static_curve.xData is None:
            return

        min_x, max_x = sorted([self.line1.value(), self.line2.value()])
        x_data, y_data = self.static_curve.getData()

        if x_data is None or len(x_data) == 0: return

        mask = (x_data >= min_x) & (x_data <= max_x)
        self.analysis_requested.emit(x_data[mask], y_data[mask])

    @Slot(np.ndarray, np.ndarray)
    def set_data(self, x, y):
        self.static_curve.setData(x, y)
        self.plot_widget.autoRange()

        if len(x) > 1:
            data_range = x[-1] - x[0]
            self.line1.setValue(x[0] + data_range * 0.25)
            self.line2.setValue(x[0] + data_range * 0.75)
            self.line1.show()
            self.line2.show()
            self._request_analysis()
        else:
            self.line1.hide()
            self.line2.hide()
            self.static_curve.setData([], [])
            self.analysis_requested.emit(np.array([]), np.array([]))


class ControlAndOutputWidget(QFrame):
    """操作和输出区 (无改动)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QGridLayout(self)

        self.select_area_button = QPushButton("选择区域")
        layout.addWidget(self.select_area_button, 0, 0)

        layout.addWidget(QLabel("     选择功能:"), 0, 1)
        self.function_combo = QComboBox()
        self.function_combo.addItem("亮度振荡分析")
        layout.addWidget(self.function_combo, 0, 2)

        layout.addWidget(QLabel("结果输出区:"), 1, 0, 1, 3)
        self.result_output = QTextEdit()
        self.result_output.setReadOnly(True)
        layout.addWidget(self.result_output, 2, 0, 1, 3)

        layout.setColumnStretch(2, 1)

    @Slot(str)
    def set_result_text(self, text):
        self.result_output.setPlainText(text)


class MainPlottingWidget(QWidget):
    """
    整合所有绘图相关控件的主控件
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)

        self.dynamic_plot = DynamicPlotWidget()
        self.static_plot = StaticPlotWidget()
        self.control_output = ControlAndOutputWidget()

        main_layout.addWidget(self.dynamic_plot, 3)
        main_layout.addWidget(self.static_plot, 3)
        main_layout.addWidget(self.control_output, 2)

        self.dynamic_plot.range_selected.connect(self.static_plot.set_data)

