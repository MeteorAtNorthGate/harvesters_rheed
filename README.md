# harvesters_rheed
This is a GUI built with Harvesters and PySide6 for accessing GenICam-compliant CCD cameras and processing RHEED videos.<br/>
这是一个用于管理工业CCD相机和预览、保存、分析Rheed图像的软件，基于Qt和harvesters。<br/>
基本上只要相机遵循GENICAM传输层规范（你安装完相机驱动和runtime什么的之后能在系统环境变量里找到一个独特的GENICAM的path），这个软件就可以通用。<br/>
![rheed_analyzer](https://github.com/user-attachments/assets/5f8388bc-43d2-4ac2-80d5-e2e8e2f06424)
Please use Python version >=3.9 <=3.11 ,the lastest 3.13 would not work, for we are using harvesters.<br/>
In short, I recommend using .venv or such to configure the environment.<br/>
python版本建议3.9~3.11，3.13不行，其他依赖包参见requirements，请使用对应版本的依赖包，否则pyqtgraph容易失效（比如画不出曲线什么的=。=）<br/>
嘛总而言之,基本上是必须使用虚拟环境了，几个依赖包都挺脆的。<br/>
**the main entry is main_app.py**<br/>
**程序主入口是 main_app.py**<br/>
