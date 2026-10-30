// This worker is served unchanged in dev and production. No server code execution.
let python;
let output = "";
self.onmessage = async ({data: {code, tests}}) => {
  output = "";
  let namespace;
  try {
    namespace = python.toPy({});
    await python.runPythonAsync(code, {globals: namespace});
    if (tests) await python.runPythonAsync(tests, {globals: namespace});
    self.postMessage({type: "result", passed: Boolean(tests), output: output || (tests ? "全部示例检查通过。" : "运行完成，没有打印输出。")});
  } catch (error) {
    self.postMessage({type: "result", passed: false, output: output + String(error).slice(-6000)});
  } finally {
    namespace?.destroy();
  }
};
async function initialize() {
  const {loadPyodide} = await import(RUNTIME_BASE + "pyodide.mjs");
  const record = text => { output = (output + text + "\n").slice(0,12000); };
  python = await loadPyodide({indexURL: RUNTIME_BASE, stdout: record, stderr: record});
  self.postMessage({type: "ready"});
}
initialize().catch(error => self.postMessage({type:"error", output:"Python 环境加载失败：" + String(error)}));
