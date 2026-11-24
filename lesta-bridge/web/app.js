let cfg,
  pulses = [],
  fields = [],
  dirty = false,
  checking = false;
const $ = (id) => document.getElementById(id),
  say = (text) => ($("message").textContent = text);
async function api(path, body, rawFile = false) {
  let r = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: rawFile ? body : JSON.stringify(body),
        },
  );
  let d = await r.json();
  if (!r.ok) throw Error(d.error || r.statusText);
  return d;
}
function read(path) {
  return path.split(".").reduce((v, k) => v[k], cfg);
}
function write(path, value) {
  let a = path.split("."),
    k = a.pop();
  a.reduce((v, k) => v[k], cfg)[k] = value;
}
function input(parent, label, path, kind = "number", options) {
  let box = document.createElement("label");
  box.textContent = label;
  let el = document.createElement(options ? "select" : "input");
  if (!options) {
    el.type = kind;
    if (kind === "number") el.step = "any";
  } else for (let [value, text] of options) el.add(new Option(text, value));
  if (kind === "checkbox") el.checked = read(path);
  else el.value = read(path);
  el.dataset.configPath = path;
  box.append(el);
  parent.append(box);
  fields.push(() => {
    if (kind === "number" && !el.value.trim()) throw Error(label + "不能为空");
    write(
      path,
      kind === "checkbox"
        ? el.checked
        : kind === "number"
          ? Number(el.value)
          : el.value,
    );
  });
  return el;
}
function pulseSelect(parent, label, path) {
  let box = document.createElement("label");
  box.textContent = label;
  let el = document.createElement("select");
  el.dataset.path = path;
  box.append(el);
  parent.append(box);
  fillPulse(el, read(path));
  fields.push(() => write(path, JSON.parse(el.value)));
}
function fillPulse(el, value) {
  el.replaceChildren(new Option("不切换", "null"));
  for (let p of pulses)
    el.add(new Option(p.name + " (" + p.id + ")", JSON.stringify(p.id)));
  let v = JSON.stringify(value);
  if (![...el.options].some((o) => o.value === v))
    el.add(new Option("已配置：" + v, v));
  el.value = v;
}
function render() {
  fields = [];
  for (let id of ["general", "rules", "tuning", "advanced", "connection"])
    $(id).replaceChildren();
  let g = $("general");
  input(g, "直接指定日志路径（可留空）", "log_path", "text");
  input(g, "文件检查间隔 / 秒", "poll_sec");
  input(g, "伤害合并窗口 / 秒", "window_sec");
  input(g, "每窗口基础增量 / 强度点", "shock.addStrengthWhenHitInThisRound");
  input(g, "基础下限", "shock.minBaseStrength");
  input(g, "软件发送上限（设备另有限制）", "shock.maxStrength");
  pulseSelect(g, "默认波形", "shock.defaultPulseId");
  const labels = {
    kill: "击杀",
    achievement: "成就",
    streak: "连杀",
    burning: "起火",
    flooding: "进水",
    death: "沉没",
  };
  for (let [key, title] of Object.entries(labels)) {
    let row = document.createElement("div");
    row.className = "rule";
    let b = document.createElement("b");
    b.textContent = title;
    row.append(b);
    input(row, "启用", "rules." + key + ".enabled", "checkbox");
    input(row, "强度变化", "rules." + key + ".strengthDelta");
    pulseSelect(row, "事件波形", "rules." + key + ".pulseId");
    if ("pulseDuration" in cfg.rules[key])
      input(row, "波形秒数", "rules." + key + ".pulseDuration");
    $("rules").append(row);
  }
  let t = $("tuning");
  input(t, "随机偏移下限", "hub.randomize_strength_range.0");
  input(t, "随机偏移上限", "hub.randomize_strength_range.1");
  input(t, "启用衰减", "hub.decay.enabled", "checkbox");
  input(t, "衰减间隔 / 秒", "hub.decay.interval");
  input(t, "每步保留比例", "hub.decay.factor");
  input(t, "不衰减时受击持续 / 秒", "hub.hit_duration");
  input(t, "死亡强度持续 / 秒", "rules.death.duration");
  input(t, "曲线模式", "hub.interpolation", "text", [
    ["step", "阶梯（兼容旧参数）"],
    ["linear", "线性插值"],
  ]);
  input(t, "衰减方式", "hub.decay.mode", "text", [
    ["step", "分步按比例"],
    ["half_life", "平滑半衰期"],
    ["linear", "匀速下降"],
  ]);
  input(t, "受击峰值保持 / 秒", "hub.decay.hold_sec");
  input(t, "半衰期 / 秒", "hub.decay.half_life");
  input(t, "匀速每秒下降 / 点", "hub.decay.linear_rate");
  input(t, "受击效果最长 / 秒", "hub.decay.max_duration");
  input(t, "衰减底值", "hub.decay.min_strength");
  input(t, "再次受击", "shock.retrigger", "text", [
    ["replace", "以新伤害替换"],
    ["max", "保留较强效果"],
    ["add", "叠加剩余效果"],
  ]);
  let a = $("advanced");
  input(a, "游戏采集间隔 / 秒", "recorder.sample_sec");
  input(a, "过滤低于该损血比例 / %", "shock.minDamagePercent");
  input(a, "伤害曲线倍率", "shock.damageScale");
  input(a, "基础值自动恢复", "shock.baseRecovery.enabled", "checkbox");
  input(a, "无受击或奖励后等待 / 秒", "shock.baseRecovery.delay");
  input(a, "基础值每秒恢复 / 点", "shock.baseRecovery.rate");
  input(a, "连杀间隔 / 秒", "rules.streak.window");
  input(a, "连杀门槛 / 次", "rules.streak.minConsecutive");
  input(a, "输出检查间隔 / 秒", "output.tick_sec");
  input(a, "状态重申间隔 / 秒", "output.heartbeat_sec");
  input(a, "断线重试间隔 / 秒", "output.retry_sec");
  let c = $("connection");
  input(c, "Hub 服务地址", "hub.api_url", "text");
  input(c, "广播到所有设备", "hub.toAllDevices", "checkbox");
  input(c, "单设备游戏 ID", "hub.client_id", "text");
  input(c, "HTTP 请求超时 / 秒", "hub.timeout");
  $("segments").value = JSON.stringify(cfg.hub.Segment);
  $("raw").value = JSON.stringify(cfg, null, 2);
  $("game-path").value = cfg.wows_path;
  dirty = false;
  decayFields();
}
async function load() {
  cfg = (await api("/api/get_config")).config;
  render();
  await setupStatus();
}
async function refresh() {
  pulses = (await api("/api/pulses")).pulse_list;
  document
    .querySelectorAll("select[data-path]")
    .forEach((el) => fillPulse(el, JSON.parse(el.value)));
  $("pulse-status").textContent =
    "已读取 " + pulses.length + " 个真实波形。模拟模式返回空列表。";
}
function action(id, fn) {
  $(id).onclick = async () => {
    let b = $(id),
      text = b.textContent;
    b.disabled = true;
    b.textContent = "处理中…";
    try {
      await fn();
    } catch (e) {
      say(e.message);
    } finally {
      b.disabled = false;
      b.textContent = text;
    }
  };
}
action("save", async () => {
  for (let f of fields) f();
  cfg.hub.Segment = JSON.parse($("segments").value);
  let d = await api("/api/save_config", cfg);
  await load();
  say(
    d.paused
      ? "配置已保存；输出处于暂停状态，请检查连接后恢复。"
      : "配置已保存并应用。",
  );
});
action("save-raw", async () => {
  let d = await api("/api/save_config", JSON.parse($("raw").value));
  await load();
  say(d.paused ? "配置已保存，输出仍暂停。" : "完整配置已保存。");
});
action("reload", async () => {
  if (dirty && !confirm("重新读取会放弃尚未保存的参数，是否继续？")) return;
  await load();
  say("已重新读取。");
});
action("refresh", refresh);
action("stop", async () => {
  await api("/api/stop", {});
  say("已暂停并发送归零。");
});
action("resume", async () => {
  await api("/api/resume", {});
  showPage("battle");
  say("已恢复；从当前日志位置接受新事件。");
});
action("import", async () => {
  let f = $("pulse-file").files[0];
  if (!f) throw Error("请先选择波形文件或二维码图片");
  if (f.size > 2 * 1024 * 1024) throw Error("文件不能超过 2 MiB");
  let d;
  if (/\.(pulse|png|jpe?g|webp)$/i.test(f.name)) {
    const { importPulseFrames } = await import("/assets/pulse-file-import.js");
    const frames = await importPulseFrames(f);
    d = await api("/api/pulses/import", { name: f.name.replace(/\.[^.]+$/, ""), pulseData: frames });
  } else {
    d = await api("/api/pulses/import", f, true);
  }
  if (d.dry_run) return say(d.message);
  $("pulse-file").value = "";
  say(d.message + " 正在确认 Hub 列表…");
  try {
    for (const wait of [0, 300, 700, 1200]) {
      if (wait) await new Promise((resolve) => setTimeout(resolve, wait));
      await refresh();
      const visible = new Set(pulses.map((pulse) => pulse.id));
      if (d.ids.every((id) => visible.has(id))) return say(d.message + " 已在 Hub 列表中确认，可以在规则里选择。");
    }
  } catch {}
  say(d.message + " 当前 Hub 列表尚未确认，请稍后点「刷新波形列表」，无需重复导入。");
});
async function poll() {
  try {
    let [s, logs] = await Promise.all([
      api("/api/status"),
      api("/api/get_logs"),
    ]);
    $("check-hub").textContent =
      "4 · " +
      (s.dry_run
        ? "模拟模式，不连接设备"
        : s.hub_reachable
          ? "Hub 可达；设备配对请点上方入口"
          : "等待 Hub，请检查设备连接入口");
    $("check-log").textContent =
      "3 · " +
      (s.log_exists
        ? "日志已找到；已读取 " + s.lines + " 行"
        : "等待日志；请先进入一场对局");
    $("mode").textContent =
      (s.dry_run ? "模拟 · " : "") +
      (s.device_mode
        ? "设备设置"
        : s.paused
          ? "已暂停"
          : s.hub_reachable || s.dry_run
            ? "监听中"
            : "等待 Hub");
    $("strength").textContent =
      s.desired_strength + " / " + (s.sent_strength ?? "—");
    $("base").textContent = s.base.toFixed(2);
    $("latency").textContent =
      s.request_ms === null ? "—" : s.request_ms + " ms";
    $("log-status").textContent =
      (s.log_exists ? "日志已找到：" : "等待日志：") +
      s.log_path +
      " | 已读 " +
      s.lines +
      " 行，异常 " +
      s.parse_errors +
      " 行" +
      (s.health != null
        ? " | 血量 " + s.health + " / " + s.max_health
        : " | 等待血量快照") +
      (s.last_line_age_sec === null
        ? ""
        : " | " + s.last_line_age_sec + " 秒前更新") +
      (s.hub_error ? " | " + s.hub_error : "");
    $("logs").textContent = logs.join("\n");
  } catch (e) {
    $("mode").textContent = "控制台连接中断";
  }
  setTimeout(poll, 1000);
}

