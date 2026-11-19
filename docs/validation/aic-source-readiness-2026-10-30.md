# AIC 源码交付与隔离启动核查

核查日期：2026-10-30（北京时间）。范围为当前打包流程和不含用户数据的源码副本，不是全新机器的完整在线安装验收。最终提交包应在代码冻结后另行生成，本次审计包不能替代最终版本。

## 本次实际执行

1. 使用当前 `scripts/package_release.py` 生成中间审计包 `.releases/audit-source-20261030.zip`：634 个源码文件，1,909,401 字节，SHA-256 为 `3b1a0aa07dd37c4aa94c546d648e4416dc88a7e580d2eef1eadae6f46793719d`。
2. 在 `.tmp/aic-source-final/extracted-v2/` 独立目录解压，校验 ZIP CRC 和清单中每份文件的 SHA-256。全部通过，未读写业务数据目录。
3. 检查包内没有数据库、PDF/DOCX、模型权重、`.env`、虚拟环境、`node_modules`、生成的 PDF/Python 运行时及个人报告；同时检查了常见 `sk-` 凭据模式。该检查不能替代完整人工秘密审查，但本包未发现匹配。
4. 包含后端与前端锁文件、依赖安装脚本、Docling 模型准备脚本和第三方声明。顶层项目许可证仍未选择，清单中的 `project_license` 为 `null`；本包不代表已经完成开源授权或公开发布。
5. 从解压源码启动独立后端，使用新的临时数据目录和端口 18189，显式关闭模型并清除子进程 API 密钥。实际 HTTP 状态返回数据库 `available`、模型 `unconfigured`。旧可选 GROBID 服务使总状态为 `degraded`，不影响该次 SQLite 初始化。测试结束只停止本次创建的进程。
6. 对解压包内 PowerShell 文件进行语法解析，并检查前端资源准备脚本的 Node.js 语法。结果见 `.tmp/aic-source-final/powershell-syntax.json`；Node 检查通过。
7. 执行当前 `uv 0.13.1 lock --project backend --check --offline`：成功核对锁文件，解析为 128 个包，未下载新依赖。

隔离启动复用了开发机已安装的后端依赖。因此，它证明该源码副本能够在现有依赖和新数据目录中启动，不证明一个完全空白操作系统已完成首次安装。未执行新的模型调用、论文解析质量评测、Docker 构建或 Linux 验收。原始机器可读证据保存在 `.tmp/aic-source-final/result.json`。

## 安装链条核对

Windows 本机完整安装入口仍为：

```powershell
.\scripts\setup-dependencies.ps1
.\scripts\setup-docling.ps1 -Check
.\start.ps1 -Mode Local -Check
.\start.ps1 -Mode Local
```

需要 Windows x64 PowerShell、curl 和事先安装的 Node.js。依赖脚本使用固定 uv 和锁文件，默认调用 `setup-docling.ps1` 下载结构解析、表格、公式与 OCR 模型，再执行前端 `npm ci`。首次安装需要联网和足够磁盘空间，源码包本身不携带这些大依赖。

若分开准备，可先 `setup-dependencies.ps1 -SkipParserModels`，随后单独执行 `setup-docling.ps1`。未准备模型时，不能把文字降级结果当作完整结构解析。`setup-docling.ps1 -Check` 检查本机模型缓存的存在性和清单哈希，不会下载模型。

`frontend/package.json` 的 `predev`、`prebuild`，以及本机启动脚本，均调用 `frontend/scripts/pdf-assets.mjs`，由已安装的 `pdfjs-dist` 和 `pyodide` 包恢复浏览器资源。源码打包完整排除 `frontend/public/pdf-assets/` 与 `python-runtime/`，避免只分发一部分运行时。执行 `npm ci` 后，使用 `npm run dev` 或 `npm run build`，而不是跳过前置脚本直接调用 Vite。

无原论文缓存时，可用 `demo.ps1 -Synthetic` 创建明确标注的原创合成资料，检查软件流程；这不是真实论文分析或研究效果验证。默认真实论文演示依赖另外提供、已校验并有权使用的 PDF 缓存，源码包不包含论文全文。

## 最终冻结时仍需完成

- 在最后学习逻辑修复完成后重新打包，记录该最终包的新版本、字节数和 SHA-256；不要把本页中间包哈希写成最终交付版本。
- 确定最终许可、第三方义务和评审访问方式。受限评审不免除第三方许可要求，本次没有授权公开发布。
- 最终包中的源码与报告描述保持一致；评审期实际访问链接由提交者核对。全新机器首次在线安装、Docker/Linux 路径和外部服务可用性未在本轮补验。
