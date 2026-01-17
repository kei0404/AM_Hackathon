"""
音声合成サービス - Qwen3-TTS-Flash
"""

import logging
from typing import Optional

import requests
from dashscope.audio.qwen_tts import SpeechSynthesizer

from ..config import settings

logger = logging.getLogger(__name__)


class TTSService:
    """Qwen3-TTS-Flashを使用した音声合成サービス"""

    def __init__(self) -> None:
        """TTSサービスの初期化"""
        self.api_key = settings.TTS_API_KEY or settings.DASHSCOPE_API_KEY
        self.model = settings.TTS_MODEL
        self.voice = settings.TTS_VOICE
        self.speed = settings.TTS_SPEED

    def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> bytes:
        """
        テキストを音声に変換

        Args:
            text: 変換するテキスト
            voice: 音声タイプ（デフォルト: 設定値）

        Returns:
            音声データ（バイナリ、MP3形式）
        """
        if not self.api_key:
            logger.warning("TTS APIキーが設定されていません")
            return b""

        if not text or not text.strip():
            logger.warning("変換するテキストが空です")
            return b""

        try:
            logger.info(f"TTS変換開始: text={text[:50]}...")

            # Qwen3-TTS-Flash API呼び出し
            response = SpeechSynthesizer.call(
                model=self.model,
                api_key=self.api_key,
                text=text,
                voice=voice or self.voice,
            )

            logger.info(f"TTS APIレスポンス: {response}")

            # レスポンスから音声URLを取得
            audio_url = None
            if response is not None and hasattr(response, 'output'):
                output = response.output
                if hasattr(output, 'audio'):
                    audio = output.audio
                    # audio が辞書の場合
                    if isinstance(audio, dict) and 'url' in audio:
                        audio_url = audio['url']
                    # audio が url 属性を持つ場合
                    elif hasattr(audio, 'url'):
                        audio_url = audio.url

            if not audio_url:
                logger.error(f"TTS APIエラー: 音声URLを取得できません。response={response}")
                return b""

            logger.info(f"音声URLを取得: {audio_url[:100]}...")

            # 音声データをダウンロード
            audio_response = requests.get(audio_url, timeout=30)
            if audio_response.status_code == 200:
                audio_data = audio_response.content
                logger.info(f"TTS変換成功: {len(audio_data)} bytes")
                return audio_data
            else:
                logger.error(f"音声ダウンロードエラー: status={audio_response.status_code}")
                return b""

        except Exception as e:
            logger.error(f"TTS変換エラー: {e}", exc_info=True)
            return b""

    def is_available(self) -> bool:
        """TTSサービスが利用可能かどうかを確認"""
        return bool(self.api_key)


# シングルトンインスタンス
tts_service = TTSService()
