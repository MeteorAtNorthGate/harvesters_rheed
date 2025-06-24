# camera_setup.py
# 作用: 初始化 Harvester 库并发现连接的相机设备。

from harvesters.core import Harvester


def setup_harvester(cti_path):
    """
    使用指定的 CTI 文件路径初始化 Harvester。
    :param cti_path: GenTL Producer (.cti) 文件的完整路径。
    """
    if not cti_path:
        print("[错误] CTI 文件路径为空。请检查 config.ini 文件。")
        return None

    try:
        h = Harvester()
        h.add_file(cti_path)
        h.update()

        if not h.device_info_list:
            print(f"[警告] CTI 文件 '{cti_path}' 已加载，但未发现任何设备。请检查相机连接和电源。")
        else:
            print(f"发现设备: {h.device_info_list}")

        return h
    except Exception as e:
        print(f"[错误] 初始化 Harvester 失败: {e}")
        return None


def cleanup_harvester(harvester):
    """
    重置 Harvester 实例以释放所有相关资源。
    """
    if harvester:
        harvester.reset()
        print("Harvester 资源已成功释放。")
