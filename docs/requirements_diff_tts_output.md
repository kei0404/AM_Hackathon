# 要件差分: Qwen3-TTS-Flashによる音声出力機能

**作成日**: 2025-01-27  
**バージョン**: 1.0.0  
**ステータス**: Draft  
**関連仕様**: `docs/requirements_diff_mobile_voice.md` v1.0.0

---

## 概要

LLMの応答をテキストと音声の両方で出力できるようにします。Qwen3-TTS-Flashを使用して、LLMが生成したテキスト応答を音声に変換し、クライアントに返送します。これにより、モバイルアプリや車載デバイスで音声による応答が可能になります。

---

## 変更点の概要

### 変更前
- LLMの応答はテキストのみ
- `ChatResponse`モデルには`message`フィールドのみ
- 音声出力機能なし

### 変更後
- LLMの応答をテキストと音声の両方で出力
- `ChatResponse`モデルに音声データフィールドを追加
- Qwen3-TTS-Flashを使用した音声合成機能を追加
- REST APIとWebSocketの両方で音声データを返送可能

---

## 詳細な変更内容

### 1. TTSサービスの実装

#### 1.1 新規ファイル: `src/backend/services/tts_service.py`

**変更内容**:
- Qwen3-TTS-Flash APIを使用した音声合成サービスを実装
- テキストを音声データ（バイナリ）に変換する機能を提供

**実装例**:
```python
"""
音声合成サービス - Qwen3-TTS-Flash
"""

import logging
import requests
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)


class TTSService:
    """Qwen3-TTS-Flashを使用した音声合成サービス"""
    
    def __init__(self) -> None:
        """TTSサービスの初期化"""
        self.api_key = settings.TTS_API_KEY or settings.DASHSCOPE_API_KEY
        self.model = settings.TTS_MODEL
        self.base_url = settings.TTS_BASE_URL
        
    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> bytes:
        """
        テキストを音声に変換
        
        Args:
            text: 変換するテキスト
            voice: 音声タイプ（デフォルト: "alloy"）
            speed: 再生速度（0.25-4.0、デフォルト: 1.0）
        
        Returns:
            音声データ（バイナリ、MP3形式）
        """
        if not self.api_key:
            logger.warning("TTS APIキーが設定されていません")
            return b""
        
        try:
            # Qwen3-TTS-Flash API呼び出し
            response = requests.post(
                f"{self.base_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": text,
                    "voice": voice or "alloy",
                    "speed": speed,
                },
                timeout=30,
            )
            
            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"TTS APIエラー: {response.status_code} - {response.text}")
                return b""
                
        except Exception as e:
            logger.error(f"TTS変換エラー: {e}")
            return b""
    
    def is_available(self) -> bool:
        """TTSサービスが利用可能かどうかを確認"""
        return bool(self.api_key)


# シングルトンインスタンス
tts_service = TTSService()
```

#### 1.2 設定ファイルの更新: `src/backend/config.py`

**変更内容**:
- TTS関連の設定を追加

**追加する設定**:
```python
# TTS (Text-to-Speech) 設定
TTS_API_KEY: str = os.getenv("TTS_API_KEY", "")
TTS_MODEL: str = os.getenv("TTS_MODEL", "qwen3-tts-flash-2025-11-27")
TTS_BASE_URL: str = os.getenv(
    "TTS_BASE_URL", 
    "https://dashscope.aliyuncs.com/api/v1/services/audio/tts"
)
TTS_VOICE: str = os.getenv("TTS_VOICE", "alloy")  # デフォルト音声
TTS_SPEED: float = float(os.getenv("TTS_SPEED", "1.0"))  # 再生速度
```

---

### 2. データモデルの拡張

#### 2.1 `ChatResponse`モデルの更新: `src/backend/models/chat.py`

**変更前**:
```python
class ChatResponse(BaseModel):
    """チャットレスポンス"""
    
    message: str = Field(..., description="AIからの応答")
    session_id: str = Field(..., description="セッションID")
    turn_count: int = Field(..., description="現在の会話ターン数")
    is_complete: bool = Field(False, description="目的地決定が完了したか")
    suggestions: list[str] = Field(default_factory=list, description="提案された選択肢")
```

**変更後**:
```python
class ChatResponse(BaseModel):
    """チャットレスポンス"""
    
    message: str = Field(..., description="AIからの応答")
    session_id: str = Field(..., description="セッションID")
    turn_count: int = Field(..., description="現在の会話ターン数")
    is_complete: bool = Field(False, description="目的地決定が完了したか")
    suggestions: list[str] = Field(default_factory=list, description="提案された選択肢")
    # 新規追加フィールド
    audio_data: Optional[str] = Field(
        None, 
        description="音声データ（Base64エンコードされたMP3データ）"
    )
    audio_url: Optional[str] = Field(
        None,
        description="音声データのURL（一時的なストレージを使用する場合）"
    )
    has_audio: bool = Field(
        False,
        description="音声データが含まれているかどうか"
    )
```

**注意事項**:
- `audio_data`はBase64エンコードされた文字列として返す（JSON互換性のため）
- 大きな音声ファイルの場合は`audio_url`を使用して一時的なストレージに保存
- `has_audio`フラグでクライアントが音声データの有無を判定可能

