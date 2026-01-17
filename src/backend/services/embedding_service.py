"""
Embeddingサービス - DashScope text-embedding-v4 との連携
"""

import logging
from http import HTTPStatus
from typing import Optional

import dashscope

from ..config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """DashScope text-embedding-v4 を使用したEmbeddingサービス"""

    # text-embedding-v4の出力次元数
    EMBEDDING_DIMENSION: int = 1024

    def __init__(self) -> None:
        """Embeddingサービスの初期化"""
        self.demo_mode = False
        self.model = settings.EMBEDDING_MODEL

        # EMBEDDING_API_KEY を優先、なければ DASHSCOPE_API_KEY を使用
        api_key = settings.EMBEDDING_API_KEY or settings.DASHSCOPE_API_KEY

        if not api_key:
            logger.warning("EMBEDDING_API_KEY が未設定 - デモモードで動作します")
            self.demo_mode = True
        else:
            dashscope.api_key = api_key
            logger.info(f"Embedding API 初期化完了: モデル={self.model}")

    def get_embedding(self, text: str) -> list[float]:
        """
        テキストをベクトルに変換する

        Args:
            text: 変換するテキスト

        Returns:
            埋め込みベクトル（1024次元）
        """
        if self.demo_mode:
            return self._generate_demo_embedding(text)

        try:
            response = dashscope.TextEmbedding.call(
                model=self.model,
                input=text,
            )

            if response.status_code == HTTPStatus.OK:
                embedding = response.output["embeddings"][0]["embedding"]
                logger.debug(f"Embedding生成成功: {len(embedding)}次元")
                return embedding
            else:
                logger.error(
                    f"Embedding APIエラー: {response.code} - {response.message}"
                )
                return self._generate_demo_embedding(text)

        except Exception as e:
            logger.error(f"Embedding生成エラー: {e}")
            return self._generate_demo_embedding(text)

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        複数テキストをバッチでベクトル化する

        Args:
            texts: 変換するテキストのリスト

        Returns:
            埋め込みベクトルのリスト
        """
        if self.demo_mode:
            return [self._generate_demo_embedding(text) for text in texts]

        try:
            response = dashscope.TextEmbedding.call(
                model=self.model,
                input=texts,
            )

            if response.status_code == HTTPStatus.OK:
                embeddings = [
                    item["embedding"] for item in response.output["embeddings"]
                ]
                logger.debug(f"バッチEmbedding生成成功: {len(embeddings)}件")
                return embeddings
            else:
                logger.error(
                    f"Embedding APIエラー: {response.code} - {response.message}"
                )
                return [self._generate_demo_embedding(text) for text in texts]

        except Exception as e:
            logger.error(f"バッチEmbedding生成エラー: {e}")
            return [self._generate_demo_embedding(text) for text in texts]

    def _generate_demo_embedding(self, text: str) -> list[float]:
        """
        デモモード用の疑似埋め込みベクトルを生成

        テキストのハッシュ値を使用して決定論的なベクトルを生成
        """
        import hashlib

        # テキストのハッシュを取得
        hash_bytes = hashlib.sha256(text.encode()).digest()

        # ハッシュを基に1024次元のベクトルを生成
        embedding = []
        for i in range(self.EMBEDDING_DIMENSION):
            # ハッシュバイトを循環して使用
            byte_val = hash_bytes[i % len(hash_bytes)]
            # -1.0 ~ 1.0 の範囲に正規化
            normalized = (byte_val / 127.5) - 1.0
            embedding.append(normalized)

        return embedding


# シングルトンインスタンス
embedding_service = EmbeddingService()
