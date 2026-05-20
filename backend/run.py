"""
开发服务器: python run.py

⚠️ Windows reload 陷阱(2026-05-06 实测):
uvicorn 在 reload 模式下用 multiprocessing.spawn fork worker 进程。
如果你 kill 了 reloader (uvicorn 主进程,占着 8000 端口),Windows 上
spawn 出来的 worker 子进程**不会自动死**,变成孤儿继续监听 8000。
表现:
  - netstat 显示 8000 端口有多个 LISTENING PID
  - taskkill 报"找不到进程"但端口仍占
  - 请求被旧 worker 处理,改的代码永远不生效
  - 日志一片空白,加的探针/print 不出现
排查:
  powershell -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" \\
    | Select-Object ProcessId, CommandLine"
  → 看到带 "spawn_main(parent_pid=...)" 的 python.exe 就是孤儿
清理:
  pnpm kill:backend
  → 等价于 powershell -File scripts/kill-port-8000.ps1
  → 自动追溯 8000 LISTENING PID 的进程树并 taskkill /F /T

⚠️ 双保险:本文件结尾注册了 atexit 钩子和 SIGINT/SIGTERM handler,
   reloader 正常退出时主动 taskkill /T 杀掉自己的子进程树,
   避免 Ctrl+C 后留下 spawn 孤儿继续占 8000。
   Windows 下 Ctrl+C 不一定走 atexit(看终端宿主),所以 predev 钩子
   还是兜底跑一次 kill-port-8000.ps1 清场。
"""
import atexit
import os
import signal
import subprocess
import sys

# Windows PowerShell 默认 GBK,Python 日志的中文会乱码。
# 1) PYTHONIOENCODING 让 reload 模式下 spawn 出来的 worker 子进程也走 UTF-8
# 2) reconfigure 修当前主进程已初始化的 stdout/stderr
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

import uvicorn

from app.core.config import settings


# Windows 下 reloader 退出前杀掉自己的整棵进程树(包括 spawn worker)
# 不是 Windows 就直接跳过(Linux/macOS spawn worker 会跟着 reloader 死)
def _kill_self_tree():
    if sys.platform != "win32":
        return
    my_pid = os.getpid()
    try:
        # taskkill /T 会把 my_pid 的所有子孙一起杀掉
        # /F 强制(spawn worker 不响应正常退出信号)
        # 用 subprocess 而非 os.system,避免没有终端时 system 抛错
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(my_pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        # atexit/信号处理器里出错也别炸;就算这步失败,predev 还会兜底
        pass


def _signal_handler(signum, frame):
    # 信号到了先跑 atexit 钩子链,然后强退
    # raise SystemExit 会触发 atexit 但不一定能在 5s 内跑完;直接 _kill_self_tree
    _kill_self_tree()
    sys.exit(0)


if __name__ == "__main__":
    # 1. 注册 atexit:正常退出时清自己的进程树
    atexit.register(_kill_self_tree)

    # 2. 注册信号 handler:Ctrl+C(SIGINT) / 终端关闭(SIGTERM) 时也清
    # Windows 上 SIGINT 一般会走;SIGTERM 多数 Python 实现会忽略,但试试无害
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    # 白名单 reload_dirs(只盯 backend/app) 比 reload_excludes 通配符更可靠:
    # 默认 watchfiles 监视项目根整个目录,写 ./data/* 任何运行时文件
    # (简报/视频产物/上传文件)都会立即触发 reload,正在响应的请求被中断,
    # 客户端拿到 500。白名单只关心 backend/app 下的源码改动,运行时数据文件永不触发 reload。
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_dirs=["backend/app"] if settings.debug else None,
    )
