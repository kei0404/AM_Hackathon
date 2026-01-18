"""
WebSocketエンドポイント - 音声ストリーミング入力
"""

import base64
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
    # セッションの確認 - 存在しない場合は自動生成
    original_session_id = session_id
    context = conversation_service.get_session(session_id)
    if not context:
        # ユーザーデータを初期化（VectorStore、サンプルデータ）
        data_count = conversation_service.initialize_user_data()
        logger.info(f"ユーザーデータを初期化: {data_count}件")

        # セッションが存在しない場合、自動的に作成
        session_id = conversation_service.create_session()
        context = conversation_service.get_session(session_id)
        logger.info(f"新しいセッションを自動生成: {session_id}")

    # WebSocket接続を確立（新しいセッションIDで）
    await manager.connect(websocket, session_id)

    # 古いセッションIDで接続が登録されていた場合は削除
    if original_session_id != session_id and original_session_id in manager.active_connections:
        del manager.active_connections[original_session_id]

    await websocket.send_json({
        "type": "connected",
        "message": "WebSocket接続が確立されました",
        "session_id": session_id,
    })

    asr_client = None

    # メインイベントループを取得（スレッドセーフな呼び出しに使用）
    import asyncio
    main_loop = asyncio.get_running_loop()

    async def process_transcription(text: str) -> None:
        """認識されたテキストをチャット処理"""
        try:
            logger.info(f"チャット処理開始: {text}")
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
                "suggestion_index": response.suggestion_index,
                "suggestion_total": response.suggestion_total,
                "destination": response.destination.model_dump() if response.destination else None,
                "stopover": response.stopover.model_dump() if response.stopover else None,
                "has_audio": response.has_audio,
            })

            # 音声データがあればバイナリで送信
            if response.has_audio and response.audio_data:
                audio_bytes = base64.b64decode(response.audio_data)
                await manager.send_bytes(session_id, audio_bytes)
                logger.info(f"音声データを送信: {len(audio_bytes)} bytes, is_complete={response.is_complete}")
            else:
                logger.warning(f"音声データなし: has_audio={response.has_audio}, audio_data_exists={response.audio_data is not None}")

            logger.info(f"チャット処理完了: turn_count={response.turn_count}, is_complete={response.is_complete}")

        except Exception as e:
            logger.error(f"チャット処理エラー: {e}")
            await manager.send_json(session_id, {
                "type": "error",
                "message": f"処理エラー: {str(e)}",
            })

    async def send_transcription_async(text: str, is_final: bool) -> None:
        """文字起こし結果を送信"""
        try:
            logger.info(f"文字起こし送信: text={text}, is_final={is_final}")
            await manager.send_json(session_id, {
                "type": "transcription",
                "text": text,
                "is_final": is_final,
            })
            # 最終結果の場合、チャット処理を実行
            if is_final and text.strip():
                await process_transcription(text)
        except Exception as e:
            logger.error(f"文字起こし送信エラー: {e}")

    def on_transcription(text: str, is_final: bool) -> None:
        """ASR認識結果コールバック（別スレッドから呼ばれる）"""
        logger.info(f"on_transcription コールバック: text={text}, is_final={is_final}")
        # メインイベントループにコルーチンをスケジュール
        future = asyncio.run_coroutine_threadsafe(
            send_transcription_async(text, is_final),
            main_loop
        )
        # 結果を待機（タイムアウト10秒）
        try:
            future.result(timeout=10)
        except Exception as e:
            logger.error(f"on_transcription実行エラー: {e}")

    async def send_asr_error_async(error: str) -> None:
        """ASRエラーを送信"""
        await manager.send_json(session_id, {
            "type": "asr_error",
            "message": error,
        })

    def on_asr_error(error: str) -> None:
        """ASRエラーコールバック（別スレッドから呼ばれる）"""
        logger.error(f"on_asr_error コールバック: {error}")
        future = asyncio.run_coroutine_threadsafe(
            send_asr_error_async(error),
            main_loop
        )
        try:
            future.result(timeout=10)
        except Exception as e:
            logger.error(f"on_asr_error実行エラー: {e}")

    async def send_asr_connected_async() -> None:
        """ASR接続完了を送信"""
        await manager.send_json(session_id, {
            "type": "asr_connected",
            "message": "音声認識が開始されました",
        })

    def on_asr_connected() -> None:
        """ASR接続完了コールバック（別スレッドから呼ばれる）"""
        logger.info("on_asr_connected コールバック")
        future = asyncio.run_coroutine_threadsafe(
            send_asr_connected_async(),
            main_loop
        )
        try:
            future.result(timeout=10)
        except Exception as e:
            logger.error(f"on_asr_connected実行エラー: {e}")

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
    # セッションの確認 - 存在しない場合は自動生成
    original_session_id = session_id
    context = conversation_service.get_session(session_id)
    if not context:
        # ユーザーデータを初期化（VectorStore、サンプルデータ）
        data_count = conversation_service.initialize_user_data()
        logger.info(f"ユーザーデータを初期化: {data_count}件")

        # セッションが存在しない場合、自動的に作成
        session_id = conversation_service.create_session()
        context = conversation_service.get_session(session_id)
        logger.info(f"新しいセッションを自動生成: {session_id}")

    # WebSocket接続を確立（新しいセッションIDで）
    await manager.connect(websocket, session_id)

    # 古いセッションIDで接続が登録されていた場合は削除
    if original_session_id != session_id and original_session_id in manager.active_connections:
        del manager.active_connections[original_session_id]

    await websocket.send_json({
        "type": "connected",
        "message": "チャットセッションが開始されました",
        "session_id": session_id,
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
                            "suggestion_index": response.suggestion_index,
                            "suggestion_total": response.suggestion_total,
                            "destination": response.destination.model_dump() if response.destination else None,
                            "stopover": response.stopover.model_dump() if response.stopover else None,
                            "has_audio": response.has_audio,
                        })

                        # 音声データがあればバイナリで送信
                        if response.has_audio and response.audio_data:
                            audio_bytes = base64.b64decode(response.audio_data)
                            await websocket.send_bytes(audio_bytes)
                            logger.info(f"音声データを送信: {len(audio_bytes)} bytes, is_complete={response.is_complete}")
                        else:
                            logger.warning(f"音声データなし: has_audio={response.has_audio}")

                        logger.info(f"チャット処理完了: turn_count={response.turn_count}, is_complete={response.is_complete}")

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
