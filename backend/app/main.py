"""FastAPI 主入口"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 在导入 settings 前加载 .env。
# 项目里实际有两份 .env 各管一摊:
#   - backend/.env  : 后端服务专属(QINGTIAN_* 擎天陪伴专家、其它 backend 私有 key)
#   - 项目根 /.env   : 公共配置(LLM_*、SEEDANCE_*,被 LLM/视频脚本共用)
# 之前只加载根 .env,导致 QINGTIAN_ENABLED 根本没进 os.environ,前端显示"专家暂时离线"。
# 顺序: 先 backend/.env 打底(override=False),再根 .env(override=True)允许根目录覆盖。
_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_BACKEND_ENV, override=False)
_PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_PROJECT_ENV, override=True)

from .core.config import settings
from .routers import agent, compliance, data, expert, report, system, video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.report_dir).mkdir(parents=True, exist_ok=True)
    logger.info("应用启动: %s", settings.app_name)
    # 演示兜底模式状态(演示现场用)
    try:
        from .services.fallback_player import is_offline_mode
        if is_offline_mode():
            logger.warning("⚠️  OFFLINE_MODE 已启用,所有 Agent 编排走 _fallback 回放,不调外网 LLM")
        else:
            logger.info("OFFLINE_MODE 未启用,Agent 编排走真实 LLM(开发/调试模式)")
    except Exception as e:
        logger.warning("演示兜底状态探查失败: %s", e)

    # 视频任务状态扫盘恢复(VIDEO_TASKS 是内存字典,重启后从 _task.json 读回)
    try:
        from .routers.video import _restore_video_tasks_from_disk
        _restore_video_tasks_from_disk()
    except Exception as e:
        logger.warning("视频任务恢复失败: %s", e)
    # 启动时打印视频后端选择,方便确认 .env 是否生效
    try:
        from .core.config import seedance_settings
        logger.info(
            "视频后端: VIDEO_BACKEND=%s, SEEDANCE_API_KEY=%s, model=%s",
            seedance_settings.video_backend,
            "set" if seedance_settings.api_key else "MISSING",
            seedance_settings.model,
        )
    except Exception as e:
        logger.warning("视频后端配置探查失败: %s", e)
    yield
    logger.info("应用关闭")


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent.router, prefix="/api")
app.include_router(compliance.router, prefix="/api")
app.include_router(data.router, prefix="/api")
app.include_router(expert.router, prefix="/api")
app.include_router(report.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(video.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"code": 0, "msg": "ok", "data": {"status": "running", "app": settings.app_name}}
