# WebSocketセッション自動生成機能 仕様書

## 概要

WebSocketエンドポイントにおいて、セッションIDを事前に取得しなくても、サーバー側で自動的にセッションを生成して接続できるようにする機能の仕様書です。

## 変更日

2024年12月

## 変更の目的

従来は、WebSocket接続前に`POST /api/v1/chat/start`を呼び出してセッションIDを取得する必要がありました。この変更により、クライアントはセッションIDを事前に取得せずに、直接WebSocket接続を開始できるようになります。

### メリット

1. **シンプルな接続フロー**: クライアント側の実装が簡素化される
2. **柔軟性の向上**: セッションIDを指定するか、自動生成するかを選択可能
3. **後方互換性**: 既存のセッションID指定方式も引き続き利用可能

## 変更対象エンドポイント

以下の2つのWebSocketエンドポイントが変更対象です：

1. `/api/v1/ws/voice/{session_id}` - 音声ストリーミング入力
2. `/api/v1/ws/chat/{session_id}` - テキストチャット

## 変更前の動作

### 従来の動作フロー

1. クライアントが`POST /api/v1/chat/start`を呼び出してセッションIDを取得
2. 取得したセッションIDを使用してWebSocket接続を開始
3. セッションが存在しない場合、エラーメッセージを返して接続を閉じる

### エラーケース

```json
{
    "type": "error",
    "message": "セッションが見つかりません。先にセッションを開始してください。"
}
```

## 変更後の動作

### 新しい動作フロー

1. クライアントがWebSocket接続を開始（セッションIDは任意）
2. サーバー側でセッションIDの存在を確認
3. セッションが存在しない場合、自動的に新しいセッションを生成
4. 生成されたセッションIDをクライアントに返送
5. 接続を継続

### 接続成功時のレスポンス

```json
{
    "type": "connected",
    "message": "WebSocket接続が確立されました",
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## 実装の詳細

### サーバー側の実装

#### 変更ファイル

- `src/backend/api/websocket.py`

#### 実装ロジック

```python
# セッションの確認 - 存在しない場合は自動生成
original_session_id = session_id
context = conversation_service.get_session(session_id)
if not context:
    # セッションが存在しない場合、自動的に作成
    session_id = conversation_service.create_session()
    context = conversation_service.get_session(session_id)
    logger.info(f"新しいセッションを自動生成: {session_id}")

# WebSocket接続を確立（新しいセッションIDで）
await manager.connect(websocket, session_id)

# 古いセッションIDで接続が登録されていた場合は削除
if original_session_id != session_id and original_session_id in manager.active_connections:
    del manager.active_connections[original_session_id]
```

### セッションIDの生成方法

- UUID v4形式の文字列（例: `550e8400-e29b-41d4-a716-446655440000`）
- `conversation_service.create_session()`を使用して生成
- セッションの有効期限はデフォルト30分（TTL: 1800秒）

## クライアント側の使用方法

### 方法1: セッションIDを指定しない（自動生成）

```javascript
// 任意の文字列をセッションIDとして指定（存在しない場合は自動生成される）
const ws = new WebSocket('ws://your-api-url/api/v1/ws/voice/new-session');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'connected') {
        const sessionId = data.session_id;  // サーバーから返されたセッションIDを取得
        console.log('セッションID:', sessionId);
        // 以降、このセッションIDを使用して他のAPIを呼び出すことが可能
    }
};
```

### 方法2: 既存のセッションIDを指定

```javascript
// 既存のセッションIDを使用（従来通り）
const existingSessionId = '550e8400-e29b-41d4-a716-446655440000';
const ws = new WebSocket(`ws://your-api-url/api/v1/ws/voice/${existingSessionId}`);

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'connected') {
        console.log('既存セッションに接続:', data.session_id);
    }
};
```

### 方法3: 事前にセッションIDを取得してから接続（従来方式）

```javascript
// 従来の方式も引き続き利用可能
const response = await fetch('/api/v1/chat/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
});

const data = await response.json();
const sessionId = data.session_id;

const ws = new WebSocket(`ws://your-api-url/api/v1/ws/voice/${sessionId}`);
```

## 完全な実装例

### React Nativeでの使用例

```javascript
import { useEffect, useState } from 'react';

