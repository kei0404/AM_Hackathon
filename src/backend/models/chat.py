"""
チャット関連のデータモデル
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """メッセージの役割"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ConversationPhase(str, Enum):
    """会話フェーズ"""

    WAITING_LOCATION = "waiting_location"  # 現在地待ち
    ASKING_DESTINATION = "asking_destination"  # 目的地を質問中
    ASKING_PREFERENCES = "asking_preferences"  # 追加の希望を質問中
    SUGGESTING_FIRST = "suggesting_first"  # 1つ目の提案中
    SUGGESTING_SECOND = "suggesting_second"  # 2つ目の提案中
    SUGGESTING_THIRD = "suggesting_third"  # 3つ目の提案中
    ASKING_OTHER_PREFERENCES = "asking_other_preferences"  # 他の希望を質問中
    NAVIGATING = "navigating"  # ナビゲーション中（変更受付可能）
    CONFIRMING_STOPOVER_CHANGE = "confirming_stopover_change"  # 立ち寄り場所変更の確認中
    CONFIRMING_DESTINATION_CHANGE = "confirming_destination_change"  # 目的地変更の確認中


class ChatMessage(BaseModel):
    """チャットメッセージ"""

    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class LocationData(BaseModel):
    """位置情報データ"""

    latitude: float = Field(..., description="緯度")
    longitude: float = Field(..., description="経度")
    address: Optional[str] = Field(None, description="住所（逆ジオコーディング結果）")
    accuracy: Optional[float] = Field(None, description="GPS精度（メートル）")


class PlaceInfo(BaseModel):
    """場所情報（緯度・経度付き）"""

    name: str = Field(..., description="場所名")
    latitude: Optional[float] = Field(None, description="緯度")
    longitude: Optional[float] = Field(None, description="経度")


class ChatRequest(BaseModel):
    """チャットリクエスト"""

    message: str = Field(..., description="ユーザーからのメッセージ")
    session_id: Optional[str] = Field(None, description="セッションID")
    current_location: Optional[str] = Field(None, description="現在地（例: 東京駅）")
    destination: Optional[str] = Field(None, description="目的地（例: 横浜駅）")
    context: Optional[dict] = Field(
        None, description="追加コンテキスト（お気に入り、履歴など）"
    )
    # モバイルアプリ対応の新規フィールド
    response_type: Optional[str] = Field(
        None, description="応答タイプ: 'text', 'voice', 'selection'"
    )
    selected_suggestion: Optional[str] = Field(
        None, description="選択肢が選ばれた場合の値"
    )
    location_data: Optional[LocationData] = Field(
        None, description="GPS座標形式の位置情報"
    )


class ChatResponse(BaseModel):
    """チャットレスポンス"""

    message: str = Field(..., description="AIからの応答")
    session_id: str = Field(..., description="セッションID")
    turn_count: int = Field(..., description="現在の会話ターン数")
    is_complete: bool = Field(False, description="目的地決定が完了したか")
    suggestions: list[str] = Field(default_factory=list, description="提案された選択肢")
    # 提案管理フィールド
    suggestion_index: Optional[int] = Field(
        None,
        description="現在の提案インデックス（1, 2, 3）"
    )
    suggestion_total: Optional[int] = Field(
        None,
        description="提案の総数（通常3）"
    )
    # 旅程情報フィールド（緯度・経度付き）
    destination: Optional[PlaceInfo] = Field(
        None,
        description="決定した目的地（名前・緯度・経度）"
    )
    stopover: Optional[PlaceInfo] = Field(
        None,
        description="決定した立ち寄り場所（名前・緯度・経度）"
    )
    # 音声出力フィールド
    audio_data: Optional[str] = Field(
        None,
        description="音声データ（Base64エンコードされたWAVデータ）"
    )
    has_audio: bool = Field(
        False,
        description="音声データが含まれているかどうか"
    )


class ConversationContext(BaseModel):
    """会話コンテキスト"""

    session_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    turn_count: int = 0
    phase: ConversationPhase = ConversationPhase.WAITING_LOCATION
    user_preferences: Optional[dict] = None
    favorite_spots: list[dict] = Field(default_factory=list)
    visit_history: list[dict] = Field(default_factory=list)
    current_location: Optional[str] = None
    current_location_info: Optional[PlaceInfo] = None  # 現在地（緯度・経度付き）
    destination: Optional[str] = None
    destination_info: Optional[PlaceInfo] = None  # 目的地（緯度・経度付き）
    additional_preferences: Optional[str] = None  # 追加の希望（やりたいこと等）
    # 提案関連の新しいフィールド
    suggestions_list: list[dict] = Field(default_factory=list)  # RAG検索結果からの3つの提案
    current_suggestion_index: int = 0  # 現在提案中のインデックス（0, 1, 2）
    selected_stopover: Optional[str] = None  # 選択された立ち寄り先
    selected_stopover_info: Optional[PlaceInfo] = None  # 選択された立ち寄り先（緯度・経度付き）
