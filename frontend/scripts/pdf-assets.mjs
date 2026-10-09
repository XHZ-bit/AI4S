import { cp, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = new URL('../', import.meta.url);
await mkdir(new URL('public/pdf-assets/', root), { recursive: true });
for (const name of ['cmaps', 'standard_fonts', 'wasm']) {
  await cp(fileURLToPath(new URL(`node_modules/pdfjs-dist/${name}`, root)), fileURLToPath(new URL(`public/pdf-assets/${name}`, root)), { recursive: true });
}
