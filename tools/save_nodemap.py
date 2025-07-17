import sys
import os
import traceback
from harvesters.core import Harvester
from genicam.gentl import GenericException
# 导入底层异常类以进行精确捕获
from genicam import _genapi

# --- 用户配置 ---
# 请务必修改为您相机制造商提供的 GenTL Producer (.cti) 文件的【绝对路径】
CTI_FILE_PATH = 'C:/Program Files/Basler/pylon 6/Runtime/x64/ProducerGEV.cti'  # 示例路径，请替换

# 输出文件的名称
OUTPUT_FILENAME = 'nodemap_dump.txt'
# --- 配置结束 ---

# 定义一个已知（常见）的节点名称列表，脚本会优先尝试访问它们
# 这可以绕过一些动态探索的问题
KNOWN_NODE_NAMES = [
	'DeviceInformation', 'DeviceVendorName', 'DeviceModelName', 'DeviceSerialNumber',
	'ImageFormatControl', 'PixelFormat', 'Width', 'Height', 'OffsetX', 'OffsetY',
	'AcquisitionControl', 'AcquisitionMode', 'AcquisitionFrameRate', 'ExposureTime', 'Gain',
	'TriggerMode', 'TriggerSource', 'TriggerSelector',
	'AnalogControl',
	'TransportLayerControl'
]


def dump_node_recursively(file, parent_object, indent_level=0):
	"""
	最终决定版的递归函数。
	它结合了已知节点列表和安全的动态探索。
	"""
	indent = '    ' * indent_level

	# 获取所有可能的成员名称
	try:
		member_names = dir(parent_object)
	except Exception:
		return  # 如果对象不支持 dir(), 则无法继续

	# 创建一个集合以避免重复处理
	processed_names = set()

	# 1. 优先处理已知节点
	for name in KNOWN_NODE_NAMES:
		if name in member_names and name not in processed_names:
			process_single_node(file, parent_object, name, indent_level)
			processed_names.add(name)

	# 2. 动态探索其他节点
	for name in member_names:
		if name.startswith('_') or name in processed_names:
			continue
		process_single_node(file, parent_object, name, indent_level)


def process_single_node(file, parent_object, name, indent_level):
	"""
	处理单个节点，打印其信息并根据需要进行递归。
	"""
	indent = '    ' * indent_level
	try:
		node = getattr(parent_object, name)

		# 通过检查节点对象的类名来判断是否为有效的功能节点
		# 这是一个比 hasattr 更安全的方法
		node_class_name = node.__class__.__name__
		if not node_class_name.startswith('I'):
			return  # 如果不是接口类 (ICategory, IInteger 等)，则忽略

		# 写入节点名和类型
		file.write(f"{indent}[{node_class_name}] {name}\n")

		# --- 尝试获取并写入更多详细信息 ---
		access_mode = 'N/A'
		if hasattr(node, 'get_access_mode'):
			try:
				access_mode = node.get_access_mode().name
				file.write(f"{indent}  - Access: {access_mode}\n")
			except GenericException:
				pass

		if 'R' in access_mode and hasattr(node, 'value'):
			try:
				value = node.value
				if isinstance(value, str) and len(value) > 100:
					value = value[:100] + '...'
				file.write(f"{indent}  - Value: {value}\n")
			except (GenericException, _genapi.LogicalErrorException):
				file.write(f"{indent}  - Value: (access error)\n")

		if node_class_name == 'IEnumeration' and hasattr(node, 'symbolics'):
			try:
				file.write(f"{indent}  - Options: {node.symbolics}\n")
			except GenericException:
				pass

		# 如果是 Category（分类），则深入下一层
		if node_class_name == 'ICategory':
			dump_node_recursively(file, node, indent_level + 1)

		file.write("\n")  # 每个节点块后加一个空行

	except (_genapi.LogicalErrorException, GenericException, AttributeError, TypeError):
		# 捕获所有可能的错误，安全地跳过无效的属性
		pass


def main():
	"""
	主执行函数
	"""
	h = Harvester()
	ia = None
	try:
		if not os.path.exists(CTI_FILE_PATH):
			print(f"错误: CTI 文件未找到 at '{CTI_FILE_PATH}'")
			return

		h.add_file(CTI_FILE_PATH)
		h.update()

		if not h.device_info_list:
			print("错误: 未发现任何相机。")
			return

		device_info = h.device_info_list[0]
		print(f"已发现相机: {device_info.model} (S/N: {device_info.serial_number})")
		print(f"正在连接并导出 Node Map 到 '{OUTPUT_FILENAME}'...")

		ia = h.create(0)

		with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
			f.write(f"GenICam Node Map for: {device_info.model}\n")
			f.write(f"Serial Number: {device_info.serial_number}\n")
			f.write("=" * 80 + "\n\n")

			node_map = ia.remote_device.node_map
			dump_node_recursively(f, node_map)

		print(f"\n成功！Node Map 已完整导出。")

	except Exception as e:
		print("\n发生未预料的错误:")
		traceback.print_exc()

	finally:
		if ia:
			ia.destroy()
		h.reset()
		print("\n程序执行完毕。")


if __name__ == '__main__':
	main()
