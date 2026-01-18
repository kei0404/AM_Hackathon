"""
Data Plug Copilot - FastAPI メインアプリケーション
"""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api.chat import router as chat_router
from .api.vector import router as vector_router
from .api.web import router as web_router
from .api.websocket import router as websocket_router

# ロギング設定
import logging.handlers
from pathlib import Path

# ログディレクトリを作成
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"

# ファイルハンドラーとコンソールハンドラーを設定
file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding="utf-8",
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

# ルートロガーに設定
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.info(f"ログファイル: {LOG_FILE}")

# パス設定
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# FastAPIアプリケーション
app = FastAPI(
    title="Data Plug Copilot API",
    description="""
## Data Plug Copilot API

パーソナルデータ駆動型カーパーソナライゼーションアプリのバックエンドAPI

### 主な機能

- **目的地推薦**: 最大3回の質問で目的地を絞り込み
- **会話管理**: セッションベースの会話履歴管理
- **ベクトル検索**: ChromaDBによる類似度検索
- **プライバシー保護**: セッション終了時のデータ自動消去
- **音声入力**: WebSocket経由のリアルタイム音声認識（Qwen ASR）
- **モバイル対応**: React Nativeアプリからの位置情報連携

### プライバシー・バイ・デザイン

- ユーザーデータはセッション中のみ保持
- セッション終了時に全データを消去
- 外部サーバーへのデータ送信なし（LLM API呼び出しを除く）

### WebSocketエンドポイント

- `/ws/voice/{session_id}`: 音声ストリーミング入力
- `/ws/chat/{session_id}`: テキストチャット（リアルタイム）
    """,
    version="0.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では適切に制限
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# テンプレートとスタティックファイルの設定
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# スタティックファイルのマウント（ディレクトリが存在する場合のみ）
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ルーター登録
app.include_router(chat_router, prefix="/api/v1")
app.include_router(vector_router)
app.include_router(web_router)
app.include_router(websocket_router, prefix="/api/v1")  # WebSocket音声/チャット


@app.get("/health")
async def health_check() -> dict:
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_event() -> None:
    """アプリケーション起動時の処理"""
    logger.info("Data Plug Copilot API を起動しました")
    logger.info(f"Templates directory: {TEMPLATES_DIR}")
    logger.info(f"Static directory: {STATIC_DIR}")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """アプリケーション終了時の処理"""
    logger.info("Data Plug Copilot API を終了します")
