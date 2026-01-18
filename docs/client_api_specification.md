# クライアントAPI仕様書 - データ受け渡しガイド

**作成日**: 2025-01-27  
**バージョン**: 1.0.0  
**ステータス**: Draft

---

## 概要

このドキュメントでは、Data Plug Copilotアプリケーションとクライアント（モバイルアプリ、Webブラウザ）間のデータ受け渡しの仕様を説明します。

主な通信方式:
- **WebSocket**: 音声ストリーミングとリアルタイムテキストチャット
- **REST API**: テキストメッセージと位置情報の送受信

---

## 目次

1. [WebSocket接続](#websocket接続)
2. [音声ストリーミング](#音声ストリーミング)
3. [テキストチャット](#テキストチャット)
4. [REST API](#rest-api)
5. [位置情報の扱い](#位置情報の扱い)
6. [レスポンス形式](#レスポンス形式)
7. [実装例](#実装例)

---

## WebSocket接続

### エンドポイント

#### 音声ストリーミング
```
ws://localhost:8000/api/v1/ws/voice/{session_id}
wss://your-domain.com/api/v1/ws/voice/{session_id}  # HTTPS環境
```

#### テキストチャット
```
ws://localhost:8000/api/v1/ws/chat/{session_id}
wss://your-domain.com/api/v1/ws/chat/{session_id}  # HTTPS環境
```

### 接続の確立

```javascript
const sessionId = "your-session-id"; // 先にセッションを開始して取得

// 音声ストリーミング
const voiceWsUrl = `ws://localhost:8000/api/v1/ws/voice/${sessionId}`;
const voiceWs = new WebSocket(voiceWsUrl);
voiceWs.binaryType = 'blob'; // バイナリデータをBlobとして受信

// テキストチャット
const chatWsUrl = `ws://localhost:8000/api/v1/ws/chat/${sessionId}`;
const chatWs = new WebSocket(chatWsUrl);
```

---

## 音声ストリーミング

### クライアント → サーバー（送信）

#### 1. 音声データ（バイナリ）

**形式**: PCM音声データ（16kHz, 16bit, モノラル）

```javascript
// Float32ArrayからInt16Arrayに変換
function convertFloat32ToInt16(float32Array) {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
        // -1.0 ~ 1.0 の範囲を -32768 ~ 32767 に変換
        const s = Math.max(-1, Math.min(1, float32Array[i]));
        int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16Array;
}

// 音声データを送信
const pcmData = convertFloat32ToInt16(audioData);
voiceWs.send(pcmData.buffer); // ArrayBufferとして送信
```

#### 2. コマンド（JSON）

```javascript
// ASR開始
voiceWs.send(JSON.stringify({ 
    type: "start_asr" 
}));

// ASR停止
voiceWs.send(JSON.stringify({ 
    type: "stop_asr" 
}));

// テキスト入力（音声認識をスキップして直接テキストを送信）
voiceWs.send(JSON.stringify({ 
    type: "text", 
    text: "東京駅に行きたい" 
}));

// ハートビート
voiceWs.send(JSON.stringify({ 
    type: "ping" 
}));
```

### サーバー → クライアント（受信）

#### 1. テキスト応答（JSON）

```javascript
voiceWs.onmessage = (event) => {
    // バイナリデータ（音声）かテキストデータ（JSON）かを判定
    if (event.data instanceof Blob) {
        // 音声データ（後述）
        playAudioBlob(event.data);
    } else if (typeof event.data === 'string') {
        // JSONデータ
        const data = JSON.parse(event.data);
        handleVoiceMessage(data);
    }
};

function handleVoiceMessage(data) {
    switch (data.type) {
        case "connected":
            // 接続完了
            // {
            //   "type": "connected",
            //   "message": "WebSocket接続が確立されました",
            //   "session_id": "abc123-def456"
            // }
            console.log(data.message);
            break;
            
        case "transcription":
            // 音声認識結果（途中結果と最終結果）
            // {
            //   "type": "transcription",
            //   "text": "東京駅に行きたい",
            //   "is_final": true  // true: 最終結果, false: 途中結果
            // }
            console.log(data.text);
            console.log("最終結果:", data.is_final);
            break;
            
        case "response":
            // LLM応答
            // {
            //   "type": "response",
            //   "message": "今日はどこに行きたいですか？",
            //   "session_id": "abc123-def456",
            //   "turn_count": 1,
            //   "is_complete": false,
            //   "suggestions": ["カフェ", "公園", "美術館"],
            //   "has_audio": true
            // }
            console.log("AI応答:", data.message);
            console.log("提案:", data.suggestions);
            console.log("ターン数:", data.turn_count);
            console.log("完了:", data.is_complete);
            break;
            
        case "asr_connected":
            // ASR接続完了
            // {
            //   "type": "asr_connected",
            //   "message": "音声認識が開始されました"
            // }
            break;
            
        case "asr_error":
        case "error":
            // エラー
            // {
            //   "type": "error",
            //   "message": "エラーメッセージ"
            // }
            console.error(data.message);
            break;
            
        case "pong":
            // ハートビート応答
            // {
            //   "type": "pong"
            // }
            break;
    }
}
```

#### 2. 音声データ（バイナリ）

```javascript
voiceWs.onmessage = (event) => {
    if (event.data instanceof Blob) {
        // 音声データを再生
        const audioUrl = URL.createObjectURL(event.data);
        const audio = new Audio(audioUrl);
        audio.play();
        
        // クリーンアップ
        audio.addEventListener('ended', () => {
            URL.revokeObjectURL(audioUrl);
        });
    }
};
```

---

## テキストチャット

### クライアント → サーバー（送信）

```javascript
// テキストメッセージを送信
chatWs.send(JSON.stringify({
    type: "message",
    text: "東京駅に行きたい"
}));

// ハートビート
chatWs.send(JSON.stringify({ 
    type: "ping" 
}));
```

### サーバー → クライアント（受信）

```javascript
chatWs.onmessage = async (event) => {
    if (event.data instanceof Blob) {
        // 音声データ
        playAudioBlob(event.data);
    } else {
        const data = JSON.parse(event.data);
        
        if (data.type === "connected") {
            // 接続完了
            console.log(data.message);
        } else if (data.type === "response") {
            // LLM応答
            // {
            //   "type": "response",
            //   "message": "今日はどこに行きたいですか？",
            //   "session_id": "abc123-def456",
            //   "turn_count": 1,
            //   "is_complete": false,
            //   "suggestions": ["カフェ", "公園", "美術館"],
            //   "has_audio": true
            // }
            console.log(data.message);
            console.log(data.suggestions);
        } else if (data.type === "error") {
            console.error(data.message);
        } else if (data.type === "pong") {
            // ハートビート応答
        }
    }
};
```

---

## REST API

### エンドポイント

#### セッション開始
```
POST /api/v1/chat/start
```

#### メッセージ送信
```
POST /api/v1/chat/message
```

#### セッション情報取得
```
GET /api/v1/chat/session/{session_id}
```

#### セッション終了
```
DELETE /api/v1/chat/session/{session_id}
```

### セッション開始（位置情報を含む）

**リクエスト**:
```json
POST /api/v1/chat/start
Content-Type: application/json

{
    "user_preferences": {
        "genres": ["カフェ", "レストラン"],
        "atmosphere": "静か",
        "price_range": "中"
    },
    "favorite_spots": [
        {
            "name": "Blue Bottle Coffee",
            "category": "カフェ"
        }
    ],
    "current_location": {
        "latitude": 35.6812,
        "longitude": 139.7671,
        "address": "東京都千代田区丸の内1-9-1",
        "accuracy": 10.5
    }
}
```

**レスポンス**:
```json
{
    "message": "こんにちは！Data Plug Copilotです。\n今日はどこに行きたいですか？",
    "session_id": "abc123-def456-ghi789",
    "turn_count": 0,
    "is_complete": false,
    "suggestions": ["カフェに行きたい", "自然を楽しみたい", "新しい場所を探したい"],
    "audio_data": null,
    "has_audio": false
}
```

**JavaScript実装例**:
```javascript
const response = await fetch('/api/v1/chat/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        user_preferences: {
            genres: ["カフェ", "レストラン"],
            atmosphere: "静か",
            price_range: "中"
        },
        favorite_spots: [
            { name: "Blue Bottle Coffee", category: "カフェ" }
        ],
        current_location: {
            latitude: 35.6812,
            longitude: 139.7671,
            address: "東京都千代田区丸の内1-9-1",
            accuracy: 10.5
        }
    })
});

const data = await response.json();
const sessionId = data.session_id;
```

### メッセージ送信（位置情報を含む）

**リクエスト**:
```json
POST /api/v1/chat/message
Content-Type: application/json

{
    "session_id": "abc123-def456-ghi789",
    "message": "横浜駅に行きたい",
    "current_location": "東京駅",
    "destination": "横浜駅",
    "location_data": {
        "latitude": 35.6812,
        "longitude": 139.7671,
        "address": "東京都千代田区丸の内1-9-1"
    }
}
```

**レスポンス**:
```json
{
    "message": "横浜駅ですね。他に行きたいところややってみたいことはありますか？",
    "session_id": "abc123-def456-ghi789",
    "turn_count": 1,
    "is_complete": false,
    "suggestions": [],
    "audio_data": "UklGRiQAAABXQVZFZm10...",
    "has_audio": true
}
```

**JavaScript実装例**:
```javascript
const response = await fetch('/api/v1/chat/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        session_id: sessionId,
        message: "横浜駅に行きたい",
        current_location: "東京駅",
        destination: "横浜駅",
        location_data: {
            latitude: 35.6812,
            longitude: 139.7671,
            address: "東京都千代田区丸の内1-9-1"
        }
    })
});

