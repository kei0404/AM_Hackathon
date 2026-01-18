# LLM の想定レスポンス - WebSocket仕様

**作成日**: 2025-01-27  
**バージョン**: 2.0.0  
**ステータス**: Draft

---

## 前提

これはナビゲーションアプリのバックエンドアプリです。クライアント（モバイルアプリ、Webブラウザ）との通信は**WebSocket**を使用してリアルタイムで行います。

---

## 会話の挙動

### 1. 現在地情報の受信

**クライアント → サーバー（WebSocket）**:
```json
{
    "type": "text",
    "text": "東京駅"
}
```

または位置情報を含むセッション開始時:
```json
{
    "type": "location",
    "location_data": {
        "latitude": 35.6812,
        "longitude": 139.7671,
        "address": "東京都千代田区丸の内1-9-1"
    }
}
```

**サーバー → クライアント（WebSocket）**:
```json
{
    "type": "response",
    "message": "どこに行きたいですか？",
    "session_id": "abc123-def456",
    "turn_count": 1,
    "is_complete": false,
    "suggestions": [],
    "has_audio": true
}
```

### 2. 目的地情報の取得

**クライアント → サーバー（WebSocket）**:
```json
{
    "type": "text",
    "text": "横浜駅に行きたい"
}
```

または音声認識結果:
```json
{
    "type": "transcription",
    "text": "横浜駅に行きたい",
    "is_final": true
}
```

**サーバー → クライアント（WebSocket）**:
```json
{
    "type": "response",
    "message": "横浜駅ですね。他に行きたいところ、やってみたいことはありますか？",
    "session_id": "abc123-def456",
    "turn_count": 2,
    "is_complete": false,
    "suggestions": [],
    "has_audio": true
}
```

### 3. RAG検索と提案

**クライアント → サーバー（WebSocket）**:
```json
{
    "type": "text",
    "text": "カフェに行きたい"
}
```

**サーバー処理**:
1. RAG検索を実行（ChromaDB）
2. 検索結果を取得
3. LLMで提案を生成（最大3つ）

**サーバー → クライアント（WebSocket）**:
```json
{
    "type": "response",
    "message": "カフェですね。おすすめのカフェを3つご提案します。\n1つ目: Blue Bottle Coffee 清澄白河\nここに行きますか？",
    "session_id": "abc123-def456",
    "turn_count": 2,
    "is_complete": false,
    "suggestions": [
        "はい、そこに行きます",
        "いいえ、次の提案を見たい"
    ],
    "suggestion_index": 1,
    "suggestion_total": 3,
    "has_audio": true
}
```

---

## 提案フローの詳細仕様

### 提案の受け入れ/拒否

#### 1つ目の提案で賛成した場合

**クライアント → サーバー（WebSocket）**:
```json
{
    "type": "text",
    "text": "はい、そこに行きます"
}
```

または:
```json
{
    "type": "suggestion_selected",
    "suggestion_index": 1,
    "accepted": true
}
```

**サーバー → クライアント（WebSocket）**:
```json
{
    "type": "response",
    "message": "了解しました。目的地は横浜駅、立ち寄る場所はBlue Bottle Coffee 清澄白河です。",
    "session_id": "abc123-def456",
    "turn_count": 3,
    "is_complete": true,
    "suggestions": [],
    "destination": "横浜駅",
    "stopover": "Blue Bottle Coffee 清澄白河",
    "has_audio": true
}
```

#### 1つ目の提案で拒否した場合

**クライアント → サーバー（WebSocket）**:
```json
{
    "type": "text",
    "text": "いいえ、次の提案を見たい"
}
```

または:
```json
{
    "type": "suggestion_selected",
    "suggestion_index": 1,
    "accepted": false
}
```

**サーバー → クライアント（WebSocket）**:
```json
{
    "type": "response",
    "message": "2つ目: 代々木公園の近くのカフェ\nここに行きますか？",
    "session_id": "abc123-def456",
    "turn_count": 2,
    "is_complete": false,
    "suggestions": [
        "はい、そこに行きます",
        "いいえ、次の提案を見たい"
    ],
    "suggestion_index": 2,
    "suggestion_total": 3,
    "has_audio": true
}
```

#### 2つ目の提案で拒否した場合

**サーバー → クライアント（WebSocket）**:
```json
{
    "type": "response",
    "message": "3つ目: 森美術館の近くのカフェ\nここに行きますか？",
    "session_id": "abc123-def456",
    "turn_count": 2,
    "is_complete": false,
    "suggestions": [
        "はい、そこに行きます",
        "いいえ、他の希望を伝える"
    ],
    "suggestion_index": 3,
    "suggestion_total": 3,
    "has_audio": true
}
```

#### 3つ全ての提案で拒否した場合

**サーバー → クライアント（WebSocket）**:
```json
{
    "type": "response",
    "message": "他に希望はありますか？",
    "session_id": "abc123-def456",
    "turn_count": 2,
    "is_complete": false,
    "suggestions": [],
    "has_audio": true
}
```

### 他の希望がある場合

**クライアント → サーバー（WebSocket）**:
```json
{
    "type": "text",
    "text": "美術館にも行きたい"
}
```

