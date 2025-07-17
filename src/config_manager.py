# config_manager.py
# 作用: 负责读取和管理 config.ini 配置文件。

import configparser
import os

CONFIG_FILE = 'config.ini'


def create_default_config():
	"""如果配置文件不存在，则创建一个默认的。"""
	config = configparser.ConfigParser(comment_prefixes=('#', ';'), allow_no_value=True)

	# 查找环境变量 GENICAM_GENTL64_PATH 来构建 cti_path
	genicam_dir = os.environ.get('GENICAM_GENTL64_PATH')
	default_cti_path = 'C:\\Program Files\\Basler\\pylon 6\\Runtime\\x64\\ProducerGEV.cti'

	if genicam_dir and os.path.isdir(genicam_dir):
		final_cti_path = os.path.join(genicam_dir, 'ProducerGEV.cti')
		comment = '# CTI 文件路径已根据系统环境变量 GENICAM_GENTL64_PATH 自动生成。'
	else:
		print("警告: 未能从环境变量 'GENICAM_GENTL64_PATH' 找到有效的路径。")
		print(f"将使用默认后备路径: {default_cti_path}")
		final_cti_path = default_cti_path
		comment = '# 未找到环境变量 GENICAM_GENTL64_PATH，已使用默认路径。请在系统环境变量中设置该变量，或手动修改下方路径。'

	home_dir = os.path.expanduser('~')
	default_save_path = os.path.join(home_dir, "Desktop", "GrowthRecordings").replace("\\", "/")

	config['Paths'] = {
		comment: None,
		'cti_path': final_cti_path,
		'# 录制视频的默认保存路径': None,
		'save_path': default_save_path
	}

	config['Camera'] = {
		'# 请在此处手动设置您相机的工作帧率 (Frames Per Second)，通常可以在说明书或者官网找到': None,
		'fps': '70'
	}

	config['Display'] = {
		'# UI界面的预览帧率 (Preview FPS).': None,
		'# 注意: 这只影响UI显示, 不影响录制视频的实际帧率.': None,
		'# 较高的值会使预览更流畅, 但会增加CPU使用率. 推荐值: 30-60.': None,
		'preview_fps': '60'
	}

	config['Recording'] = {
		'# 录制模式: Quality 或 Compatibility': None,
		'# Quality: 如果相机支持YUV格式, 将直接录制YUV数据到.mov文件, 画质最高, 文件最大。': None,
		'# Compatibility: 总是录制为MJPEG编码的.avi文件, 兼容性好, 文件较大, 适合频繁启停录制。': None,
		'mode': 'Compatibility',
		'# --- 新增: MJPEG 质量控制 ---': None,
		'# MJPEG 录制质量 (0-100), 仅在兼容模式下生效. 值越高,画质越好,文件越大.': None,
		'mjpeg_quality': '95'
	}

	with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
		config.write(configfile)
	print(f"'{CONFIG_FILE}' 不存在，已创建默认配置文件。")


def load_config():
	"""加载配置文件，如果文件不存在则先创建。"""
	if not os.path.exists(CONFIG_FILE):
		create_default_config()

	config = configparser.ConfigParser(comment_prefixes=('#', ';'), allow_no_value=True)
	config.read(CONFIG_FILE, encoding='utf-8')
	return config


def get_config_value(section, key, fallback=None):
	"""安全地获取一个配置值。"""
	config = load_config()
	return config.get(section, key, fallback=fallback)


def set_config_value(section, key, value):
	"""
	安全地设置一个配置值并写回文件, 同时保留所有注释和原始格式。
	"""
	config_path = CONFIG_FILE
	if not os.path.exists(config_path):
		create_default_config()

	with open(config_path, 'r', encoding='utf-8') as f:
		lines = f.readlines()

	in_correct_section = False
	key_updated = False

	for i, line in enumerate(lines):
		stripped_line = line.strip()

		if stripped_line.startswith('[') and stripped_line.endswith(']'):
			current_section_name = stripped_line[1:-1]
			in_correct_section = (current_section_name.lower() == section.lower())
			continue

		if in_correct_section:
			if stripped_line.lower().startswith(key.lower() + ' =') or stripped_line.lower().startswith(key.lower() + '='):
				indentation = line[:len(line) - len(line.lstrip())]
				lines[i] = f'{indentation}{key} = {value}\n'
				key_updated = True
				break

	if not key_updated:
		print(f"警告: 在 '{section}' 中未找到键 '{key}'。将使用标准方法添加，这可能导致注释丢失。")
		config = load_config()
		if not config.has_section(section):
			config.add_section(section)
		config.set(section, key, str(value))
		with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
			config.write(configfile)
		return

	try:
		with open(config_path, 'w', encoding='utf-8') as f:
			f.writelines(lines)
	except Exception as e:
		print(f"错误: 无法写入配置文件 '{CONFIG_FILE}': {e}")


def ensure_config_exists():
	"""公开的函数，用于在程序启动时调用，确保配置文件存在。"""
	if not os.path.exists(CONFIG_FILE):
		create_default_config()