const data = await response.json();
// data.message: AI応答テキスト
// data.suggestions: 提案リスト
// data.audio_data: Base64エンコードされた音声データ（オプション）
// data.has_audio: 音声データ有無
```

---

## 位置情報の扱い

### 位置情報の取得（クライアント側）

#### ブラウザ（JavaScript）
```javascript
navigator.geolocation.getCurrentPosition(
    (position) => {
        const locationData = {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy,
            address: null // 逆ジオコーディングで取得可能
        };
        
        // セッション開始時に送信
        fetch('/api/v1/chat/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_location: locationData
            })
        });
    },
    (error) => {
        console.error('位置情報取得エラー:', error);
    }
);
```

#### React Native
```javascript
import Geolocation from '@react-native-community/geolocation';

Geolocation.getCurrentPosition(
    (position) => {
        const locationData = {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy,
            address: null
        };
        
        // セッション開始時に送信
        fetch('/api/v1/chat/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_location: locationData
            })
        });
    },
    (error) => {
        console.error('位置情報取得エラー:', error);
    }
);
```

### 位置情報の形式

#### GPS座標形式（推奨）
```json
{
    "latitude": 35.6812,
    "longitude": 139.7671,
    "address": "東京都千代田区丸の内1-9-1",
    "accuracy": 10.5
}
```

#### 文字列形式（簡易）
```json
{
    "current_location": "東京駅",
    "destination": "横浜駅"
}
```

---

## レスポンス形式

### ChatResponse構造

```typescript
interface ChatResponse {
    message: string;              // AIからの応答テキスト
    session_id: string;           // セッションID
    turn_count: number;           // 現在の会話ターン数（0-3）
    is_complete: boolean;         // 目的地決定が完了したか
    suggestions: string[];         // 提案された選択肢のリスト
    audio_data?: string;           // 音声データ（Base64エンコード、オプション）
    has_audio: boolean;           // 音声データが含まれているかどうか
}
```

### レスポンス例

#### 通常の応答
```json
{
    "message": "今日はどこに行きたいですか？",
    "session_id": "abc123-def456-ghi789",
    "turn_count": 1,
    "is_complete": false,
    "suggestions": ["カフェ", "公園", "美術館"],
    "has_audio": false
}
```

#### 音声付き応答
```json
{
    "message": "横浜駅ですね。他に行きたいところややってみたいことはありますか？",
    "session_id": "abc123-def456-ghi789",
    "turn_count": 1,
    "is_complete": false,
    "suggestions": [],
    "audio_data": "UklGRiQAAABXQVZFZm10...",
    "has_audio": true
}
```

#### 完了応答
```json
{
    "message": "目的地が決定しました。ルート案内を開始します。",
    "session_id": "abc123-def456-ghi789",
    "turn_count": 3,
    "is_complete": true,
    "suggestions": [],
    "has_audio": true
}
```

---

## 実装例

### 完全なクライアント実装（JavaScript）

```javascript
class ChatClient {
    constructor(baseUrl) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.sessionId = null;
        this.voiceWs = null;
        this.chatWs = null;
    }
    
    /**
     * セッション開始（位置情報付き）
     */
    async startSession(options = {}) {
        const {
            userPreferences,
            favoriteSpots,
            currentLocation
        } = options;
        
        const response = await fetch(`${this.baseUrl}/api/v1/chat/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_preferences: userPreferences,
                favorite_spots: favoriteSpots,
                current_location: currentLocation
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        this.sessionId = data.session_id;
        return data;
    }
    
    /**
     * 音声ストリーミング開始
     */
    startVoiceStream(onResponse, onError) {
        if (!this.sessionId) {
            throw new Error('セッションが開始されていません');
        }
        
        const protocol = this.baseUrl.startsWith('https') ? 'wss' : 'ws';
        const host = this.baseUrl.replace(/^https?:\/\//, '');
        const wsUrl = `${protocol}://${host}/api/v1/ws/voice/${this.sessionId}`;
        
        this.voiceWs = new WebSocket(wsUrl);
        this.voiceWs.binaryType = 'blob';
        
        this.voiceWs.onopen = () => {
            this.voiceWs.send(JSON.stringify({ type: 'start_asr' }));
        };
        
        this.voiceWs.onmessage = (event) => {
            if (event.data instanceof Blob) {
                // 音声データ
                onResponse({ type: 'audio', data: event.data });
            } else {
                const data = JSON.parse(event.data);
                if (data.type === 'response') {
                    // テキスト応答
                    onResponse({
                        type: 'text',
                        message: data.message,
                        suggestions: data.suggestions,
                        turn_count: data.turn_count,
                        is_complete: data.is_complete,
                        has_audio: data.has_audio
                    });
                } else {
                    onResponse(data);
                }
            }
        };
        
        this.voiceWs.onerror = onError;
        
        this.voiceWs.onclose = () => {
            console.log('Voice WebSocket closed');
        };
    }
    
    /**
     * 音声データを送信
     */
    sendAudio(audioBuffer) {
        if (this.voiceWs && this.voiceWs.readyState === WebSocket.OPEN) {
            this.voiceWs.send(audioBuffer);
        }
    }
    
    /**
     * テキストメッセージを送信（REST API）
     */
    async sendMessage(text, locationData = null) {
        if (!this.sessionId) {
            throw new Error('セッションが開始されていません');
        }
        
        const body = {
            session_id: this.sessionId,
            message: text
        };
        
        if (locationData) {
            body.location_data = locationData;
        }
        
        const response = await fetch(`${this.baseUrl}/api/v1/chat/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    }
    
    /**
     * テキストメッセージを送信（WebSocket）
     */
    sendMessageViaWebSocket(text) {
        if (!this.chatWs || this.chatWs.readyState !== WebSocket.OPEN) {
            throw new Error('WebSocket接続が確立されていません');
        }
        
        this.chatWs.send(JSON.stringify({
            type: 'message',
            text: text
        }));
    }
    
    /**
     * セッション終了
     */
    async endSession() {
        if (!this.sessionId) {
            return;
        }
        
        // WebSocket接続を閉じる
        if (this.voiceWs) {
            this.voiceWs.close();
            this.voiceWs = null;
        }
        
        if (this.chatWs) {
            this.chatWs.close();
            this.chatWs = null;
        }
        
        // セッションを削除
        const response = await fetch(`${this.baseUrl}/api/v1/chat/session/${this.sessionId}`, {
            method: 'DELETE'
        });
        
        this.sessionId = null;
        return await response.json();
    }
}

// 使用例
const client = new ChatClient('http://localhost:8000');

// 位置情報を取得してセッション開始
navigator.geolocation.getCurrentPosition(
    async (position) => {
        const locationData = {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy
        };
        
        const sessionData = await client.startSession({
            currentLocation: locationData
        });
        
        console.log('セッション開始:', sessionData);
        
        // 音声ストリーミング開始
        client.startVoiceStream(
            (response) => {
                if (response.type === 'text') {
                    console.log('AI応答:', response.message);
                } else if (response.type === 'audio') {
                    // 音声を再生
                    const audioUrl = URL.createObjectURL(response.data);
                    const audio = new Audio(audioUrl);
                    audio.play();
                }
            },
            (error) => {
                console.error('エラー:', error);
            }
        );
    },
    (error) => {
        console.error('位置情報取得エラー:', error);
    }
);
```

### React Native実装例

```javascript
import React, { useState, useEffect } from 'react';
import { View, Text, Button, TextInput } from 'react-native';
import Geolocation from '@react-native-community/geolocation';

const ChatScreen = () => {
    const [sessionId, setSessionId] = useState(null);
    const [message, setMessage] = useState('');
    const [response, setResponse] = useState('');
    const [voiceWs, setVoiceWs] = useState(null);
    
    useEffect(() => {
        // 位置情報を取得してセッション開始
        Geolocation.getCurrentPosition(
            async (position) => {
                const locationData = {
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy
                };
                
                const res = await fetch('http://your-api-url/api/v1/chat/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        current_location: locationData
                    })
                });
                
                const data = await res.json();
                setSessionId(data.session_id);
                
                // WebSocket接続
                const ws = new WebSocket(`ws://your-api-url/api/v1/ws/voice/${data.session_id}`);
                ws.binaryType = 'blob';
                
                ws.onmessage = (event) => {
                    if (event.data instanceof Blob) {
                        // 音声データの処理
                    } else {
                        const data = JSON.parse(event.data);
                        if (data.type === 'response') {
                            setResponse(data.message);
                        }
                    }
                };
                
                setVoiceWs(ws);
            },
            (error) => {
                console.error('位置情報取得エラー:', error);
            }
        );
        
        return () => {
            if (voiceWs) {
                voiceWs.close();
            }
        };
    }, []);
    
    const sendMessage = async () => {
        if (!sessionId) return;
        
        const res = await fetch('http://your-api-url/api/v1/chat/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });
        
        const data = await res.json();
        setResponse(data.message);
        setMessage('');
    };
    
    return (
        <View>
            <TextInput
                value={message}
                onChangeText={setMessage}
                placeholder="メッセージを入力"
            />
            <Button title="送信" onPress={sendMessage} />
            <Text>{response}</Text>
        </View>
    );
};

