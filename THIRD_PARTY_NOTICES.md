# Third-party dependency inventory and release review

本清单于2026-10-29从当前安装环境与上游说明核对，记录主要直接依赖和本地解析权重。它不是完整的传递依赖 SBOM，也不替代各上游许可全文及兼容性核对；不为本项目自研部分授予新的许可证。自研开源许可证仍须由权利人确定。

## Direct runtime dependencies

| Component | Installed version | Declared license |
| --- | --- | --- |
| FastAPI | 0.136.1 | MIT |
| Uvicorn | 0.40.0 | BSD-3-Clause |
| Pydantic | 2.12.4 | MIT |
| Pydantic Settings | 2.16.2 | MIT |
| HTTPX | 0.28.1 | BSD-3-Clause |
| Neo4j Python driver | 6.4.0 | Apache-2.0 AND Python-2.0 |
| PyMuPDF | 1.27.2.3 | GNU AGPL v3 or Artifex commercial license |
| python-multipart | 0.0.29 | Apache-2.0 |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| Docling | 2.144.0 | MIT; model weights have separate terms |
| openpyxl | 3.1.5 | MIT |
| python-docx | 1.2.0 | MIT |
| PyTorch | 2.9.1+cpu | BSD-3-Clause |
| torchvision | 0.24.1+cpu | BSD |
| React / React DOM | 18.3.1 | MIT |
| Ant Design | 5.29.3 | MIT |
| Ant Design Icons | 5.6.1 | MIT |
| KaTeX | 0.19.0 | MIT |
| PDF.js distribution | 6.4.299 | Apache-2.0 |
| Pyodide | 314.0.7 | MPL-2.0; bundled packages retain their respective terms |
| react-force-graph-2d | 1.29.1 | MIT |
| React Router DOM | 7.18.4 | MIT |
| Zustand | 4.5.7 | MIT |

精确环境记录、依赖声明和本地许可证文件索引见 [aic-dependency-licenses-2026-10-29.json](docs/validation/aic-dependency-licenses-2026-10-29.json)，版本重建以 `backend/uv.lock` 和 `frontend/package-lock.json` 为准。

PyMuPDF 的双许可由其[官方文档](https://pymupdf.readthedocs.io/en/latest/about.html)说明；不能因为其他组件使用MIT而把整个依赖组合直接标成MIT。公开分发或提供网络服务前，必须核对所选许可路径及其适用条件。

## Local document models

以下许可来自本机实际下载的模型卡，模型代码许可与权重许可分别核对。源代码交付包不包含模型权重；安装脚本从上游获取，并保存本机文件哈希。

| Repository | Model-card license |
| --- | --- |
| [docling-project/CodeFormulaV2](https://huggingface.co/docling-project/CodeFormulaV2) | CDLA-Permissive-2.0 |
| [docling-project/docling-layout-heron](https://huggingface.co/docling-project/docling-layout-heron) | Apache-2.0 |
| [docling-project/docling-layout-heron-onnx](https://huggingface.co/docling-project/docling-layout-heron-onnx) | Apache-2.0 |
| [docling-project/docling-models](https://huggingface.co/docling-project/docling-models) | CDLA-Permissive-2.0 |

[Docling官方说明](https://github.com/docling-project/docling/blob/main/README.md)明确要求另行查看各模型许可。本机哈希快照能核对已下载文件，但安装器尚未将所有上游模型固定到不可变提交；不能据此声称首次联网安装逐字节复现模型权重。

## Source and data boundaries

- Python和npm依赖安装后保留各包自带的许可证与版权信息。生成的PDF.js和Pyodide浏览器运行时不混入源包，由前端 `prebuild` 从锁定依赖恢复。
- 自带案例的上游声明位于 `backend/app/cases/UPSTREAM_LICENSE.txt`，源包继续包含该声明。
- 论文PDF、用户报告、私有代码、实验结果、数据库、API凭据和解析模型权重均不作为自研源代码重新授权。公开仓库链接或论文可访问，不代表可以任意重新分发其全文或代码。
- 当前清单尚未核验所有传递依赖、所有云模型服务条款及所有论文仓库授权。提交材料应据实列出来源，不能写成“全平台完全自研”或“所有依赖均为MIT”。
