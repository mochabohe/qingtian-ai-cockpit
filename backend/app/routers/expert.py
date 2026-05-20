"""
擎天 HiAgent 平台「东风经营分析陪伴专家」API proxy 路由

擎天 HiAgent 协议要点(基于实际接口文档):
- 鉴权头: `Apikey: <key>` (大小写敏感,不是 Bearer)
- 路径:
    POST /create_conversation  -> 创建会话(返回 Conversation.AppConversationID)
    POST /chat_query_v2        -> 发起对话(支持流式 SSE,event=message + data=chunk)
    POST /stop_conversation    -> 中断进行中的对话(可选)
    POST /upload_file          -> 上传文件(可选,本项目不用)

请求体公共字段:
    UserID            : 业务侧用户标识(自定义)
    AppKey            : API Key(同 Apikey 头)
    AppConversationID : 会话 ID(create 后拿到,chat 时传)
    Query             : 用户消息
    Inputs            : 智能体启动变量(对应擎天工作流 / Prompt 里的 {{xxx}})
    ResponseMode      : "streaming" | "blocking"

响应字段(SSE 流):
    每个 SSE 帧: `event: message\ndata: {...JSON...}\n\n`
    JSON 字段:
      Type: "message" / "agent_thought" / "completion" / ...
      Answer:   增量文本(累加追加到回答)
      ConversationID, MessageID, AnswerID  ← 后续追问可复用

本 proxy 工作流:
  前端 POST /api/expert/chat
    → 后端检查会话(没有就 create_conversation)
    → 后端 POST /chat_query_v2(streaming)
    → 把擎天 SSE 重新打包为前端约定格式 `data: {"delta": "..."}\n\n`
    → 前端流式渲染
"""

import json
import logging
import os
import uuid
from typing import AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/expert", tags=["expert"])

# Agent 元信息进程内缓存：擎天 get_app_config_preview 拉取成功后缓存到这里，
# 后续即使擎天接口偶发 ConnectTimeout，也能返回上次的真实值，避免 UI 反复闪回默认占位。
_AGENT_INFO_CACHE: Optional["AgentInfoResponse"] = None


# ============================================================================
# 配置:从 .env 读,优先级 env > 默认占位
# ============================================================================

class QingtianExpertConfig:
    """擎天 HiAgent 智能体配置"""

    # base_url 形如 https://qingtian.dfmc.com.cn/api/proxy/api/v1
    BASE_URL: str = os.environ.get(
        "QINGTIAN_BASE_URL",
        "https://qingtian.dfmc.com.cn/api/proxy/api/v1",
    )
    # AppKey/ApiKey
    API_KEY: str = os.environ.get("QINGTIAN_API_KEY", "")

    # UserID(业务侧标识,跟 AppKey 配)
    USER_ID: str = os.environ.get("QINGTIAN_USER_ID", "dongfeng-analyst-001")

    # 启用开关:env QINGTIAN_ENABLED=1 打开,默认关
    ENABLED: bool = os.environ.get("QINGTIAN_ENABLED", "0") == "1"

    # 超时(秒)。流式对话首字节可能较慢,给 30s 足够
    TIMEOUT: int = int(os.environ.get("QINGTIAN_TIMEOUT", "30"))
    # 流式 SSE 的 read 超时(秒): 擎天在 KB 检索 + 工作流思考阶段,两帧间隔可能 30s+,
    # 单独放宽,避免 ReadTimeout 把流打断。connect/write 仍走短超时。
    STREAM_READ_TIMEOUT: int = int(os.environ.get("QINGTIAN_STREAM_READ_TIMEOUT", "180"))

    @classmethod
    def is_ready(cls) -> bool:
        return bool(cls.ENABLED and cls.BASE_URL and cls.API_KEY)

    @classmethod
    def headers(cls) -> dict:
        return {"Apikey": cls.API_KEY, "Content-Type": "application/json"}


# ============================================================================
# 请求/响应模型
# ============================================================================

class ExpertChatRequest(BaseModel):
    user_query: str = Field(..., description="用户问题")
    focus_vehicle: Optional[str] = Field(None)
    briefing_title: Optional[str] = Field(None)
    briefing_summary: Optional[str] = Field(None)
    briefing_sections: Optional[str] = Field(None)
    # 多轮对话用:第一轮不传,后端创建后写在响应头 X-Conversation-Id
    conversation_id: Optional[str] = Field(None)


