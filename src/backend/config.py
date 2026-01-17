"""
設定モジュール - 環境変数からの設定読み込み
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# プロジェクトルートの.envファイルを読み込み
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)


class Settings:
    """アプリケーション設定"""

    # DashScope (Qwen) API設定
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")

    # Qwen モデル設定
    QWEN_MODEL: str = "qwen-plus"
    QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # DashScope API ベースURL（国際版対応）
    DASHSCOPE_BASE_URL: str = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/api/v1")

    # Embedding モデル設定
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("embedding_model", "text-embedding-v4")

    # Audio (ASR) 設定
    AUDIO_API_KEY: str = os.getenv("AUDIO_API_KEY", "")
    AUDIO_MODEL: str = os.getenv("audio_model", "qwen3-asr-flash-realtime")
    AUDIO_BASE_URL: str = os.getenv(
        "audio_baseurl", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    )
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_FORMAT: str = "pcm"
    AUDIO_LANGUAGE: str = "ja"  # 日本語

    # TTS (Text-to-Speech) 設定
    TTS_API_KEY: str = os.getenv("TTS_API_KEY", "")
    TTS_MODEL: str = os.getenv("tts_model", "qwen3-tts-flash-2025-11-27")
    TTS_VOICE: str = os.getenv("voice", "Cherry")
    TTS_SPEED: float = float(os.getenv("TTS_SPEED", "1.0"))

    # ChromaDB 設定
    CHROMA_PERSIST_DIR: str = str(project_root / "data" / "chroma")
    CHROMA_COLLECTION_NAME: str = "user_data"

    # 会話設定
    MAX_CONVERSATION_TURNS: int = 3
    MAX_TOKENS: int = 1024
    TEMPERATURE: float = 0.7

    # セッションキャッシュ設定（TTL）
    SESSION_TTL_SECONDS: int = int(os.getenv("SESSION_TTL_SECONDS", "1800"))  # 30分
    SESSION_CLEANUP_INTERVAL: int = int(
        os.getenv("SESSION_CLEANUP_INTERVAL", "300")
    )  # 5分
    MAX_SESSIONS: int = int(os.getenv("MAX_SESSIONS", "1000"))  # 最大セッション数

    @classmethod
    def validate(cls) -> None:
        """設定の検証"""
        if not cls.DASHSCOPE_API_KEY:
            raise ValueError("DASHSCOPE_API_KEY が設定されていません")


settings = Settings()
