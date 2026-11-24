import { g as encodeFrames, l as readQR } from './assets/dg-pulse-helper-CU48u3U2.js';

function sequence(start, end, step) {
  return Array.from({ length: Math.ceil((end - start) / step) }, (_, index) => start + index * step);
}
const frequencies = [...sequence(10, 50, 1), ...sequence(50, 80, 2), ...sequence(80, 100, 5),
  ...sequence(100, 200, 10), 200, 233, 266, 300, 333, 366, ...sequence(400, 600, 50), ...sequence(600, 1001, 100)];
const seconds = [...sequence(1, 50, 1), ...sequence(50, 80, 2), ...sequence(80, 100, 5),
  ...sequence(100, 200, 10), 200, 233, 266, 300, 333, 366, ...sequence(400, 1000, 50),
  ...sequence(1000, 2000, 200), 2000, 2500, 3000].map(value => value / 10);
const modes = [false, false, 'inSection', 'inPulse', 'perPulse'];

function readSections(text) {
  const prefix = 'Dungeonlab+pulse:';
  if (!text.startsWith(prefix)) throw Error('文件不是 Dungeonlab+pulse: 格式；JSON 文件请从控制台的波形库导入');
  const sections = [];
  for (const [position, chunk] of text.slice(prefix.length).split('+section+').entries()) {
    if (!chunk.trim()) continue;
    const [header, points, ...extra] = chunk.trim().split('/');
    const values = header.split(',');
    const invalid = () => Error(`第 ${position + 1} 节格式不正确，请重新导出原文件`);
    if (values.length < 5 || !values.slice(0, 5).every(value => /^\d+$/.test(value)) || points === undefined || extra.length) throw invalid();
    const [start, end, duration, mode, enabled] = values.map(Number);
    if (enabled === 0) continue;
    if (enabled !== 1 || frequencies[start] === undefined || frequencies[end] === undefined || seconds[duration] === undefined || modes[mode] == null) throw invalid();
    const pulse = points.replace(/,$/, '').split(',').map(point => {
      const match = /^(\d+(?:\.\d+)?)(?:-\d+(?:\.\d+)?)?$/.exec(point.trim());
      if (!match || Number(match[1]) > 100) throw invalid();
      return Math.round(Number(match[1]));
    });
    sections.push({ pulse, sectionTime: seconds[duration], freqMode: modes[mode], freq: modes[mode] ? [frequencies[start], frequencies[end]] : frequencies[start] });
  }
  return { sections, sleepTime: 0, speedFactor: 1 };
}

function framesFor(info) {
  if (!info.sections.length) throw Error('文件没有启用的波形段');
  let steps = Math.ceil((info.sleepTime || 0) * 10);
  for (const section of info.sections) {
    const length = section.pulse.length;
    const repeats = Math.max(1, Math.ceil(section.sectionTime * 1000 / (length * 100)));
    const freq = [].concat(section.freq);
    if (!length || !section.pulse.every(value => Number.isInteger(value) && value >= 0 && value <= 100) ||
        !Number.isFinite(section.sectionTime) || section.sectionTime <= 0 ||
        !freq.every(value => Number.isFinite(value) && value >= 10 && value <= 1000)) throw Error('波形段的时长、频率或幅度无效');
    steps += length * repeats;
    if (steps > 10000) throw Error('波形过长，请拆分后再导入');
    if ((section.freqMode === 'perPulse' && repeats === 1) || (section.freqMode === 'inPulse' && length === 1) ||
        (section.freqMode === 'inSection' && length * repeats === 1)) {
      section.freq = freq[0];
      section.freqMode = false;
    }
  }
  return encodeFrames(info);
}

self.onmessage = async ({ data: file }) => {
  try {
    const signature = new Uint8Array(await file.slice(0, 12).arrayBuffer());
    const image = (signature[0] === 137 && signature[1] === 80) || (signature[0] === 255 && signature[1] === 216) ||
      (String.fromCharCode(...signature.slice(0, 4)) === 'RIFF' && String.fromCharCode(...signature.slice(8)) === 'WEBP');
    const info = image ? await readQR(file) : readSections((await file.text()).trim());
    self.postMessage({ frames: framesFor(info) });
  } catch (error) {
    const reason = String(error.message || error);
    self.postMessage({ error: /[\u3400-\u9fff]/.test(reason) ? reason : '未能读取郊狼波形二维码，请选择清晰的原始 PNG / JPG 图片，或导入 .pulse 文件' });
  }
};
