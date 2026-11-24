import assert from 'node:assert/strict';
import { test } from 'node:test';

const replies = [];
globalThis.self = { postMessage: value => replies.push(value) };
import { existsSync } from 'node:fs';
const companion = new URL('../hub-overlay/public/assets/dg-pulse-helper-CU48u3U2.js', import.meta.url);
if (!existsSync(companion)) {
  test('Hub waveform import tests', {skip: 'Copy the matching Hub decoder into the test fixture first'}, () => {});
} else {
await import('../hub-overlay/public/pulse-import-worker.js');

async function read(text) {
  await self.onmessage({ data: new Blob([text]) });
  return replies.pop();
}

test('单点渐变使用起始频率，不生成频率为零的帧', async () => {
  for (const mode of [0, 1, 2, 3, 4]) {
    assert.deepEqual(await read(`Dungeonlab+pulse:0,2,0,${mode},1/0`), { frames: ['0A0A0A0A00000000'] });
  }
});

test('忽略关闭的段，保留文件里各个已开启段的顺序', async () => {
  assert.deepEqual(await read('\ufeffDungeonlab+pulse:0,0,0,1,0/1+section+0,0,0,1,1/0+section+1,1,0,1,1/0-0'),
    { frames: ['0A0A0A0A00000000', '0B0B0B0B00000000'] });
});

test('损坏的波形、空段和无启用段都不产生可导入结果', async () => {
  for (const text of ['not pulse data', 'Dungeonlab+pulse:0,0,0,1,1/', 'Dungeonlab+pulse:0,0,0,1,0/0',
    'Dungeonlab+pulse:0,0,0,1,1/101', 'Dungeonlab+pulse:0,0,900,1,1/0', 'Dungeonlab+pulse:0,0,0,1,1/x']) {
    assert.match((await read(text)).error, /文件|波形|格式/);
  }
});

}
