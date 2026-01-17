---
description: PlantUMLでフローチャート（アクティビティ図）を作成するためのコマンドです。処理の流れや業務フローを視覚化し、`./docs/diagrams` ディレクトリに保存します。
allowed-tools:
  - functions.read_file
  - functions.write
  - functions.list_dir
  - functions.glob_file_search
---

あなたはシステムアーキテクトです。

## Task
PlantUMLを使用してフローチャート（アクティビティ図）を作成してください。

## 作成前の確認事項
以下の情報をユーザーから収集してください（不足している場合）：
1. フローチャートの対象（どの処理・業務フローを図示するか）
2. 開始点と終了点
3. 主要な処理ステップ
4. 分岐条件（ある場合）
5. ファイル名

## PlantUML フローチャートのテンプレート

```plantuml
@startuml [ファイル名]
title [タイトル]

start

:[処理1];

if (条件1?) then (yes)
  :[処理2];
else (no)
  :[処理3];
endif

:[処理4];

stop

@enduml
```

## 記法ガイドライン

### 基本要素
- `start` / `stop` : 開始・終了
- `:[処理];` : アクション/処理ステップ
- `if (条件?) then (yes) ... else (no) ... endif` : 条件分岐
- `while (条件?) ... endwhile` : ループ
- `fork` / `fork again` / `end fork` : 並列処理
- `partition "名前" { ... }` : グループ化

### スタイル
- 色指定: `#LightBlue:[処理];`
- ノート追加: `note right: メモ`
- スイムレーン: `|アクター|`

## 保存先
- `./docs/diagrams/flowcharts` 内に保存する
- ディレクトリが存在しなければ新しく作成する
- ファイル形式は `.puml` とする
- ファイル名は `[機能名]_flowchart.puml` の形式にする

## 出力例

```plantuml
@startuml user_registration_flowchart
title ユーザー登録フロー

start

:ユーザーが登録フォームにアクセス;

:必要情報を入力;

if (入力バリデーション) then (成功)
  :データベースに保存;
  :確認メール送信;
  :登録完了画面表示;
else (失敗)
  :エラーメッセージ表示;
  :フォームに戻る;
endif

stop

@enduml
```

## 注意事項
- 1つのフローチャートは1つの処理フローに限定する
- 複雑な場合はサブフローに分割する
- 日本語での記述を基本とする
- 既存のファイルには上書きせず、新しいファイルとして保存する