---

### 3. 会話サービスの更新

#### 3.1 `conversation_service.py`の更新

**変更内容**:
- LLM応答生成後にTTSで音声変換を実行
- `ChatResponse`に音声データを含める

**変更箇所**:
```python
# src/backend/services/conversation_service.py

from ..services.tts_service import tts_service
import base64

class ConversationService:
    """会話管理サービス（TTL付きキャッシュ）"""
    
    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """
        ユーザーメッセージを処理してレスポンスを生成する
        
        Args:
            request: チャットリクエスト
        
        Returns:
            チャットレスポンス（テキストと音声を含む）
        """
        # ... 既存の処理 ...
        
        # LLMで応答を生成
        llm_result = llm_service.generate_stopover_suggestion(...)
        
        # 応答テキストを取得
        response_text = llm_result["message"]
        
        # TTSで音声変換（オプション）
        audio_data = None
        has_audio = False
        
        if tts_service.is_available():
            try:
                audio_bytes = await tts_service.text_to_speech(response_text)
                if audio_bytes:
                    # Base64エンコード
                    audio_data = base64.b64encode(audio_bytes).decode("utf-8")
                    has_audio = True
            except Exception as e:
                logger.warning(f"TTS変換に失敗しました: {e}")
        
        # ChatResponseを作成
        return ChatResponse(
            message=response_text,
            session_id=session_id,
            turn_count=llm_result["turn_count"],
            is_complete=llm_result["is_complete"],
            suggestions=llm_result["suggestions"],
            audio_data=audio_data,
            has_audio=has_audio,
        )
```

**注意事項**:
- TTS変換は非同期処理として実装（`async/await`）
- TTS変換に失敗した場合は音声なしでテキストのみ返す
- パフォーマンスを考慮して、TTS変換はオプションとして実装

---

### 4. APIエンドポイントの更新

#### 4.1 REST APIエンドポイント: `src/backend/api/chat.py`

**変更内容**:
- `send_message()`エンドポイントは変更不要（`ChatResponse`モデルの変更により自動対応）
- 音声データを含むレスポンスを返す

**レスポンス例**:
```json
{
  "message": "今日はどこに行きたいですか？",
  "session_id": "abc123",
  "turn_count": 1,
  "is_complete": false,
  "suggestions": ["カフェ", "公園", "美術館"],
  "audio_data": "UklGRiQAAABXQVZFZm10...",
  "has_audio": true
}
```

#### 4.2 WebSocketエンドポイント: `src/backend/api/websocket.py`

**変更内容**:
- WebSocket経由で音声データをストリーミング送信
- 音声データはバイナリ形式で送信（Base64エンコード不要）

**実装例**:
```python
@router.websocket("/ws/voice/{session_id}")
async def websocket_voice_endpoint(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """音声ストリーミングエンドポイント"""
    await websocket.accept()
    
    try:
        while True:
            # 音声データを受信（ASR処理）
            audio_data = await websocket.receive_bytes()
            # ... ASR処理 ...
            
            # LLM応答を生成
            response = await conversation_service.process_message(request)
            
            # テキスト応答を送信
            await websocket.send_json({
                "type": "response",
                "message": response.message,
                "session_id": response.session_id,
                "turn_count": response.turn_count,
                "is_complete": response.is_complete,
                "suggestions": response.suggestions,
                "has_audio": response.has_audio,
            })
            
            # 音声データを送信（バイナリ）
            if response.has_audio and response.audio_data:
                audio_bytes = base64.b64decode(response.audio_data)
                await websocket.send_bytes(audio_bytes)
                
    except WebSocketDisconnect:
        # セッション終了処理
        pass
```

---

### 5. フロントエンドの更新

#### 5.1 ダッシュボードテンプレート: `src/backend/templates/dashboard.html`

**変更内容**:
- 音声データの再生機能を追加
- 音声プレーヤーのUIコンポーネントを追加

**追加するJavaScript**:
```javascript
// 音声データの再生
function playAudioResponse(audioData) {
    if (!audioData) return;
    
    // Base64デコード
    const audioBytes = atob(audioData);
    const audioArray = new Uint8Array(audioBytes.length);
    for (let i = 0; i < audioBytes.length; i++) {
        audioArray[i] = audioBytes.charCodeAt(i);
    }
    
    // Blobを作成
    const audioBlob = new Blob([audioArray], { type: 'audio/mpeg' });
    const audioUrl = URL.createObjectURL(audioBlob);
    
    // 音声を再生
    const audio = new Audio(audioUrl);
    audio.play();
    
    // クリーンアップ
    audio.addEventListener('ended', () => {
        URL.revokeObjectURL(audioUrl);
    });
}

// LLM応答を受信した際に音声を再生
async function sendMessageToLLM(message, inputType = 'general') {
    // ... 既存の処理 ...
    
    const data = await response.json();
    
    // 音声データがあれば再生
    if (data.has_audio && data.audio_data) {
        playAudioResponse(data.audio_data);
    }
    
    // ... 既存の処理 ...
}
```

