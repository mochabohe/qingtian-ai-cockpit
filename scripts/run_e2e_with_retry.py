"""整轮重试包装器 — 整体最多 N 次,任何一次完整 5 步通过即停止。

某些 LLM 中间网络层对大 prompt 偶发 RST,即使加了单步内重试(orchestrator._run_one
重试 2 次),仍可能整轮挂掉。本脚本在更外层做整轮重试 — 跑通了就把当次输出留下,
覆盖 _latest_e2e.md。

用法:
    python scripts/run_e2e_with_retry.py            # 默认整轮最多 5 次
    python scripts/run_e2e_with_retry.py --max 8    # 整轮最多 8 次
    LLM_PROFILE=<profile-id> python scripts/...     # 切模型 profile
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REPORTS_DIR = REPO_ROOT / "data" / "reports"
LATEST_E2E = REPORTS_DIR / "_latest_e2e.md"


def _run_once(profile_id: str | None, attempt: int, max_attempts: int) -> tuple[bool, str]:
    """跑一次 e2e,返回 (是否成功, 末尾日志摘要)。流式打印子进程输出便于实时看进度。"""
    print(f"\n{'='*70}\n=== Attempt {attempt}/{max_attempts}  profile={profile_id or '<env>'} ===\n{'='*70}", flush=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if profile_id:
        env["LLM_PROFILE"] = profile_id
    env.setdefault("DATASET_SAMPLE_LIMIT", "100000")
    env.setdefault("VOC_MAX_CLUSTER_SAMPLES", "3000")
    env.setdefault("VOC_CLUSTER_BACKEND", "minibatch")

    proc = subprocess.Popen(
        [sys.executable, "-u", "scripts/run_e2e_brief.py"],
        cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        bufsize=1,
    )

    lines: list[str] = []
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            print(line, end="", flush=True)
            lines.append(line)
    finally:
        proc.wait()

    full_out = "".join(lines)
    has_saved = "saved_as:" in full_out and "saved_as: None" not in full_out
    has_step_error = "[step error]" in full_out
    success = has_saved and not has_step_error
    tail = "".join(lines[-25:]) if lines else "(no output)"
    return success, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=5, help="整轮最多重试次数")
    parser.add_argument("--profile", type=str, default=None, help="LLM_PROFILE,默认按当前 env;可在两个 profile 间轮换")
    args = parser.parse_args()

    # 默认只跑当前激活 profile;如需轮换,使用 --profile 显式指定
    profiles_rotation = [args.profile] if args.profile else [None]

    t_start = time.time()
    last_tail = ""
    for i in range(1, args.max + 1):
        profile = profiles_rotation[(i - 1) % len(profiles_rotation)]
        ok, tail = _run_once(profile, i, args.max)
        last_tail = tail
        elapsed = time.time() - t_start
        if ok:
            print(f"\n🎉 第 {i} 次跑通(profile={profile}),累计耗时 {elapsed:.1f}s")
            print(f"   产物: {LATEST_E2E.relative_to(REPO_ROOT)} (实际由 run_e2e_brief 写入)")
            return 0
        print(f"\n⚠️  第 {i} 次失败,末尾日志:\n{tail}\n")
        if i < args.max:
            wait = min(20 + i * 5, 60)  # 累进等待 25/30/35/40 秒
            print(f"   等待 {wait}s 后切换 profile 重试...\n", flush=True)
            time.sleep(wait)

    print(f"\n💥 整轮 {args.max} 次全部失败,总耗时 {time.time()-t_start:.1f}s")
    print(f"   建议改走静态降级: python scripts/build_offline_brief.py")
    print(f"   最后一次失败日志末尾:\n{last_tail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
