# DG-Lab 郊狼 · 船舶世界莱服联动

这是 [Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub) 的莱服集成版。Hub 负责设备连接。桥接读取莱服的战局日志，提供规则控制台、波形导入和直播状态。

**[安装与离线模拟](lesta-bridge/README.md)** · [更新记录](lesta-bridge/CHANGELOG.md) · [上游 Hub 下载](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub/releases)

## 当前版本

已加入本地 2026-11-19 版桥接。新版含波形文本及二维码导入，以及查询私有波形时保护公共列表的 Hub 1.5.0 兼容修复。补丁按 SHA-256 确认匹配的 Hub 构建。

## 第一次运行

在 `lesta-bridge/` 按说明安装 Python 依赖并复制示例配置。可以先启动离线模拟，示例输出上限为 0，无需连接设备。接入实际设备前按指南安装配套 Hub，并在自己的环境核对设备、规则和接口配置。

已在隔离环境运行 Python 测试和波形解析测试。真实游戏训练场、蓝牙连接及硬件输出需要另行验收。

根目录保留 Hub fork 源码和上游历史。莱服模块在 [`lesta-bridge/`](lesta-bridge/)。[早期莱服桥接仓](https://github.com/136084599/wows_dglab-lesta)用于对照。许可见 [LICENSE](LICENSE)。

公开范围为源码、限定版本的兼容补丁和示例配置。实际账号、设备配对、个人波形、现网地址和日志保留在部署环境。
