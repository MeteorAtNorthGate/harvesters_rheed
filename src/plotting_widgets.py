# plotting_widgets.py
# 使用QPainter取代了pyqtgraph，后者在预览视频文件时表现正常，但在接受CCD相机帧数据流时性能极差以至于无法使用
# 感谢伟大的gemini代替我搞定了这个折磨人的重写（

import numpy as np
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame,
							   QLabel, QGridLayout, QComboBox, QTextEdit)
from PySide6.QtCore import Signal, Slot, Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF, QFont, QFontMetrics


class CustomPlotWidget(QWidget):
	"""
	A custom plot widget that uses QPainter for high-performance 2D plotting.
	This is the rendering engine that replaces pg.PlotWidget.
	"""

	def __init__(self, title="", parent=None):
		super().__init__(parent)
		self.setMinimumHeight(150)
		self.setMouseTracking(True)

		# Plotting data
		self.x_data = np.array([])
		self.y_data = np.array([])
		self.title = title

		# Appearance
		self.background_color = QColor("#202020")
		self.grid_pen = QPen(QColor("#555"), 0.5, Qt.DotLine)
		self.axis_pen = QPen(QColor("#AAA"), 1)
		self.text_pen = QPen(QColor("#DDD"))
		self.plot_pen = QPen(QColor("yellow"), 1.5)
		self.margins = {'left': 50, 'right': 10, 'top': 30, 'bottom': 30}
		self.font = QFont("Arial", 8)
		self.title_font = QFont("Arial", 10, QFont.Weight.Medium)

		# Interactive elements (in data coordinates)
		self.selection_rect = QRectF()
		self.selection_rect_visible = False
		self.guide_lines = []  # List of x-positions
		self.is_dragging_line = -1  # -1: none, 0: line1, 1: line2
		self.mouse_pos = QPointF()

	def set_plot_pen(self, pen):
		self.plot_pen = pen
		self.update()

	def set_data(self, x_data, y_data):
		self.x_data = np.array(x_data)
		self.y_data = np.array(y_data)
		self.update()

	def set_selection_rect(self, rect):
		self.selection_rect = rect
		self.update()

	def set_selection_rect_visible(self, visible):
		if self.selection_rect_visible != visible:
			self.selection_rect_visible = visible
			self.update()

	def set_guide_lines(self, lines):
		self.guide_lines = lines
		self.update()

	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.Antialiasing)
		painter.fillRect(self.rect(), self.background_color)

		# Calculate plot area
		plot_area = self.rect().adjusted(
			self.margins['left'], self.margins['top'],
			-self.margins['right'], -self.margins['bottom']
		)

		if not np.any(self.x_data) or not np.any(self.y_data):
			painter.setPen(self.text_pen)
			painter.setFont(self.title_font)
			painter.drawText(self.rect(), Qt.AlignCenter, self.title)
			return

		# Data ranges
		x_min, x_max = self.x_data.min(), self.x_data.max()
		y_min, y_max = self.y_data.min(), self.y_data.max()
		if x_min == x_max: x_max += 1
		if y_min == y_max: y_max += 1

		# Draw Title
		painter.setPen(self.text_pen)
		painter.setFont(self.title_font)
		painter.drawText(QPointF(self.margins['left'], self.margins['top'] - 10), self.title)

		# Draw grid and axes
		self._draw_grid_and_axes(painter, plot_area, x_min, x_max, y_min, y_max)

		# Draw plot line
		self._draw_plot_line(painter, plot_area, x_min, x_max, y_min, y_max)

		# Draw interactive elements
		self._draw_interactive_elements(painter, plot_area, x_min, x_max, y_min, y_max)

	def _draw_grid_and_axes(self, painter, plot_area, x_min, x_max, y_min, y_max):
		painter.setPen(self.axis_pen)
		painter.drawRect(plot_area)

		num_ticks = 5
		x_ticks = np.linspace(x_min, x_max, num_ticks)
		y_ticks = np.linspace(y_min, y_max, num_ticks)

		painter.setFont(self.font)
		fm = QFontMetrics(self.font)

		# X-axis ticks and grid
		for tick in x_ticks:
			x_pos = self._map_x_to_widget(tick, plot_area, x_min, x_max)
			painter.setPen(self.grid_pen)
			painter.drawLine(QPointF(x_pos, plot_area.top()), QPointF(x_pos, plot_area.bottom()))
			painter.setPen(self.text_pen)
			painter.drawText(int(x_pos - 20), int(plot_area.bottom() + 15), 40, 20, Qt.AlignCenter, f"{tick:.1f}")

		# Y-axis ticks and grid
		for tick in y_ticks:
			y_pos = self._map_y_to_widget(tick, plot_area, y_min, y_max)
			painter.setPen(self.grid_pen)
			painter.drawLine(QPointF(plot_area.left(), y_pos), QPointF(plot_area.right(), y_pos))
			painter.setPen(self.text_pen)
			label = f"{tick:.1f}"
			text_rect = QRectF(plot_area.left() - self.margins['left'], y_pos - fm.height() / 2,
							   self.margins['left'] - 5, fm.height())
			painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, label)

	def _draw_plot_line(self, painter, plot_area, x_min, x_max, y_min, y_max):
		painter.setPen(self.plot_pen)
		polygon = QPolygonF()
		for x, y in zip(self.x_data, self.y_data):
			wx = self._map_x_to_widget(x, plot_area, x_min, x_max)
			wy = self._map_y_to_widget(y, plot_area, y_min, y_max)
			polygon.append(QPointF(wx, wy))

		painter.setClipRect(plot_area)  # Prevent drawing outside the plot area
		painter.drawPolyline(polygon)
		painter.setClipping(False)

	def _draw_interactive_elements(self, painter, plot_area, x_min, x_max, y_min, y_max):
		# Draw selection rectangle
		if self.selection_rect_visible and self.selection_rect.isValid():
			rect_pen = QPen(QColor(0, 150, 255, 200), 1, Qt.DashLine)
			rect_brush = QBrush(QColor(0, 150, 255, 50))

			x1 = self._map_x_to_widget(self.selection_rect.left(), plot_area, x_min, x_max)
			x2 = self._map_x_to_widget(self.selection_rect.right(), plot_area, x_min, x_max)

			widget_rect = QRectF(QPointF(x1, plot_area.top()), QPointF(x2, plot_area.bottom())).normalized()
			painter.setPen(rect_pen)
			painter.setBrush(rect_brush)
			painter.drawRect(widget_rect)

		# Draw guidelines
		if self.guide_lines:
			line_pen = QPen(QColor("green"), 2)
			for i, line_x in enumerate(self.guide_lines):
				x_pos = self._map_x_to_widget(line_x, plot_area, x_min, x_max)

				# Highlight line if mouse is over it
				if self._is_line_hovered(self.mouse_pos.x(), i):
					line_pen.setWidth(3)
				else:
					line_pen.setWidth(2)

				painter.setPen(line_pen)
				painter.drawLine(QPointF(x_pos, plot_area.top()), QPointF(x_pos, plot_area.bottom()))

	def _map_x_to_widget(self, x, plot_area, x_min, x_max):
		if (x_max - x_min) == 0: return plot_area.left()
		return plot_area.left() + (x - x_min) / (x_max - x_min) * plot_area.width()

	def _map_y_to_widget(self, y, plot_area, y_min, y_max):
		if (y_max - y_min) == 0: return plot_area.bottom()
		return plot_area.bottom() - (y - y_min) / (y_max - y_min) * plot_area.height()

	def _map_widget_to_x(self, wx, plot_area, x_min, x_max):
		if plot_area.width() == 0: return x_min
		return x_min + (wx - plot_area.left()) / plot_area.width() * (x_max - x_min)

	def _get_plot_area(self):
		return self.rect().adjusted(
			self.margins['left'], self.margins['top'],
			-self.margins['right'], -self.margins['bottom']
		)

	def _is_line_hovered(self, mouse_x, line_index):
		if not self.guide_lines or line_index >= len(self.guide_lines):
			return False

		plot_area = self._get_plot_area()
		if not np.any(self.x_data): return False
		x_min, x_max = self.x_data.min(), self.x_data.max()
		if x_min == x_max: x_max += 1

		line_widget_x = self._map_x_to_widget(self.guide_lines[line_index], plot_area, x_min, x_max)
		return abs(mouse_x - line_widget_x) < 5