function decayFields() {
  let mode = document.querySelector('[data-config-path="hub.decay.mode"]');
  if (!mode) return;
  for (let [path, expected] of [
    ["hub.decay.interval", "step"],
    ["hub.decay.factor", "step"],
    ["hub.decay.half_life", "half_life"],
    ["hub.decay.linear_rate", "linear"],
  ]) {
    let field = document.querySelector('[data-config-path="' + path + '"]');
    field.parentElement.hidden = mode.value !== expected;
  }
  mode.onchange = decayFields;
}
async function setupStatus(path) {
  let info = await api(
    "/api/setup" +
      (path === undefined ? "" : "?path=" + encodeURIComponent(path)),
  );
  $("setup-hint").textContent = info.valid
    ? info.edition + " · 版本 " + info.version + " · " + info.path
    : info.message;
  if (path === undefined) {
    $("check-game").textContent =
      "1 · " +
      (info.valid
        ? "游戏目录已确认 · " + info.version
        : "尚未设置有效游戏目录");
    $("check-mod").textContent =
      "2 · " +
      (info.valid && info.mod_installed
        ? "采集脚本与加载标记已就绪"
        : info.recorder_present
          ? "已有脚本，缺少 ModsAPI 加载标记"
          : "当前版本缺少采集插件");
    $("install-mod").disabled = !info.valid;
  }
  return info;
}
async function detect() {
  if (checking) return;
  checking = true;
  try {
    let d = await api("/api/detect_games");
    let select = $("detected-games");
    select.replaceChildren(
      new Option(
        d.candidates.length ? "请选择检测结果" : "未检测到，请手动选择目录",
        "",
      ),
    );
    for (let item of d.candidates)
      select.add(
        new Option(
          item.edition + " · " + item.path + " [" + item.source + "]",
          item.path,
        ),
      );
    if (d.candidates.length === 1) {
      select.value = d.candidates[0].path;
      if (!$("game-path").value) {
        $("game-path").value = d.candidates[0].path;
        await setupStatus(d.candidates[0].path);
      }
    }
    $("setup-hint").textContent =
      d.message + " 找到 " + d.candidates.length + " 个安装。";
  } finally {
    checking = false;
  }
}
action("detect", detect);
$("detected-games").onchange = async () => {
  if ($("detected-games").value) {
    $("game-path").value = $("detected-games").value;
    try {
      await setupStatus($("game-path").value);
    } catch (e) {
      say(e.message);
    }
  }
};
$("game-path").onchange = () =>
  setupStatus($("game-path").value).catch((e) => say(e.message));
