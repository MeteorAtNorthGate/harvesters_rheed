from harvesters.core import Harvester

# 导入适用于您环境的正确异常类
try:
	from genicam.gentl import GenericException
except ImportError:
	# 如果上面的导入失败，尝试备用路径（尽管根据您提供的gentl.py，上面的应该是正确的）
	try:
		from genicam.api import GenICamException as GenericException
	except ImportError:
		# 如果两者都失败，定义一个基础的Exception作为后备
		GenericException = Exception

# ---------------------------------------------------------------
# 1. 初始化 Harvester
# ---------------------------------------------------------------
h = Harvester()

# ---------------------------------------------------------------
# 2. 加载相机制造商提供的 GenTL Producer 文件 (.cti)
#	您需要将其替换为您相机驱动的实际路径。
# ---------------------------------------------------------------
# 请确保此路径是正确的
cti_path = r'C:\Program Files\Basler\pylon 6\Runtime\x64\ProducerGEV.cti'
h.add_file(cti_path)

# ---------------------------------------------------------------
# 3. 更新设备列表并创建图像采集器
# ---------------------------------------------------------------
ia = None  # 先声明 ia 变量
try:
	h.update()

	if not h.device_info_list:
		print("未发现任何相机，请检查 .cti 文件路径和相机连接。")
		h.reset()
		exit()

	# =======================【已修复】=======================
	# 使用点(.)来访问 DeviceInfo 对象的属性
	device_info = h.device_info_list[0]
	print(f"发现相机: {device_info.model} (S/N: {device_info.serial_number})")
	# =======================================================

	ia = h.create(0)
	# ---------------------------------------------------------------
	# 4. 关键步骤：操作 PixelFormat 节点
	# ---------------------------------------------------------------
	node_map = ia.remote_device.node_map

	# a) 查看当前相机的 PixelFormat
	current_format = node_map.PixelFormat.value
	print(f"当前的像素格式: {current_format}")

	# b) 查看该相机支持的所有 PixelFormat 模式
	print("\n相机支持的所有像素格式:")
	available_formats = node_map.PixelFormat.symbolics
	for fmt in available_formats:
		print(f"- {fmt}")

	#尝试切换像素格式
	try:
		target_format = 'YUV422Packed'
		# 或者 'BayerBG8', 'RGB8Packed', 'YUV422Packed' 等，只要相机支持
		if target_format in available_formats:
			print(f"\n正在尝试切换到: {target_format} ...")
			node_map.PixelFormat.value = target_format
			print(f"成功切换！新的像素格式: {node_map.PixelFormat.value}")
		else:
			print(f"\n切换失败: 相机不支持 {target_format} 格式。")

	except GenericException as e: # 使用正确的异常类
		print(f"切换像素格式时发生错误: {e}")

	# 5. 开始采集图像 (示例)
	# ia.start_image_acquisition()
	# with ia.fetch_buffer() as buffer:
	#	 # buffer.payload 包含了图像数据
	#	 # 注意：切换到不同格式（如 Packed 格式）后，
	#	 # 您需要用不同的方式来解析图像数据。
	#	 print("成功获取一帧图像。")
	# ia.stop_image_acquisition()

except Exception as e:
	import traceback

	print("\n程序执行过程中发生错误:")
	traceback.print_exc()

finally:
	# ---------------------------------------------------------------
	# 6. 清理资源
	# ---------------------------------------------------------------
	if ia:
		ia.destroy()
	h.reset()
	print("\n程序执行完毕。")

