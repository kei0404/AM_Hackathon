"""
ベクトルストアサービス - ChromaDB を使用したベクトルデータベース
"""

import logging
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..config import settings
from .embedding_service import embedding_service

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB を使用したベクトルストア"""

    def __init__(self) -> None:
        """ベクトルストアの初期化"""
        # 永続化ディレクトリを作成
        persist_dir = Path(settings.CHROMA_PERSIST_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)

        # ChromaDBクライアントを初期化
        self.client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # コレクションを取得または作成
        self.collection = self.client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"description": "Data Plug Copilot ユーザーデータ"},
        )

        logger.info(
            f"ChromaDB初期化完了: {persist_dir}, "
            f"コレクション: {settings.CHROMA_COLLECTION_NAME}"
        )

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        ドキュメントをベクトルDBに追加する

        Args:
            doc_id: ドキュメントの一意識別子
            text: ドキュメントのテキスト内容
            metadata: 追加のメタデータ
        """
        embedding = embedding_service.get_embedding(text)

        self.collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata or {}],
        )

        logger.debug(f"ドキュメント追加: {doc_id}")

    def add_documents(
        self,
        doc_ids: list[str],
        texts: list[str],
        metadatas: Optional[list[dict]] = None,
    ) -> None:
        """
        複数ドキュメントをバッチでベクトルDBに追加する

        Args:
            doc_ids: ドキュメントIDのリスト
            texts: テキストのリスト
            metadatas: メタデータのリスト
        """
        logger.info(f"Embedding生成開始: {len(texts)}件のテキスト")
        embeddings = embedding_service.get_embeddings(texts)
        logger.info(f"Embedding生成完了: {len(embeddings)}件, 次元数={len(embeddings[0]) if embeddings else 0}")

        logger.info(f"ChromaDB upsert開始: コレクション={self.collection.name}")
        self.collection.upsert(
            ids=doc_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas or [{} for _ in doc_ids],
        )

        # 登録後の件数を確認
        current_count = self.collection.count()
        logger.info(f"バッチドキュメント追加完了: {len(doc_ids)}件, コレクション内総数: {current_count}件")

    def search(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """
        クエリに類似したドキュメントを検索する

        Args:
            query: 検索クエリテキスト
            n_results: 返す結果の最大数
            where: フィルタリング条件

        Returns:
            検索結果のリスト（スコア順）
        """
        query_embedding = embedding_service.get_embedding(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # 結果を整形
        formatted_results = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                formatted_results.append(
                    {
                        "id": doc_id,
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i],
                    }
                )

        logger.debug(f"検索完了: {len(formatted_results)}件の結果")
        return formatted_results

    def search_by_category(
        self,
        query: str,
        category: str,
        n_results: int = 5,
    ) -> list[dict]:
        """
        カテゴリでフィルタリングして検索する

        Args:
            query: 検索クエリテキスト
            category: カテゴリ（例: "favorite_spot", "preference", "history"）
            n_results: 返す結果の最大数

        Returns:
            検索結果のリスト
        """
        return self.search(
            query=query,
            n_results=n_results,
            where={"category": category},
        )

    def get_document(self, doc_id: str) -> Optional[dict]:
        """
        IDでドキュメントを取得する

        Args:
            doc_id: ドキュメントID

        Returns:
            ドキュメント情報、または存在しない場合はNone
        """
        results = self.collection.get(
            ids=[doc_id],
            include=["documents", "metadatas"],
        )

        if results["ids"]:
            return {
                "id": results["ids"][0],
                "document": results["documents"][0],
                "metadata": results["metadatas"][0],
            }
        return None

    def delete_document(self, doc_id: str) -> None:
        """
        ドキュメントを削除する

        Args:
            doc_id: 削除するドキュメントID
        """
        self.collection.delete(ids=[doc_id])
        logger.debug(f"ドキュメント削除: {doc_id}")

    def delete_by_session(self, session_id: str) -> None:
        """
        セッションに紐づく全ドキュメントを削除する
        （セッション終了時のデータクリーンアップ用）

        Args:
            session_id: セッションID
        """
        # セッションIDでフィルタして削除
        results = self.collection.get(
            where={"session_id": session_id},
            include=[],
        )

        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            logger.info(
                f"セッションデータ削除: {session_id}, {len(results['ids'])}件"
            )

    def count(self) -> int:
        """コレクション内のドキュメント数を取得"""
        return self.collection.count()

    def reinitialize(self) -> None:
        """VectorStoreを再初期化する（Startエンドポイント用）"""
        # クライアントが無効な場合は新規作成
        if self.client is None:
            persist_dir = Path(settings.CHROMA_PERSIST_DIR)
            persist_dir.mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )

        # コレクションをクリアして再作成
        try:
            self.client.delete_collection(settings.CHROMA_COLLECTION_NAME)
        except Exception:
            pass  # コレクションが存在しない場合は無視

        self.collection = self.client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"description": "Data Plug Copilot ユーザーデータ"},
        )
        logger.info(f"VectorStore再初期化完了: コレクション={settings.CHROMA_COLLECTION_NAME}")

    def clear_collection(self) -> None:
        """コレクション内の全データを削除（開発用）"""
        # コレクションを削除して再作成
        self.client.delete_collection(settings.CHROMA_COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"description": "Data Plug Copilot ユーザーデータ"},
        )
        logger.warning("コレクションをクリアしました")

    def clear_all_data(self) -> None:
        """
        コレクション内の全データを削除する
        （プライバシー・バイ・デザイン: セッション終了時のデータ消去用）
        """
        # コレクションを削除して再作成（データのみ削除、ディレクトリは保持）
        try:
            self.client.delete_collection(settings.CHROMA_COLLECTION_NAME)
            logger.info(f"コレクション削除: {settings.CHROMA_COLLECTION_NAME}")
        except Exception as e:
            logger.warning(f"コレクション削除エラー（無視）: {e}")

        # 空のコレクションを再作成
        self.collection = self.client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"description": "Data Plug Copilot ユーザーデータ"},
        )
        logger.info("ChromaDBコレクションをクリアしました")


# シングルトンインスタンス
vector_store = VectorStore()