class ExpertStatusResponse(BaseModel):
    enabled: bool
    ready: bool
    message: str
    base_url_masked: str    # 脱敏后的 base_url(前端只用来核对没串号)


class ConversationBrief(BaseModel):
    """擎天 get_conversation_list 返回的单条会话摘要。

    字段命名与擎天接口保持一致（驼峰），前端直接按擎天字段用。
    """
    AppConversationID: str
    ConversationName: str = ""
    CreateTime: str = ""
    LastChatTime: str = ""
    EmptyConversation: bool = False


class ConversationListResponse(BaseModel):
    ConversationList: list[ConversationBrief] = Field(default_factory=list)


class ConversationMessage(BaseModel):
    """会话内一条消息（extract 自擎天 get_conversation_messages）。

    Role: "user" | "assistant"；Content: 文本正文（擎天可能分 Query/Answer，合并后用统一 role）
    """
    role: str
    content: str
    created_at: str = ""


class ConversationMessagesResponse(BaseModel):
    messages: list[ConversationMessage] = Field(default_factory=list)


class AgentInfoResponse(BaseModel):
    """Agent 元信息(从擎天 GetAppConfigPreview 提取)"""
    name: str = Field(default="经营分析陪伴专家", description="Agent 名称")
    avatar: str = Field(default="👨‍💼", description="头像(emoji 或 URL)")
    subtitle: str = Field(default="由擎天平台提供企业知识增强", description="副标题")
    description: str = Field(default="", description="Agent 描述")
    greeting: str = Field(
        default="您好,我是您的经营分析陪伴专家。已读取您当前查看的简报,可以围绕销售归因、售后异常、VOC 口碑、产品矩阵、行业基准等话题深问。",
        description="开场白"
    )
    open_questions: list[str] = Field(
        default_factory=lambda: [
            "这条结论的归因方法论是什么",
            "同比和环比的标准用法",
            "给我对比同价位竞品的产品定位",
            "这个数字符合行业基准吗",
        ],
        description="推荐问题列表"
    )


# ============================================================================
# 路由
# ============================================================================

@router.get("/status")
async def get_expert_status() -> ExpertStatusResponse:
    is_ready = QingtianExpertConfig.is_ready()
    if not QingtianExpertConfig.ENABLED:
        message = "专家智能体未启用(QINGTIAN_ENABLED!=1)"
    elif not QingtianExpertConfig.API_KEY:
        message = "未配置 QINGTIAN_API_KEY"
    elif not is_ready:
        message = "擎天 API 配置不完整"
    else:
        message = "专家智能体就绪"

    base_masked = (
        QingtianExpertConfig.BASE_URL.split("//")[-1].split("/")[0]
        if QingtianExpertConfig.BASE_URL else ""
    )
    return ExpertStatusResponse(
        enabled=QingtianExpertConfig.ENABLED,
        ready=is_ready,
        message=message,
        base_url_masked=base_masked,
    )


@router.get("/agent-info")
async def get_agent_info() -> AgentInfoResponse:
    """
    获取 Agent 元信息(名称/头像/开场白/推荐问题)。
    优先从擎天 GetAppConfigPreview 拉取,失败则返回默认值。

    缓存策略：擎天接口偶发 ConnectTimeout（10s 超时），如果每次失败都掉到默认占位，
    前端会反复看到"经营分析陪伴专家"这种通用文案。这里加进程内缓存——
    一旦从擎天拉到过真实配置，后续即使擎天暂时不可达，也优先返回上次成功的值，
    保证 UI 文案稳定。
    """
    if not QingtianExpertConfig.is_ready():
        return AgentInfoResponse()

    # global 必须在函数顶部声明（Python 不允许先读 _AGENT_INFO_CACHE 再 declare global）
    global _AGENT_INFO_CACHE

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            payload = {
                "AppKey": QingtianExpertConfig.API_KEY,
                "UserID": QingtianExpertConfig.USER_ID,
            }
            resp = await client.post(
                f"{QingtianExpertConfig.BASE_URL}/get_app_config_preview",
                json=payload,
                headers=QingtianExpertConfig.headers(),
            )
            if resp.status_code != 200:
                logger.warning("get_app_config_preview 返回 %s: %s", resp.status_code, resp.text[:200])
                # 拉取失败但缓存里有真实值 → 用缓存
                if _AGENT_INFO_CACHE is not None:
                    return _AGENT_INFO_CACHE
                return AgentInfoResponse()

            body = resp.json()
            name = body.get("Name") or "经营分析陪伴专家"
            avatar = body.get("ImageUrl") or "👨‍💼"
            description = body.get("Description") or ""
            greeting = body.get("OpenMessage") or (
                "您好,我是您的经营分析陪伴专家。已读取您当前查看的简报,"
                "可以围绕销售归因、售后异常、VOC 口碑、产品矩阵、行业基准等话题深问。"
            )
            open_query = body.get("OpenQuery") or []
            questions = open_query if isinstance(open_query, list) and open_query else [
                "这条结论的归因方法论是什么",
                "同比和环比的标准用法",
                "给我对比同价位竞品的产品定位",
                "这个数字符合行业基准吗",
            ]

            info = AgentInfoResponse(
                name=name,
                avatar=avatar,
                subtitle=description or "由擎天平台提供企业知识增强",
                description=description,
                greeting=greeting,
                open_questions=questions,
            )
            # 写缓存：下次擎天超时时仍能返回真实配置
            _AGENT_INFO_CACHE = info
            return info
    except Exception:
        logger.exception("get_app_config_preview 调用失败,降级到缓存或默认值")
        # 接口异常但缓存里有真实值 → 用缓存
        if _AGENT_INFO_CACHE is not None:
            return _AGENT_INFO_CACHE
        return AgentInfoResponse()


