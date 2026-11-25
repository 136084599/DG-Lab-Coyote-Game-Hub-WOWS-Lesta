# 莱服郊狼 Windows x64 懒人包

完整解压 ZIP 到一个可写目录，再双击 **Start-Demo.cmd**。控制台默认在 http://127.0.0.1:8080/。离线演示使用示例日志，无需联网安装依赖，默认不连接设备。

## 接入自己安装的莱服与郊狼

1. 退出离线控制台，双击 **Start.cmd**。包内的 Hub 会启动，桥接默认在 8080，Hub 在 8920。首次从示例创建配置，设备输出上限为 0。
2. 在「战局与规则」选择实际游戏目录，点「使用此目录」。退出游戏后，点「安装 / 更新采集插件」。安装器会补齐 ModsAPI 加载标记并安装包里的 BattleRecorder，更新时备份原插件。
3. 进入「设备与波形」完成自己的设备连接，再回到战局页。在训练场先验证日志、规则和设备状态。详细步骤见 [使用手册](README.md)。
4. 关闭控制台用 Ctrl+C。若同一台电脑已运行其他 Hub 或桥接，先退出原实例或使用互不冲突的端口。

## 包内组件

本包带 Windows x64 Python 3.13.16、桥接依赖、官方 Hub v2.0.0 Windows 构建和 Node.js 22、经过哈希核对的波形补丁，以及所需的采集插件。官方 Hub 安装包的软件元数据同时使用 v2.0.0 发布标签和 1.5.0 内部包版本。Python、Node 和 Hub 来源与校验值见 `upstream-components.json`。相关授权说明在 Python、Node 和 Hub 目录，以及 `LICENSE-Hub.txt`。游戏客户端由 Lesta Game Center 安装。实际账号、游戏路径、设备配对、个人波形和日志在使用时由各自电脑生成。

[项目首页](https://github.com/136084599/DG-Lab-Coyote-Game-Hub-WOWS-Lesta) · [Lesta 模组政策](https://lesta.ru/support/ru/products/mk/article/10720/)
