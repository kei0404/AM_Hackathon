"""
音声再生サービス - サーバー側で音声を再生
"""

import logging
import os
import platform
import subprocess
import tempfile
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class AudioPlayerService:
    """サーバー側で音声を再生するサービス"""

    def __init__(self) -> None:
        """音声再生サービスの初期化"""
        self.system = platform.system()
        self._current_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

        logger.info(f"AudioPlayerService初期化: OS={self.system}")

    def play_audio(self, audio_data: bytes, audio_format: str = "mp3") -> bool:
        """
        音声データをサーバー側で再生する

        Args:
            audio_data: 音声データ（バイナリ）
            audio_format: 音声フォーマット（mp3, wav等）

        Returns:
            再生成功の場合True
        """
        if not audio_data:
            logger.warning("音声データが空です")
            return False

        try:
            # 一時ファイルに保存
            with tempfile.NamedTemporaryFile(
                suffix=f".{audio_format}",
                delete=False
            ) as temp_file:
                temp_file.write(audio_data)
                temp_path = temp_file.name

            logger.info(f"音声ファイルを一時保存: {temp_path}, サイズ={len(audio_data)} bytes")

            # 非同期で再生（別スレッド）
            thread = threading.Thread(
                target=self._play_audio_async,
                args=(temp_path,),
                daemon=True
            )
            thread.start()

            return True

        except Exception as e:
            logger.error(f"音声再生エラー: {e}", exc_info=True)
            return False

    def _play_audio_async(self, file_path: str) -> None:
        """音声を非同期で再生（別スレッド）"""
        try:
            with self._lock:
                # 前の再生を停止
                if self._current_process and self._current_process.poll() is None:
                    self._current_process.terminate()
                    self._current_process.wait(timeout=1)

            # OSに応じたコマンドで再生
            if self.system == "Darwin":  # macOS
                cmd = ["afplay", file_path]
            elif self.system == "Linux":
                # Linux: aplay (ALSA) または mpg123
                if file_path.endswith(".mp3"):
                    cmd = ["mpg123", "-q", file_path]
                else:
                    cmd = ["aplay", "-q", file_path]
            elif self.system == "Windows":
                # Windows: PowerShellを使用
                cmd = [
                    "powershell",
                    "-c",
                    f"(New-Object Media.SoundPlayer '{file_path}').PlaySync()"
                ]
            else:
                logger.warning(f"未対応のOS: {self.system}")
                return

            logger.info(f"音声再生開始: {' '.join(cmd)}")

            with self._lock:
                self._current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            # 再生完了を待機
            self._current_process.wait()
            logger.info("音声再生完了")

        except FileNotFoundError as e:
            logger.error(f"再生コマンドが見つかりません: {e}")
        except Exception as e:
            logger.error(f"音声再生エラー: {e}", exc_info=True)
        finally:
            # 一時ファイルを削除
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"一時ファイルを削除: {file_path}")
            except Exception as e:
                logger.warning(f"一時ファイル削除エラー: {e}")

    def stop(self) -> None:
        """現在の再生を停止"""
        with self._lock:
            if self._current_process and self._current_process.poll() is None:
                self._current_process.terminate()
                logger.info("音声再生を停止")


# シングルトンインスタンス
audio_player_service = AudioPlayerService()
