# main_app.py

import sys
from PySide6.QtWidgets import QApplication

# Import configuration manager and the modified main window
import config_manager
from main_window import MainWindow

import cProfile  # 1. 导入 cProfile
import pstats    # 2. 导入 pstats


def main():
	"""
    用于启动窗口的主入口
    """
	# 开启调试记录
	profiler = cProfile.Profile()
	profiler.enable()

	# Ensure the configuration file exists
	config_manager.ensure_config_exists()

	# Create the Qt application instance
	app = QApplication(sys.argv)

	# Create and show the main window
	window = MainWindow()
	window.show()

	# Start the Qt event loop
	exit_code = app.exec()

	# 结束调试记录
	profiler.disable()
	# 5. 将分析结果保存到文件中
	profiler.dump_stats("output.prof")
	print("性能分析数据已保存到 output.prof 文件。")

	print("退出程序")
	return exit_code


if __name__ == "__main__":
	MIN_PYTHON_VERSION = (3, 9)
	MAX_PYTHON_VERSION = (3, 11, 99)

	# Check the current Python version
	if not (MIN_PYTHON_VERSION <= sys.version_info < (MAX_PYTHON_VERSION[0], MAX_PYTHON_VERSION[1] + 1)):
		current_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
		required_version = f"Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]} to {MAX_PYTHON_VERSION[0]}.{MAX_PYTHON_VERSION[1]}"

		print(f"软件运行需要 {required_version}. 您的版本是 {current_version}.", file=sys.stderr)
		print("请切换到可用的python版本", file=sys.stderr)
		sys.exit(1)

	print("python版本适配，启动程序")
	sys.exit(main())
