export function importPulseFrames(file) {
  if (!file.size || file.size > 2 * 1024 * 1024) throw Error('请选择非空、至多 2 MiB 的波形文件');
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('../pulse-import-worker.js', import.meta.url), { type: 'module' });
    const timer = setTimeout(() => finish(reject, Error('识别超时，请换用原始二维码图片或波形文件')), 10000);
    function finish(done, value) {
      clearTimeout(timer);
      worker.terminate();
      done(value);
    }
    worker.onmessage = ({ data }) => data.error ? finish(reject, Error(data.error)) : finish(resolve, data.frames);
    worker.onerror = () => finish(reject, Error('本地波形解析器未能运行，请刷新页面后重试'));
    worker.postMessage(file);
  });
}