@router.post("/chat")
async def chat_with_expert(req: ExpertChatRequest):
    if not QingtianExpertConfig.is_ready():
        raise HTTPException(status_code=503, detail="专家智能体配置未完成")
    return StreamingResponse(
        _stream_expert(req),
        media_type="text/event-stream",
    )


# ============================================================================
# 会话历史记录(GetConversationList + GetConversationMessages)
# ============================================================================

@router.get("/conversations")
async def list_conversations(limit: int = 20) -> ConversationListResponse:
    """
    获取当前 UserID 在擎天的历史会话列表(从近到远,用于"打开历史记录"侧栏)。

    擎天接口: POST /get_conversation_list
      body: {"AppKey": "...", "UserID": "..."}
      resp: {"ConversationList": [{"AppConversationID","ConversationName","CreateTime","LastChatTime","EmptyConversation"}, ...]}

    - 擎天没有分页参数，本地按 LastChatTime 倒序截断到 limit 条。
    - EmptyConversation=true 的空会话过滤掉（只是创建但没真发过消息，展示出来没意义）。
    - 配置未就绪或接口失败 → 返回空列表(前端侧栏显示"暂无历史")。
    """
    if not QingtianExpertConfig.is_ready():
        return ConversationListResponse()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            payload = {
                "AppKey": QingtianExpertConfig.API_KEY,
                "UserID": QingtianExpertConfig.USER_ID,
            }
            resp = await client.post(
                f"{QingtianExpertConfig.BASE_URL}/get_conversation_list",
                json=payload,
                headers=QingtianExpertConfig.headers(),
            )
            if resp.status_code != 200:
                logger.warning("get_conversation_list 返回 %s: %s", resp.status_code, resp.text[:200])
                return ConversationListResponse()
            body = resp.json() or {}
            raw = body.get("ConversationList") or []
            items: list[ConversationBrief] = []
            for it in raw:
                if not isinstance(it, dict):
                    continue
                cid = it.get("AppConversationID") or ""
                if not cid:
                    continue
                if it.get("EmptyConversation") is True:
                    continue
                items.append(
                    ConversationBrief(
                        AppConversationID=cid,
                        ConversationName=it.get("ConversationName") or "",
                        CreateTime=it.get("CreateTime") or "",
                        LastChatTime=it.get("LastChatTime") or "",
                        EmptyConversation=bool(it.get("EmptyConversation") or False),
                    )
                )
            # 按 LastChatTime 倒序(字符串比较即可,擎天 LastChatTime 形如 "2024-12-09 18:47:05")
            items.sort(key=lambda x: (x.LastChatTime or x.CreateTime), reverse=True)
            return ConversationListResponse(ConversationList=items[: max(1, min(limit, 100))])
    except Exception:
        logger.exception("get_conversation_list 调用失败")
        return ConversationListResponse()


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str, limit: int = 50) -> ConversationMessagesResponse:
    """
    获取指定会话的历史消息(用于"打开历史记录"后点击某条会话回填到聊天面板)。

    擎天接口: POST /get_conversation_messages
      body: {"AppKey":"...","UserID":"...","AppConversationID":"...","Limit":50}
      resp: {"Messages":[{"Query":"...","Answer":"...","CreatedAt":...,"MessageID":"..."}]}

    把擎天一条消息(一轮 Query→Answer)拆成 user/assistant 两条,便于前端直接 push 到
    chat 历史。
    """
    if not QingtianExpertConfig.is_ready():
        return ConversationMessagesResponse()
    if not conversation_id:
        raise HTTPException(status_code=400, detail="缺少 conversation_id")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            payload = {
                "AppKey": QingtianExpertConfig.API_KEY,
                "UserID": QingtianExpertConfig.USER_ID,
                "AppConversationID": conversation_id,
                "Limit": max(1, min(limit, 200)),
            }
            resp = await client.post(
                f"{QingtianExpertConfig.BASE_URL}/get_conversation_messages",
                json=payload,
                headers=QingtianExpertConfig.headers(),
            )
            if resp.status_code != 200:
                logger.warning("get_conversation_messages 返回 %s: %s", resp.status_code, resp.text[:200])
                return ConversationMessagesResponse()
            body = resp.json() or {}
            # 擎天常见字段名: Messages / MessageList / ConversationMessageList,兼容处理
            raw = (
                body.get("Messages")
                or body.get("MessageList")
                or body.get("ConversationMessageList")
                or body.get("messages")
                or []
            )
            if not raw:
                logger.info("get_conversation_messages 返回空消息,原始 body keys=%s", list(body.keys()))
            out: list[ConversationMessage] = []
            for m in raw:
                if not isinstance(m, dict):
                    continue
                # 擎天 V1 实测结构:每条消息是一轮 Q&A
                #   {"Query":"...", "AnswerInfo":{"Answer":"..."}, "CreatedTime": <unix>, ...}
                # 老版本可能直接 {"Query":..., "Answer":...}
                query = (m.get("Query") or m.get("query") or "").strip()
                answer_info = m.get("AnswerInfo") or m.get("answerInfo") or {}
                answer = (
                    (answer_info.get("Answer") if isinstance(answer_info, dict) else "")
                    or m.get("Answer")
                    or m.get("answer")
                    or ""
                ).strip()
                # CreatedTime 是 unix 秒,转字符串方便排序
                created = m.get("CreatedTime") or m.get("CreatedAt") or m.get("CreateTime") or ""

                # 角色分条形态兜底
                role_raw = (m.get("Role") or m.get("role") or m.get("MessageType") or "").lower()
                content_field = (
                    m.get("Content")
                    or m.get("content")
                    or m.get("Message")
                    or m.get("message")
                    or ""
                )

                if query or answer:
                    if query:
                        out.append(ConversationMessage(role="user", content=query, created_at=str(created)))
                    if answer:
                        out.append(ConversationMessage(role="assistant", content=answer, created_at=str(created)))
                    continue

                if role_raw and content_field:
                    role_norm = "assistant" if role_raw in ("assistant", "bot", "ai", "system") else "user"
                    out.append(
                        ConversationMessage(
                            role=role_norm,
                            content=str(content_field).strip(),
                            created_at=str(created),
                        )
                    )
            # 按 created_at 升序;CreatedTime 是 unix 秒(数字字符串可直接 ascii 比较,只要长度一致)
            out.sort(key=lambda x: x.created_at or "")
            return ConversationMessagesResponse(messages=out)
    except Exception:
        logger.exception("get_conversation_messages 调用失败")
        return ConversationMessagesResponse()


