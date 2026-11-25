# 莱服郊狼桥接 · 2026-11-19

桥接读取《船舶世界》战局日志，通过 Coyote Game Hub V2 API 更新事件规则、波形和直播状态。当前源代码包含 11 月 19 日的波形导入修复。设备连接由独立运行的 Hub 管理。

[Release 的桥接源码 ZIP](https://github.com/136084599/DG-Lab-Coyote-Game-Hub-WOWS-Lesta/releases/tag/lesta-2026.11.19-r1)包含桥接、示例配置和日志、采集插件源码及 Hub 波形补丁。Hub 程序、Node 运行时和原版解码资源由配套 Hub 提供。完整克隆仓库还能拿到根目录的 Hub 源码。

## 先运行离线模拟

需要 Python 3.13 及以上。在本目录运行：

    python -m pip install requests aiohttp pyyaml "pyjson5>=2.0.1,<2.1"
    Copy-Item config.example.yaml config.yaml
    python main.py --check-config --config config.yaml
    python main.py --dry-run --config config.yaml

浏览器打开 http://127.0.0.1:8080/。示例配置将输出上限设为 0，离线模拟无需 Hub 或设备。

## 配套 Hub 与波形导入

使用能提供 `/api/v2/game/…` 接口的独立 Hub。在桥接的 `config.yaml` 中把 `hub.api_url` 指到正在运行的 Hub，已有 Hub 可直接复用。Windows 的 `start.bat` 会在预期目录存在可用 Hub、且本机 Hub 尚未运行时尝试代启。Hub 程序需预先准备。

11 月 19 日的兼容补丁针对已核对的 Hub 1.5.0 构建，防止查询私有波形时污染公共列表。上游公开发布页当前未列出已核对的 1.5.0 构建。页面列出的 2.0.0 尚未做这套桥接的实机验证。补丁以构建哈希和实际资源为准。

从桥接目录先运行下列命令，将路径换成包含 `server/index.js` 和 `public/` 的 Hub 程序目录。

```powershell
python tools/apply_hub_150_overlay.py "你的 Hub 程序目录"
```

如果显示兼容，退出 Hub，备份程序，再在命令末尾追加 `--apply` 并重启 Hub。检查会同时确认程序哈希、原版 JavaScript 解码器和 ZXing WASM 文件。没有匹配的 Hub 时，可以继续使用上面的离线模拟。

采集插件源码在 mods/BattleRecorder。按游戏官方 ModsAPI 和项目目录约定自行安装，安装前退出游戏。真实训练场及硬件联动在使用者的环境单独验收。设备输出以设备端状态为准。

[上游 Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub) · [早期莱服桥接](https://github.com/136084599/wows_dglab-lesta)

## 验证

Python：python -m unittest discover -s tests。波形前端测试：把配套 Hub 原版的 dg-pulse-helper-CU48u3U2.js 复制到 hub-overlay/public/assets，再运行 node --test tests/pulse-import.test.mjs。缺少配套资源时，前端测试会明确跳过。
