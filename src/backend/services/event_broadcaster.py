"""
イベントブロードキャスター - ダッシュボードへのリアルタイムイベント配信
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """
    イベントブロードキャスター

    セッションイベントをダッシュボードにリアルタイムで配信
    """

    def __init__(self) -> None:
        # ダッシュボード監視用のWebSocket接続
        self.dashboard_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def register_dashboard(self, websocket: WebSocket) -> None:
        """ダッシュボードを登録"""
        async with self._lock:
            self.dashboard_connections.append(websocket)
            logger.info(f"ダッシュボード登録: 合計{len(self.dashboard_connections)}接続")

    async def unregister_dashboard(self, websocket: WebSocket) -> None:
        """ダッシュボードを登録解除"""
        async with self._lock:
            if websocket in self.dashboard_connections:
                self.dashboard_connections.remove(websocket)
                logger.info(f"ダッシュボード解除: 合計{len(self.dashboard_connections)}接続")

    async def broadcast_event(
        self,
        event_type: str,
        session_id: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        イベントをすべてのダッシュボードにブロードキャスト

        Args:
            event_type: イベントタイプ（session_start, session_end, user_message, ai_response など）
            session_id: セッションID
            data: イベントデータ
        """
        event = {
            "type": "dashboard_event",
            "event_type": event_type,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        }

        logger.info(f"イベントブロードキャスト: {event_type}, session={session_id}")

        # 切断された接続を追跡
        disconnected = []

        async with self._lock:
            for ws in self.dashboard_connections:
                try:
                    await ws.send_json(event)
                except Exception as e:
                    logger.warning(f"ダッシュボード送信エラー: {e}")
                    disconnected.append(ws)

            # 切断された接続を削除
            for ws in disconnected:
                if ws in self.dashboard_connections:
                    self.dashboard_connections.remove(ws)

    async def broadcast_session_start(
        self,
        session_id: str,
        welcome_message: str,
        location: Optional[dict] = None,
    ) -> None:
        """セッション開始イベント"""
        await self.broadcast_event(
            "session_start",
            session_id,
            {
                "welcome_message": welcome_message,
                "location": location,
            },
        )

    async def broadcast_session_end(self, session_id: str) -> None:
        """セッション終了イベント"""
        await self.broadcast_event("session_end", session_id)

    async def broadcast_user_message(
        self,
        session_id: str,
        message: str,
        source: str = "text",  # text, voice
    ) -> None:
        """ユーザーメッセージイベント"""
        await self.broadcast_event(
            "user_message",
            session_id,
            {
                "message": message,
                "source": source,
            },
        )

    async def broadcast_ai_response(
        self,
        session_id: str,
        message: str,
        turn_count: int,
        is_complete: bool,
        suggestions: list[str],
        destination: Optional[dict] = None,
        stopover: Optional[dict] = None,
    ) -> None:
        """AI応答イベント"""
        await self.broadcast_event(
            "ai_response",
            session_id,
            {
                "message": message,
                "turn_count": turn_count,
                "is_complete": is_complete,
                "suggestions": suggestions,
                "destination": destination,
                "stopover": stopover,
            },
        )

    async def broadcast_transcription(
        self,
        session_id: str,
        text: str,
        is_final: bool,
    ) -> None:
        """音声認識結果イベント"""
        await self.broadcast_event(
            "transcription",
            session_id,
            {
                "text": text,
                "is_final": is_final,
            },
        )

    async def broadcast_asr_status(
        self,
        session_id: str,
        status: str,  # starting, connected, stopped, error
        message: Optional[str] = None,
    ) -> None:
        """ASRステータスイベント"""
        await self.broadcast_event(
            "asr_status",
            session_id,
            {
                "status": status,
                "message": message,
            },
        )


# シングルトンインスタンス
event_broadcaster = EventBroadcaster()
