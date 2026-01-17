# Design Concept - Data Plug Copilot ver02

**Version**: ver02
**Created**: 2025-01-17
**Designer**: UI/UX Design Team
**Based on**: spec.md v2.3.0

---

## 概要

Data Plug Copilot MVPのデータフロー可視化ダッシュボードデザインです。spec.md v2.3.0の「どんな情報を受け取り、どんな情報を返しているか」を明確に表示するUI方針に基づいています。

---

## コアコンセプト

### MVP/デモ UI方針（spec.md v2.3.0より）

> - **重視点**: 「どんな情報を受け取り、どんな情報を返しているか」が明確にわかること
> - **目的**: データフローの可視化、API入出力の確認、デモンストレーション
> - **非重視**: 洗練されたビジュアルデザイン、モバイル最適化、SPA

### デザインの目標

1. **入力データの可視化**: LLMに送信されるデータ（ユーザー嗜好、お気に入り、メッセージ）を明示
2. **出力データの可視化**: LLMからの応答（メッセージ、選択肢、推論理由）を明示
3. **データフローの追跡**: 会話の各ターンで何が入力され、何が出力されたかを時系列で表示
4. **APIログの表示**: 実際のAPI呼び出しのログを確認可能

---

## デザイン原則

### 1. 開発者向けの透明性

- JSON形式でデータ構造を表示
- シンタックスハイライトによる可読性向上
- リアルタイムでの入出力更新

### 2. ダークテーマ

- 開発者ツール/ターミナルライクな外観
- 目に優しいダークカラースキーム
- データパネルの視認性向上

### 3. 明確なデータ区分

- **INPUT（青）**: LLMへ送信するデータ
- **OUTPUT（緑）**: LLMからの応答データ
- **METADATA（黄）**: セッション状態などの補助情報

### 4. 2カラムレイアウト

- 左: INPUT（入力データ）
- 右: OUTPUT（出力データ）
- 視覚的にデータの流れを左から右へ

---

## カラーパレット

| 用途 | カラー | Tailwind Class |
|------|--------|----------------|
| Background | #0f172a (Slate 900) | `bg-slate-900` |
| Panel | #1e293b (Slate 800) | `bg-slate-800` |
| Input Accent | #3B82F6 (Blue 500) | `text-blue-400` |
| Output Accent | #10B981 (Emerald 500) | `text-emerald-400` |
| Metadata Accent | #F59E0B (Amber 500) | `text-amber-400` |
| Flow Accent | #8B5CF6 (Violet 500) | `text-violet-400` |
| JSON Key | #7dd3fc (Sky 300) | `text-sky-300` |
| JSON String | #86efac (Green 300) | `text-green-300` |
| JSON Number | #fcd34d (Yellow 300) | `text-yellow-300` |
| JSON Boolean | #f472b6 (Pink 400) | `text-pink-400` |

---

## コンポーネント構成

### 1. ヘッダー
- アプリロゴ・名前
- MVP Demoバッジ
- API接続状態
- 使用モデル名表示

### 2. Data Flow Overview Banner
- INPUT/OUTPUTの凡例
- データフローの説明

### 3. INPUT Panel（左カラム）
- `user_preferences`: ユーザー嗜好データ（JSON表示）
- `favorite_spots`: お気に入りスポットリスト（JSON表示）
- `user_message`: 現在の入力メッセージ（ハイライト表示）
- チャット入力UI: 実際の入力インターフェース

### 4. OUTPUT Panel（右カラム）
- `llm_response`: LLMからの応答（JSON表示）
- Rendered UI: レンダリングされたチャット画面
- `session_state`: セッション状態情報

### 5. Conversation Flow
- 各ターンのINPUT/OUTPUTを時系列で表示
- 最大3ターンの進捗を視覚化
- 完了/待機中のステータス表示

### 6. API Call Log
- APIエンドポイント
- HTTPステータス
- レスポンスタイム
- タイムスタンプ

---

## レスポンシブ対応

| デバイス | ブレークポイント | レイアウト |
|----------|-----------------|------------|
| Mobile | < 1024px | 1カラム（INPUT/OUTPUT縦並び） |
| Desktop | >= 1024px | 2カラム（INPUT左/OUTPUT右） |

**注意**: MVP/デモ用途のため、デスクトップ優先で設計。モバイル最適化は非重視。

---

## ファイル構成

```
ver02/
├── design-concept.md         # このファイル
└── dashboard-dataflow.html   # データフロー可視化ダッシュボード
```

---

## ver01からの変更点

| 項目 | ver01 | ver02 |
|------|-------|-------|
| テーマ | ライトテーマ | ダークテーマ（開発者向け） |
| 焦点 | ユーザー向けUI | データフロー可視化 |
| データ表示 | カード形式 | JSON形式 |
| 目的 | 製品UI | MVP/デモ・開発確認 |
| レイアウト | 3カラム | 2カラム（INPUT/OUTPUT） |

---

## 使用技術

- **Tailwind CSS** (CDN)
- **JetBrains Mono** (コード用フォント)
- **Inter** (UIフォント)

---

## 参照

- 要件定義: `/specs/001-navi-schedule/spec.md` (v2.3.0)
- 実行計画: `/PLANS.md` (v1.2.0)
- 既存デザイン: `/docs/designs/ver01/`
