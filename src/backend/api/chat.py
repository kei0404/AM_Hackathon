"""
チャットAPIエンドポイント
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models.chat import ChatRequest, ChatResponse
from ..services.conversation_service import conversation_service
from ..services.sample_data import (
    clear_data_files,
    get_data_from_files,
    save_sample_data_to_files,
)
from ..services.vector_store import vector_store

logger = logging.getLogger(__name__)

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

    処理フロー:
    1. sample_data.py のデータ → data/user_data/*.json に保存
    2. 同時に data/chroma にベクトルDBとして登録
    """
    try:
        # VectorStoreを先に再初期化
        vector_store.reinitialize()
        logger.info("[Start] VectorStore再初期化完了")

        # sample_data.py の VISIT_RECORDS を data/user_data/*.json に保存
        saved_count = save_sample_data_to_files()
        logger.info(f"[Start] data/user_data に保存: {saved_count}件")

        # ファイルからデータを読み込み、ベクトル化してChromaDBに登録
        vector_data = get_data_from_files()
        logger.info(f"[Start] ベクトル化対象: {len(vector_data)}件")

        if vector_data:
            doc_ids = [d["id"] for d in vector_data]
            texts = [d["text"] for d in vector_data]
            metadatas = [d["metadata"] for d in vector_data]

            vector_store.add_documents(
                doc_ids=doc_ids,
                texts=texts,
                metadatas=metadatas,
            )

            count = vector_store.count()
            logger.info(f"[Start] ChromaDB登録完了: {count}件")
    except Exception as e:
        logger.error(f"[Start] データ初期化エラー: {e}", exc_info=True)

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
    - ベクトルDBのデータも削除
    - data/user_data 内のファイルも削除
    """
    # 会話キャッシュを削除
    success = conversation_service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    # ベクトルDBのデータを完全に削除（永続化ファイルも含む）
    try:
        vector_store.clear_all_data()
        logger.info(f"ベクトルDBのデータを完全消去: session_id={session_id}")
    except Exception as e:
        logger.error(f"ベクトルDBの消去に失敗: {e}")

    # data/user_data 内のファイルを削除
    try:
        deleted_count = clear_data_files()
        logger.info(f"データファイルを削除: {deleted_count}件")
    except Exception as e:
        logger.error(f"データファイルの削除に失敗: {e}")

    return SessionResponse(
        session_id=session_id,
        message="セッションを終了し、ベクトルDB・会話キャッシュ・データファイルを消去しました",
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


@router.get("/debug/vector-store", response_model=dict)
async def debug_vector_store() -> dict:
    """
    ベクトルストアのデバッグ情報を取得する
    """
    from pathlib import Path

    from ..config import settings

    persist_dir = Path(settings.CHROMA_PERSIST_DIR)

    return {
        "persist_dir": str(persist_dir),
        "persist_dir_exists": persist_dir.exists(),
        "persist_dir_contents": [str(p) for p in persist_dir.iterdir()] if persist_dir.exists() else [],
        "collection_name": settings.CHROMA_COLLECTION_NAME,
        "document_count": vector_store.count(),
        "collection_metadata": vector_store.collection.metadata if vector_store.collection else None,
    }
