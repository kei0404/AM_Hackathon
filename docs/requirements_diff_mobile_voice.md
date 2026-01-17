# 要件差分: モバイルアプリ対応と音声ストリーミング機能

**作成日**: 2025-01-27  
**バージョン**: 1.0.0  
**ステータス**: Draft  
**関連仕様**: `specs/001-navi-schedule/spec.md` v2.3.0

---

## 概要

React NativeモバイルアプリからのHTTPS接続によるリクエスト処理と、WebSocketを使用した音声ストリーミング入力機能を追加します。既存のWebアプリケーション（ブラウザベース）との互換性を保ちつつ、モバイルアプリと音声入力に対応します。

---

## 変更点の概要

### 1. クライアント入力ソースの拡張

**変更前**:
- Webアプリケーション（ブラウザ）からのHTTPリクエストのみ
- テキスト入力のみ対応

**変更後**:
- React NativeモバイルアプリからのHTTPSリクエストに対応
- Webアプリケーション（ブラウザ）からのHTTPリクエストも継続サポート
- テスト用ターミナル入力も可能
- 音声ストリーミング入力（WebSocket）に対応

---

## 詳細な変更内容

### 1.1 モバイルアプリからのHTTPS接続

#### 変更内容
- React NativeモバイルアプリからのHTTPS接続によるリクエストを受け付ける
- 既存のREST APIエンドポイントをモバイルアプリからも利用可能にする
- CORS設定を更新してモバイルアプリのオリジンを許可

#### 影響範囲
- `src/backend/main.py`: CORS設定の更新
- `src/backend/api/chat.py`: エンドポイントの互換性確保
- 認証・認可: モバイルアプリ用の認証方式を検討（APIキー、トークンベース等）

#### 実装要件
- HTTPS接続のサポート（本番環境）
- モバイルアプリのUser-Agent識別
- エラーハンドリングとレスポンス形式の統一

---

### 1.2 位置情報の自動取得

#### 変更内容
- `/chat/start`エンドポイントに位置情報（GPS座標）を含める
- クライアントから送信された位置情報を現在地として自動設定
- 位置情報が提供されない場合は既存の動作を維持（手動入力またはデフォルト値）

#### API変更

**変更前**:
```python
class WelcomeRequest(BaseModel):
    session_id: Optional[str] = None
    user_preferences: Optional[dict] = None
    favorite_spots: Optional[list[dict]] = None
```

**変更後**:
```python
class WelcomeRequest(BaseModel):
    session_id: Optional[str] = None
    user_preferences: Optional[dict] = None
    favorite_spots: Optional[list[dict]] = None
    current_location: Optional[LocationData] = None  # 新規追加

class LocationData(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None  # 住所（逆ジオコーディング結果）
    accuracy: Optional[float] = None  # GPS精度（メートル）
```

#### 処理フロー
1. クライアント（モバイルアプリ）が`/chat/start`を呼び出す際に位置情報を含める
2. サーバー側で位置情報を受け取り、`ConversationContext`の`current_location`に設定
3. 位置情報が文字列形式の場合はそのまま使用、GPS座標の場合は逆ジオコーディングを実行（オプション）

#### 影響範囲
- `src/backend/api/chat.py`: `start_conversation()`関数の更新
- `src/backend/models/chat.py`: `WelcomeRequest`モデルの更新
- `src/backend/services/conversation_service.py`: 位置情報の処理ロジック追加

---

### 1.3 目的地と質問応答のクライアント入力

#### 変更内容
- 目的地情報をクライアントから取得
- 質問に対する応答もクライアントから取得
- 既存のテキスト入力方式も継続サポート

#### API変更

**変更前**:
```python
class ChatRequest(BaseModel):
    session_id: str
    message: str
    current_location: Optional[str] = None
    destination: Optional[str] = None
```

**変更後**:
```python
class ChatRequest(BaseModel):
    session_id: str
    message: str
    current_location: Optional[str] = None
    destination: Optional[str] = None
    # 新規追加フィールド
    response_type: Optional[str] = None  # "text", "voice", "selection"
    selected_suggestion: Optional[str] = None  # 選択肢が選ばれた場合
    location_data: Optional[LocationData] = None  # GPS座標形式の位置情報
```

