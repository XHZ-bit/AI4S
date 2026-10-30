// Trusted runner bootstrap, isolated from the application in an opaque iframe.
// RUNTIME_BASE is supplied by the parent runner, never by exercise source.
let python;
let output = '';
let lastOutput = 0;
function record(text) {
  output = (output + String(text) + '\n').slice(-18000);
  if (Date.now() - lastOutput > 100) {
    lastOutput = Date.now();
    self.postMessage({type: 'output', output});
  }
}
self.onmessage = async ({data}) => {
  if (data.type !== 'execute' || !python) return;
  output = '';
  let namespace;
  try {
    namespace = python.toPy({inputs: data.inputs});
    await python.runPythonAsync(data.code, {globals: namespace});
    if (data.tests) await python.runPythonAsync(data.tests, {globals: namespace});
    self.postMessage({type: 'result', status: 'success', passed: data.tests ? true : null,
      output: output || '运行完成，没有打印输出。'});
  } catch (error) {
    self.postMessage({type: 'result', status: 'error', passed: data.tests ? false : null,
      output: (output + String(error)).slice(-20000)});
  } finally {
    namespace?.destroy();
  }
};
async function initialize() {
  const {loadPyodide} = await import(RUNTIME_BASE + 'pyodide.mjs');
  python = await loadPyodide({indexURL: RUNTIME_BASE, stdout: record, stderr: record});
  self.postMessage({type: 'ready'});
}
initialize().catch(error => self.postMessage({type: 'fatal', output: '本地 Python 环境加载失败：' + String(error)}));
