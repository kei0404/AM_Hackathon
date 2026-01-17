"""
WebSocketエンドポイント - 音声ストリーミング入力
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..models.chat import ChatRequest
from ..services.conversation_service import conversation_service
from ..services.speech_service import speech_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """WebSocket接続管理"""

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """WebSocket接続を確立"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket接続: {session_id}")

    def disconnect(self, session_id: str) -> None:
        """WebSocket接続を終了"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket切断: {session_id}")

    async def send_json(self, session_id: str, data: dict) -> None:
        """JSONデータを送信"""
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(data)

    async def send_text(self, session_id: str, text: str) -> None:
        """テキストを送信"""
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_text(text)

    async def send_bytes(self, session_id: str, data: bytes) -> None:
        """バイナリデータを送信"""
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_bytes(data)

    def get_websocket(self, session_id: str) -> Optional[WebSocket]:
        """WebSocketを取得"""
        return self.active_connections.get(session_id)


manager = ConnectionManager()


@router.websocket("/ws/voice/{session_id}")
async def websocket_voice_endpoint(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    音声ストリーミング入力エンドポイント

    処理フロー:
    1. WebSocket接続を確立
    2. クライアントから音声データ（バイナリ）を受信
    3. Qwen ASRで音声認識を実行
    4. 認識結果をテキストメッセージとして処理
    5. LLMで応答を生成
    6. 応答をクライアントに返送

    メッセージ形式:
    - 受信（バイナリ）: PCM音声データ (16kHz, 16bit, モノラル)
    - 受信（テキスト）: JSON形式のコマンド
        - {"type": "start_asr"}: ASR開始
        - {"type": "stop_asr"}: ASR停止
        - {"type": "text", "text": "..."}: テキスト入力
    - 送信（テキスト）: JSON形式のレスポンス
        - {"type": "transcription", "text": "...", "is_final": bool}
        - {"type": "response", "message": "...", "suggestions": [...]}
        - {"type": "error", "message": "..."}
    """
    await manager.connect(websocket, session_id)

    # セッションの確認
    context = conversation_service.get_session(session_id)
    if not context:
        await websocket.send_json({
            "type": "error",
            "message": "セッションが見つかりません。先にセッションを開始してください。",
        })
        await websocket.close()
        return

    await websocket.send_json({
        "type": "connected",
        "message": "WebSocket接続が確立されました",
        "session_id": session_id,
    })

    asr_client = None

    async def process_transcription(text: str) -> None:
        """認識されたテキストをチャット処理"""
        try:
            request = ChatRequest(
                message=text,
                session_id=session_id,
                response_type="voice",
            )
            response = conversation_service.process_message(request)

            await manager.send_json(session_id, {
                "type": "response",
                "message": response.message,
                "session_id": response.session_id,
                "turn_count": response.turn_count,
                "is_complete": response.is_complete,
                "suggestions": response.suggestions,
            })

        except Exception as e:
            logger.error(f"チャット処理エラー: {e}")
            await manager.send_json(session_id, {
                "type": "error",
                "message": f"処理エラー: {str(e)}",
            })

    def on_transcription(text: str, is_final: bool) -> None:
        """ASR認識結果コールバック"""
        import asyncio

        async def send_transcription():
            await manager.send_json(session_id, {
                "type": "transcription",
                "text": text,
                "is_final": is_final,
            })
            # 最終結果の場合、チャット処理を実行
            if is_final and text.strip():
                await process_transcription(text)

        # 非同期関数を実行
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(send_transcription())
            else:
                loop.run_until_complete(send_transcription())
        except Exception as e:
            logger.error(f"transcription送信エラー: {e}")

    def on_asr_error(error: str) -> None:
        """ASRエラーコールバック"""
        import asyncio

        async def send_error():
            await manager.send_json(session_id, {
                "type": "asr_error",
                "message": error,
            })

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(send_error())
            else:
                loop.run_until_complete(send_error())
        except Exception as e:
            logger.error(f"エラー送信エラー: {e}")

    def on_asr_connected() -> None:
        """ASR接続完了コールバック"""
        import asyncio

        async def send_connected():
            await manager.send_json(session_id, {
                "type": "asr_connected",
                "message": "音声認識が開始されました",
            })

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(send_connected())
            else:
                loop.run_until_complete(send_connected())
        except Exception as e:
            logger.error(f"connected送信エラー: {e}")

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                # バイナリデータ（音声）
                audio_data = message["bytes"]
                if asr_client and asr_client.is_connected:
                    asr_client.send_audio(audio_data)
                else:
                    logger.warning("ASR未接続: 音声データを破棄")

            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                    cmd_type = data.get("type", "")

                    if cmd_type == "start_asr":
                        # ASR開始
                        if asr_client is None:
                            try:
                                asr_client = speech_service.create_asr_session(
                                    session_id=session_id,
                                    on_transcription=on_transcription,
                                    on_error=on_asr_error,
                                    on_connected=on_asr_connected,
                                )
                            except Exception as e:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": f"ASR開始エラー: {str(e)}",
                                })
                        else:
                            await websocket.send_json({
                                "type": "info",
                                "message": "ASRは既に開始されています",
                            })

                    elif cmd_type == "stop_asr":
                        # ASR停止
                        if asr_client:
                            speech_service.close_asr_session(session_id)
                            asr_client = None
                            await websocket.send_json({
                                "type": "asr_stopped",
                                "message": "音声認識が停止されました",
                            })

                    elif cmd_type == "text":
                        # テキストメッセージとして処理
                        text = data.get("text", "")
                        if text:
                            await process_transcription(text)

                    elif cmd_type == "ping":
                        await websocket.send_json({"type": "pong"})

                except json.JSONDecodeError:
                    logger.warning(f"無効なJSONメッセージ: {message['text']}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket切断: {session_id}")

    except Exception as e:
        logger.error(f"WebSocketエラー: {e}")

    finally:
        manager.disconnect(session_id)
        if asr_client:
            speech_service.close_asr_session(session_id)


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    テキストチャット用WebSocketエンドポイント
    """
    await manager.connect(websocket, session_id)

    context = conversation_service.get_session(session_id)
    if not context:
        await websocket.send_json({
            "type": "error",
            "message": "セッションが見つかりません",
        })
        await websocket.close()
        return

    await websocket.send_json({
        "type": "connected",
        "message": "チャットセッションが開始されました",
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "message":
                text = data.get("text", "")
                if text:
                    try:
                        request = ChatRequest(
                            message=text,
                            session_id=session_id,
                            response_type="text",
                        )
                        response = conversation_service.process_message(request)

                        await websocket.send_json({
                            "type": "response",
                            "message": response.message,
                            "session_id": response.session_id,
                            "turn_count": response.turn_count,
                            "is_complete": response.is_complete,
                            "suggestions": response.suggestions,
                        })

                    except Exception as e:
                        logger.error(f"チャット処理エラー: {e}")
                        await websocket.send_json({
                            "type": "error",
                            "message": str(e),
                        })

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket切断: {session_id}")

    except Exception as e:
        logger.error(f"WebSocketエラー: {e}")

    finally:
        manager.disconnect(session_id)
