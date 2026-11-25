# DG-Lab 郊狼 · 船舶世界莱服联动

这个 fork 同时保存 [Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub) 的源码和莱服桥接。Hub 负责连接设备，桥接读取莱服战局日志并提供规则控制台、波形导入和直播状态。

**接真机需要一个单独运行的兼容 Hub。** 当前 Release 的 `lesta-coyote-bridge-source.zip` 只装了莱服桥接，Hub 程序和原版二维码解码资源由配套 Hub 提供。已有兼容 Hub 可以继续使用。离线模拟只需要桥接和 Python 3.13+。

[下载莱服桥接源码包](https://github.com/136084599/DG-Lab-Coyote-Game-Hub-WOWS-Lesta/releases/tag/lesta-2026.11.19-r1) · [安装与离线模拟](lesta-bridge/README.md) · [更新记录](lesta-bridge/CHANGELOG.md) · [上游 Hub 发布页](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub/releases)

## 下载和使用

| 我想做什么 | 用哪个包 | 还需要什么 |
| --- | --- | --- |
| 离线看控制台或模拟战局 | 下载 `lesta-coyote-bridge-source.zip` | Python 3.13+。包内示例日志的输出上限为 0 |
| 玩莱服并联动郊狼设备 | 使用同一个桥接源码包 | 独立运行的兼容 Hub、已配对设备和游戏内的战局日志采集插件 |
| 查看或维护 Hub 源码 | 拉取本仓库，或下载 GitHub 自动生成的 `Source code (zip)` | 根目录的 `frontend/` 和 `server/` 是 Hub 源码，`lesta-bridge/` 是桥接源码 |

## Hub 兼容性

桥接通过 Hub 的 `/api/v2/game/…` 接口工作。这里的 V2 指接口版本。随桥接提供的波形补丁只匹配已核对的 Hub 1.5.0 构建，安装前的 SHA-256 和资源检查以[桥接指南](lesta-bridge/README.md#配套-hub-与波形导入)为准。仓库根目录的 Hub 源码标为 2.0.0。这个版本和其他 Hub 构建的实际设备联动尚未验证。

已在隔离环境运行 Python 测试和波形解析测试。真实游戏训练场、蓝牙连接及硬件输出需要另行验收。

[早期莱服桥接仓](https://github.com/136084599/wows_dglab-lesta)用于对照。许可见 [LICENSE](LICENSE)。实际账号、设备配对、个人波形、现网地址和日志保留在部署环境。
