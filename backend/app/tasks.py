"""进程内后台任务执行器：有界线程池，替代裸 daemon 线程。

线程数有上限，防止并发请求无限创建线程；进程退出时由解释器统一回收。
生产化时可整体替换为 Celery/Arq 等任务队列，调用方接口不变。
"""

import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="atlas-task")


def submit_task(fn, *args) -> None:
    _executor.submit(fn, *args)


def shutdown_executor(wait: bool = False) -> None:
    _executor.shutdown(wait=wait, cancel_futures=True)