**サーバー → クライアント（WebSocket）**:
```json
{
    "type": "response",
    "message": "美術館ですね。他に行きたいところ、やってみたいことはありますか？",
    "session_id": "abc123-def456",
    "turn_count": 2,
    "is_complete": false,
    "suggestions": [],
    "has_audio": true
}
```

### 他の希望がない場合

**クライアント → サーバー（WebSocket）**:
```json
{
    "type": "text",
    "text": "特にない"
}
```

**サーバー → クライアント（WebSocket）**:
```json
{
    "type": "response",
    "message": "了解しました。目的地は横浜駅です。直行します。",
    "session_id": "abc123-def456",
    "turn_count": 3,
    "is_complete": true,
    "suggestions": [],
    "destination": "横浜駅",
    "stopover": null,
    "has_audio": true
}
```

---

## WebSocketメッセージ形式

### クライアント → サーバー

#### テキストメッセージ
```json
{
    "type": "text",
    "text": "ユーザーの入力テキスト"
}
```

#### 提案選択
```json
{
    "type": "suggestion_selected",
    "suggestion_index": 1,
    "accepted": true
}
```

#### 位置情報
```json
{
    "type": "location",
    "location_data": {
        "latitude": 35.6812,
        "longitude": 139.7671,
        "address": "東京都千代田区丸の内1-9-1"
    }
}
```

#### ASRコマンド
```json
{
    "type": "start_asr"
}
```

```json
{
    "type": "stop_asr"
}
```

### サーバー → クライアント

#### 通常の応答
```json
{
    "type": "response",
    "message": "AIからの応答テキスト",
    "session_id": "abc123-def456",
    "turn_count": 2,
    "is_complete": false,
    "suggestions": ["選択肢1", "選択肢2"],
    "suggestion_index": 1,
    "suggestion_total": 3,
    "destination": "横浜駅",
    "stopover": "Blue Bottle Coffee",
    "has_audio": true
}
```

#### 音声認識結果（途中）
```json
{
    "type": "transcription",
    "text": "認識されたテキスト",
    "is_final": false
}
```

#### 音声認識結果（最終）
```json
{
    "type": "transcription",
    "text": "認識されたテキスト",
    "is_final": true
}
```

#### 音声データ（バイナリ）
- `Blob`形式で送信
- `has_audio: true`のレスポンスの後に送信される

#### エラー
```json
{
    "type": "error",
    "message": "エラーメッセージ"
}
```

---

## 会話フロー図

```
[セッション開始]
    ↓
[現在地受信] → "どこに行きたいですか？"
    ↓
[目的地受信] → "他に行きたいところ、やってみたいことはありますか？"
    ↓
[希望受信] → RAG検索 → 提案1: "ここに行きますか？"
    ↓
[賛成] → [旅程決定] → "目的地は〇〇、立ち寄る場所は〇〇です"
    ↓
[拒否] → 提案2: "ここに行きますか？"
    ↓
[賛成] → [旅程決定]
    ↓
[拒否] → 提案3: "ここに行きますか？"
    ↓
[賛成] → [旅程決定]
    ↓
[拒否] → "他に希望はありますか？"
    ↓
[希望あり] → "他に行きたいところ、やってみたいことはありますか？"
    ↓
[希望なし] → [旅程決定] → "目的地は〇〇です。直行します。"
```

---

## 実装要件

### 1. 提案の管理

- 提案は最大3つまで
- 各提案に対して「ここに行きますか？」と質問
- 提案のインデックス（1, 2, 3）を管理
- 提案を受け入れた時点で旅程を決定

### 2. RAG検索

- ユーザーの「行きたいところ・やってみたいこと」に対してRAG検索を実行
- ChromaDBから類似度の高い訪問履歴を取得
- 検索結果をLLMのコンテキストに含める

### 3. 旅程決定

- 提案を受け入れた時点で決定
- 目的地と立ち寄り場所を明確に返す
- `is_complete: true`を設定

### 4. WebSocket通信

- すべての応答をWebSocket経由で送信
- 音声データはバイナリ（Blob）として送信
- テキスト応答はJSON形式で送信

---

## 注意事項

1. **提案の順序**: 1つ目 → 2つ目 → 3つ目の順で提案
2. **旅程決定**: 提案を受け入れた時点で即座に決定（他の希望は質問しない）
3. **音声出力**: すべての応答に対してTTSで音声を生成し、クライアントに送信
4. **状態管理**: セッション内で会話の状態（フェーズ、提案インデックス）を管理
5. **エラーハンドリング**: エラー発生時は適切なエラーメッセージをWebSocket経由で送信

---

## 関連ドキュメント

- `docs/client_api_specification.md`: クライアントAPI仕様書
- `src/backend/api/websocket.py`: WebSocketエンドポイント実装
- `src/backend/services/conversation_service.py`: 会話管理サービス

---

## 変更履歴

| 日付 | バージョン | 変更内容 | 作成者 |
|------|-----------|---------|--------|
| 2025-01-27 | 2.0.0 | WebSocket仕様に更新 | - |