#### 処理フロー
1. クライアントが`/chat/message`を呼び出す際に、テキストメッセージまたは選択された提案を含める
2. サーバー側でメッセージタイプを判定し、適切に処理
3. 目的地が指定された場合は`ConversationContext`の`destination`に設定

#### 影響範囲
- `src/backend/api/chat.py`: `send_message()`関数の更新
- `src/backend/models/chat.py`: `ChatRequest`モデルの更新
- `src/backend/services/conversation_service.py`: 応答タイプの処理ロジック追加

---

### 1.4 テスト用ターミナル入力のサポート

#### 変更内容
- 既存のCLIツール（`scripts/chat_cli.py`）を拡張
- ターミナルから位置情報、目的地、質問応答を入力可能にする
- モバイルアプリと同等の機能をテストできるようにする

#### 実装要件
- `scripts/chat_cli.py`の拡張
- 位置情報の手動入力またはデフォルト値の設定
- 対話的なCLIインターフェースの改善

#### 影響範囲
- `scripts/chat_cli.py`: CLIツールの機能拡張
- テストシナリオの追加

---

### 1.5 WebSocketによる音声ストリーミング入力

#### 変更内容
- WebSocketエンドポイントを追加して音声ストリーミング入力に対応
- 音声データをリアルタイムで受信し、音声認識（STT）を実行
- 音声認識結果をテキストメッセージとして処理
- 応答を音声合成（TTS）してクライアントに返送

#### 新規エンドポイント

```python
@router.websocket("/ws/voice/{session_id}")
async def websocket_voice_endpoint(
    websocket: WebSocket,
    session_id: str
):
    """
    音声ストリーミング入力エンドポイント
    
    処理フロー:
    1. WebSocket接続を確立
    2. クライアントから音声データ（バイナリ）を受信
    3. Qwen3-ASR-Flash-Realtimeで音声認識を実行
    4. 認識結果をテキストメッセージとして処理
    5. LLMで応答を生成
    6. 応答を音声合成（TTS）してクライアントに返送
    """
```

#### 音声処理フロー
1. **接続確立**: クライアントがWebSocket接続を開始
2. **音声受信**: クライアントから音声データ（バイナリ）をストリーミング受信
3. **音声認識**: Qwen3-ASR-Flash-Realtime APIを使用して音声をテキストに変換
4. **メッセージ処理**: 認識されたテキストを既存の`process_message()`で処理
5. **応答生成**: LLMで応答を生成
6. **音声合成**: 応答テキストを音声に変換（TTS）
7. **音声送信**: 音声データをクライアントに返送

#### 音声処理サービス

**新規ファイル**: `src/backend/services/speech_service.py`

```python
class SpeechService:
    """音声処理サービス"""
    
    async def transcribe_audio_stream(
        self,
        audio_stream: bytes
    ) -> str:
        """
        Qwen3-ASR-Flash-Realtimeを使用して音声をテキストに変換
        
        Args:
            audio_stream: 音声データ（バイナリ）
        
        Returns:
            認識されたテキスト
        """
        # Qwen3-ASR-Flash-Realtime API呼び出し
        pass
    
    async def text_to_speech(
        self,
        text: str
    ) -> bytes:
        """
        テキストを音声に変換（TTS）
        
        Args:
            text: 変換するテキスト
        
        Returns:
            音声データ（バイナリ）
        """
        # TTS API呼び出し（Qwen TTSまたは他のサービス）
        pass
```

#### Qwen3-ASR-Flash-Realtime仕様

- **API**: DashScope Qwen3-ASR-Flash-Realtime
- **入力形式**: 音声データ（バイナリ、WAV/MP3等）
- **出力形式**: テキスト（JSON形式）
- **リアルタイム性**: ストリーミング対応
- **設定**: `src/backend/config.py`にAPI設定を追加

```python
# config.py への追加
QWEN_ASR_API_KEY: str = os.getenv("QWEN_ASR_API_KEY", "")
QWEN_ASR_MODEL: str = "qwen3-asr-flash-realtime"
QWEN_ASR_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/..."
```

