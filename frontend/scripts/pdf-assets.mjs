import { cp, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = new URL('../', import.meta.url);
await mkdir(new URL('public/pdf-assets/', root), { recursive: true });
for (const name of ['cmaps', 'standard_fonts', 'wasm']) {
  await cp(fileURLToPath(new URL(`node_modules/pdfjs-dist/${name}`, root)), fileURLToPath(new URL(`public/pdf-assets/${name}`, root)), { recursive: true });
}
await mkdir(new URL('public/python-runtime/', root), {recursive:true});
for (const name of ['pyodide.mjs','pyodide.asm.mjs','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json']) {
  await cp(fileURLToPath(new URL(`node_modules/pyodide/${name}`,root)),fileURLToPath(new URL(`public/python-runtime/${name}`,root)));
}
