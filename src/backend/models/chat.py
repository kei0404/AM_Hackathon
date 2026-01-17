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
    SUGGESTING_STOPOVER = "suggesting_stopover"  # 立ち寄り先を提案中
    COMPLETE = "complete"  # 会話完了


class ChatMessage(BaseModel):
    """チャットメッセージ"""

    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatRequest(BaseModel):
    """チャットリクエスト"""

    message: str = Field(..., description="ユーザーからのメッセージ")
    session_id: Optional[str] = Field(None, description="セッションID")
    current_location: Optional[str] = Field(None, description="現在地（例: 東京駅）")
    destination: Optional[str] = Field(None, description="目的地（例: 横浜駅）")
    context: Optional[dict] = Field(None, description="追加コンテキスト（お気に入り、履歴など）")


class ChatResponse(BaseModel):
    """チャットレスポンス"""

    message: str = Field(..., description="AIからの応答")
    session_id: str = Field(..., description="セッションID")
    turn_count: int = Field(..., description="現在の会話ターン数")
    is_complete: bool = Field(False, description="目的地決定が完了したか")
    suggestions: list[str] = Field(default_factory=list, description="提案された選択肢")


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
    destination: Optional[str] = None
    additional_preferences: Optional[str] = None  # 追加の希望（やりたいこと等）
