<div align="center">

# EldenRingTool

**艾尔登法环探索、任务与收集助手**

在一张地图上整理探索进度，在任务与图鉴中寻找下一步。

[![Version](https://img.shields.io/badge/version-0.1.0-247a68?style=flat-square)](pyproject.toml)
[![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Qt](https://img.shields.io/badge/UI-PySide6%20%2B%20QML-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![License](https://img.shields.io/badge/License-LGPL--3.0-5865A1?style=flat-square)](LICENSE)
[![Local](https://img.shields.io/badge/Game%20%26%20Saves-Read--only-68717A?style=flat-square)](#存档与本地数据)

[功能亮点](#功能亮点) · [快速开始](#快速开始) · [常见问题](#常见问题) · [参考与致谢](#参考与致谢)

</div>

---

EldenRingTool 是一款使用 Python 与 Qt 构建的本地桌面工具，将地图探索、角色收集进度和任务指引集中在一起。游戏资源与存档以只读方式读取，手动标记独立保存在工具目录中。

> **自带游戏，自行解析。** 本仓库不附带从游戏副本提取的地图、物品图标、资源索引或任何玩家存档。首次启动时，请选择你自己的《艾尔登法环》PC 游戏副本，程序会在本地生成所需资源。

## 功能亮点

| 功能 | 你可以做什么 |
| --- | --- |
| 地图探索 | 切换地图区域、搜索和筛选标记，查看位置并隐藏已完成内容。 |
| 收集图鉴 | 按类别浏览收集品、查看持有状态与来源，寻找尚未收集的物品。 |
| 任务指引 | 查看任务步骤与进度，结合存档状态和手动确认整理旅程。 |
| 多角色进度 | 切换角色，各角色的手动标记独立保存。 |
| 存档更新 | 读取本地存档，在游戏保存后更新可识别的角色与收集状态。 |
| 内容筛选 | 在设置中选择 DLC 内容的显示或隐藏，按自己的游玩范围浏览。 |
| 本地资源解析 | 从自己的游戏副本生成地图与图鉴；游戏或模组资源变化后可重新解析。 |

## 快速开始

### 准备工作

- 已安装的《艾尔登法环》PC 版及其完整游戏资源。
- [Python 3.13 或更新版本](https://www.python.org/downloads/)，并确保可以使用 `python` 命令和 `pip`。
- 一个可写的工具目录，用于保存解析结果和个人进度。
- 首次安装依赖需要网络连接；解析资源时需要预留本地磁盘空间。

### Windows

1. 下载本仓库源码并解压到独立目录。
2. 双击 **`Run_EldenRingTool.bat`**。
3. 首次启动会在缺少 PySide6 时自动安装界面依赖。
4. 在资源解析界面选择 **`ELDEN RING/Game/eldenring.exe`**。
5. 按界面提示开始解析，缺少的解析依赖会自动安装，进度与日志会显示在界面中。
6. 解析完成并校验通过后进入主界面，选择角色开始查看进度。

如果没有自动找到存档，可以在设置中手动选择存档文件。

<details>
<summary><strong>手动安装与启动</strong></summary>

在解压后的项目目录打开终端：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

后续继续使用最后一条命令，即可在同一个独立环境中启动。

</details>

<details>
<summary><strong>Linux 启动</strong></summary>

使用 Python 3.13+ 创建独立环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
sh run-eldenringtool.sh
```

选择可访问的 PC 版游戏目录。Proton 环境中的存档可通过设置手动指定；不同 Linux 环境下的兼容情况需要实际验证。

</details>

## 存档与本地数据

**工具不修改游戏文件或游戏存档。** 手动收集标记、任务确认和界面设置保存到 `data/user-state.json`，可以单独备份该文件。

| 内容 | 保存位置 | 是否随源码分发 |
| --- | --- | --- |
| 地图瓦片与清单 | `assets/tiles/` | 否，由用户本地解析 |
| 游戏物品与地图图标 | `assets/icons/items/`、`assets/icons/` 下的数字图标与索引 | 否，由用户本地解析 |
| 地图标记、图鉴与资源索引 | `data/` 下的生成文件、`cache/` | 否，由用户本地解析 |
| 个人设置与手动进度 | `data/user-state.json` | 否，由使用过程生成 |
| 任务定义、解析规则和基础分类资源 | `data/quests/`、`data/paramdefs/`、`data/mfg/` 等 | 是，供程序运行使用 |

设置中的“清理解析缓存”会保留手动进度。游戏或模组更新后，请按提示重新解析，使本地索引与当前资源一致。

## 常见问题

**为什么下载后没有地图或图鉴？**  
这是干净的源码版本。地图、图标和图鉴内容需要从你自己的游戏副本生成；首次启动会先进入解析界面。

**解析失败怎么办？**  
确认选择的是完整游戏的 `Game` 目录或其中的 `eldenring.exe`，而不是启动器。检查界面日志中的依赖安装或资源读取错误；解析期间不要更新、移动或替换游戏文件，修复后重新解析。

**能读取模组存档吗？**  
设置中可以选择 `.sl2`、`.co2` 或 `.err` 文件。能否读取取决于文件内部格式，扩展名并不保证兼容。模组资源也可能改变物品、事件和任务逻辑，具体支持情况以实际解析结果为准。

**为什么完成状态没有立刻更新？**  
进度根据已写入磁盘的存档读取。请等待游戏完成保存，并确认选择了正确的存档与角色。无法从存档可靠判断的内容可使用手动标记。

**隐藏 DLC 是否会修改游戏？**  
不会。这只是本工具的内容显示设置，不检测或改变购买状态；未指定时保持内容可见。

**如何反馈问题？**  
请在本仓库的 Issues 中提供工具版本、系统与 Python 版本、游戏或模组版本、复现步骤和相关错误日志。提交前去掉个人路径、账号信息和存档内容。

## 参考与致谢

本项目参考了 **[egormagurin/EldenRingMap](https://github.com/egormagurin/EldenRingMap)**，感谢该项目为艾尔登法环地图与探索工具提供的思路。本项目是独立的社区工具，不代表参考项目作者或游戏官方。

同时感谢提供解析资料、参数定义与基础资源的开源项目。相关来源和保留的许可声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 开源许可

本项目原创代码以 **GNU Lesser General Public License v3.0（LGPL-3.0-only）** 发布，完整文本见 [LICENSE](LICENSE) 及其引用的 [COPYING](COPYING)。第三方代码、数据和资源保留各自的权利与许可声明，不因本项目的许可证而变更。

《艾尔登法环》及相关名称、游戏内容的权利归各自权利人所有。本仓库不分发用户游戏副本的解析产物。
