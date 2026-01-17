"""
音声処理サービス - Qwen Realtime ASR
sample_audio.md の実装に基づく
"""

import base64
import json
import logging
import threading
import time
from typing import Callable, Optional

import websocket

from ..config import settings

logger = logging.getLogger(__name__)


class RealtimeASRClient:
    """
    Qwen Realtime ASR クライアント
    sample_audio.md の実装に基づく WebSocket クライアント
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        sample_rate: int = 16000,
        language: str = "ja",
    ) -> None:
        self.api_key = api_key or settings.AUDIO_API_KEY or settings.DASHSCOPE_API_KEY
        self.model = model or settings.AUDIO_MODEL
        self.base_url = base_url or settings.AUDIO_BASE_URL
        self.sample_rate = sample_rate
        self.language = language

        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_connected: bool = False
        self.is_running: bool = False

        # コールバック関数
        self.on_transcription: Optional[Callable[[str, bool], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_connected: Optional[Callable[[], None]] = None

        # 認識結果
        self._transcription: str = ""
        self._thread: Optional[threading.Thread] = None

    @property
    def websocket_url(self) -> str:
        """WebSocket接続URLを生成"""
        return f"{self.base_url}?model={self.model}"

    @property
    def headers(self) -> list:
        """WebSocket接続ヘッダーを生成"""
        return [
            f"Authorization: Bearer {self.api_key}",
            "OpenAI-Beta: realtime=v1",
        ]

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        """WebSocket接続確立時のコールバック"""
        logger.info("ASR WebSocket接続確立")
        self.is_connected = True

        # セッション設定を送信
        session_config = {
            "event_id": f"event_{int(time.time() * 1000)}",
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "input_audio_format": "pcm",
                "sample_rate": self.sample_rate,
                "input_audio_transcription": {
                    "language": self.language,
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.2,
                    "silence_duration_ms": 800,
                },
            },
        }
        ws.send(json.dumps(session_config))
        logger.info("ASRセッション設定を送信")

        if self.on_connected:
            self.on_connected()

    def _on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        """メッセージ受信時のコールバック"""
        try:
            data = json.loads(message)
            event_type = data.get("type", "")

            logger.debug(f"ASR受信: {event_type}")

            if event_type == "session.created":
                logger.info("ASRセッション作成完了")

            elif event_type == "session.updated":
                logger.info("ASRセッション設定更新完了")

            elif event_type == "conversation.item.input_audio_transcription.completed":
                # 音声認識完了（最終結果）
                transcript = data.get("transcript", "")
                if transcript:
                    self._transcription = transcript
                    logger.info(f"ASR認識結果（最終）: {transcript}")
                    if self.on_transcription:
                        self.on_transcription(transcript, True)

            elif event_type == "conversation.item.input_audio_transcription.delta":
                # 途中結果
                delta = data.get("delta", "")
                if delta:
                    logger.debug(f"ASR認識結果（途中）: {delta}")
                    if self.on_transcription:
                        self.on_transcription(delta, False)

            elif event_type == "error":
                error_info = data.get("error", {})
                error_msg = error_info.get("message", str(data))
                logger.error(f"ASRエラー: {error_msg}")
                if self.on_error:
                    self.on_error(error_msg)

        except json.JSONDecodeError:
            logger.error(f"JSON解析エラー: {message}")

    def _on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        """エラー発生時のコールバック"""
        logger.error(f"ASR WebSocketエラー: {error}")
        if self.on_error:
            self.on_error(str(error))

    def _on_close(
        self,
        ws: websocket.WebSocketApp,
        close_status_code: Optional[int],
        close_msg: Optional[str],
    ) -> None:
        """接続終了時のコールバック"""
        logger.info(f"ASR WebSocket接続終了: {close_status_code} - {close_msg}")
        self.is_connected = False

    def connect(self) -> bool:
        """WebSocket接続を開始（非同期）"""
        try:
            logger.info(f"ASR接続開始: {self.websocket_url}")

            self.ws = websocket.WebSocketApp(
                self.websocket_url,
                header=self.headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )

            # バックグラウンドスレッドで実行
            self.is_running = True
            self._thread = threading.Thread(
                target=self._run_forever,
                daemon=True,
            )
            self._thread.start()

            # 接続待機（最大5秒）
            for _ in range(50):
                if self.is_connected:
                    return True
                time.sleep(0.1)

            logger.warning("ASR接続タイムアウト")
            return False

        except Exception as e:
            logger.error(f"ASR接続エラー: {e}")
            return False

    def _run_forever(self) -> None:
        """WebSocket接続を維持"""
        try:
            self.ws.run_forever()
        except Exception as e:
            logger.error(f"ASR run_forever エラー: {e}")
        finally:
            self.is_running = False

    def send_audio(self, audio_data: bytes) -> None:
        """
        音声データを送信

        Args:
            audio_data: PCM音声データ（16kHz, 16bit, モノラル）
        """
        if not self.is_connected or not self.ws:
            logger.warning("ASR未接続: 音声データを送信できません")
            return

        # Base64エンコード
        encoded_data = base64.b64encode(audio_data).decode("utf-8")

        event = {
            "event_id": f"event_{int(time.time() * 1000)}",
            "type": "input_audio_buffer.append",
            "audio": encoded_data,
        }
        self.ws.send(json.dumps(event))

    def commit_audio(self) -> None:
        """音声バッファをコミット（VAD無効時に使用）"""
        if not self.is_connected or not self.ws:
            return

        event = {
            "event_id": f"event_{int(time.time() * 1000)}",
            "type": "input_audio_buffer.commit",
        }
        self.ws.send(json.dumps(event))

    def disconnect(self) -> None:
        """接続を終了"""
        self.is_running = False
        if self.ws:
            self.ws.close()
        self.is_connected = False
        logger.info("ASR接続終了")

    def get_transcription(self) -> str:
        """認識結果を取得"""
        return self._transcription

    def clear_transcription(self) -> None:
        """認識結果をクリア"""
        self._transcription = ""


class SpeechService:
    """音声処理サービス"""

    def __init__(self) -> None:
        self.asr_clients: dict[str, RealtimeASRClient] = {}

    def create_asr_session(
        self,
        session_id: str,
        on_transcription: Optional[Callable[[str, bool], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_connected: Optional[Callable[[], None]] = None,
    ) -> RealtimeASRClient:
        """ASRセッションを作成"""
        client = RealtimeASRClient()
        client.on_transcription = on_transcription
        client.on_error = on_error
        client.on_connected = on_connected

        if client.connect():
            self.asr_clients[session_id] = client
            logger.info(f"ASRセッション作成: {session_id}")
            return client
        else:
            raise RuntimeError("ASR接続に失敗しました")

    def close_asr_session(self, session_id: str) -> None:
        """ASRセッションを終了"""
        if session_id in self.asr_clients:
            self.asr_clients[session_id].disconnect()
            del self.asr_clients[session_id]
            logger.info(f"ASRセッション終了: {session_id}")

    def get_asr_client(self, session_id: str) -> Optional[RealtimeASRClient]:
        """ASRクライアントを取得"""
        return self.asr_clients.get(session_id)

    def send_audio(self, session_id: str, audio_data: bytes) -> None:
        """音声データを送信"""
        client = self.asr_clients.get(session_id)
        if client:
            client.send_audio(audio_data)


# シングルトンインスタンス
speech_service = SpeechService()
