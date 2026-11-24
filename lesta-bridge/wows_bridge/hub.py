"""Bounded HTTP transport; all output is absolute and uses one writer."""
import asyncio
import logging
import time

import aiohttp

LOG = logging.getLogger(__name__)


class HubClient:
    def __init__(self, cfg, dry_run=False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.session = None
        self.last_error = None
        self.last_latency_ms = None
        self.connected = False
        self.outputs = []
        self._dry_strength = None
        self.target_ids = []

    @property
    def target(self):
        return 'all' if self.cfg['toAllDevices'] else self.cfg['client_id']

    async def request(self, method, path, payload=None):
        if self.session is None:
            self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=4))
        started = time.monotonic()
        try:
            async with self.session.request(method, self.cfg['api_url'].rstrip('/') + '/' + path,
                                            json=payload, timeout=aiohttp.ClientTimeout(total=self.cfg['timeout'])) as response:
                response.raise_for_status()
                data = await response.json()
                if not isinstance(data, dict) or data.get('status') != 1:
                    raise RuntimeError(f"Hub 拒绝请求: {data}")
                self.last_latency_ms = round((time.monotonic() - started) * 1000, 2)
                self.connected = True
                self.last_error = None
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RuntimeError) as e:
            self.connected = False
            self.last_error = str(e) or type(e).__name__
            raise RuntimeError(self.last_error) from e

    async def strength(self, value):
        if self.dry_run:
            self.outputs.append(('strength', value))
            self.outputs = self.outputs[-100:]
            if value != self._dry_strength:
                LOG.info('[模拟输出] 强度 %d', value)
                self._dry_strength = value
            return
        data = await self.request('POST', f'api/v2/game/{self.target}/strength',
                           {'strength': {'set': value}, 'randomStrength': {'set': 0}})
        self.target_ids = [value for value in data.get('successClientIds', []) if isinstance(value, str)]

    async def pulse(self, value):
        if not value:
            return
        if self.dry_run:
            self.outputs.append(('pulse', value))
            self.outputs = self.outputs[-100:]
            LOG.info('[模拟输出] 波形 %s', value)
            return
        await self.request('POST', f'api/v2/game/{self.target}/pulse', {'pulseId': value})

    async def pulses(self):
        if self.dry_run:
            return []
        data = await self.request('GET', f'api/v2/game/{self.target}/pulse_list')
        unique = {}
        for item in data.get('pulseList', []):
            if isinstance(item, dict) and isinstance(item.get('id'), str):
                unique[item['id']] = {'id': item['id'], 'name': str(item.get('name', item['id']))}
        return list(unique.values())

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None


class OutputWorker:
    def __init__(self, engine, client):
        self.engine, self.client = engine, client
        self.wake = asyncio.Event()
        self.lock = asyncio.Lock()
        self.last_strength = None
        self.last_pulse = None
        self.last_sent = 0
        self.running = True
        self.suspended = False
        self.failures = 0

    async def run(self):
        while self.running:
            self.wake.clear()
            if self.suspended:
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=0.2)
                except asyncio.TimeoutError:
                    pass
                continue
            try:
                async with self.lock:
                    now = time.monotonic()
                    value, pulse = self.engine.desired(now)
                    # Send decreases before optional waveform I/O.
                    if value != self.last_strength or now - self.last_sent >= self.engine.cfg['output']['heartbeat_sec']:
                        await self.client.strength(value)
                        self.last_strength = value
                        self.last_sent = now
                    _, pulse = self.engine.desired(time.monotonic())
                    if pulse and pulse != self.last_pulse:
                        await self.client.pulse(pulse)
                        self.last_pulse = pulse
                self.failures = 0
            except RuntimeError as e:
                self.failures += 1
                self.engine.stop(time.monotonic())
                self.last_strength = None
                self.last_pulse = None
                if self.failures == 1 or self.failures % 30 == 0:
                    LOG.error('通信失败，已暂停事件输出；重新连接后请点恢复：%s', e)
                # Retry only the latest zero state, never queue stale hits.
                await asyncio.sleep(self.engine.cfg['output']['retry_sec'])
                continue
            try:
                interval = self.engine.cfg['output']['tick_sec']
                if self.engine.paused or not self.engine.active:
                    interval = self.engine.cfg['output']['heartbeat_sec']
                await asyncio.wait_for(self.wake.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def stop_output(self):
        self.suspended = False
        self.engine.stop(time.monotonic())
        # Wait for the one in-flight request before sending zero.
        async with self.lock:
            await self.client.strength(0)
            self.last_strength = 0
        self.wake.set()
