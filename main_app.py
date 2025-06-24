# main_app.py
# 作用: 应用程序的主入口。

import sys
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication

# 导入配置管理器和主窗口
import config_manager
from main_window import MainWindow

def main():
    """
    主函数，用于设置和运行相机GUI应用。
    """

    # 确保配置文件存在
    config_manager.ensure_config_exists()

    # 设置 pyqtgraph 的全局配置
    pg.setConfigOption('imageAxisOrder', 'row-major')

    # 创建Qt应用实例
    app = QApplication(sys.argv)

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    # 启动Qt事件循环
    exit_code = app.exec()

    print("应用程序已关闭。")
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
