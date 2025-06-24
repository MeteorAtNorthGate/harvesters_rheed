# main_app.py

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
    MIN_PYTHON_VERSION = (3, 9)
    MAX_PYTHON_VERSION = (3, 11, 99)  # 使用一个足够大的第三位来表示所有 3.11.x 版本

    # 检查当前 Python 版本
    if not (MIN_PYTHON_VERSION <= sys.version_info < (MAX_PYTHON_VERSION[0], MAX_PYTHON_VERSION[1] + 1)):
        current_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        required_version = f"Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]} 到 {MAX_PYTHON_VERSION[0]}.{MAX_PYTHON_VERSION[1]}"

        print(f"错误：此项目需要 {required_version} 版本。您当前使用的版本是 {current_version}。", file=sys.stderr)
        print("请切换到兼容的 Python 版本后重试。", file=sys.stderr)
        sys.exit(1)  # 以错误码退出程序
    print("Python 版本检查通过。项目正在启动...")

    sys.exit(main())
