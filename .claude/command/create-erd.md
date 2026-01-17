---
description: PlantUMLでER図（Entity-Relationship Diagram）を作成するためのコマンドです。データベース設計やエンティティ間の関係を視覚化し、`./docs/diagrams` ディレクトリに保存します。
allowed-tools:
  - functions.read_file
  - functions.write
  - functions.list_dir
  - functions.glob_file_search
---

あなたはデータベースアーキテクトです。

## Task
PlantUMLを使用してER図（Entity-Relationship Diagram）を作成してください。

## 作成前の確認事項
以下の情報をユーザーから収集してください（不足している場合）：
1. 対象のエンティティ（テーブル）一覧
2. 各エンティティの主要な属性（カラム）
3. エンティティ間のリレーション（1対1、1対多、多対多）
4. 主キー・外部キーの情報
5. ファイル名

## PlantUML ER図のテンプレート

```plantuml
@startuml [ファイル名]
title [タイトル]

' エンティティ定義
entity "エンティティ名" as alias {
  *id : number <<PK>>
  --
  *必須カラム : type
  任意カラム : type
}

' リレーション
entity1 ||--o{ entity2 : "リレーション名"

@enduml
```

## 記法ガイドライン

### エンティティ定義
```
entity "テーブル名" as alias {
  *id : number <<PK>>          ' 主キー（必須）
  --
  *name : varchar(100)         ' 必須カラム（*付き）
  description : text           ' 任意カラム
  *foreign_id : number <<FK>>  ' 外部キー
}
```

### リレーション記号
- `||--||` : 1対1（必須）
- `||--o|` : 1対1（任意）
- `||--o{` : 1対多
- `}o--o{` : 多対多
- `|o--o|` : 0または1対0または1

### カーディナリティ記号
- `||` : 1（必須）
- `|o` : 0または1
- `o{` : 0以上
- `|{` : 1以上

### スタイル
- 色指定: `entity "名前" as e #LightBlue { ... }`
- グループ化: `package "グループ名" { ... }`

## 保存先
- `./docs/diagrams/erd` 内に保存する
- ディレクトリが存在しなければ新しく作成する
- ファイル形式は `.puml` とする
- ファイル名は `[スキーマ名]_erd.puml` の形式にする

## 出力例

```plantuml
@startuml user_management_erd
title ユーザー管理システム ER図

entity "users" as users {
  *id : bigint <<PK>>
  --
  *email : varchar(255) <<unique>>
  *password_hash : varchar(255)
  *name : varchar(100)
  created_at : timestamp
  updated_at : timestamp
}

entity "profiles" as profiles {
  *id : bigint <<PK>>
  --
  *user_id : bigint <<FK>>
  bio : text
  avatar_url : varchar(500)
  birth_date : date
}

entity "roles" as roles {
  *id : bigint <<PK>>
  --
  *name : varchar(50)
  *description : text
}

entity "user_roles" as user_roles {
  *user_id : bigint <<FK>>
  *role_id : bigint <<FK>>
  --
  assigned_at : timestamp
}

users ||--o| profiles : "has"
users ||--o{ user_roles : "has"
roles ||--o{ user_roles : "assigned to"

@enduml
```

## 注意事項
- テーブル名は英語（スネークケース）を推奨
- 属性名も英語で記述する
- コメントは日本語で補足説明を追加可能
- 複雑な場合はドメインごとに分割する
- 既存のファイルには上書きせず、新しいファイルとして保存する
