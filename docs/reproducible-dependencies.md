# 锁定依赖与本机安装

本轮固定 uv 0.13.1、默认 Python 3.11.17，并提交 `backend/uv.lock`。初次锁定以已经通过本机验收的依赖闭包为基线，35 个运行/测试依赖保留原版本；构建后端 setuptools 固定为 80.9.0。Linux 的 uvicorn 标准扩展另解析出 uvloop 0.23.0，没有盲目升级现有包。

`backend/pyproject.toml` 继续表达允许的依赖范围；`uv.lock` 保存本次解析版本及发行包哈希。`dev` 仍是 optional extra，包含 pytest、respx 和 Ruff，使用 `--extra dev` 安装。`[tool.uv].required-version` 要求精确 uv 版本，构建约束防止独立构建环境再任意选择 setuptools。

## Windows 首次安装

在仓库根目录运行，需要 Windows 64 位 PowerShell、系统自带 curl 和已有 Node.js：

```powershell
.\scripts\setup-dependencies.ps1
.\start.ps1 -Mode Local -Check
.\start.ps1 -Mode Local -Offline
```

安装脚本从官方 PyPI 下载固定版本 uv Windows x64 wheel，核验官方元数据中的 SHA-256，只抽取独立可执行程序到 `.tmp/tools/uv-0.13.1/`。它不调用全局 pip，不修改机器 PATH，也不注册全局 Python。Python 下载、缓存和临时构建目录均放在项目 `.tmp/`，环境安装到 `backend/.venv/`。

`start.ps1` 和 `demo.ps1` 只使用 `backend/.venv/Scripts/python.exe`；缺少环境时明确要求安装，不再根据全局 `python` 猜测服务解释器。原有运行实例不会因为安装依赖自动停止或重启，更新后需要自行按原数据配置重启。

可选参数：

```powershell
# 只同步后端，保留现有前端 node_modules
.\scripts\setup-dependencies.ps1 -SkipFrontend
# 不安装测试工具；本机日常使用即可，开发验证使用默认配置
.\scripts\setup-dependencies.ps1 -Production -SkipFrontend
# 系统代理失效时显式使用直连，仅对该脚本和子进程生效
.\scripts\setup-dependencies.ps1 -Direct -SkipFrontend
# 有意选择另一个解释器时必须显式指定，仍安装隔离的项目环境
.\scripts\setup-dependencies.ps1 -Python 'C:\path\to\python.exe' -SkipFrontend
```

更换解释器或同步依赖前先停止使用该项目虚拟环境的进程，避免 Windows 已加载 DLL 造成安装冲突。脚本临时设置的缓存、安装目录、代理例外和 TEMP/TMP/TMPDIR 均在成功或失败后恢复。受限 Windows 账号可能拒绝 uv 的全局次版本链接；脚本可改用已经下载到项目的精确版本解释器重试，不依赖全局链接。

Windows PowerShell 5.1 与 PowerShell 7 均支持本机启停。停止时保留 JSON 进程时间戳的完整精度进行身份比对；原本不存在的环境变量在清理时移除，避免新版 .NET 把空值保留为变量。

## Linux 与其他平台

Windows 引导器只下载 x64 Windows uv。其他平台先按 [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)安装固定 0.13.1，再在项目根目录执行：

```sh
uv sync --project backend --locked --extra dev --python 3.11.17
backend/.venv/bin/python backend/scripts/test.py -q
backend/.venv/bin/python -m ruff check backend/app backend/scripts backend/tests evaluation/research_atlas evaluation/retrieval
```

这里的 Linux 路径是部署/CI 策略；本机没有把 Linux 命令执行结果冒充实测。依赖安装可能联网下载 Python 和发行包，业务模型仍由原授权开关控制。

## CI 与 Docker

CI 使用固定提交的官方 setup-uv Action 和 uv 0.13.1，先检查锁文件，再运行 `uv sync --locked --extra dev`。随后将项目环境放到 CI 的 PATH，并设置 `ATLAS_PYTHON` 为绝对解释器路径，使 Python 脚本与浏览器子进程使用同一环境。Windows/Ubuntu 的配置目标均为 Python 3.11.17；本轮实际运行的是本机 Windows，远端 CI 尚未触发。检索回归分别运行默认索引和 `--scan` 两种方式并上传报告。

后端 Dockerfile 使用官方 `python:3.11.17-slim-bookworm` 与固定 uv 0.13.1；先复制元数据、锁文件和 MANIFEST 并安装依赖，再复制源码并非 editable 安装项目，避免源码尚未复制就安装空项目。运行时仍为非 root，使用 `/app/.venv/bin/python` 所在环境。构建中禁用额外 Python 下载；生产镜像不安装 `dev` extra。

上述固定了 Python 补丁号、uv 版本与依赖解析，但镜像标签本身仍可能被上游重新构建。正式发布还应在可用 registry/构建环境记录并固定已验证镜像 digest；不能把锁文件等同于整个镜像逐字节可重复。当前机器 Docker 引擎不可用，尚未完成镜像构建或容器启动验收。

## 验证与升级

在 Windows 安装默认开发依赖后，从项目根目录运行：

```powershell
.\.tmp\tools\uv-0.13.1\uv.exe lock --project backend --check --cache-dir .tmp/uv-cache
.\backend\.venv\Scripts\python.exe backend/scripts/test.py -q
.\backend\.venv\Scripts\python.exe -m ruff check backend/app backend/scripts backend/tests evaluation/research_atlas evaluation/retrieval
.\backend\.venv\Scripts\python.exe evaluation/retrieval/evaluate_retrieval.py
.\backend\.venv\Scripts\python.exe evaluation/retrieval/evaluate_retrieval.py --scan
```

`--locked` 会在项目声明与锁文件不符时失败；`--frozen` 会跳过一致性检查，不能替代 CI 检查。[官方锁定说明](https://docs.astral.sh/uv/concepts/projects/sync/)。需要升级时在隔离环境明确选择包，例如 `uv lock --project backend --upgrade-package fastapi`，审查锁文件差异后重跑相关测试；不要在启动脚本自动升级。

包构建隔离、非 editable 安装及缓存层的方案参考 [uv Docker 文档](https://docs.astral.sh/uv/guides/integration/docker/)，CI 参考 [uv GitHub Actions 文档](https://docs.astral.sh/uv/guides/integration/github/)。本次 uv 工具 wheel 的已核验 SHA-256 为 `4f693cd4feb52f08f30474c4612f24be2050472609be65b9960b635f286da284`；它是 PyPI wheel 的哈希，不是 GitHub ZIP 的哈希。

当前版本的复现范围与实际验收入口见 `docs/unified-release.md`；数据与账号不属于依赖安装范围。历史依赖改造记录仅在本机归档中保留。
