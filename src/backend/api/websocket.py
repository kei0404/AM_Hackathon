"""
WebSocketエンドポイント - 音声ストリーミング入力
"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..models.chat import ChatRequest
from ..services.conversation_service import conversation_service
from ..services.event_broadcaster import event_broadcaster
from ..services.location_service import location_service
from ..services.speech_service import speech_service

logger = logging.getLogger(__name__)

# タイムアウト設定（秒）
USER_RESPONSE_TIMEOUT = 180  # 180秒 = 3分

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


@router.websocket("/ws/voice")
async def websocket_voice_endpoint_auto(
    websocket: WebSocket,
) -> None:
    """セッションIDなしで接続（自動生成）"""
    await websocket_voice_endpoint(websocket, session_id=None)


@router.websocket("/ws/voice/{session_id}")
async def websocket_voice_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = None,
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
    context = None
    if session_id:
        context = conversation_service.get_session(session_id)

    if not context:
        # ユーザーデータを初期化（VectorStore、サンプルデータ）
        data_count = conversation_service.initialize_user_data()
        logger.info(f"ユーザーデータを初期化: {data_count}件")

    # WebSocket接続を確立
    await websocket.accept()

    # サーバー側の現在位置を取得
    server_location = location_service.get_current_location()
    location_data = None
    if server_location:
        location_data = {
            "latitude": server_location.latitude,
            "longitude": server_location.longitude,
            "address": server_location.address,
            "source": server_location.source,
        }
        logger.info(f"サーバー位置情報: {server_location.latitude}, {server_location.longitude} ({server_location.source})")

    # セッション開始 - ウェルカムメッセージを取得（セッションも自動作成される）
    welcome_response = conversation_service.get_welcome_message(session_id)
    session_id = welcome_response.session_id
    logger.info(f"セッション開始: {session_id}")

    # 接続管理に登録
    manager.active_connections[session_id] = websocket

    # 古いセッションIDで接続が登録されていた場合は削除
    if original_session_id and original_session_id != session_id and original_session_id in manager.active_connections:
        del manager.active_connections[original_session_id]

    # 接続確立とウェルカムメッセージを送信
    await websocket.send_json({
        "type": "session_start",
        "message": welcome_response.message,
        "session_id": session_id,
        "has_audio": welcome_response.has_audio,
        "location": location_data,
    })

    # ダッシュボードにセッション開始をブロードキャスト
    await event_broadcaster.broadcast_session_start(
        session_id=session_id,
        welcome_message=welcome_response.message,
        location=location_data,
    )

    # ウェルカムメッセージの音声データがあれば送信
    if welcome_response.has_audio and welcome_response.audio_data:
        audio_bytes = base64.b64decode(welcome_response.audio_data)
        await websocket.send_bytes(audio_bytes)
        logger.info(f"ウェルカム音声を送信: {len(audio_bytes)} bytes")

    asr_client = None

    # メインイベントループを取得（スレッドセーフな呼び出しに使用）
    main_loop = asyncio.get_running_loop()

    # タイムアウト管理用の変数
    last_response_time = datetime.now()
    last_response_message = welcome_response.message
    timeout_task: Optional[asyncio.Task] = None

    async def generate_timeout_response() -> None:
        """タイムアウト時にLLMで応答を再生成"""
        nonlocal last_response_time, last_response_message
        try:
            logger.info(f"タイムアウト: LLMで応答を再生成します（session={session_id}）")

            # LLMでタイムアウト応答を生成（ベクトルデータと会話キャッシュを使用）
            response = conversation_service.generate_timeout_response(session_id)

            if response:
                # 応答を送信
                await manager.send_json(session_id, {
                    "type": "timeout_response",
                    "message": response.message,
                    "session_id": response.session_id,
                    "turn_count": response.turn_count,
                    "is_complete": response.is_complete,
                    "suggestions": response.suggestions,
                    "suggestion_index": response.suggestion_index,
                    "suggestion_total": response.suggestion_total,
                    "has_audio": response.has_audio,
                })

                # ダッシュボードにタイムアウト応答をブロードキャスト
                await event_broadcaster.broadcast_event(
                    "timeout_response",
                    session_id,
                    {
                        "message": response.message,
                        "suggestions": response.suggestions,
                    },
                )

                # 音声データがあれば送信
                if response.has_audio and response.audio_data:
                    audio_bytes = base64.b64decode(response.audio_data)
                    await manager.send_bytes(session_id, audio_bytes)
                    logger.info(f"タイムアウト応答音声を送信: {len(audio_bytes)} bytes")

                # タイムアウト時刻とメッセージを更新
                last_response_time = datetime.now()
                last_response_message = response.message
            else:
                logger.warning(f"タイムアウト応答生成失敗: セッションが見つかりません")

        except Exception as e:
            logger.error(f"タイムアウト応答生成エラー: {e}")

    async def timeout_monitor() -> None:
        """タイムアウト監視タスク"""
        nonlocal last_response_time
        while True:
            try:
                await asyncio.sleep(10)  # 10秒ごとにチェック
                elapsed = (datetime.now() - last_response_time).total_seconds()
                if elapsed >= USER_RESPONSE_TIMEOUT:
                    # LLMでタイムアウト応答を再生成
                    await generate_timeout_response()
            except asyncio.CancelledError:
                logger.info("タイムアウト監視タスクがキャンセルされました")
                break
            except Exception as e:
                logger.error(f"タイムアウト監視エラー: {e}")

    # タイムアウト監視タスクを開始
    timeout_task = asyncio.create_task(timeout_monitor())

    async def process_transcription(text: str, source: str = "voice") -> None:
        """認識されたテキストをチャット処理"""
        nonlocal last_response_time, last_response_message
        try:
            logger.info(f"チャット処理開始: {text}")

            # ユーザー応答を受信したのでタイムアウトタイマーをリセット
            last_response_time = datetime.now()

            # ダッシュボードにユーザーメッセージをブロードキャスト
            await event_broadcaster.broadcast_user_message(session_id, text, source)

            request = ChatRequest(
                message=text,
                session_id=session_id,
                response_type="voice",
            )
            response = conversation_service.process_message(request)

            # AI応答後にタイムアウトタイマーをリセットし、最後のメッセージを更新
            last_response_time = datetime.now()
            last_response_message = response.message

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

            # ダッシュボードにAI応答をブロードキャスト
            await event_broadcaster.broadcast_ai_response(
                session_id=session_id,
                message=response.message,
                turn_count=response.turn_count,
                is_complete=response.is_complete,
                suggestions=response.suggestions,
                destination=response.destination.model_dump() if response.destination else None,
                stopover=response.stopover.model_dump() if response.stopover else None,
            )

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
            # ダッシュボードに音声認識結果をブロードキャスト
            await event_broadcaster.broadcast_transcription(session_id, text, is_final)
            # 最終結果の場合、チャット処理を実行
            if is_final and text.strip():
                await process_transcription(text, source="voice")
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
        # ダッシュボードにASRステータスをブロードキャスト
        await event_broadcaster.broadcast_asr_status(session_id, "connected", "音声認識が開始されました")

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
                            logger.info(f"音声入力開始リクエスト受信: {session_id}")
                            # 即座に受付応答を返す
                            await websocket.send_json({
                                "type": "asr_starting",
                                "message": "音声認識を開始しています...",
                            })
                            try:
                                asr_client = speech_service.create_asr_session(
                                    session_id=session_id,
                                    on_transcription=on_transcription,
                                    on_error=on_asr_error,
                                    on_connected=on_asr_connected,
                                )
                                logger.info(f"ASRセッション作成成功: {session_id}")
                            except Exception as e:
                                logger.error(f"ASR開始エラー: {e}")
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
                            await process_transcription(text, source="text")

                    elif cmd_type == "ping":
                        await websocket.send_json({"type": "pong"})

                except json.JSONDecodeError:
                    logger.warning(f"無効なJSONメッセージ: {message['text']}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket切断: {session_id}")

    except Exception as e:
        logger.error(f"WebSocketエラー: {e}")

    finally:
        # タイムアウト監視タスクをキャンセル
        if timeout_task:
            timeout_task.cancel()
            try:
                await timeout_task
            except asyncio.CancelledError:
                pass
        # セッション終了処理
        manager.disconnect(session_id)
        if asr_client:
            speech_service.close_asr_session(session_id)
        # セッションを削除（プライバシー・バイ・デザイン）
        conversation_service.delete_session(session_id)
        # ダッシュボードにセッション終了をブロードキャスト
        await event_broadcaster.broadcast_session_end(session_id)
        logger.info(f"セッション終了・削除: {session_id}")


@router.websocket("/ws/chat")
async def websocket_chat_endpoint_auto(
    websocket: WebSocket,
) -> None:
    """セッションIDなしで接続（自動生成）"""
    await websocket_chat_endpoint(websocket, session_id=None)


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = None,
) -> None:
    """
    テキストチャット用WebSocketエンドポイント
    """
    # セッションの確認 - 存在しない場合は自動生成
    original_session_id = session_id
    context = None
    if session_id:
        context = conversation_service.get_session(session_id)

    if not context:
        # ユーザーデータを初期化（VectorStore、サンプルデータ）
        data_count = conversation_service.initialize_user_data()
        logger.info(f"ユーザーデータを初期化: {data_count}件")

    # WebSocket接続を確立
    await websocket.accept()

    # セッション開始 - ウェルカムメッセージを取得（セッションも自動作成される）
    welcome_response = conversation_service.get_welcome_message(session_id)
    session_id = welcome_response.session_id
    logger.info(f"セッション開始: {session_id}")

    # 接続管理に登録
    manager.active_connections[session_id] = websocket

    # 古いセッションIDで接続が登録されていた場合は削除
    if original_session_id and original_session_id != session_id and original_session_id in manager.active_connections:
        del manager.active_connections[original_session_id]

    # 接続確立とウェルカムメッセージを送信
    await websocket.send_json({
        "type": "session_start",
        "message": welcome_response.message,
        "session_id": session_id,
        "has_audio": welcome_response.has_audio,
    })

    # ウェルカムメッセージの音声データがあれば送信
    if welcome_response.has_audio and welcome_response.audio_data:
        audio_bytes = base64.b64decode(welcome_response.audio_data)
        await websocket.send_bytes(audio_bytes)
        logger.info(f"ウェルカム音声を送信: {len(audio_bytes)} bytes")

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
        # セッション終了処理
        manager.disconnect(session_id)
        # セッションを削除（プライバシー・バイ・デザイン）
        conversation_service.delete_session(session_id)
        # ダッシュボードにセッション終了をブロードキャスト
        await event_broadcaster.broadcast_session_end(session_id)
        logger.info(f"セッション終了・削除: {session_id}")


@router.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket) -> None:
    """
    ダッシュボード監視用WebSocketエンドポイント

    セッションイベントをリアルタイムで受信:
    - session_start: セッション開始
    - session_end: セッション終了
    - user_message: ユーザーメッセージ
    - ai_response: AI応答
    - transcription: 音声認識結果
    - asr_status: ASRステータス変更
    """
    await websocket.accept()
    await event_broadcaster.register_dashboard(websocket)
    logger.info("ダッシュボード監視接続確立")

    # 接続確認メッセージ
    await websocket.send_json({
        "type": "dashboard_connected",
        "message": "ダッシュボード監視が開始されました",
    })

    try:
        while True:
            # クライアントからのメッセージを待機（ping/pong など）
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("ダッシュボード監視切断")

    except Exception as e:
        logger.error(f"ダッシュボード監視エラー: {e}")

    finally:
        await event_broadcaster.unregister_dashboard(websocket)