# ============================================================================
# 擎天 HiAgent 协议封装
# ============================================================================

async def _create_conversation(client: httpx.AsyncClient, inputs: dict) -> Optional[str]:
    """
    擎天 create_conversation: 创建一次新会话,返回 AppConversationID。
    失败返回 None。
    """
    payload = {
        "UserID": QingtianExpertConfig.USER_ID,
        "AppKey": QingtianExpertConfig.API_KEY,
        "Inputs": inputs or {},
    }
    try:
        resp = await client.post(
            f"{QingtianExpertConfig.BASE_URL}/create_conversation",
            json=payload,
            headers=QingtianExpertConfig.headers(),
        )
        body = resp.json()
        # 擎天返回结构 {"Conversation": {"AppConversationID": "xxx"}, "ResponseMetadata": {...}}
        # 或老版本 {"AppConversationID": "xxx"}
        conv = body.get("Conversation") or body
        cid = conv.get("AppConversationID")
        if not cid:
            logger.error("create_conversation 返回未找到 AppConversationID: %s", body)
            return None
        return cid
    except Exception:
        logger.exception("create_conversation 失败")
        return None


def _build_inputs(req: ExpertChatRequest) -> dict:
    """
    把简报上下文塞到擎天 Inputs 里(对应工作流里声明的变量名)。

    ⚠️ 擎天 VariableConfigs 对 Text 类型字段有 TextMaxLength 限制(实测 32 字符)。
    超长会导致 create_conversation 直接 400 拒绝,前端表现为"创建会话失败"。
    所以这里在塞入前做强制截断;前端发上来的简报摘要/章节往往是几百字,必须截。
    用户搭建时如果改了变量命名或长度上限,这里要同步改。
    """
    MAX_LEN = 32  # 跟擎天 VariableConfigs.TextMaxLength 对齐

    def clip(s: Optional[str]) -> str:
        if not s:
            return ""
        s = s.strip()
        return s[:MAX_LEN]

    return {
        "focus_vehicle": clip(req.focus_vehicle),
        "briefing_title": clip(req.briefing_title),
        "briefing_summary": clip(req.briefing_summary),
        "briefing_sections": clip(req.briefing_sections),
    }


