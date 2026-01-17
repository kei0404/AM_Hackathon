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
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Embedding モデル設定
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("embedding_model", "text-embedding-v4")

    # ChromaDB 設定
    CHROMA_PERSIST_DIR: str = str(project_root / "data" / "chroma")
    CHROMA_COLLECTION_NAME: str = "user_data"

    # 会話設定
    MAX_CONVERSATION_TURNS: int = 3
    MAX_TOKENS: int = 1024
    TEMPERATURE: float = 0.7

    @classmethod
    def validate(cls) -> None:
        """設定の検証"""
        if not cls.DASHSCOPE_API_KEY:
            raise ValueError("DASHSCOPE_API_KEY が設定されていません")


settings = Settings()
