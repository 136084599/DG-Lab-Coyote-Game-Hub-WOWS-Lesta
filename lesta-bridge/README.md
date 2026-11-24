# 莱服郊狼桥接 · 2026-11-19

桥接读取《船舶世界》战局日志，通过 Coyote Game Hub V2 API 更新事件规则、波形和直播状态。当前源代码包含 11 月 19 日的波形导入修复。设备连接由 Hub 管理。

## 先运行离线模拟

需要 Python 3.13 及以上。在本目录运行：

    python -m pip install requests aiohttp pyyaml "pyjson5>=2.0.1,<2.1"
    Copy-Item config.example.yaml config.yaml
    python main.py --check-config --config config.yaml
    python main.py --dry-run --config config.yaml

浏览器打开 http://127.0.0.1:8080/。示例配置将输出上限设为 0，离线模拟无需 Hub 或设备。

## 配套 Hub 与波形导入

使用自己安装的 Coyote Game Hub V2。已运行的 Hub 可以由桥接复用，实际服务 URL 写在本机的 config.yaml 中。旧 Windows 启动器在匹配目录存在且 Hub 未运行时可代启 Hub。此处只发布源码与安全示例。

11 月 19 日兼容补丁针对已核对的 Hub 1.5.0 构建，防止查询私有波形时污染公共列表。先运行：python tools/apply_hub_150_overlay.py "你的 Hub 程序目录"。如果显示兼容，关闭 Hub 并备份程序，再追加 --apply 安装补丁。哈希不符时脚本保留现有文件。原版二维码解码资源需要由配套 Hub 提供。

采集插件源码在 mods/BattleRecorder。按游戏官方 ModsAPI 和项目目录约定自行安装，安装前退出游戏。真实训练场及硬件联动在使用者的环境单独验收。设备输出以设备端状态为准。

[上游 Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub) · [早期莱服桥接](https://github.com/136084599/wows_dglab-lesta)

## 验证

Python：python -m unittest discover -s tests。波形前端测试：把配套 Hub 原版的 dg-pulse-helper-CU48u3U2.js 复制到 hub-overlay/public/assets，再运行 node --test tests/pulse-import.test.mjs。缺少配套资源时，前端测试会明确跳过。
