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
        # 如果环境变量存在且是一个有效的目录，则拼接路径
        final_cti_path = os.path.join(genicam_dir, 'ProducerGEV.cti')
        comment = '# CTI 文件路径已根据系统环境变量 GENICAM_GENTL64_PATH 自动生成。'
    else:
        # 否则，使用默认路径并提示用户
        print("警告: 未能从环境变量 'GENICAM_GENTL64_PATH' 找到有效的路径。")
        print(f"将使用默认后备路径: {default_cti_path}")
        final_cti_path = default_cti_path
        comment = '# 未找到环境变量 GENICAM_GENTL64_PATH，已使用默认路径。请在系统环境变量中设置该变量，或手动修改下方路径。'

    # Paths Section
    config['Paths'] = {
        comment: None,
        'cti_path': final_cti_path
    }

    # Camera Section
    config['Camera'] = {
        '# 请在此处手动设置您相机的工作帧率 (Frames Per Second)，通常可以在说明书或者官网找到': None,
        'fps': '70'
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


def ensure_config_exists():
    """公开的函数，用于在程序启动时调用，确保配置文件存在。"""
    if not os.path.exists(CONFIG_FILE):
        create_default_config()
