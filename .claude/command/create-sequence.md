---
description: PlantUMLでシーケンス図を作成するためのコマンドです。オブジェクト間のメッセージのやり取りを時系列で視覚化し、`./docs/diagrams` ディレクトリに保存します。
allowed-tools:
  - functions.read_file
  - functions.write
  - functions.list_dir
  - functions.glob_file_search
---

あなたはシステムアーキテクトです。

## Task
PlantUMLを使用してシーケンス図を作成してください。

## 作成前の確認事項
以下の情報をユーザーから収集してください（不足している場合）：
1. シーケンス図の対象（どの機能・処理を図示するか）
2. 登場するアクター/オブジェクト
3. メッセージの流れ（呼び出し順序）
4. 戻り値や応答の有無
5. ファイル名

## PlantUML シーケンス図のテンプレート

```plantuml
@startuml [ファイル名]
title [タイトル]

' 参加者定義
actor ユーザー as user
participant "フロントエンド" as frontend
participant "バックエンド" as backend
database "データベース" as db

' シーケンス
user -> frontend : リクエスト
frontend -> backend : API呼び出し
backend -> db : クエリ実行
db --> backend : 結果返却
backend --> frontend : レスポンス
frontend --> user : 画面表示

@enduml
```

## 記法ガイドライン

### 参加者タイプ
- `actor` : 人間のユーザー
- `participant` : 一般的なオブジェクト
- `boundary` : UI/境界
- `control` : コントローラー
- `entity` : エンティティ
- `database` : データベース
- `collections` : コレクション
- `queue` : キュー

### メッセージタイプ
- `->` : 同期メッセージ
- `-->` : 戻りメッセージ（点線）
- `->>` : 非同期メッセージ
- `-\` / `-/` : 途中で終わるメッセージ
- `->x` : 失われたメッセージ

### 制御構造
```plantuml
' 条件分岐
alt 条件1
  A -> B : 処理1
else 条件2
  A -> B : 処理2
end

' ループ
loop 繰り返し条件
  A -> B : 繰り返し処理
end

' オプション
opt 条件
  A -> B : 条件付き処理
end

' 並列処理
par
  A -> B : 処理1
else
  A -> C : 処理2
end
```

### その他の要素
- `note left of A : メモ` : ノート追加
- `activate A` / `deactivate A` : ライフライン活性化
- `ref over A,B : 参照` : 参照フレーム
- `== セクション名 ==` : 区切り線
- `...` : 遅延（省略）
- `|||` : スペース追加

## 保存先
- `./docs/diagrams/sequences` 内に保存する
- ディレクトリが存在しなければ新しく作成する
- ファイル形式は `.puml` とする
- ファイル名は `[機能名]_sequence.puml` の形式にする

## 出力例

```plantuml
@startuml login_sequence
title ログイン処理シーケンス図

actor "ユーザー" as user
participant "ログイン画面" as login_page
participant "認証API" as auth_api
participant "認証サービス" as auth_service
database "ユーザーDB" as user_db
participant "セッション管理" as session

== ログイン処理 ==

user -> login_page : メールアドレス・パスワード入力
activate login_page

login_page -> auth_api : POST /api/auth/login
activate auth_api

auth_api -> auth_service : authenticate(email, password)
activate auth_service

auth_service -> user_db : SELECT * FROM users WHERE email = ?
activate user_db
user_db --> auth_service : ユーザー情報
deactivate user_db

alt パスワード一致
  auth_service -> session : createSession(userId)
  activate session
  session --> auth_service : sessionToken
  deactivate session

  auth_service --> auth_api : 認証成功 + トークン
  auth_api --> login_page : 200 OK + JWT
  login_page --> user : ダッシュボードへリダイレクト
else パスワード不一致
  auth_service --> auth_api : 認証失敗
  auth_api --> login_page : 401 Unauthorized
  login_page --> user : エラーメッセージ表示
end

deactivate auth_service
deactivate auth_api
deactivate login_page

@enduml
```

## 注意事項
- 1つのシーケンス図は1つのユースケースに限定する
- 複雑な場合はサブシーケンスに分割する
- 参加者名は役割が分かるように命名する
- メッセージは具体的なアクションを記述する
- 既存のファイルには上書きせず、新しいファイルとして保存する
