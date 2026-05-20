"""
LLMClient 使用示例

运行前:
  1. cp .env.example .env  并按需修改
  2. pip install -r requirements.txt
  3. python example.py
"""

import json
import logging

from dotenv import load_dotenv
from llm_client import LLMClient

# 打开日志可看到重试过程
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# 加载 .env
load_dotenv()


def demo_basic():
    """方式 1：从环境变量构建（推荐）"""
    print("\n========== 1. 从环境变量构建 ==========")
    client = LLMClient.from_env()
    reply = client.chat("用一句话介绍国内新能源汽车行业的现状")
    print("回复:", reply)


def demo_explicit():
    """方式 2：显式参数"""
    print("\n========== 2. 显式参数示例 ==========")
    # 注释掉是因为没真实 endpoint，仅示意写法
    # client = LLMClient(
    #     provider="custom",
    #     base_url="https://your-llm-proxy.example.com/v1",
    #     api_key="sk-xxx",
    #     model="your-model",
    #     extra_headers={"X-Tenant": "demo"},
    # )
    # print(client.chat("你好"))
    print("(示例代码已注释，需要时取消注释并填入真实 endpoint)")


def demo_streaming():
    """方式 3：流式输出"""
    print("\n========== 3. 流式输出 ==========")
    client = LLMClient.from_env()
    print("流式回复: ", end="", flush=True)
    for chunk in client.stream("用 30 个字介绍 AI Agent 是什么"):
        print(chunk, end="", flush=True)
    print()


def demo_multi_turn():
    """方式 4：多轮对话 + 自定义参数"""
    print("\n========== 4. 多轮对话 ==========")
    client = LLMClient.from_env()
    messages = [
        {"role": "system", "content": "你是一名汽车行业数据分析专家，回答简洁专业。"},
        {"role": "user", "content": "什么是聚类分析？给一个汽车行业应用例子。"},
    ]
    reply = client.chat(messages, temperature=0.3, max_tokens=200)
    print("回复:", reply)


def demo_usage_stats():
    """方式 5：用量统计"""
    print("\n========== 5. 用量统计 ==========")
    client = LLMClient.from_env()
    client.chat("说一句鼓励的话")
    client.chat("再说一句")
    for chunk in client.stream("数到 5"):
        print(chunk, end="", flush=True)
    print()
    print("\n累计用量:")
    print(json.dumps(client.usage_summary(), indent=2, ensure_ascii=False))
    print("\n最近一次:")
    last = client.last_usage()
    if last:
        print(f"  模型={last.model}, tokens={last.total_tokens}, "
              f"耗时={last.duration_s:.2f}s, 成本=${last.cost_usd:.6f}")


def demo_provider_switch():
    """方式 6：同一份代码切换多个 provider"""
    print("\n========== 6. 同代码切多 provider ==========")
    # 演示理念：同一份业务代码，换个 client 就行
    candidates = [
        # ("openai",   {"model": "gpt-4o-mini"}),
        # ("deepseek", {"model": "deepseek-chat"}),
        ("ollama",   {"model": "qwen2.5:7b"}),
    ]
    for provider, kwargs in candidates:
        try:
            client = LLMClient(provider=provider, **kwargs)
            print(f"[{provider}] {client.chat('一个字回答：你好')}")
        except Exception as e:
            print(f"[{provider}] 调用失败: {e}")


if __name__ == "__main__":
    demo_basic()
    demo_explicit()
    demo_streaming()
    demo_multi_turn()
    demo_usage_stats()
    demo_provider_switch()
