# 莱服郊狼桥接使用手册

桥接读取《船舶世界》战局日志，经 Coyote Game Hub 的游戏接口提供事件联动。控制台默认只监听本机 `127.0.0.1:8080`。

[Release 下载与校验](https://github.com/136084599/DG-Lab-Coyote-Game-Hub-WOWS-Lesta/releases/latest) · [项目首页](../README.md) · [更新记录](CHANGELOG.md)

## Windows 快速启动

先解压 `lesta-coyote-bridge-source.zip`，在解压后的 `lesta-bridge` 目录打开 PowerShell。新电脑先准备 [Python 3.13+](https://www.python.org/downloads/) 并运行下面的命令。若原整合目录已经有可用的 `python_env`，可以直接运行启动器。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install requests aiohttp pyyaml "pyjson5>=2.0.1,<2.1"
```

若使用更高版本或没有 `py` 命令，将第一条改为 `python -m venv .venv`，先用 `python --version` 确认版本。依赖只在首次准备环境时安装。启动器依次使用本目录的 `python_env`、`.venv` 和 PATH 中的 `python`。

```powershell
$demo = Join-Path (Get-Location) 'config.offline.yaml'
if (-not (Test-Path $demo)) {
    Copy-Item .\config.example.yaml $demo
}
.\start.bat --dry-run --config $demo
```

打开 [http://127.0.0.1:8080/](http://127.0.0.1:8080/)。在「战局与规则」看示例日志与模拟状态，也可以到「调参实验室」点击模拟按钮。示例上限为 0；`--dry-run` 始终只做模拟，即使改了参数也不会连接 Hub 或设备。按 Ctrl+C 可以停止。若端口被占用，先退出另一个控制台，或在配置文件中设置未占用的 `web_port`。

## 接入游戏和真实设备

1. 准备一个可用的 Hub。已有运行中的 Hub 可复用。在单独的 `config.yaml` 中配置其 `hub.api_url`。首次可复制 `config.example.yaml` 后再修改，已有部署保留自己的配置。
2. 结束离线实例，双击 `start.bat` 或运行 `.\start.bat --config .\config.yaml`。本地 Hub 如果放在 `coyote-game-hub-windows-amd64-dist/coyote-game-hub/`，启动器会在端口匹配且 Hub 尚未运行时尝试代启。远端 Hub 由对应电脑启动。
3. 到「战局与规则 → 开始使用 · 游戏与连接」自动检测，或手动选莱服安装目录，点「使用此目录」。关闭游戏后再点「安装 / 更新采集插件」。界面会在更新前备份已有插件文件。
4. 在「设备与波形」使用 Hub 确认设备连接、通道和输出设置。回到战局页核对游戏目录、采集插件、战局日志及 Hub 四项状态。Hub 可达只代表服务在线。
5. 保持示例上限为 0，先在训练场确认新日志与事件能到达控制台。点击「恢复监听」前核对目标；需要结束联动时可暂停或停止程序。

真实游戏、蓝牙和设备输出尚未在公开版本中做实机验收。

## 战局、事件和调参

- **监听与强度**设置合并窗口、基础值、默认波形与上限。受击合并不会延迟首击，同一窗口内后续受击累计伤害。
- **事件规则**可分别配置击沉、成就、连杀、起火、进水和沉没。启用事件波形前先配置默认波形。临时波形结束后会按状态回到仍有效的波形或默认波形。
- **伤害曲线和衰减**使用递增的伤害百分比阈值。可在「调参实验室」用尚未保存的表单值查看软件计算结果。曲线显示软件指令，设备反馈看 Hub。
- **设备目标**可选全部或指定游戏会话。切换目标会暂停新目标。核对连接后再点「恢复监听」。
- **配置管理**可导出 JSON 方案，也可先导入表单再确认「保存并应用」。完整 YAML 有独立的校验和保存按钮。修改游戏采集间隔后需要重新安装插件并重启游戏。导出的方案包含本机路径和设备目标，分享前先检查。
- **诊断**查看四项检查和「运行日志」，以及上方的目标、已发送状态、基础值和最近 HTTP 用时。

## 配套 Hub 与波形导入

先确认 Hub 提供 `/api/v2/game/…` 接口。波形补丁只适用于核对过的 Hub 1.5.0 构建。现有上游公开发布页未列该构建，页面列出的 2.0.0 尚未做此桥接的实机验证。Hub 的原版 JavaScript 解码器和 ZXing WASM 随匹配构建提供。

在桥接目录运行以下兼容性检查，将路径替换为包含 `server/index.js` 和 `public/` 的 Hub 程序目录。

```powershell
python tools/apply_hub_150_overlay.py "你的 Hub 程序目录"
```

如果使用本地虚拟环境，把 `python` 替换为 `.\.venv\Scripts\python.exe` 或已有的 `.\python_env\python.exe`。只有显示兼容时，再退出 Hub、备份安装目录，并用同一命令追加 `--apply`，最后重启 Hub。

- **公共库**进入「战局与规则 → 波形库」。选择 `.pulse` 文本、波形二维码图片或 Hub JSON / JSON5。点「导入到公共波形库」后刷新列表。重复项自动跳过，同 ID 内容不同会中止该批。桥接内导入需要使用预期目录的本机 Hub。远端 Hub 请使用它自己的导入界面。
- **设备波形**进入「设备与波形」，在 Hub 中给指定设备导入或编辑。进入此页会暂停战局控制，设置完成后回战局页手动恢复。配对二维码用于连接，波形二维码才用于导入。

[上游 Hub 公共发布页](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub/releases)

## OBS 直播与悬浮窗

1. 打开「直播 / 悬浮窗」。这个页面只读显示状态，切换过去不会暂停战局。
2. **原版设备显示**选择配套 Hub 的会话，可在预览中核对状态。不要公开带会话信息的浏览器源链接。
3. **联动状态条**直接显示桥接发出的指令、暂停和离线状态，无需会话 ID。在页面预览后复制浏览器源地址，粘贴到同一台电脑上的 OBS「浏览器」来源。
4. OBS 显示离线时先确认桥接仍在运行，再刷新来源。直播浏览器源用于叠加到 OBS 画面。

## 源码和测试

Release 的桥接 ZIP 提供 Python 源码、示例、采集插件源码和波形补丁。完整 fork 的根目录另外保留上游 Hub 源码。配套 Hub 程序、运行数据和设备配对由各自部署管理。

运行 `python -m unittest discover -s tests` 验证桥接。将匹配 Hub 的原版 `dg-pulse-helper-CU48u3U2.js` 放入 `hub-overlay/public/assets` 后，运行 `node --test tests/pulse-import.test.mjs` 检查波形解析。没有原版资源时，对应测试会跳过。
