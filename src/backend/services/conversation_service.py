"""
会話サービス - セッション管理と会話フローの制御
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from ..models.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationContext,
    MessageRole,
)
from .llm_service import llm_service

logger = logging.getLogger(__name__)


class ConversationService:
    """会話管理サービス"""

    def __init__(self) -> None:
        """会話サービスの初期化"""
        # インメモリのセッションストレージ（本番ではRedis等を使用）
        self._sessions: dict[str, ConversationContext] = {}

    def create_session(
        self,
        user_preferences: Optional[dict] = None,
        favorite_spots: Optional[list[dict]] = None,
        visit_history: Optional[list[dict]] = None,
    ) -> str:
        """
        新しい会話セッションを作成する

        Args:
            user_preferences: ユーザーの嗜好設定
            favorite_spots: お気に入りスポットのリスト
            visit_history: 訪問履歴

        Returns:
            セッションID
        """
        session_id = str(uuid.uuid4())
        context = ConversationContext(
            session_id=session_id,
            messages=[],
            turn_count=0,
            user_preferences=user_preferences,
            favorite_spots=favorite_spots or [],
            visit_history=visit_history or [],
        )
        self._sessions[session_id] = context
        logger.info(f"新しいセッションを作成: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[ConversationContext]:
        """セッションを取得する"""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """セッションを削除する"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"セッションを削除: {session_id}")
            return True
        return False

    def process_message(self, request: ChatRequest) -> ChatResponse:
        """
        ユーザーメッセージを処理してレスポンスを生成する

        Args:
            request: チャットリクエスト

        Returns:
            チャットレスポンス
        """
        # セッションの取得または作成
        session_id = request.session_id
        if not session_id or session_id not in self._sessions:
            session_id = self.create_session(
                user_preferences=request.context.get("preferences")
                if request.context
                else None,
                favorite_spots=request.context.get("favorite_spots")
                if request.context
                else None,
            )

        context = self._sessions[session_id]

        # ユーザーメッセージを履歴に追加
        user_message = ChatMessage(
            role=MessageRole.USER,
            content=request.message,
            timestamp=datetime.now(),
        )
        context.messages.append(user_message)

        # LLMで応答を生成
        llm_result = llm_service.generate_destination_question(
            user_message=request.message,
            turn_count=context.turn_count,
            user_preferences=context.user_preferences,
            favorite_spots=context.favorite_spots,
        )

        # AIメッセージを履歴に追加
        ai_message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=llm_result["message"],
            timestamp=datetime.now(),
        )
        context.messages.append(ai_message)

        # ターンカウントを更新
        context.turn_count = llm_result["turn_count"]

        # セッションを更新
        self._sessions[session_id] = context

        return ChatResponse(
            message=llm_result["message"],
            session_id=session_id,
            turn_count=llm_result["turn_count"],
            is_complete=llm_result["is_complete"],
            suggestions=llm_result["suggestions"],
        )

    def get_welcome_message(self, session_id: Optional[str] = None) -> ChatResponse:
        """
        ウェルカムメッセージを取得する

        Args:
            session_id: 既存のセッションID（オプション）

        Returns:
            ウェルカムメッセージを含むチャットレスポンス
        """
        if not session_id:
            session_id = self.create_session()

        welcome_message = (
            "こんにちは！Data Plug Copilotです。\n"
            "今日はどこに行きたいですか？\n"
            "あなたのお気に入りや訪問履歴を参考に、最適な場所をご提案します。"
        )

        context = self._sessions[session_id]
        ai_message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=welcome_message,
            timestamp=datetime.now(),
        )
        context.messages.append(ai_message)

        return ChatResponse(
            message=welcome_message,
            session_id=session_id,
            turn_count=0,
            is_complete=False,
            suggestions=["カフェに行きたい", "自然を楽しみたい", "新しい場所を探したい"],
        )


# シングルトンインスタンス
conversation_service = ConversationService()
