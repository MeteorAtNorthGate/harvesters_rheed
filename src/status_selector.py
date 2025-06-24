# status_selector.py
# 作用: 定义一个自定义的、基于按钮的状态选择器控件。

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup
from PySide6.QtCore import Signal, Slot


class StatusSelector(QWidget):
    """
    一个自定义的状态选择器，由一组互斥的按钮组成。
    """
    selectionChanged = Signal(int, str)

    def __init__(self, states, parent=None):
        """
        初始化选择器。
        :param states: 一个包含状态文本的字符串列表。
        """
        super().__init__(parent)
        self.states = states

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)  # 按钮间的间距

        for i, state_text in enumerate(self.states):
            button = QPushButton(state_text)
            button.setCheckable(True)
            button.setFixedSize(100, 35)
            layout.addWidget(button)
            self.button_group.addButton(button, i)

        self.button_group.idClicked.connect(self._on_button_clicked)

        if self.button_group.buttons():
            self.button_group.buttons()[0].setChecked(True)

        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #333;
                border: none;
                padding: 8px;
                font-size: 14px;
                border-radius: 8px; /* 给所有按钮都加上圆角 */
            }
            QPushButton:hover {
                background-color: #e6e6e6;
            }
            QPushButton:checked {
                background-color: #ffffff;
                color: #000;
                /* 设置一个更粗、更深的边框来凸显选中状态 */
                border: 2px solid #5c5c5c;
                font-weight: bold;
            }
        """)

    @Slot(int)
    def _on_button_clicked(self, button_id):
        button = self.button_group.button(button_id)
        if button:
            self.selectionChanged.emit(button_id, button.text())

    def value(self) -> int:
        return self.button_group.checkedId()

    def currentText(self) -> str:
        button = self.button_group.checkedButton()
        return button.text() if button else ""