class DynamicPlotWidget(QFrame):
	"""
	Native replacement for the dynamic plot.
	Handles mouse dragging to select a data range, mimicking the pyqtgraph logic.
	"""
	range_selected = Signal(np.ndarray, np.ndarray)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setFrameShape(QFrame.StyledPanel)

		layout = QGridLayout(self)
		self.plot_widget = CustomPlotWidget("动态捕获区")
		self.plot_widget.set_plot_pen(QPen(QColor("yellow"), 1.5))

		self.x_data = []
		self.y_data = []

		# --- State flags to mimic pyqtgraph version's logic ---
		self._is_selection_active = False
		self._user_has_interacted = False
		self._is_dragging = False
		self._selection_start_pos = QPointF()
		self._selection_end_pos = QPointF()

		# --- Monkey-patch the event handlers to redirect them from child to parent ---
		self.plot_widget.mousePressEvent = self.mousePressEvent
		self.plot_widget.mouseMoveEvent = self.mouseMoveEvent
		self.plot_widget.mouseReleaseEvent = self.mouseReleaseEvent

		self.select_range_button = QPushButton("选择范围")
		self.clear_button = QPushButton("清除")

		button_layout = QHBoxLayout()
		button_layout.addStretch()
		button_layout.addWidget(self.select_range_button)
		button_layout.addWidget(self.clear_button)

		layout.addWidget(self.plot_widget, 0, 0)
		layout.addLayout(button_layout, 1, 0)

		# --- Connect signals to slots ---
		self.select_range_button.clicked.connect(self._on_select_range)
		self.clear_button.clicked.connect(self.clear_plot)

	def mousePressEvent(self, event):
		if self._is_selection_active and event.button() == Qt.LeftButton:
			self._is_dragging = True
			self.plot_widget.setCursor(Qt.CrossCursor)
			self._selection_start_pos = event.position()
			self._selection_end_pos = event.position()
			self._update_selection_rect()
			event.accept()

	def mouseMoveEvent(self, event):
		if self._is_dragging:
			self._selection_end_pos = event.position()
			self._update_selection_rect()
			event.accept()

	def mouseReleaseEvent(self, event):
		if self._is_dragging and event.button() == Qt.LeftButton:
			self._is_dragging = False
			self.plot_widget.unsetCursor()
			self._user_has_interacted = True
			self._emit_selection()
			event.accept()

	def _update_selection_rect(self):
		plot_area = self.plot_widget._get_plot_area()
		if not self.x_data: return
		x_min, x_max = min(self.x_data), max(self.x_data)
		if x_min == x_max: x_max += 1

		data_x1 = self.plot_widget._map_widget_to_x(self._selection_start_pos.x(), plot_area, x_min, x_max)
		data_x2 = self.plot_widget._map_widget_to_x(self._selection_end_pos.x(), plot_area, x_min, x_max)

		# FIX: Give the rectangle a non-zero height to make it valid.
		self.plot_widget.set_selection_rect(QRectF(QPointF(data_x1, 0), QPointF(data_x2, 1)).normalized())

	def _emit_selection(self):
		is_visible = self.plot_widget.selection_rect_visible
		is_valid = self.plot_widget.selection_rect.isValid()
		has_data = bool(self.x_data)

		if not is_visible or not is_valid or not has_data:
			self.range_selected.emit(np.array([]), np.array([]))
			return

		min_x = self.plot_widget.selection_rect.left()
		max_x = self.plot_widget.selection_rect.right()

		x_data_np = np.array(self.x_data)
		y_data_np = np.array(self.y_data)

		mask = (x_data_np >= min_x) & (x_data_np <= max_x)
		selected_x = x_data_np[mask]

		self.range_selected.emit(selected_x, y_data_np[mask])

	@Slot()
	def _on_select_range(self):
		"""
		Activates selection mode. If it's the first time, sets a default
		region. Then, immediately triggers an analysis on the current region.
		"""
		if not self.x_data:
			return

		self._is_selection_active = True
		self.plot_widget.set_selection_rect_visible(True)

		if not self._user_has_interacted:
			latest_time = self.x_data[-1]
			start_time = max(self.x_data[0], latest_time - 5.0)
			if latest_time - start_time < 0.1 and len(self.x_data) > 1:
				start_time = self.x_data[0]

			default_rect = QRectF(QPointF(start_time, 0), QPointF(latest_time, 1)).normalized()
			self.plot_widget.set_selection_rect(default_rect)

		self._emit_selection()

	@Slot(float, float)
	def add_point(self, x, y):
		self.x_data.append(x)
		self.y_data.append(y)
		self.plot_widget.set_data(self.x_data, self.y_data)

	@Slot()
	def clear_plot(self):
		"""Clears all data and resets the selection state."""
		self.x_data.clear()
		self.y_data.clear()
		self.plot_widget.set_data([], [])
		self.plot_widget.set_selection_rect(QRectF())
		self.plot_widget.set_selection_rect_visible(False)

		self._is_selection_active = False
		self._user_has_interacted = False
		self._is_dragging = False
		self.plot_widget.unsetCursor()

		# Also clear the static plot
		self.range_selected.emit(np.array([]), np.array([]))


