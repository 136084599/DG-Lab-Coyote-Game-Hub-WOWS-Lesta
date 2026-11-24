import argparse
import asyncio
from collections import deque
import logging
import json
import socket
from pathlib import Path
import time
from urllib.parse import urlparse
import webbrowser

from aiohttp import web
from .config import ROOT, HUB_DIR, load, log_path, merge, pulse_ids, read_yaml, save, validate
from .engine import RuleEngine
from .hub import HubClient, OutputWorker
from .monitor import BattleParser, LogTail
from .pulses import append_library, read_document, validate_pulses
from .discovery import browse_folder, discover, inspect_game
from .setup import install_recorder
from .preview import simulate
from .streaming import THEMES, browser_url, saved_sessions, viewer_link

LOG = logging.getLogger(__name__)


class LogBuffer(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = deque(maxlen=200)
        self.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))

    def emit(self, record):
        self.lines.append(self.format(record))


class Bridge:
    def __init__(self, config_path, dry_run=False):
        self.path = Path(config_path)
        self.cfg = load(self.path)
        self.engine = RuleEngine(self.cfg)
        self.client = HubClient(self.cfg['hub'], dry_run)
        self.output = OutputWorker(self.engine, self.client)
        self.parser = BattleParser(self.engine)
        self.tail = LogTail(log_path(self.cfg))
        self.logs = LogBuffer()
        self.mutation = asyncio.Lock()
        self.running = True
        self.last_line_at = None
        self.read_error = None
        self.discovery_lock = asyncio.Lock()
        self.folder_lock = asyncio.Lock()
        self.discovery_cache = None
        self.discovery_at = 0
        self.overlay_clients = 0

    async def setup_status(self, request):
        selected = request.query.get('path', self.cfg['wows_path'])
        info = await asyncio.to_thread(inspect_game, selected)
        info['custom_log_path'] = self.cfg['log_path']
        info['hub_url'] = self.cfg['hub']['api_url']
        return web.json_response(info)

    async def detect_games(self, request):
        async with self.discovery_lock:
            if self.discovery_cache is None or time.monotonic() - self.discovery_at > 30:
                self.discovery_cache = await asyncio.to_thread(discover, self.cfg['wows_path'])
                self.discovery_at = time.monotonic()
            return web.json_response({'candidates': self.discovery_cache,
                'message': '已检查保存目录、Windows 安装信息、Steam 游戏库和本地常见位置。其他位置可手动选择。'})

    async def browse(self, request):
        if self.folder_lock.locked():
            raise ValueError('文件夹选择窗口已经打开，请先完成或取消选择')
        async with self.folder_lock:
            path = await asyncio.to_thread(browse_folder, self.cfg['wows_path'])
        return web.json_response({'path': path})

    async def apply_path(self, request):
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError('目录参数必须是对象')
        info = await asyncio.to_thread(inspect_game, data.get('path', ''))
        if not info['valid']:
            raise ValueError(info['message'])
        await self.update_config({'wows_path': info['path'], 'log_path': ''})
        self.discovery_cache = None
        return web.json_response({'status': 'ok', 'game': info})

    async def install_mod(self, request):
        info = await asyncio.to_thread(inspect_game, self.cfg['wows_path'])
        if not info['valid']:
            raise ValueError(info['message'])
        if self.client.dry_run:
            return web.json_response({'message': '模拟模式：目录检查通过，未修改游戏文件。正式运行后可安装。'})
        async with self.mutation:
            try:
                await self.output.stop_output()
            except RuntimeError:
                pass  # Local pause is latched even if Hub is currently offline.
            result = await asyncio.to_thread(install_recorder, info['path'], self.cfg['recorder']['sample_sec'])
            self.discovery_cache = None
            LOG.info('采集插件：%s', result['message'])
        return web.json_response(result)

    async def monitor(self):
        next_discovery = 0
        while self.running:
            path_changed = False
            try:
                async with self.mutation:
                    if time.monotonic() >= next_discovery:
                        path = await asyncio.to_thread(log_path, self.cfg)
                        if path != self.tail.path:
                            path_changed = True
                            self.tail = LogTail(path)
                            self.parser.reset()
                            self.engine.reset(time.monotonic())
                            LOG.info('监控路径更新：%s', path)
                        next_discovery = time.monotonic() + 5
                    reset, baseline, lines = await asyncio.to_thread(self.tail.read)
                    now = time.monotonic()
                    if reset:
                        self.parser.reset()
                        self.engine.reset(now)
                        LOG.info('日志重置，已清空上一局状态')
                    for line in lines:
                        if line:
                            self.parser.feed(line, now, baseline)
                    if lines:
                        self.last_line_at = now
                    self.read_error = None
                    if lines or reset or path_changed:
                        self.output.wake.set()
            except OSError as e:
                if self.read_error != str(e):
                    LOG.error('读取日志失败：%s', e)
                self.read_error = str(e)
                self.engine.stop(time.monotonic())
                self.output.wake.set()
            await asyncio.sleep(self.cfg['poll_sec'])

    async def index(self, request):
        return web.FileResponse(ROOT / 'web' / 'index.html')

    async def asset(self, request):
        name = request.match_info['name']
        if name in ('pulse-file-import.js', 'dg-pulse-helper-CU48u3U2.js'):
            return web.FileResponse(HUB_DIR / 'public' / 'assets' / name, headers={'Content-Type': 'text/javascript'})
        if name not in ('app.js', 'style.css'):
            raise web.HTTPNotFound()
        return web.FileResponse(ROOT / 'web' / name)

    async def pulse_worker(self, request):
        return web.FileResponse(HUB_DIR / 'public/pulse-import-worker.js', headers={'Content-Type': 'text/javascript'})

    async def barcode_reader(self, request):
        return web.FileResponse(HUB_DIR / 'public/lib/zxing_full.wasm', headers={'Content-Type': 'application/wasm'})

    async def overlay(self, request):
        return web.FileResponse(ROOT / 'web' / 'overlay.html')

    def overlay_state(self):
        value, _ = self.engine.desired(time.monotonic())
        if self.output.suspended:
            mode = '设备设置中'
        elif self.engine.paused:
            mode = '战局已暂停'
        elif not self.tail.exists:
            mode = '等待战局日志'
        else:
            mode = '战局监听中'
        return {'mode': mode, 'dry_run': self.client.dry_run,
                'connected': self.client.connected or self.client.dry_run,
                'manual': self.output.suspended, 'desired': value,
                'sent': self.output.last_strength, 'limit': self.cfg['shock']['maxStrength']}

    async def overlay_events(self, request):
        if self.overlay_clients >= 16:
            raise web.HTTPServiceUnavailable(text='显示窗口过多，请关闭重复窗口')
        response = web.StreamResponse(headers={'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
        await response.prepare(request)
        self.overlay_clients += 1
        last = None
        heartbeat = time.monotonic()
        try:
            while self.running:
                data = json.dumps(self.overlay_state(), ensure_ascii=False)
                if data != last:
                    await response.write(('data: ' + data + '\n\n').encode('utf8'))
                    last = data
                elif time.monotonic() - heartbeat > 10:
                    await response.write(b': heartbeat\n\n')
                    heartbeat = time.monotonic()
                await asyncio.sleep(.2)
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self.overlay_clients -= 1
        return response

    async def streaming(self, request):
        candidates = [{'id': value, 'source': 'Hub 最近响应中的会话'} for value in self.client.target_ids]
        if not self.cfg['hub']['toAllDevices']:
            candidates.insert(0, {'id': self.cfg['hub']['client_id'], 'source': '当前指定目标'})
        parsed = urlparse(self.cfg['hub']['api_url'])
        if parsed.hostname in ('127.0.0.1', 'localhost', '::1'):
            try:
                hub_cfg = await asyncio.to_thread(read_yaml, HUB_DIR / 'config.yaml')
            except FileNotFoundError:
                hub_cfg = None
            if hub_cfg is not None and (parsed.port or 80) == hub_cfg.get('port', 8920):
                for value in await asyncio.to_thread(saved_sessions, HUB_DIR):
                    if value not in {entry['id'] for entry in candidates}:
                        candidates.append({'id': value, 'source': '历史保存的会话，需核对是否正在使用'})
        return web.json_response({'themes': THEMES, 'sessions': candidates,
            'selected': self.cfg['hub']['client_id'] if not self.cfg['hub']['toAllDevices'] else '',
            'hub_url': browser_url(self.cfg['hub']['api_url']), 'dry_run': self.client.dry_run})

    async def viewer_url(self, request):
        return web.json_response(viewer_link(self.cfg['hub']['api_url'], request.query.get('client_id', ''), request.query.get('theme', 'circle')))

    async def get_config(self, request):
        return web.json_response({'config': self.cfg})

    async def preview(self, request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('预览请求必须是对象')
        if not isinstance(body.get('config', {}), dict):
            raise ValueError('预览配置必须是对象')
        result = simulate(merge(self.cfg, body.get('config', {})), body.get('events', []), body.get('duration', 10))
        return web.json_response(result)

    async def export_config(self, request):
        return web.json_response(self.cfg, headers={'Content-Disposition': 'attachment; filename="wows-profile.json"'})

    async def get_logs(self, request):
        return web.json_response(list(self.logs.lines))

    async def status(self, request):
        now = time.monotonic()
        value, pulse = self.engine.desired(now)
        snapshot = self.parser.previous
        return web.json_response({'dry_run': self.client.dry_run, 'paused': self.engine.paused,
            'device_mode': self.output.suspended,
            'hub_reachable': self.client.connected, 'hub_error': self.client.last_error,
            'request_ms': self.client.last_latency_ms, 'log_path': str(self.tail.path),
            'log_exists': self.tail.exists, 'read_error': self.read_error,
            'last_line_age_sec': round(now - self.last_line_at, 1) if self.last_line_at else None,
            'desired_strength': value, 'sent_strength': self.output.last_strength,
            'pulse': pulse, 'base': self.engine.base, 'lines': self.parser.lines,
            'health': snapshot.health if snapshot else None,
            'max_health': snapshot.maximum if snapshot else self.parser.maximum,
            'kills': snapshot.kills if snapshot else None,
            'parse_errors': self.parser.errors, 'dead': self.engine.dead})

    async def save_config(self, request):
        data = await request.json()
        await self.update_config(data)
        return web.json_response({'status': 'ok', 'paused': self.engine.paused})

    async def update_config(self, data):
        if not isinstance(data, dict):
            raise ValueError('配置必须是对象')
        async with self.mutation:
            cfg = validate(merge(self.cfg, data))
            changed_target = any(cfg['hub'][k] != self.cfg['hub'][k] for k in ('api_url', 'client_id', 'toAllDevices'))
            added_pulses = pulse_ids(cfg) if changed_target else pulse_ids(cfg) - pulse_ids(self.cfg)
            if added_pulses and not self.client.dry_run:
                check_client = HubClient(cfg['hub']) if changed_target else self.client
                try:
                    available = {p['id'] for p in await check_client.pulses()}
                finally:
                    if changed_target:
                        await check_client.close()
                if added_pulses - available:
                    raise ValueError('Hub 中不存在这些波形 ID：' + ', '.join(sorted(added_pulses - available)))
            if cfg['web_port'] != self.cfg['web_port']:
                raise ValueError('web_port 请在退出程序后编辑 YAML，再重启')
            new_path = await asyncio.to_thread(log_path, cfg)
            async with self.output.lock:
                if changed_target:
                    self.engine.stop(time.monotonic())
                    try:
                        await self.client.strength(0)
                    except RuntimeError as exc:
                        LOG.warning('旧目标归零未获确认：%s', exc)
                    await self.client.close()
                    self.client.target_ids = []
                    self.output.last_strength = self.output.last_pulse = None
                await asyncio.to_thread(save, self.path, cfg)
                self.cfg = cfg
                self.client.cfg = cfg['hub']
                self.engine.configure(cfg, time.monotonic())
                if new_path != self.tail.path:
                    self.tail = LogTail(new_path)
                    self.parser.reset()
                    self.engine.reset(time.monotonic())
                value, _ = self.engine.desired(time.monotonic())
                if not self.output.suspended or changed_target:
                    try:
                        await self.client.strength(value)
                        self.output.last_strength = value
                    except RuntimeError:
                        self.engine.stop(time.monotonic())
                        self.output.last_strength = None
            self.output.wake.set()
        LOG.info('配置已校验、原子保存并应用')

    async def stop(self, request):
        await self.output.stop_output()
        return web.json_response({'status': 'ok'})

    async def resume(self, request):
        async with self.mutation:
            self.engine.reset(time.monotonic())
            self.engine.paused = False
            self.output.suspended = False
            self.parser.reset()
            self.tail = LogTail(self.tail.path)
            self.output.wake.set()
        return web.json_response({'status': 'ok'})

    async def device_mode(self, request):
        try:
            await self.output.stop_output()
        except RuntimeError:
            pass
        self.output.suspended = True
        return web.json_response({'dry_run': self.client.dry_run, 'url': browser_url(self.cfg['hub']['api_url']),
                                  'message': '已暂停战局控制；设备设置由内嵌 Hub 管理。完成后点击恢复监听。'})

    async def pulses(self, request):
        return web.json_response({'pulse_list': await self.client.pulses()})

    async def import_pulses(self, request):
        raw = await request.read()
        incoming = await asyncio.to_thread(lambda: validate_pulses(read_document(raw, '导入文件')))
        if self.client.dry_run:
            return web.json_response({'status': 'ok', 'dry_run': True, 'message': f'模拟模式：{len(incoming)} 个波形校验通过，未写入 Hub'})
        async with self.mutation:
            url = urlparse(self.cfg['hub']['api_url'])
            hub_config = await asyncio.to_thread(read_yaml, HUB_DIR / 'config.yaml')
            if url.hostname not in ('127.0.0.1', 'localhost', '::1') or (url.port or 80) != hub_config.get('port', 8920):
                raise ValueError('网页导入只支持项目附带的本机 Hub；远端请使用对应 Hub 导入界面')
            library = HUB_DIR / 'data' / 'pulse.json5'
            added = await asyncio.to_thread(append_library, library, incoming)
        skipped = len(incoming) - len(added)
        message = f'已写入 {len(added)} 个波形并备份原库' if added else '波形已存在，原库未改动'
        return web.json_response({'status': 'ok', 'ids': [item['id'] for item in incoming],
                                  'added': len(added), 'skipped': skipped, 'message': f'{message}；跳过 {skipped} 个相同项。'})

    async def lifecycle(self, app):
        logging.getLogger().addHandler(self.logs)
        tasks = [asyncio.create_task(self.monitor()), asyncio.create_task(self.output.run())]
        try:
            yield
        finally:
            self.running = self.output.running = False
            self.engine.stop(time.monotonic())
            tasks[0].cancel()
            self.output.wake.set()
            # Let the bounded in-flight output finish before final zero.
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await self.output.stop_output()
            except RuntimeError as e:
                LOG.error('退出归零请求未确认：%s', e)
            await self.client.close()
            logging.getLogger().removeHandler(self.logs)

    async def on_shutdown(self, app):
        # End long-lived read-only streams before aiohttp waits for requests.
        self.running = False
        self.engine.stop(time.monotonic())
        self.output.wake.set()

    def app(self):
        @web.middleware
        async def errors(request, handler):
            origin = request.headers.get('Origin')
            if request.method == 'POST' and origin and origin != f'{request.scheme}://{request.host}':
                return web.json_response({'error': '不允许跨站修改'}, status=403)
            if request.method == 'POST' and request.content_type != 'application/json':
                return web.json_response({'error': '需要 application/json'}, status=415)
            try:
                return await handler(request)
            except web.HTTPRequestEntityTooLarge:
                return web.json_response({'error': '文件或请求超过 2 MiB，请拆分后再导入'}, status=413)
            except (ValueError, KeyError, TypeError) as e:
                return web.json_response({'error': str(e)}, status=400)
            except (RuntimeError, OSError) as e:
                return web.json_response({'error': str(e)}, status=503)
        app = web.Application(middlewares=[errors], client_max_size=2 * 1024 * 1024)
        for path, handler in [('/', self.index), ('/api/get_config', self.get_config),
                ('/assets/{name}', self.asset),
                ('/lib/zxing_full.wasm', self.barcode_reader),
                ('/pulse-import-worker.js', self.pulse_worker),
                ('/api/get_logs', self.get_logs), ('/api/status', self.status), ('/api/pulses', self.pulses),
                ('/api/setup', self.setup_status), ('/api/detect_games', self.detect_games),
                ('/api/config/export', self.export_config), ('/api/streaming', self.streaming),
                ('/api/viewer_url', self.viewer_url), ('/overlay', self.overlay),
                ('/api/overlay/events', self.overlay_events)]:
            app.router.add_get(path, handler)
        for path, handler in [('/api/save_config', self.save_config), ('/api/stop', self.stop),
                ('/api/resume', self.resume), ('/api/pulses/import', self.import_pulses),
                ('/api/browse_folder', self.browse), ('/api/apply_path', self.apply_path),
                ('/api/install_mod', self.install_mod), ('/api/preview', self.preview),
                ('/api/device_mode', self.device_mode)]:
            app.router.add_post(path, handler)
        app.cleanup_ctx.append(self.lifecycle)
        app.on_shutdown.append(self.on_shutdown)
        return app


def main():
    parser = argparse.ArgumentParser(description='WoWs → Coyote Game Hub')
    parser.add_argument('--config', type=Path, default=ROOT / 'config.yaml')
    parser.add_argument('--dry-run', action='store_true', help='仅模拟输出，不连接设备')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check-config', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    try:
        bridge = Bridge(args.config, args.dry_run)
    except (ValueError, OSError) as e:
        parser.exit(2, f'配置错误：{e}\n')
    if args.check_config:
        print('配置校验通过；日志路径：', bridge.tail.path)
        return
    url = f"http://127.0.0.1:{bridge.cfg['web_port']}"
    async def ready(app):
        LOG.info('控制台 %s；模式：%s', url, '模拟' if args.dry_run else 'Hub 联动')
        if bridge.cfg['open_browser'] and not args.no_browser:
            asyncio.get_running_loop().call_later(0.8, lambda: asyncio.create_task(asyncio.to_thread(webbrowser.open, url)))
    app = bridge.app()
    app.on_startup.append(ready)
    # Bind before starting cleanup contexts (which start the output worker).
    # A duplicate launch must not send commands before discovering port conflict.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        listener.bind(('127.0.0.1', bridge.cfg['web_port']))
        listener.listen(128)
    except OSError:
        listener.close()
        parser.exit(2, f'控制台端口 {bridge.cfg["web_port"]} 已被占用。请检查是否已经启动，或退出后修改 web_port。\n')
    try:
        web.run_app(app, sock=listener, print=None)
    finally:
        listener.close()