const VoiceChatScreen = () => {
    const [sessionId, setSessionId] = useState(null);
    const [ws, setWs] = useState(null);

    useEffect(() => {
        // セッションIDを取得せずに直接WebSocket接続
        const websocket = new WebSocket('ws://your-api-url/api/v1/ws/voice/auto');
        
        websocket.onopen = () => {
            console.log('WebSocket接続開始');
        };

        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'connected') {
                // サーバーから返されたセッションIDを保存
                setSessionId(data.session_id);
                console.log('セッションID取得:', data.session_id);
            } else if (data.type === 'response') {
                console.log('AI応答:', data.message);
            }
        };

        websocket.onerror = (error) => {
            console.error('WebSocketエラー:', error);
        };

        setWs(websocket);

        return () => {
            websocket.close();
        };
    }, []);

    const sendAudio = (audioData) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(audioData);
        }
    };

    return (
        // UIコンポーネント
    );
};
```

### JavaScript/TypeScriptでの使用例

```typescript
class VoiceChatClient {
    private ws: WebSocket | null = null;
    private sessionId: string | null = null;

    async connect(): Promise<string> {
        return new Promise((resolve, reject) => {
            // セッションIDを指定せずに接続（自動生成される）
            this.ws = new WebSocket('ws://your-api-url/api/v1/ws/voice/auto');
            
            this.ws.onopen = () => {
                console.log('WebSocket接続確立');
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'connected') {
                    this.sessionId = data.session_id;
                    resolve(data.session_id);
                } else if (data.type === 'error') {
                    reject(new Error(data.message));
                }
            };

            this.ws.onerror = (error) => {
                reject(error);
            };
        });
    }

    sendAudio(audioData: ArrayBuffer): void {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(audioData);
        }
    }

    disconnect(): void {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}
```

## 互換性

### 後方互換性

- **完全な後方互換性を維持**: 既存のセッションID指定方式は引き続き動作します
- **既存のクライアントコード**: 変更なしで動作し続けます
- **既存のAPI**: `POST /api/v1/chat/start`エンドポイントは引き続き利用可能です

### 推奨される使用方法

1. **新規実装**: セッションID自動生成機能を使用（シンプル）
2. **既存実装**: 従来の方式を継続使用可能（変更不要）
3. **ハイブリッド**: 必要に応じて両方の方式を組み合わせ可能

## API仕様の更新

### WebSocketエンドポイント

#### `/api/v1/ws/voice/{session_id}`

**変更点:**
- `session_id`パラメータは任意の文字列を指定可能
- 存在しないセッションIDが指定された場合、自動的に新しいセッションを生成
- 接続成功時に`session_id`フィールドを含むレスポンスを返送

**レスポンス形式:**

```json
{
    "type": "connected",
    "message": "WebSocket接続が確立されました",
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `/api/v1/ws/chat/{session_id}`

**変更点:**
- `session_id`パラメータは任意の文字列を指定可能
- 存在しないセッションIDが指定された場合、自動的に新しいセッションを生成
- 接続成功時に`session_id`フィールドを含むレスポンスを返送

**レスポンス形式:**

```json
{
    "type": "connected",
    "message": "チャットセッションが開始されました",
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## エラーハンドリング

### エラーケース

この変更により、セッションが見つからないエラーは発生しなくなります。ただし、以下のエラーは引き続き発生する可能性があります：

1. **ネットワークエラー**: WebSocket接続の確立に失敗
2. **サーバーエラー**: セッション生成時の内部エラー
3. **認証エラー**: 将来的に認証機能が追加された場合

### エラーレスポンス例

```json
{
    "type": "error",
    "message": "セッション生成に失敗しました"
}
```

## ログ出力

### サーバー側のログ

セッションが自動生成された場合、以下のログが出力されます：

```
INFO: 新しいセッションを自動生成: 550e8400-e29b-41d4-a716-446655440000
INFO: WebSocket接続: 550e8400-e29b-41d4-a716-446655440000
```

## テストケース

### テストシナリオ

1. **新規セッション自動生成**
   - 存在しないセッションIDで接続
   - 新しいセッションが生成されることを確認
   - セッションIDがレスポンスに含まれることを確認

2. **既存セッション使用**
   - 既存のセッションIDで接続
   - 既存のセッションが使用されることを確認

3. **後方互換性**
   - 従来の方式（事前にセッションID取得）で接続
   - 正常に動作することを確認

## 今後の拡張可能性

1. **セッションIDの形式検証**: 将来的に特定の形式を要求する場合
2. **認証機能**: セッション生成時に認証情報を要求する場合
3. **セッション設定**: 接続時にセッションの設定を指定する場合

## 関連ドキュメント

- `docs/client_api_specification.md` - クライアントAPI仕様書
- `src/backend/api/websocket.py` - 実装コード
- `src/backend/services/conversation_service.py` - セッション管理サービス

## 変更履歴

- 2024年12月: 初版作成（セッション自動生成機能追加）

