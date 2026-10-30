"""进程内后台任务执行器：有界线程池，替代裸 daemon 线程。

线程数有上限，防止并发请求无限创建线程；进程退出时由解释器统一回收。
生产化时可整体替换为 Celery/Arq 等任务队列，调用方接口不变。
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Lock

logger = logging.getLogger(__name__)

_executor = None
_executor_lock = Lock()


def submit_task(fn, *args):
    global _executor
    # A request's workspace scope must survive execution in another thread.
    context = copy_context()
    with _executor_lock:
        if _executor is None:
            from app.config import get_settings
            workers = 1 if get_settings().access_mode == "multiuser" else 4
            _executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="atlas-task")
        return _executor.submit(context.run, fn, *args)


def shutdown_executor(wait: bool = False) -> None:
    global _executor
    with _executor_lock:
        executor = _executor
        _executor = None
    if executor is not None:
        executor.shutdown(wait=wait, cancel_futures=True)