export default ChatScreen;
```

---

## エラーハンドリング

### WebSocketエラー

```javascript
voiceWs.onerror = (error) => {
    console.error('WebSocketエラー:', error);
    // 再接続ロジックを実装
};

voiceWs.onclose = (event) => {
    console.log('WebSocket切断:', event.code, event.reason);
    // 再接続ロジックを実装
};
```

### REST APIエラー

```javascript
try {
    const response = await fetch('/api/v1/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({...})
    });
    
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    // 処理
} catch (error) {
    console.error('エラー:', error);
    // エラーハンドリング
}
```

---

## 注意事項

1. **セッションIDの取得**: WebSocket接続前に必ず`/api/v1/chat/start`でセッションを開始してください
2. **音声データ形式**: PCM音声データは16kHz, 16bit, モノラル形式である必要があります
3. **Base64エンコード**: REST APIの`audio_data`はBase64エンコードされた文字列です
4. **WebSocketバイナリ**: WebSocket経由の音声データはバイナリ（Blob）として送受信されます
5. **位置情報**: GPS座標形式と文字列形式の両方に対応していますが、GPS座標形式を推奨します
6. **HTTPS環境**: 本番環境では`wss://`（WebSocket Secure）を使用してください

---

## 関連ドキュメント

- `docs/requirements_diff_mobile_voice.md`: モバイルアプリ対応と音声ストリーミング機能
- `docs/requirements_diff_tts_output.md`: TTS出力機能の要件差分
- `src/backend/api/websocket.py`: WebSocketエンドポイント実装
- `src/backend/api/chat.py`: REST APIエンドポイント実装

---

## 変更履歴

| 日付 | バージョン | 変更内容 | 作成者 |
|------|-----------|---------|--------|
| 2025-01-27 | 1.0.0 | 初版作成 | - |