async def _stream_expert(req: ExpertChatRequest) -> AsyncGenerator[str, None]:
    """
    完整对话流程:
      (1) 没有 conversation_id 就先 create_conversation
      (2) chat_query_v2 流式调用
      (3) 把擎天 SSE 重打包为前端约定格式
    前端约定格式:
      data: {"delta": "增量文本", "conversation_id": "...", "done": false}\n\n
      data: {"delta": "", "done": true}\n\n
    """
    inputs = _build_inputs(req)

    # 流式 SSE: connect/write 短超时(快速发现网络不通),read 放宽到 STREAM_READ_TIMEOUT
    # —— 擎天在 knowledge_retrieve + agent_thought 阶段两帧之间可能静默 30s+,
    # 单一 30s timeout 会被 read 阶段触发 ReadTimeout,前端表现为"流式异常: ReadTimeout: "
    stream_timeout = httpx.Timeout(
        connect=10.0,
        read=float(QingtianExpertConfig.STREAM_READ_TIMEOUT),
        write=10.0,
        pool=10.0,
    )
    async with httpx.AsyncClient(timeout=stream_timeout) as client:
        # 1. 会话 ID
        conv_id = req.conversation_id
        if not conv_id:
            conv_id = await _create_conversation(client, inputs)
            if not conv_id:
                yield f"data: {json.dumps({'error': '创建会话失败,请检查擎天 API 是否启用'})}\n\n"
                return

        # 2. 流式 chat
        chat_payload = {
            "UserID": QingtianExpertConfig.USER_ID,
            "AppKey": QingtianExpertConfig.API_KEY,
            "AppConversationID": conv_id,
            "Query": req.user_query,
            "Inputs": inputs,
            "ResponseMode": "streaming",
        }

        try:
            async with client.stream(
                "POST",
                f"{QingtianExpertConfig.BASE_URL}/chat_query_v2",
                json=chat_payload,
                headers=QingtianExpertConfig.headers(),
            ) as resp:
                if resp.status_code != 200:
                    err_body = await resp.aread()
                    err_text = err_body.decode("utf-8", errors="replace")[:500]
                    logger.error("chat_query_v2 错误: %s %s", resp.status_code, err_text)
                    yield f"data: {json.dumps({'error': f'API {resp.status_code}: {err_text[:200]}'})}\n\n"
                    return

                # 3. SSE 行解析
                # 擎天 SSE 一帧形如:
                #   event: message
                #   data: {"Type":"message","Answer":"...","ConversationID":"..."}
                #   <空行>
                buffer_data = []
                async for line in resp.aiter_lines():
                    if not line:
                        # 空行 = 一帧结束
                        if buffer_data:
                            yield _wrap_qingtian_chunk("\n".join(buffer_data), conv_id)
                            buffer_data = []
                        continue
                    if line.startswith("data:"):
                        buffer_data.append(line[5:].lstrip())
                    # event: / id: / 等行忽略

                # 末尾兜底
                if buffer_data:
                    yield _wrap_qingtian_chunk("\n".join(buffer_data), conv_id)

                # 收尾标记
                yield f"data: {json.dumps({'delta': '', 'done': True, 'conversation_id': conv_id})}\n\n"
        except httpx.ReadTimeout:
            logger.exception("chat_query_v2 ReadTimeout (擎天两帧 SSE 间隔超过 %ss)", QingtianExpertConfig.STREAM_READ_TIMEOUT)
            yield f"data: {json.dumps({'error': f'擎天响应超时(>{QingtianExpertConfig.STREAM_READ_TIMEOUT}s),请重试'}, ensure_ascii=False)}\n\n"
        except httpx.ConnectTimeout:
            logger.exception("chat_query_v2 ConnectTimeout")
            yield f"data: {json.dumps({'error': '连接擎天 API 超时,请检查网络'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("chat_query_v2 流式异常")
            err_repr = f"{type(e).__name__}: {str(e) or repr(e)}"
            yield f"data: {json.dumps({'error': f'流式异常: {err_repr[:300]}'}, ensure_ascii=False)}\n\n"