class StaticPlotWidget(QFrame):
	"""
	Native replacement for the static plot.
	Handles dragging vertical lines for analysis range.
	"""
	analysis_requested = Signal(np.ndarray, np.ndarray)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setFrameShape(QFrame.StyledPanel)

		layout = QGridLayout(self)
		self.plot_widget = CustomPlotWidget("静态分析区")
		self.plot_widget.set_plot_pen(QPen(QColor("red"), 1.5))
		layout.addWidget(self.plot_widget, 0, 0)

		self.plot_widget.mousePressEvent = self.mousePressEvent
		self.plot_widget.mouseMoveEvent = self.mouseMoveEvent
		self.plot_widget.mouseReleaseEvent = self.mouseReleaseEvent

	def mousePressEvent(self, event):
		if event.button() == Qt.LeftButton:
			for i in range(len(self.plot_widget.guide_lines)):
				if self.plot_widget._is_line_hovered(event.position().x(), i):
					self.plot_widget.is_dragging_line = i
					self.plot_widget.setCursor(Qt.SizeHorCursor)
					event.accept()
					return

	def mouseMoveEvent(self, event):
		self.plot_widget.mouse_pos = event.position()
		if self.plot_widget.is_dragging_line != -1:
			plot_area = self.plot_widget._get_plot_area()
			if not np.any(self.plot_widget.x_data): return
			x_min, x_max = self.plot_widget.x_data.min(), self.plot_widget.x_data.max()
			if x_min == x_max: x_max += 1

			new_x = self.plot_widget._map_widget_to_x(event.position().x(), plot_area, x_min, x_max)
			self.plot_widget.guide_lines[self.plot_widget.is_dragging_line] = new_x
			self.plot_widget.update()
			self._request_analysis()
			event.accept()
		else:
			# Update cursor on hover
			new_cursor = Qt.ArrowCursor
			for i in range(len(self.plot_widget.guide_lines)):
				if self.plot_widget._is_line_hovered(event.position().x(), i):
					new_cursor = Qt.SizeHorCursor
					break
			if self.plot_widget.cursor().shape() != new_cursor:
				self.plot_widget.setCursor(new_cursor)
			self.plot_widget.update()

	def mouseReleaseEvent(self, event):
		if event.button() == Qt.LeftButton and self.plot_widget.is_dragging_line != -1:
			self.plot_widget.is_dragging_line = -1
			self.plot_widget.unsetCursor()
			self._request_analysis()
			event.accept()

	def _request_analysis(self):
		if not self.plot_widget.guide_lines or self.plot_widget.x_data is None or len(self.plot_widget.x_data) == 0:
			self.analysis_requested.emit(np.array([]), np.array([]))
			return

		min_x, max_x = sorted(self.plot_widget.guide_lines)
		x_data, y_data = self.plot_widget.x_data, self.plot_widget.y_data

		if x_data is None or len(x_data) == 0: return

		mask = (x_data >= min_x) & (x_data <= max_x)
		self.analysis_requested.emit(x_data[mask], y_data[mask])

	@Slot(np.ndarray, np.ndarray)
	def set_data(self, x, y):
		self.plot_widget.set_data(x, y)
		if len(x) > 1:
			data_range = x.max() - x.min()
			line1_pos = x.min() + data_range * 0.25
			line2_pos = x.min() + data_range * 0.75
			self.plot_widget.set_guide_lines([line1_pos, line2_pos])
			self._request_analysis()
		else:
			self.plot_widget.set_guide_lines([])
			self.analysis_requested.emit(np.array([]), np.array([]))


