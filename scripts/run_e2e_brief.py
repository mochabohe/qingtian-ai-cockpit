"""
端到端跑一次完整 5-step Agent 编排,基于真实主线数据生成战略简报。

不启 web server,直接调用 AgentOrchestrator;产物自动保存到 data/reports/。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Windows 控制台默认 GBK 编码,主线 prompt 含⚠/标点等非 GBK 字符,强制 UTF-8 stdout
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# 把 backend 加入 path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

# 显式加载 backend/.env(脚本独立跑时 env 不会自动加载)
# backend/.env 与根目录 .env 同步,优先 backend/.env(更具体)
from dotenv import load_dotenv
for _env in (REPO_ROOT / "backend" / ".env", REPO_ROOT / ".env"):
    if _env.exists():
        load_dotenv(dotenv_path=_env, override=False)

from app.llm_client import LLMClient
from app.services.orchestrator import AgentOrchestrator


TOPIC = "eπ007 经营战略简报 · 销售-售后-市场口碑全景"


async def main() -> int:
    client = LLMClient.from_env()
    orch = AgentOrchestrator(client, data_file=None)

    run_task = asyncio.create_task(orch.run(TOPIC))

    print(f"=== 启动编排: {TOPIC} ===\n")
    last_step = None
    async for event, data in orch.stream_events():
        if event == "start":
            print(f"[start] topic={data['topic']}, total_steps={data['total_steps']}")
        elif event == "data_loaded":
            print(f"[data_loaded] file={data['file']}, rows={data.get('rows')}, cols={data.get('cols')}")
            print(f"  主线分析摘要(前 200 字): {data.get('summary', '')[:200]}\n")
        elif event == "step_start":
            last_step = data
            print(f"\n[step {data['index']}/{5}] 启动 {data['name']} - {data['title']}")
        elif event == "step_done":
            preview = (data.get('output') or '')[:160].replace("\n", " ")
            print(f"[step {data['index']} done] output 前 160 字: {preview}...")
        elif event == "step_error":
            print(f"[step error] step={data.get('index')} name={data.get('name')} msg={data.get('message')}")
        elif event == "end":
            print(f"\n=== 编排结束 ===")
            print(f"  saved_as: {data.get('saved_as')}")
            md = data.get("report", "")
            if md:
                # 也存一份 e2e 版本的 markdown 在脚本目录,方便对外展示
                out = REPO_ROOT / "data" / "reports" / "_latest_e2e.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(md, encoding="utf-8")
                print(f"  已写: {out}")
        elif event == "error":
            print(f"[error] {data.get('message')}")

    await run_task
    last = client.last_usage()
    if last:
        print(f"\nToken usage: {last.__dict__}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
