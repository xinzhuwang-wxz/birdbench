"""让测试无需安装项目即可 import birdbench（离线 gate：src 上 sys.path）。"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