#### 影響範囲
- `src/backend/api/websocket.py`: 新規作成（WebSocketエンドポイント）
- `src/backend/services/speech_service.py`: 新規作成（音声処理サービス）
- `src/backend/config.py`: 音声処理API設定の追加
- `src/backend/main.py`: WebSocketルーターの登録
- `requirements.txt`: WebSocket関連ライブラリの追加

---

## 技術的な実装要件

### 2.1 依存関係の追加

**requirements.txt への追加**:
```txt
# WebSocket
websockets>=12.0
python-socketio>=5.10.0

# 音声処理
dashscope>=1.14.0  # 既存（Qwen ASR用）
pydub>=0.25.1  # 音声ファイル処理
```

### 2.2 エラーハンドリング

- WebSocket接続エラーの処理
- 音声認識エラーの処理（タイムアウト、無音検出等）
- ネットワーク切断時の再接続ロジック
- セッションタイムアウトの処理

### 2.3 セキュリティ

- WebSocket接続の認証（セッションID検証）
- HTTPS接続の強制（本番環境）
- 音声データの暗号化（必要に応じて）
- CORS設定の適切な管理

### 2.4 パフォーマンス

- 音声ストリーミングのバッファリング
- 非同期処理によるレイテンシ削減
- 接続数の制限（同時接続数）
- メモリ使用量の最適化

---

## 互換性の維持

### 3.1 既存機能との互換性

- 既存のWebアプリケーション（ブラウザ）からのHTTPリクエストは継続して動作
- 既存のAPIエンドポイントの動作は変更しない（後方互換性）
- 新機能はオプショナルなフィールドとして追加

### 3.2 データ形式の統一

- 位置情報は文字列形式とGPS座標形式の両方に対応
- メッセージはテキスト形式を基本とし、音声は内部でテキストに変換
- レスポンス形式は既存の`ChatResponse`モデルを維持

---

## テスト要件

### 4.1 ユニットテスト

- 位置情報の処理ロジック
- 音声認識サービスのモックテスト
- WebSocket接続のテスト

### 4.2 統合テスト

- モバイルアプリからのHTTPS接続テスト
- WebSocket音声ストリーミングのエンドツーエンドテスト
- ターミナルCLIツールのテスト

### 4.3 パフォーマンステスト

- 音声ストリーミングのレイテンシ測定
- 同時接続数の負荷テスト
- メモリ使用量の監視

---

## 実装の優先順位

### Phase 1: モバイルアプリ対応（優先度: 高）
1. HTTPS接続のサポート
2. 位置情報の自動取得機能
3. 目的地と質問応答のクライアント入力
4. テスト用ターミナル入力の拡張

### Phase 2: 音声ストリーミング（優先度: 中）
1. WebSocketエンドポイントの実装
2. 音声処理サービスの実装（Qwen3-ASR-Flash-Realtime統合）
3. 音声合成（TTS）の実装
4. エラーハンドリングと再接続ロジック

### Phase 3: 最適化とテスト（優先度: 低）
1. パフォーマンス最適化
2. セキュリティ強化
3. 包括的なテストの実装

---

## 注意事項

### 5.1 既存コードへの影響

- 既存のAPIエンドポイントは後方互換性を維持
- 新機能はオプショナルなフィールドとして追加
- 既存のテストは引き続き動作する必要がある

### 5.2 外部サービス依存

- Qwen3-ASR-Flash-Realtime APIの可用性に依存
- TTSサービスの選択（Qwen TTSまたは他のサービス）
- APIキーの管理とセキュリティ

### 5.3 モバイルアプリ側の要件

- React Nativeアプリ側での位置情報取得実装
- WebSocketクライアントの実装
- 音声録音・再生機能の実装
- エラーハンドリングとUIフィードバック

---

## 関連ドキュメント

- `specs/001-navi-schedule/spec.md`: 基本仕様書
- `src/backend/api/chat.py`: 既存のチャットAPI
- `src/backend/services/conversation_service.py`: 会話管理サービス
- `scripts/chat_cli.py`: CLIテストツール

---

## 変更履歴

| 日付 | バージョン | 変更内容 | 作成者 |
|------|-----------|---------|--------|
| 2025-01-27 | 1.0.0 | 初版作成 | - |