class ControlAndOutputWidget(QFrame):
	"""This widget does not use pyqtgraph and remains unchanged."""

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setFrameShape(QFrame.StyledPanel)
		layout = QGridLayout(self)
		self.select_area_button = QPushButton("选择区域")
		layout.addWidget(self.select_area_button, 0, 0)
		layout.addWidget(QLabel("     选择功能:"), 0, 1)
		self.function_combo = QComboBox()
		# MODIFICATION: Add blank item and set default
		self.function_combo.addItem("")
		self.function_combo.addItem("亮度振荡分析")
		self.function_combo.setCurrentText("亮度振荡分析")
		layout.addWidget(self.function_combo, 0, 2)
		layout.addWidget(QLabel("结果输出:"), 1, 0, 1, 3)
		self.result_output = QTextEdit()
		self.result_output.setReadOnly(True)
		layout.addWidget(self.result_output, 2, 0, 1, 3)
		layout.setColumnStretch(2, 1)

	@Slot(str)
	def set_result_text(self, text):
		self.result_output.setPlainText(text)


class MainPlottingWidget(QWidget):
	"""
	The main widget that integrates all plotting-related controls,
	now using the native QPainter-based widgets.
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

		# Connect signals and slots between the new native widgets
		self.dynamic_plot.range_selected.connect(self.static_plot.set_data)