**追加するUI要素**:
```html
<!-- 音声再生ボタン -->
<button 
    id="play-audio-btn" 
    class="hidden px-3 py-1 bg-emerald-500 hover:bg-emerald-600 rounded-lg text-sm"
    onclick="playLastAudioResponse()"
>
    🔊 音声を再生
</button>
```

---

### 6. 環境変数の追加

#### 6.1 `.env`ファイルへの追加

**追加する環境変数**:
```env
# TTS (Text-to-Speech) 設定
TTS_API_KEY=your_tts_api_key_here
TTS_MODEL=qwen3-tts-flash-2025-11-27
TTS_BASE_URL=https://dashscope.aliyuncs.com/api/v1/services/audio/tts
TTS_VOICE=alloy
TTS_SPEED=1.0
```

**注意事項**:
- `TTS_API_KEY`が設定されていない場合は、`DASHSCOPE_API_KEY`をフォールバックとして使用
- `TTS_MODEL`のデフォルト値は`qwen3-tts-flash-2025-11-27`（.envファイルで確認済み）

---

### 7. 依存関係の追加

#### 7.1 `requirements.txt`への追加

**追加するパッケージ**:
```txt
# 音声処理（既存のものに追加）
requests>=2.31.0  # TTS API呼び出し用（既存の可能性あり）
```

**注意事項**:
- `requests`は既にインストールされている可能性が高いが、明示的に記載
- 非同期処理のため、`aiohttp`を使用する場合は追加が必要

---

## 実装の優先順位

### Phase 1: 基本TTS機能（優先度: 高）
1. TTSサービスの実装（`tts_service.py`）
2. 設定ファイルの更新（`config.py`）
3. `ChatResponse`モデルの拡張（`models/chat.py`）
4. 会話サービスの更新（`conversation_service.py`）

### Phase 2: API統合（優先度: 高）
1. REST APIエンドポイントの動作確認
2. WebSocketエンドポイントの更新
3. エラーハンドリングの実装

### Phase 3: フロントエンド統合（優先度: 中）
1. ダッシュボードテンプレートの更新
2. 音声再生機能の実装
3. UI/UXの改善

### Phase 4: 最適化（優先度: 低）
1. 音声データのキャッシング
2. ストリーミング最適化
3. パフォーマンス監視

---

## 技術的な考慮事項

### 1. パフォーマンス

**課題**:
- TTS変換はAPI呼び出しのため、レイテンシが発生する可能性がある
- 大きなテキストの場合、音声ファイルサイズが大きくなる

**対策**:
- TTS変換を非同期処理として実装
- 音声データのキャッシング（同じテキストの場合は再利用）
- ストリーミングTTSの検討（将来の拡張）

### 2. ストレージ

**課題**:
- Base64エンコードによりデータサイズが約33%増加
- 大きな音声ファイルをJSONで送信するのは非効率

**対策**:
- 小さい音声ファイル（数秒程度）はBase64で送信
- 大きい音声ファイルは一時的なストレージに保存し、URLを返す
- クライアント側で音声データのサイズに応じて処理を分岐

### 3. エラーハンドリング

**課題**:
- TTS API呼び出しが失敗した場合の処理
- ネットワークエラーの処理

**対策**:
- TTS変換に失敗した場合は音声なしでテキストのみ返す
- エラーログを記録してデバッグ可能にする
- クライアント側で`has_audio`フラグを確認して適切に処理

### 4. セキュリティ

**課題**:
- 音声データの送信時のセキュリティ
- APIキーの管理

**対策**:
- HTTPS接続の強制（本番環境）
- APIキーは環境変数で管理
- 音声データの暗号化（必要に応じて）

---

## テスト要件

### 1. ユニットテスト

- TTSサービスのテスト（モックAPIを使用）
- `ChatResponse`モデルのテスト
- Base64エンコード/デコードのテスト

### 2. 統合テスト

- REST APIエンドポイントのテスト
- WebSocketエンドポイントのテスト
- エンドツーエンドのテスト（テキスト入力→音声出力）

### 3. パフォーマンステスト

- TTS変換のレイテンシ測定
- 音声ファイルサイズの測定
- 同時リクエストの負荷テスト

---

## 互換性の維持

### 1. 後方互換性

- `audio_data`フィールドはオプショナル（既存クライアントは影響なし）
- `has_audio`フラグで音声データの有無を判定可能
- TTSサービスが利用できない場合は音声なしで動作

### 2. 既存機能への影響

- 既存のテキスト応答機能は変更なし
- 音声出力は追加機能として実装
- 既存のテストは引き続き動作する必要がある

---

## 関連ドキュメント

- `docs/requirements_diff_mobile_voice.md`: モバイルアプリ対応と音声ストリーミング機能
- `docs/sample_tts.md`: TTSサンプルコード
- `src/backend/services/speech_service.py`: 音声認識サービス（ASR）
- `src/backend/models/chat.py`: チャットデータモデル

---

## 変更履歴

| 日付 | バージョン | 変更内容 | 作成者 |
|------|-----------|---------|--------|
| 2025-01-27 | 1.0.0 | 初版作成 | - |

