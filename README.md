# DG-Lab 郊狼 · 船舶世界莱服联动

把莱服战局日志接入 Coyote Game Hub。浏览器控制台可以检查游戏采集、编辑事件规则、导入波形、离线调参，并为 OBS 提供直播显示。

**[下载 Windows x64 懒人包](https://github.com/136084599/DG-Lab-Coyote-Game-Hub-WOWS-Lesta/releases/tag/lesta-2026.11.19-windows-r1)** · [懒人包说明](packaging/windows/PORTABLE-README.md) · [桥接源码 ZIP](https://github.com/136084599/DG-Lab-Coyote-Game-Hub-WOWS-Lesta/releases/tag/lesta-2026.11.19-r2) · [完整使用教程](lesta-bridge/README.md) · [更新记录](lesta-bridge/CHANGELOG.md)

## 懒人包快速启动

下载 `Lesta-Coyote-Windows-x64-Portable.zip` 并完整解压。双击 `Start-Demo.cmd` 可直接体验离线控制台。双击 `Start.cmd` 启动桥接与包内 Hub，在「战局与规则」选游戏目录后，可以直接安装包内采集插件及 ModsAPI 加载标记。默认输出上限为 0。

整包已带 Python、Node.js、匹配的 Hub、波形修复和采集插件。已有游戏客户端和郊狼设备由使用者自行配置。 [懒人包说明](packaging/windows/PORTABLE-README.md)

## 使用桥接源码包

1. 下载并解压 Release 附件 `lesta-coyote-bridge-source.zip`。新电脑按[安装步骤](lesta-bridge/README.md#windows-快速启动)准备 Python 3.13+ 和依赖。
2. 在解压后的 `lesta-bridge` 目录用 PowerShell 运行下面的命令。已有项目目录的 `start.bat` 会优先使用随目录准备的 `python_env`。

```powershell
$demo = Join-Path (Get-Location) 'config.offline.yaml'
if (-not (Test-Path $demo)) {
    Copy-Item .\config.example.yaml $demo
}
.\start.bat --dry-run --config $demo
```

打开 [http://127.0.0.1:8080/](http://127.0.0.1:8080/)，进入「调参实验室」试用模拟。它使用示例日志，输出上限为 0，并且不会连接 Hub 或设备。配置文件与实际联动分开保存。

## 功能与入口

| 功能 | 在哪里用 |
| --- | --- |
| 检测莱服、安装采集插件与检查日志 | 「战局与规则 → 开始使用 · 游戏与连接」 |
| 受击响应、事件规则、伤害曲线和衰减 | 「战局与规则 → 监听与强度」「事件规则」「伤害曲线与衰减」 |
| 设备连接、通道与私有波形 | 「设备与波形」打开配套 Hub。进入该页会暂停战局控制 |
| 公共波形导入与列表刷新 | 「战局与规则 → 波形库」。支持 `.pulse`、波形二维码和 JSON / JSON5 |
| 保存或共享参数方案 | 「战局与规则 → 参数方案」。导入先进入表单，确认后再保存 |
| 模拟受击与比较参数 | 「调参实验室」。用未保存的参数绘制模拟曲线 |
| OBS 原版设备显示、指令状态条与预览 | 「直播 / 悬浮窗」。选样式后复制浏览器源链接 |
| 联动状态、最近响应与故障诊断 | 「战局与规则」的状态栏、检查清单和运行日志 |

## Release 和现有环境

- **桥接 ZIP**包含控制台、示例、采集插件源码和波形补丁。新电脑使用 Python 3.13+ 即可离线运行。
- **实际联动**需要独立运行的兼容 Hub。已有 Hub 可以复用。旧的本地整合目录如果已有 `python_env` 和 Hub 程序，可继续用原目录的 `start.bat`。迁移到新目录前按[联动教程](lesta-bridge/README.md#接入游戏和真实设备)检查游戏路径、设备目标和 Hub。
- **完整源码**可通过克隆本仓或下载 GitHub 自动生成的 `Source code (zip)` 获取。根目录 `frontend/`、`server/` 是上游 [Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub) 的源码，标为 2.0.0。`lesta-bridge/` 是莱服桥接。它们需要分别运行。

桥接调用 Hub 的 `/api/v2/game/…` 接口。随包波形补丁只适用于通过 SHA-256 与原版资源检查的 Hub 1.5.0 构建。已验证官方 Hub v2.0.0 的 Windows 构建与包内波形补丁匹配，官方包内部版本号为 1.5.0。已在干净目录验证双击启动、Hub 接口与采集插件安装。游戏训练场和实际设备仍需在使用者环境验收。 [Hub 兼容与波形导入](lesta-bridge/README.md#配套-hub-与波形导入)

[早期桥接](https://github.com/136084599/wows_dglab-lesta)用于对照。许可见 [LICENSE](LICENSE)。实际账号、配对信息、个人波形、实际部署配置和日志留在本机。
