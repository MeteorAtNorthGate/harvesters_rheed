# -*- coding: utf-8 -*-
import traceback
from harvesters.core import Harvester

# 导入适用于您环境的正确异常类
# 根据您提供的脚本，我们优先使用 genicam.gentl.GenericException
try:
	from genicam.gentl import GenericException
except ImportError:
	try:
		from genicam.api import GenICamException as GenericException
	except ImportError:
		# 如果两者都失败，定义一个基础的Exception作为后备
		GenericException = Exception

# --- 用户配置 ---
# 请确保此路径是您相机 GenTL Producer (.cti) 文件的正确绝对路径。
# 我使用了您在 check_output_format.py 中提供的路径。
CTI_FILE_PATH = r'C:\Program Files\Basler\pylon 6\Runtime\x64\ProducerGEV.cti'


# --- 配置结束 ---


def main():
	"""
	主函数，用于连接相机、查看和修改曝光时间。
	"""
	# ---------------------------------------------------------------
	# 1. 初始化 Harvester
	# ---------------------------------------------------------------
	h = Harvester()
	ia = None  # 先声明图像采集器变量

	try:
		# ---------------------------------------------------------------
		# 2. 加载 .cti 文件并更新设备列表
		# ---------------------------------------------------------------
		h.add_file(CTI_FILE_PATH)
		h.update()

		if not h.device_info_list:
			print("错误: 未发现任何相机。")
			print("请检查：")
			print(f"1. .cti 文件路径是否正确: '{CTI_FILE_PATH}'")
			print("2. 相机是否已连接并正常供电。")
			print("3. 防火墙或网络设置是否阻止了相机通信。")
			return

		# ---------------------------------------------------------------
		# 3. 创建图像采集器 (Image Acquirer)
		# ---------------------------------------------------------------
		print(f"正在连接相机: {h.device_info_list[0].model}...")
		ia = h.create(0)
		node_map = ia.remote_device.node_map
		print("相机连接成功！")

		# ---------------------------------------------------------------
		# 4. 关键步骤：操作曝光相关节点
		# ---------------------------------------------------------------
		print("\n" + "=" * 20 + " 曝光控制 " + "=" * 20)

		# a) 检查并关闭自动曝光 (ExposureAuto)
		#    这是手动设置曝光时间通常需要的第一步。
		print("\n--- 步骤 1: 检查自动曝光模式 ---")
		try:
			exposure_auto_node = node_map.ExposureAuto
			print(f"当前 'ExposureAuto' 模式: {exposure_auto_node.value}")

			if exposure_auto_node.value != 'Off':
				print("检测到自动曝光已开启，正在尝试关闭...")
				exposure_auto_node.value = 'Off'
				print(f"成功将 'ExposureAuto' 设置为: {exposure_auto_node.value}")
			else:
				print("'ExposureAuto' 已处于 'Off' 状态，无需更改。")

		except (AttributeError, GenericException) as e:
			print(f"警告: 无法操作 'ExposureAuto' 节点。可能您的相机不支持或命名不同。错误: {e}")
			print("将继续尝试直接设置曝光时间。")

		# b) 查看和修改曝光时间 (ExposureTimeAbs)
		#    'ExposureTimeAbs' 通常指以微秒(us)为单位的绝对曝光时间。
		print("\n--- 步骤 2: 查看和修改曝光时间 ---")
		try:
			exposure_time_node = node_map.ExposureTimeAbs

			# 读取并打印当前值和范围
			current_exposure = exposure_time_node.value
			min_exposure = exposure_time_node.min
			max_exposure = exposure_time_node.max
			print(f"当前曝光时间: {current_exposure:.2f} us")
			print(f"允许的范围: 从 {min_exposure:.2f} us 到 {max_exposure:.2f} us")

			# 设置一个新的曝光时间值
			# 注意：请确保设置的值在允许的范围内
			target_exposure = 457.0  # 尝试设置为 457 us (0.457ms)
			if not (min_exposure <= target_exposure <= max_exposure):
				print(f"\n警告: 目标曝光值 {target_exposure} us 超出允许范围，将使用中间值代替。")
				target_exposure = (min_exposure + max_exposure) / 2.0

			print(f"\n正在尝试将曝光时间设置为: {target_exposure:.2f} us ...")
			exposure_time_node.value = target_exposure

			# 再次读取以确认设置成功
			new_exposure = exposure_time_node.value
			print(f"成功！新的曝光时间为: {new_exposure:.2f} us")

		except (AttributeError, GenericException) as e:
			print(f"错误: 无法操作 'ExposureTimeAbs' 节点。请检查 nodemap 中正确的曝光时间节点名称。")
			print(f"具体错误: {e}")
			# 有些相机可能使用 'ExposureTimeRaw'
			if hasattr(node_map, 'ExposureTimeRaw'):
				print("提示: 发现 'ExposureTimeRaw' 节点，您可能需要操作这个节点。")


	except Exception as e:
		print("\n程序执行过程中发生严重错误:")
		traceback.print_exc()

	finally:
		# ---------------------------------------------------------------
		# 5. 清理资源
		# ---------------------------------------------------------------
		if ia:
			ia.destroy()
			print("\n图像采集器已销毁。")
		if h:
			h.reset()
			print("Harvester 已重置。")
		print("\n程序执行完毕。")


if __name__ == '__main__':
	main()
