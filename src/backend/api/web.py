"""
Webページルーター - Jinja2テンプレートを使用したHTML配信
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..services.conversation_service import conversation_service

router = APIRouter(tags=["web"])

# テンプレート設定
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# サンプルデータ（デモ用）
SAMPLE_USER_PREFERENCES = {
    "genres": ["カフェ", "レストラン", "自然"],
    "atmosphere": "静か",
    "price_range": "中",
}

SAMPLE_FAVORITE_SPOTS = [
    {"name": "Blue Bottle Coffee 清澄白河", "category": "カフェ"},
    {"name": "代々木公園", "category": "公園"},
    {"name": "東京国立博物館", "category": "美術館"},
]


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """
    トップページ（データフロー可視化ダッシュボード）
    """
    # 新しいセッションを作成
    session_id = conversation_service.create_session(
        user_preferences=SAMPLE_USER_PREFERENCES,
        favorite_spots=SAMPLE_FAVORITE_SPOTS,
    )

    # ウェルカムメッセージを取得
    welcome = conversation_service.get_welcome_message(session_id)

    context = {
        "request": request,
        "session_id": session_id,
        "user_preferences": SAMPLE_USER_PREFERENCES,
        "favorite_spots": SAMPLE_FAVORITE_SPOTS,
        "welcome_message": welcome.message,
        "suggestions": welcome.suggestions,
        "turn_count": welcome.turn_count,
        "max_turns": 3,
        "is_complete": False,
        "api_logs": [],
        "conversation_history": [],
    }

    return templates.TemplateResponse("dashboard.html", context)


@router.get("/chat/{session_id}", response_class=HTMLResponse)
async def chat_page(request: Request, session_id: str) -> HTMLResponse:
    """
    チャットページ（特定のセッション）
    """
    session = conversation_service.get_session(session_id)

    if not session:
        # セッションが存在しない場合は新規作成
        session_id = conversation_service.create_session(
            user_preferences=SAMPLE_USER_PREFERENCES,
            favorite_spots=SAMPLE_FAVORITE_SPOTS,
        )
        session = conversation_service.get_session(session_id)

    # 会話履歴をフォーマット
    conversation_history = []
    for i, msg in enumerate(session.messages):
        conversation_history.append(
            {
                "role": msg.role.value,
                "content": msg.content,
                "timestamp": msg.timestamp.strftime("%H:%M:%S"),
            }
        )

    context = {
        "request": request,
        "session_id": session_id,
        "user_preferences": session.user_preferences or SAMPLE_USER_PREFERENCES,
        "favorite_spots": session.favorite_spots or SAMPLE_FAVORITE_SPOTS,
        "turn_count": session.turn_count,
        "max_turns": 3,
        "is_complete": session.turn_count >= 3,
        "conversation_history": conversation_history,
    }

    return templates.TemplateResponse("dashboard.html", context)
