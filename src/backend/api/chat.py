"""
チャットAPIエンドポイント
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models.chat import ChatRequest, ChatResponse
from ..services.conversation_service import conversation_service

router = APIRouter(prefix="/chat", tags=["chat"])


class WelcomeRequest(BaseModel):
    """ウェルカムメッセージリクエスト"""

    session_id: Optional[str] = None
    user_preferences: Optional[dict] = None
    favorite_spots: Optional[list[dict]] = None


class SessionResponse(BaseModel):
    """セッションレスポンス"""

    session_id: str
    message: str


@router.post("/start", response_model=ChatResponse)
async def start_conversation(request: WelcomeRequest) -> ChatResponse:
    """
    会話を開始してウェルカムメッセージを取得する

    - セッションIDが指定されていない場合は新規作成
    - ユーザーの嗜好やお気に入りを渡すことで、よりパーソナライズされた応答が可能
    """
    # ユーザー情報がある場合はセッションを作成
    if request.user_preferences or request.favorite_spots:
        session_id = conversation_service.create_session(
            user_preferences=request.user_preferences,
            favorite_spots=request.favorite_spots,
        )
    else:
        session_id = request.session_id

    return conversation_service.get_welcome_message(session_id)


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest) -> ChatResponse:
    """
    メッセージを送信してAIからの応答を取得する

    - 最大3回の質問で目的地を絞り込み
    - is_complete が True になったら目的地が決定
    - suggestions に選択肢が含まれる場合がある
    """
    try:
        return conversation_service.process_message(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"エラーが発生しました: {str(e)}")


@router.get("/session/{session_id}", response_model=dict)
async def get_session(session_id: str) -> dict:
    """
    セッション情報を取得する
    """
    context = conversation_service.get_session(session_id)
    if not context:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    return {
        "session_id": context.session_id,
        "turn_count": context.turn_count,
        "message_count": len(context.messages),
        "user_preferences": context.user_preferences,
        "favorite_spots_count": len(context.favorite_spots),
    }


@router.delete("/session/{session_id}", response_model=SessionResponse)
async def end_session(session_id: str) -> SessionResponse:
    """
    セッションを終了してデータを消去する

    - プライバシー・バイ・デザイン原則に基づき、セッションデータを完全に削除
    """
    success = conversation_service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    return SessionResponse(
        session_id=session_id,
        message="セッションを終了し、データを消去しました",
    )


@router.get("/session/{session_id}/ttl", response_model=dict)
async def get_session_ttl(session_id: str) -> dict:
    """
    セッションの残りTTL（秒）を取得する
    """
    ttl = conversation_service.get_session_ttl(session_id)
    if ttl is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    return {
        "session_id": session_id,
        "ttl_seconds": ttl,
        "message": f"残り有効期限: {ttl}秒",
    }


@router.post("/session/{session_id}/extend", response_model=dict)
async def extend_session_ttl(session_id: str) -> dict:
    """
    セッションのTTLを延長する
    """
    success = conversation_service.extend_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    ttl = conversation_service.get_session_ttl(session_id)
    return {
        "session_id": session_id,
        "ttl_seconds": ttl,
        "message": "セッションのTTLを延長しました",
    }


@router.get("/cache/stats", response_model=dict)
async def get_cache_stats() -> dict:
    """
    セッションキャッシュの統計情報を取得する
    """
    return conversation_service.get_cache_stats()


@router.post("/cache/cleanup", response_model=dict)
async def cleanup_expired_sessions() -> dict:
    """
    期限切れセッションを手動でクリーンアップする
    """
    cleaned = conversation_service.cleanup_expired_sessions()
    stats = conversation_service.get_cache_stats()
    return {
        "cleaned_sessions": cleaned,
        "message": f"{cleaned}件の期限切れセッションを削除しました",
        "current_stats": stats,
    }
