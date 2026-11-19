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
    await python.runPythonAsync(`
_paperstride_stdin = inputs.get("stdin", []) if isinstance(inputs, dict) else []
if isinstance(_paperstride_stdin, str):
    _paperstride_stdin = _paperstride_stdin.splitlines()
if not isinstance(_paperstride_stdin, list):
    _paperstride_stdin = []
_paperstride_input_iter = iter(_paperstride_stdin)
def input(prompt=""):
    if prompt:
        print(prompt, end="")
    try:
        return str(next(_paperstride_input_iter))
    except StopIteration:
        raise EOFError('请在输入值 JSON 的 stdin 数组中提供每次 input() 的内容')
`, {globals: namespace});
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
