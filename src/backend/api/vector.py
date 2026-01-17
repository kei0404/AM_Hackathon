"""
ベクトル検索API
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.sample_data import get_all_sample_data
from ..services.vector_store import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vector", tags=["vector"])


class SearchRequest(BaseModel):
    """検索リクエスト"""

    query: str
    n_results: int = 5
    category: Optional[str] = None


class SearchResult(BaseModel):
    """検索結果"""

    id: str
    document: str
    metadata: dict
    distance: float


class SearchResponse(BaseModel):
    """検索レスポンス"""

    query: str
    results: list[SearchResult]
    count: int


class AddDocumentRequest(BaseModel):
    """ドキュメント追加リクエスト（レガシー形式）"""

    doc_id: str
    text: str
    metadata: Optional[dict] = None


class AddVisitRecordRequest(BaseModel):
    """訪問履歴追加リクエスト（新形式）"""

    datetime: str  # 日時 (例: "2026-01-15 12:30")
    address: str  # 住所 (例: "東京都渋谷区...")
    place_name: str  # 場所の名前 (例: "Blue Bottle Coffee")
    impression: str  # 感想


class StatusResponse(BaseModel):
    """ステータスレスポンス"""

    status: str
    document_count: int
    message: str


@router.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest) -> SearchResponse:
    """
    ベクトル類似度検索を実行する

    Args:
        request: 検索リクエスト

    Returns:
        類似ドキュメントのリスト
    """
    try:
        if request.category:
            results = vector_store.search_by_category(
                query=request.query,
                category=request.category,
                n_results=request.n_results,
            )
        else:
            results = vector_store.search(
                query=request.query,
                n_results=request.n_results,
            )

        return SearchResponse(
            query=request.query,
            results=[SearchResult(**r) for r in results],
            count=len(results),
        )

    except Exception as e:
        logger.error(f"検索エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add", response_model=StatusResponse)
async def add_document(request: AddDocumentRequest) -> StatusResponse:
    """
    ドキュメントをベクトルDBに追加する（レガシー形式）

    Args:
        request: 追加リクエスト

    Returns:
        ステータスレスポンス
    """
    try:
        vector_store.add_document(
            doc_id=request.doc_id,
            text=request.text,
            metadata=request.metadata,
        )

        return StatusResponse(
            status="success",
            document_count=vector_store.count(),
            message=f"ドキュメント '{request.doc_id}' を追加しました",
        )

    except Exception as e:
        logger.error(f"ドキュメント追加エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-visit", response_model=StatusResponse)
async def add_visit_record(request: AddVisitRecordRequest) -> StatusResponse:
    """
    訪問履歴をベクトルDBに追加する

    Args:
        request: 訪問履歴追加リクエスト（日時、住所、場所の名前、感想）

    Returns:
        ステータスレスポンス
    """
    try:
        import uuid

        doc_id = f"visit_{uuid.uuid4().hex[:8]}"

        # ベクトル検索用のテキストを生成
        text = (
            f"日時: {request.datetime} "
            f"場所: {request.place_name} "
            f"住所: {request.address} "
            f"感想: {request.impression}"
        )

        metadata = {
            "datetime": request.datetime,
            "address": request.address,
            "place_name": request.place_name,
            "impression": request.impression,
            "category": "visit_record",
        }

        vector_store.add_document(
            doc_id=doc_id,
            text=text,
            metadata=metadata,
        )

        return StatusResponse(
            status="success",
            document_count=vector_store.count(),
            message=f"訪問履歴 '{request.place_name}' を追加しました (ID: {doc_id})",
        )

    except Exception as e:
        logger.error(f"訪問履歴追加エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/init", response_model=StatusResponse)
async def initialize_sample_data() -> StatusResponse:
    """
    サンプルデータでベクトルDBを初期化する

    Returns:
        ステータスレスポンス
    """
    try:
        sample_data = get_all_sample_data()

        doc_ids = [d["id"] for d in sample_data]
        texts = [d["text"] for d in sample_data]
        metadatas = [d["metadata"] for d in sample_data]

        vector_store.add_documents(
            doc_ids=doc_ids,
            texts=texts,
            metadatas=metadatas,
        )

        return StatusResponse(
            status="success",
            document_count=vector_store.count(),
            message=f"サンプルデータ {len(sample_data)} 件を追加しました",
        )

    except Exception as e:
        logger.error(f"初期化エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """
    ベクトルDBのステータスを取得する

    Returns:
        ステータスレスポンス
    """
    try:
        count = vector_store.count()
        return StatusResponse(
            status="healthy",
            document_count=count,
            message=f"ChromaDB稼働中: {count}件のドキュメント",
        )

    except Exception as e:
        logger.error(f"ステータス取得エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear", response_model=StatusResponse)
async def clear_collection() -> StatusResponse:
    """
    コレクション内の全データを削除する（開発用）

    Returns:
        ステータスレスポンス
    """
    try:
        vector_store.clear_collection()

        return StatusResponse(
            status="success",
            document_count=0,
            message="コレクションをクリアしました",
        )

    except Exception as e:
        logger.error(f"クリアエラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))
