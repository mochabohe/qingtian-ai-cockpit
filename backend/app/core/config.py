"""应用配置（从环境变量加载）"""
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "dongfeng-ai-contest"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    data_dir: str = "./data"
    report_dir: str = "./data/reports"


settings = Settings()


# =================================================================
# 视频文生模型(Seedance / 火山方舟) - 独立读取,SEEDANCE_ 前缀
# 不挂 APP_ 前缀,保持与 LLM_ 同级、便于 .env 维护。
# =================================================================
import os

class SeedanceSettings:
    """运行期读环境变量(允许热改 .env 后重启即生效)"""
    @property
    def base_url(self) -> str:
        return os.getenv("SEEDANCE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")

    @property
    def api_key(self) -> str:
        return os.getenv("SEEDANCE_API_KEY", "").strip()

    @property
    def model(self) -> str:
        # 默认 1.5 Pro;可切 doubao-seedance-2-0-260128
        return os.getenv("SEEDANCE_MODEL", "doubao-seedance-1-5-pro-251215").strip()

    @property
    def resolution(self) -> str:
        # 720p 性价比高,1080p 画质明显更好但贵 2-3 倍
        return os.getenv("SEEDANCE_RESOLUTION", "1080p").strip()

    @property
    def duration_s(self) -> int:
        try:
            return max(3, min(int(os.getenv("SEEDANCE_DURATION_S", "10")), 12))
        except ValueError:
            return 10

    @property
    def poll_interval_s(self) -> float:
        try:
            return float(os.getenv("SEEDANCE_POLL_INTERVAL_S", "8"))
        except ValueError:
            return 8.0

    @property
    def poll_timeout_s(self) -> float:
        # 单分镜最长等待
        try:
            return float(os.getenv("SEEDANCE_POLL_TIMEOUT_S", "600"))
        except ValueError:
            return 600.0

    @property
    def enabled(self) -> bool:
        # 由 video backend 选择 + key 是否填写共同决定
        return bool(self.api_key) and self.video_backend == "seedance"

    @property
    def video_backend(self) -> str:
        # local_stub / seedance
        return os.getenv("VIDEO_BACKEND", "local_stub").strip().lower()


seedance_settings = SeedanceSettings()