def _wrap_qingtian_chunk(data_str: str, conv_id: str) -> str:
    """
    把擎天一帧 data:<JSON> 转成前端约定的 `data: {"delta":...}\n\n`。

    擎天 HiAgent 实测协议(v1):
      data:{"event":"message_start","task_id":"...","conversation_id":"..."}
      data:{"event":"knowledge_retrieve","query":"...","dataset_ids":[...]}     ← KB 检索开始
      data:{"event":"knowledge_retrieve_end","docs":[...],"latency":12.3}       ← KB 检索结束
      data:{"event":"agent_thought","thought":"...","tool":"<工作流名>"}        ← 工作流调用
      data:{"event":"message","answer":"用户问题是","conversation_id":...}      ← ✅ token
      data:{"event":"message_output_end", ...}                                   ← 回答结束
      data:{"event":"message_cost", "input_tokens":N, ...}                       ← 用量统计

    转发策略:
      (1) event=message → {delta: token}（正常增量回答,前端拼到 content）
      (2) event=knowledge_retrieve → {tool_call: {tool:"知识库检索"}}
      (3) event=knowledge_retrieve_end → {tool_call_end: {...}}（前端给最后一个 KB chip 收尾）
      (4) event=agent_thought → {tool_call: {...}}（工作流 chip）
      (5) 其他事件 → 丢弃
    """
    if not data_str or data_str == "[DONE]":
        return ""
    try:
        obj = json.loads(data_str)
    except json.JSONDecodeError:
        return ""

    event_type = obj.get("event") or obj.get("Event") or ""
    real_conv = obj.get("conversation_id") or conv_id

    if event_type == "message":
        delta = obj.get("answer") or obj.get("Answer") or ""
        if not delta:
            return ""
        out = {"delta": delta, "conversation_id": real_conv}
        return f"data: {json.dumps(out, ensure_ascii=False)}\n\n"

    if event_type == "knowledge_retrieve":
        # 擎天 KB 检索开始:擎天没返回数据集名,前端就显示"知识库检索"
        query = obj.get("query") or ""
        out = {
            "tool_call": {
                "tool": "knowledge_retrieval",
                "thought": query,
                "input": "",
            },
            "conversation_id": real_conv,
        }
        return f"data: {json.dumps(out, ensure_ascii=False)}\n\n"

    if event_type == "knowledge_retrieve_end":
        # KB 检索结束:返回延迟,前端给最后一个 KB chip 收尾
        docs = obj.get("docs") or []
        latency = obj.get("latency") or 0
        out = {
            "tool_call_end": {
                "tool": "knowledge_retrieval",
                "doc_count": len(docs) if isinstance(docs, list) else 0,
                "latency": latency,
            },
            "conversation_id": real_conv,
        }
        return f"data: {json.dumps(out, ensure_ascii=False)}\n\n"

    if event_type == "agent_thought":
        tool_name = obj.get("tool") or obj.get("Tool") or ""
        thought = obj.get("thought") or obj.get("Thought") or ""
        tool_input = obj.get("tool_input") or obj.get("ToolInput") or ""
        if not (tool_name or thought):
            return ""
        out = {
            "tool_call": {
                "tool": tool_name,
                "thought": thought,
                "input": tool_input,
            },
            "conversation_id": real_conv,
        }
        return f"data: {json.dumps(out, ensure_ascii=False)}\n\n"

    return ""