action("browse", async () => {
  say("文件夹选择窗口已打开；如果没看到，请检查任务栏。");
  let d = await api("/api/browse_folder", {});
  if (d.path) {
    $("game-path").value = d.path;
    await setupStatus(d.path);
    say("已选择目录，点击“使用此目录”保存。");
  } else say("已取消选择，原设置保持不变。");
});
action("apply-path", async () => {
  if (dirty)
    throw Error("下面还有未保存的参数，请先保存参数，再切换游戏目录。");
  await api("/api/apply_path", { path: $("game-path").value });
  await load();
  say("游戏目录已保存，版本和日志路径会自动更新。");
});
action("install-mod", async () => {
  if ($("game-path").value !== cfg.wows_path)
    throw Error("请先点击“使用此目录”，再安装采集插件。");
  let d = await api("/api/install_mod", {});
  say(d.message + (d.backup ? " 原文件备份：" + d.backup : ""));
  await setupStatus();
});
for (let id of [
  "general",
  "rules",
  "tuning",
  "advanced",
  "connection",
  "segments",
  "raw",
])
  $(id).addEventListener("input", () => {
    dirty = true;
  });
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});

function showPage(page) {
  for (let name of ["battle", "device", "lab", "stream"])
    $(name + "-panel").hidden = page !== name;
  for (let name of ["battle", "device", "lab", "stream"])
    $("nav-" + name).className = name === page ? "" : "secondary";
}
async function devices() {
  let result = await api("/api/device_mode", {});
  showPage("device");
  $("device-note").textContent = result.dry_run
    ? "当前为模拟模式，不加载真实设备连接页面。"
    : result.message;
  let frame = $("device-frame");
  if (!result.dry_run) {
    if (frame.getAttribute("src") !== result.url) frame.src = result.url;
    frame.hidden = false;
  }
  say(result.message);
}
action("hub-link", devices);
action("nav-device", devices);
action("nav-battle", async () => showPage("battle"));
action("nav-lab", async () => showPage("lab"));
function collect() {
  for (let f of fields) f();
  cfg.hub.Segment = JSON.parse($("segments").value);
  return cfg;
}
action("import-profile", async () => {
  let file = $("profile-file").files[0];
  if (!file) throw Error("请选择导出的 JSON 配置文件");
  if (file.size > 1024 * 1024) throw Error("配置文件过大");
  let imported = JSON.parse(await file.text());
  let result = await api("/api/preview", {
    config: imported,
    events: [],
    duration: 1,
  });
  if (!result.samples) throw Error("配置无效");
  cfg = result.config;
  render();
  dirty = true;
  say("配置已载入表单，尚未应用。可先到调参实验室预览。");
});
function svgElement(name, attrs, text) {
  let el = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (let [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text !== undefined) el.textContent = text;
  return el;
}
action("preview", async () => {
  let percent = Number($("preview-damage").value),
    duration = Number($("preview-duration").value),
    scenario = $("scenario").value;
  let events = [{ time: 0, kind: "damage", percent }];
  if (scenario === "repeat")
    events = [0, 0.6, 1.2].map((time) => ({ time, kind: "damage", percent }));
  if (scenario === "fire")
    events = [
      { time: 0, kind: "burning", active: true },
      ...events,
      { time: 3, kind: "burning", active: false },
    ];
  if (scenario === "death") events.push({ time: 1, kind: "death" });
  if (scenario === "custom") events = JSON.parse($("preview-events").value);
  let d = await api("/api/preview", { config: collect(), events, duration });
  let svg = $("preview-chart");
  svg.replaceChildren();
  let max = Math.max(10, d.limit, d.peak),
    x = (t) => 55 + (t / d.duration) * 920,
    y = (v) => 290 - (v / max) * 260;
  for (let i = 0; i <= 4; i++) {
    let v = (max * i) / 4;
    svg.append(
      svgElement("line", {
        x1: 55,
        y1: y(v),
        x2: 975,
        y2: y(v),
        stroke: "#263b53",
      }),
      svgElement(
        "text",
        { x: 8, y: y(v) + 4, fill: "#a9bed4", "font-size": 12 },
        v.toFixed(0),
      ),
    );
  }
  for (let i = 0; i <= 5; i++) {
    let t = (d.duration * i) / 5;
    svg.append(
      svgElement(
        "text",
        { x: x(t) - 6, y: 318, fill: "#a9bed4", "font-size": 12 },
        t.toFixed(1),
      ),
    );
  }
  for (let [key, color] of [
    ["base", "#8d9fb2"],
    ["strength", "#64d8cd"],
  ])
    svg.append(
      svgElement("polyline", {
        points: d.samples
          .map((p) => x(p.time).toFixed(1) + "," + y(p[key]).toFixed(1))
          .join(" "),
        fill: "none",
        stroke: color,
        "stroke-width": 2,
      }),
    );
  $("preview-summary").textContent =
    "模拟峰值 " +
    d.peak +
    " 点 · " +
    d.duration +
    " 秒 · " +
    d.samples.length +
    " 个采样点 · 未保存配置、未发送硬件指令";
  say("预览完成。可返回调参数再比较。");
});
let streamInfo = null,
  nativeLink = null;
function overlayUrl() {
  let query = new URLSearchParams({
    color: $("overlay-color").value,
    layout: $("overlay-layout").value,
  });
  return location.origin + "/overlay?" + query;
}
async function loadStreaming() {
  streamInfo = await api("/api/streaming");
  let select = $("stream-session");
  select.replaceChildren(new Option("选择会话，或在下面粘贴原版链接", ""));
  for (let item of streamInfo.sessions)
    select.add(new Option(item.id + " · " + item.source, item.id));
  if (!$("stream-client").value) {
    let recent = streamInfo.sessions.filter(
      (s) => s.source === "Hub 最近响应中的会话",
    );
    $("stream-client").value =
      streamInfo.selected || (recent.length === 1 ? recent[0].id : "");
  }
  $("overlay-url").value = overlayUrl();
}
action("nav-stream", async () => {
  showPage("stream");
  await loadStreaming();
});
action("refresh-stream", loadStreaming);
$("stream-session").onchange = () => {
  $("stream-client").value = $("stream-session").value;
  nativeLink = null;
  $("native-url").value = "";
};
for (let id of ["stream-client", "stream-theme"])
  $(id).addEventListener("input", () => {
    nativeLink = null;
    $("native-url").value = "";
  });
for (let id of ["overlay-color", "overlay-layout"])
  $(id).onchange = () => {
    $("overlay-url").value = overlayUrl();
  };
async function buildViewer() {
  let data = await api(
    "/api/viewer_url?" +
      new URLSearchParams({
        client_id: $("stream-client").value,
        theme: $("stream-theme").value,
      }),
  );
  nativeLink = data;
  $("native-url").value = data.url;
  $("native-size").textContent =
    "建议浏览器源尺寸：" +
    data.width +
    " × " +
    data.height +
    "。确认这个 ID 与已连接设备一致。";
  return data;
}
action("build-viewer", buildViewer);
async function copyField(id) {
  let field = $(id);
  if (!field.value) throw Error("请先生成显示链接");
  try {
    await navigator.clipboard.writeText(field.value);
  } catch {
    field.select();
    if (!document.execCommand("copy"))
      throw Error("自动复制不可用，请选中链接后按 Ctrl+C");
  }
  say("链接已复制。OBS 中添加“浏览器”来源并粘贴 URL。");
}
action("copy-native", () => copyField("native-url"));
action("copy-overlay", () => copyField("overlay-url"));
function showOverlayPreview(url, width, height) {
  $("stream-preview-box").hidden = false;
  $("stream-preview").width = width;
  $("stream-preview").height = height;
  $("stream-preview").src = url;
}
action("preview-native", async () => {
  if (streamInfo?.dry_run)
    throw Error("模拟模式不连接真实 Hub；可预览右侧的联动状态条。");
  let data = nativeLink || (await buildViewer());
  showOverlayPreview(data.url, data.width, data.height);
});
action("preview-overlay", async () =>
  showOverlayPreview(overlayUrl(), 440, 180),
);
function popup(url, width, height) {
  let win = window.open(
    url,
    "wows-stream-view",
    "popup,width=" + width + ",height=" + height,
  );
  if (!win)
    throw Error("浏览器拦截了小窗，请允许本站弹窗，或直接使用显示链接。");
}
action("popup-native", async () => {
  if (streamInfo?.dry_run) throw Error("模拟模式请使用联动状态条。");
  let data = nativeLink || (await buildViewer());
  popup(data.url, data.width, data.height);
  say("原版显示已在独立窗口打开；查看不会暂停战局。");
});
action("popup-overlay", async () => {
  let url = overlayUrl();
  if ("documentPictureInPicture" in window) {
    try {
      let win = await window.documentPictureInPicture.requestWindow({
        width: 440,
        height: 200,
      });
      win.document.body.style.margin = "0";
      let frame = win.document.createElement("iframe");
      frame.src = url;
      frame.style.cssText = "width:100vw;height:100vh;border:0";
      win.document.body.append(frame);
      say("已打开置顶状态小窗。");
      return;
    } catch {
      // A browser may expose the API but disallow it in an embedded context.
    }
  }
  popup(url, 440, 200);
  say("当前环境无法使用置顶画中画，已打开普通独立小窗。");
});
load()
  .then(() => {
    detect().catch((e) =>
      say("自动检测失败：" + e.message + "；仍可手动选择目录。"),
    );
    refresh().catch((e) => say("波形列表暂不可用：" + e.message));
  })
  .catch((e) => say(e.message));
poll();
