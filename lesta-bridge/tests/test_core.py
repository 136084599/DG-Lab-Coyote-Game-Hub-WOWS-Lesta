import asyncio
from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import time
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from wows_bridge.config import DEFAULTS, load, merge, save, validate
from wows_bridge.engine import RuleEngine, mapped_strength
from wows_bridge.monitor import BattleParser, LogTail
from wows_bridge.hub import HubClient, OutputWorker
from wows_bridge.app import Bridge
from wows_bridge.pulses import append_library, validate_pulses


def config(**kwargs):
    cfg = deepcopy(DEFAULTS)
    cfg['hub']['randomize_strength_range'] = [0, 0]
    return validate(merge(cfg, kwargs))


def line(hp=1000, kills=0, achievements=0, dead=False, fire=False, flood=False, stamp='2026-10-30 12:00:00'):
    return f'{stamp}(1000),{hp},isDied:{dead},Burning:{fire},Flooding:{flood},Kills:{kills},Achievements:{achievements}'


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.engine = RuleEngine(config(), random.Random(1))

    def test_first_hit_immediate_aggregation_base_once(self):
        e = self.engine
        e.damage(10, 1000, 1)
        self.assertEqual(e.desired(1)[0], 26)
        e.damage(20, 1000, 1.1)
        self.assertAlmostEqual(e.base, .12)
        self.assertEqual(e.hit_total, 30)
        self.assertEqual(e.desired(1.1)[0], 61)
        e.damage(10, 1000, 1.4)
        self.assertAlmostEqual(e.base, .24)

    def test_final_clamp_includes_random_status_base_and_death(self):
        e = self.engine
        e.cfg['hub']['randomize_strength_range'] = [200, 200]
        e.status('burning', True, 0)
        e.damage(900, 1000, 1)
        self.assertEqual(e.desired(1)[0], 100)
        e.death(2)
        self.assertEqual(e.desired(2)[0], 100)
        self.assertEqual(e.desired(12)[0], 0)

    def test_status_clamp_does_not_steal_base_when_removed(self):
        e = self.engine
        e.base = 95
        e.status('burning', True, 1)
        e.status('flooding', True, 1)
        self.assertEqual(e.desired(1)[0], 100)
        e.status('burning', False, 2)
        e.status('flooding', False, 2)
        self.assertEqual(e.desired(2)[0], 95)

    def test_reward_updates_same_base_as_damage(self):
        e = self.engine
        e.base = 5
        e.damage(10, 1000, 0)
        e.reward('kill', 1, 1)
        self.assertAlmostEqual(e.base, 4.12)

    def test_repeated_pulse_renews_lease_and_restores_active_status(self):
        e = self.engine
        e.cfg['shock']['defaultPulseId'] = 'default'
        e.cfg['rules']['kill']['pulseId'] = 'hit'
        e.cfg['rules']['burning']['pulseId'] = 'fire'
        e.status('burning', True, 0)
        e.reward('kill', 1, 1)
        e.reward('kill', 1, 4)
        self.assertEqual(e.desired(6)[1], 'hit')
        self.assertEqual(e.desired(9)[1], 'fire')
        e.status('burning', False, 9)
        self.assertEqual(e.desired(9)[1], 'default')

    def test_death_once_duration_and_restart(self):
        e = self.engine
        e.cfg['rules']['death']['duration'] = 2
        e.death(1)
        e.death(2)
        self.assertEqual(e.death_until, 3)
        self.assertEqual(e.desired(3)[0], 0)
        e.reset(4)
        self.assertEqual(e.desired(4)[0], 0)
        e.damage(10, 1000, 4)
        self.assertGreater(e.desired(4)[0], 0)

    def test_stop_latched_across_battle_reset(self):
        e = self.engine
        e.damage(20, 1000, 1)
        e.stop(1)
        e.reset(2)
        e.damage(20, 1000, 2)
        self.assertEqual(e.desired(2)[0], 0)

    def test_decay_falls_to_updated_floor(self):
        e = self.engine
        e.base = 10
        e.damage(50, 1000, 0)
        e.reward('achievement', 2, 1)
        self.assertEqual(e.desired(10)[0], 7)

    def test_interpolation(self):
        hub = self.engine.cfg['hub']
        self.assertEqual(mapped_strength(2, hub), 25)
        hub['interpolation'] = 'linear'
        self.assertEqual(mapped_strength(2, hub), 42.5)

    def test_parser_baseline_heal_and_repeated_death(self):
        p = BattleParser(self.engine)
        p.feed(line(500, kills=2, achievements=1), 0, baseline=True)
        p.feed(line(600, kills=2, achievements=1), 1)
        self.assertFalse(self.engine.active)
        p.feed(line(590, kills=2, achievements=1), 2)
        self.assertEqual(self.engine.hit_total, 10)
        p.feed(line(0, kills=2, achievements=1, dead=True), 3)
        until = self.engine.death_until
        p.feed(line(0, kills=2, achievements=1, dead=True), 4)
        self.assertEqual(self.engine.death_until, until)

    def test_bad_log_does_not_kill_parser(self):
        p = BattleParser(self.engine)
        p.feed('MaxHealth,nan', 0)
        p.feed('x(1000),1.2.3,isDied:False,Burning:False,Flooding:False,Kills:0,Achievements:0', 0)
        self.assertEqual(p.errors, 2)
        p.feed(line(), 0)
        p.feed(line(990), 1)
        self.assertEqual(self.engine.hit_total, 10)

    def test_broken_snapshot_cannot_trigger_legacy_death(self):
        p = BattleParser(self.engine)
        p.feed('broken,isDied:True,Burning:False,Kills:0', 0)
        self.assertEqual(p.errors, 1)
        self.assertFalse(self.engine.dead)

    def test_explicit_battle_markers_reset_same_ship_and_zero_on_exit(self):
        p = BattleParser(self.engine)
        p.feed(line(), 0)
        p.feed(line(950), 1)
        self.assertGreater(self.engine.desired(1)[0], 0)
        p.feed('BattleEnd', 2)
        self.assertEqual(self.engine.desired(2)[0], 0)
        p.feed('BattleStart,new-id', 3)
        p.feed(line(), 3)
        p.feed(line(990), 4)
        self.assertEqual(self.engine.hit_total, 10)


class TailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'log.txt'

    def test_partial_utf8_and_newline(self):
        self.path.write_bytes(b'')
        tail = LogTail(self.path)
        tail.read()
        data = '伤害\n'.encode()
        self.path.write_bytes(data[:2])
        self.assertEqual(tail.read()[2], [])
        with self.path.open('ab') as f:
            f.write(data[2:])
        self.assertEqual(tail.read()[2], ['伤害'])

    def test_same_size_and_larger_rewrite(self):
        self.path.write_text('one\n')
        tail = LogTail(self.path)
        self.assertTrue(tail.read()[1])
        self.path.write_text('two\n')
        reset, baseline, lines = tail.read()
        self.assertTrue(reset)
        self.assertFalse(baseline)
        self.assertEqual(lines, ['two'])
        self.path.write_text('new\nlonger\n')
        self.assertTrue(tail.read()[0])

    def test_delete_and_recreate_not_old_offset(self):
        self.path.write_text('original\n')
        tail = LogTail(self.path)
        tail.read()
        self.path.unlink()
        self.assertTrue(tail.read()[0])
        self.path.write_text('new\n')
        self.assertEqual(tail.read()[2], ['new'])


class ConfigTests(unittest.TestCase):
    def test_nan_ranges_bad_factor_duplicate_segment(self):
        for patch in [{'window_sec': float('nan')}, {'hub': {'decay': {'factor': 1}}},
                      {'shock': {'maxStrength': 201}}, {'hub': {'Segment': [[1, 10], [1, 20]]}},
                      {'hub': {'randomize_strength_range': [3, -2]}}, {'rules': {'kill': {'pulseId': 'x'}}}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                config(**patch)

    def test_preserve_hidden_settings_and_roundtrip(self):
        cfg = config()
        cfg['custom_extension'] = {'x': 7}
        patched = validate(merge(cfg, {'shock': {'maxStrength': 80}}))
        self.assertEqual(patched['shock']['usingApi'], ['dglab'])
        self.assertEqual(patched['custom_extension']['x'], 7)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'config.yaml'
            save(path, patched)
            self.assertEqual(load(path), patched)

    def test_pulse_import_and_backup_collision_and_encoding(self):
        item = {'id': 'test', 'name': '测试', 'pulseData': ['0A0A0A0A64646464']}
        self.assertEqual(validate_pulses([item])[0]['id'], 'test')
        with self.assertRaises(ValueError):
            validate_pulses([dict(item, pulseData=['FFFFFFFFFFFFFFFF'])])
        with self.assertRaises(ValueError):
            validate_pulses([dict(item, pulseData=['0000000064646464'])])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'pulse.json5'
            path.write_bytes(b'[]')
            self.assertEqual(append_library(path, [item]), ['test'])
            self.assertEqual(len(list(Path(d).glob('*.bak'))), 1)
            self.assertEqual(append_library(path, [item]), [])
            self.assertEqual(append_library(path, [dict(item, name='同一波形的另一个文件名')]), [])
            with self.assertRaisesRegex(ValueError, '整批未写入'):
                append_library(path, [dict(item, id='new'), dict(item, pulseData=['0A0A0A0A00000000'])])
            self.assertEqual(len(list(Path(d).glob('*.bak'))), 1)
            self.assertEqual(json.loads(path.read_text('utf8')), [item])


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.log = self.path / 'damage.txt'
        self.log.write_text(line() + '\n')
        self.received = []
        self.hub_fail = False
        async def strength(request):
            data = await request.json()
            self.received.append(data['strength']['set'])
            if self.hub_fail:
                return web.json_response({'status': 0, 'code': 'ERR::GAME_NOT_FOUND'})
            return web.json_response({'status': 1, 'successClientIds': ['test']})
        async def pulses(request):
            if request.query.get('type') == 'full':
                return web.json_response({'status': 1, 'pulseList': []})
            return web.json_response({'status': 1, 'pulseList': [{'id': 'test', 'name': '<script>x</script>'}]})
        hub = web.Application()
        hub.router.add_post('/api/v2/game/all/strength', strength)
        hub.router.add_get('/api/v2/game/all/pulse_list', pulses)
        self.server = TestServer(hub)
        await self.server.start_server()
        cfg = config(log_path=str(self.log), open_browser=False, poll_sec=.01,
                     hub={'api_url': str(self.server.make_url('/'))})
        self.config_path = self.path / 'config.yaml'
        save(self.config_path, cfg)
        self.bridge = Bridge(self.config_path)
        self.client = TestClient(TestServer(self.bridge.app()))
        await self.client.start_server()
        await asyncio.sleep(.05)

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()
        self.tmp.cleanup()

    async def until(self, condition, timeout=2):
        end = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > end:
                self.fail('timed out')
            await asyncio.sleep(.01)

    async def test_log_to_http_stop_resume_and_shutdown(self):
        with self.log.open('a') as f:
            f.write(line(990) + '\n')
        await self.until(lambda: any(x > 0 for x in self.received))
        response = await self.client.post('/api/stop', json={})
        self.assertEqual(response.status, 200)
        self.assertEqual(self.received[-1], 0)
        with self.log.open('a') as f:
            f.write(line(900) + '\n')
        await asyncio.sleep(.05)
        self.assertEqual(self.received[-1], 0)
        response = await self.client.post('/api/resume', json={})
        self.assertEqual(response.status, 200)
        await asyncio.sleep(.05)
        self.assertEqual(self.bridge.engine.base, 0)
        await self.client.close()
        self.assertEqual(self.received[-1], 0)
        self.assertIsNone(self.bridge.client.session)

    async def test_web_validation_persistence_and_status(self):
        response = await self.client.post('/api/save_config', json={'window_sec': -1})
        self.assertEqual(response.status, 400)
        self.assertEqual(load(self.config_path)['window_sec'], .3)
        response = await self.client.post('/api/save_config', json={'shock': {'maxStrength': 70}})
        self.assertEqual(response.status, 200)
        self.assertEqual(load(self.config_path)['shock']['usingApi'], ['dglab'])
        self.assertEqual(load(self.config_path)['shock']['maxStrength'], 70)
        response = await self.client.get('/api/status')
        status = await response.json()
        self.assertTrue(status['log_exists'])
        self.assertEqual(status['health'], 1000)
        self.assertEqual(status['max_health'], 1000)
        response = await self.client.get('/api/pulses')
        self.assertEqual((await response.json())['pulse_list'][0]['id'], 'test')

    async def test_error_latches_pause_and_does_not_replay(self):
        self.hub_fail = True
        with self.log.open('a') as f:
            f.write(line(950) + '\n')
        await self.until(lambda: self.bridge.engine.paused)
        self.hub_fail = False
        await asyncio.sleep(1.1)
        self.assertEqual(self.received[-1], 0)
        self.assertTrue(self.bridge.engine.paused)

    async def test_dry_run_never_opens_session(self):
        client = HubClient(self.bridge.cfg['hub'], dry_run=True)
        await client.strength(100)
        await client.pulse('test')
        await client.pulses()
        self.assertIsNone(client.session)

    async def test_invalid_waveform_never_persisted(self):
        response = await self.client.post('/api/save_config', json={'shock': {'defaultPulseId': 'missing'}})
        self.assertEqual(response.status, 400)
        self.assertIsNone(load(self.config_path)['shock']['defaultPulseId'])

    async def test_setup_path_selection_and_cancelled_folder_picker(self):
        game = self.path / 'game'
        (game / 'bin/123/bin64').mkdir(parents=True)
        (game / 'Korabli.exe').touch()
        response = await self.client.post('/api/apply_path', json={'path': str(game / 'bin/123/bin64')})
        self.assertEqual(response.status, 200)
        cfg = load(self.config_path)
        self.assertEqual(cfg['wows_path'], str(game))
        self.assertEqual(cfg['log_path'], '')
        self.assertEqual(cfg['rules']['kill']['strengthDelta'], -1)
        response = await self.client.get('/api/setup')
        info = await response.json()
        self.assertTrue(info['valid'])
        self.assertFalse(info['mod_installed'])
        with patch('wows_bridge.app.browse_folder', return_value=''):
            response = await self.client.post('/api/browse_folder', json={})
        self.assertEqual((await response.json())['path'], '')
        self.assertEqual(load(self.config_path), cfg)
        response = await self.client.post('/api/apply_path', json={'path': str(self.path / 'missing')})
        self.assertEqual(response.status, 400)
        self.assertEqual(load(self.config_path), cfg)

    async def test_import_into_empty_library_via_http(self):
        local_hub = self.path / 'hub'
        (local_hub / 'data').mkdir(parents=True)
        save(local_hub / 'config.yaml', {'port': self.server.port})
        library = local_hub / 'data/pulse.json5'
        library.write_text('[]')
        item = {'id': 'import-test', 'name': '测试', 'pulseData': ['0A0A0A0A00000000']}
        with patch('wows_bridge.app.HUB_DIR', local_hub):
            response = await self.client.post('/api/pulses/import', json=[item])
        self.assertEqual(response.status, 200, await response.text())
        self.assertEqual(json.loads(library.read_text('utf8')), [item])
        self.assertEqual(len(list(library.parent.glob('*.bak'))), 1)

    async def test_import_uses_disk_across_back_to_back_requests(self):
        local = self.path / 'hub'
        (local / 'data').mkdir(parents=True)
        save(local / 'config.yaml', {'port': self.server.port})
        library = local / 'data/pulse.json5'
        original = "\ufeff[/*自定义*/{id:'old', name:'原波形', pulseData:['0A0A0A0A00000000'], extra:42,},]".encode('utf8')
        library.write_bytes(original)
        def item(pid):
            return {'id': pid, 'name': pid, 'pulseData': ['0a0a0a0a00000000']}
        with patch('wows_bridge.app.HUB_DIR', local):
            first, second = await asyncio.gather(*[self.client.post('/api/pulses/import', json=item(pid)) for pid in ('first', 'second')])
            for response in (first, second):
                self.assertEqual(response.status, 200, await response.text())
                self.assertEqual((await response.json())['added'], 1)
            repeat = await self.client.post('/api/pulses/import', json={'pulseList': [item('second')]})
            self.assertEqual((await repeat.json())['skipped'], 1)
        entries = json.loads(library.read_text('utf8'))
        self.assertEqual({entry['id'] for entry in entries}, {'old', 'first', 'second'})
        self.assertEqual(entries[0]['extra'], 42)
        backups = [saved.read_bytes() for saved in library.parent.glob('*.bak')]
        self.assertEqual(len(backups), 2)
        self.assertIn(original, backups)

    async def test_import_json5_bom_and_invalid_library(self):
        local = self.path / 'hub'
        (local / 'data').mkdir(parents=True)
        save(local / 'config.yaml', {'port': self.server.port})
        library = local / 'data/pulse.json5'
        library.write_bytes(b'[]')
        payload = "\ufeff{name:'静默',pulseData:['0a0a0a0a00000000'],}".encode('utf8')
        with patch('wows_bridge.app.HUB_DIR', local):
            res = await self.client.post('/api/pulses/import', data=payload, headers={'Content-Type': 'application/json'})
            self.assertEqual(res.status, 200, await res.text())
            self.assertEqual(len((await res.json())['ids'][0]), 8)
            library.write_bytes(b'[broken')
            bad = await self.client.post('/api/pulses/import', data=payload, headers={'Content-Type': 'application/json'})
            self.assertEqual(bad.status, 400)
            self.assertEqual(library.read_bytes(), b'[broken')
            self.assertEqual(len(list(library.parent.glob('*.bak'))), 1)

    async def test_malformed_json_and_cross_site_request(self):
        response = await self.client.post('/api/save_config', data='{', headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status, 400)
        response = await self.client.post('/api/stop', json={}, headers={'Origin': 'https://example.com'})
        self.assertEqual(response.status, 403)

    async def test_preview_and_export_do_not_change_live_output(self):
        before = load(self.config_path)
        response = await self.client.post('/api/preview', json={'config': {'hub': {'decay': {'mode': 'linear'}}},
            'events': [{'time': 0, 'kind': 'damage', 'percent': 50}], 'duration': 2})
        self.assertEqual(response.status, 200)
        self.assertGreater((await response.json())['peak'], 0)
        self.assertEqual(load(self.config_path), before)
        self.assertEqual(self.bridge.engine.desired(time.monotonic())[0], 0)
        self.assertTrue(all(v == 0 for v in self.received))
        response = await self.client.get('/api/config/export')
        self.assertEqual(await response.json(), before)

    async def test_device_mode_yields_output_and_resume_reclaims_it(self):
        response = await self.client.post('/api/device_mode', json={})
        self.assertEqual(response.status, 200)
        self.assertTrue(self.bridge.output.suspended)
        self.assertTrue(self.bridge.engine.paused)
        count = len(self.received)
        self.bridge.output.last_sent = 0
        await asyncio.sleep(.06)
        self.assertEqual(len(self.received), count)
        await self.client.post('/api/resume', json={})
        self.assertFalse(self.bridge.output.suspended)
        self.assertFalse(self.bridge.engine.paused)

    async def test_manual_device_settings_not_overwritten_by_rule_save(self):
        await self.client.post('/api/device_mode', json={})
        count = len(self.received)
        response = await self.client.post('/api/save_config', json={'window_sec': .5})
        self.assertEqual(response.status, 200)
        self.assertEqual(len(self.received), count)

    async def test_streaming_endpoints_are_read_only_and_hide_private_paths(self):
        paused = self.bridge.engine.paused
        response = await self.client.get('/api/streaming')
        self.assertEqual(response.status, 200)
        response = await self.client.get('/api/viewer_url', params={'client_id': 'test-session', 'theme': 'bar'})
        data = await response.json()
        self.assertIn('viewer.html?clientId=test-session#/bar1', data['url'])
        self.assertEqual(self.bridge.engine.paused, paused)
        self.assertFalse(self.bridge.output.suspended)
        stream = await self.client.get('/api/overlay/events')
        first = await asyncio.wait_for(stream.content.readline(), 1)
        self.assertTrue(first.startswith(b'data: '))
        self.assertNotIn(b'log_path', first)
        self.assertNotIn(b'api_url', first)
        stream.close()

    async def test_split_frontend_and_overlay_are_served(self):
        for path, expected in [('/', '直播'), ('/assets/app.js', 'loadStreaming'),
                               ('/assets/style.css', 'background'), ('/overlay', 'EventSource')]:
            response = await self.client.get(path)
            self.assertEqual(response.status, 200)
            self.assertIn(expected, await response.text())
        response = await self.client.get('/assets/config.yaml')
        self.assertEqual(response.status, 404)

    async def test_open_overlay_stream_does_not_delay_shutdown(self):
        stream = await self.client.get('/api/overlay/events')
        await stream.content.readline()
        await asyncio.wait_for(self.client.close(), 2)
        self.assertEqual(self.bridge.overlay_clients, 0)

    async def test_target_change_pauses_and_zeros_old_target(self):
        # Change an explicitly stored target while keeping the mock route all.
        response = await self.client.post('/api/save_config', json={'hub': {'client_id': 'test-target'}})
        self.assertEqual(response.status, 200)
        self.assertTrue(self.bridge.engine.paused)
        self.assertTrue(all(value == 0 for value in self.received))
        self.assertEqual(load(self.config_path)['hub']['client_id'], 'test-target')

    async def test_shutdown_finishes_inflight_request_then_zero(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        actual = self.bridge.client.strength
        async def slow(value):
            if value > 0:
                entered.set()
                await finish.wait()
            await actual(value)
        self.bridge.client.strength = slow
        with self.log.open('a') as f:
            f.write(line(950) + '\n')
        await asyncio.wait_for(entered.wait(), 1)
        closing = asyncio.create_task(self.client.close())
        await asyncio.sleep(.02)
        finish.set()
        await asyncio.wait_for(closing, 2)
        self.assertEqual(self.received[-1], 0)


if __name__ == '__main__':
    unittest.main()
