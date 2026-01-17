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
from ..services.sample_data import get_user_data_summary

router = APIRouter(tags=["web"])

# テンプレート設定
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """
    トップページ（データフロー可視化ダッシュボード）
    """
    # 新しいセッションを作成
    session_id = conversation_service.create_session()

    # ウェルカムメッセージを取得
    welcome = conversation_service.get_welcome_message(session_id)

    # data/user_data のデータを取得
    user_data = get_user_data_summary()

    context = {
        "request": request,
        "session_id": session_id,
        "user_data": user_data,
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
        session_id = conversation_service.create_session()
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

    # data/user_data のデータを取得
    user_data = get_user_data_summary()

    context = {
        "request": request,
        "session_id": session_id,
        "user_data": user_data,
        "turn_count": session.turn_count,
        "max_turns": 3,
        "is_complete": session.turn_count >= 3,
        "conversation_history": conversation_history,
    }

    return templates.TemplateResponse("dashboard.html", context)
