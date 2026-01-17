---
description: Playwright MCP ツールを用いてアプリケーションの E2E テストとコード品質チェック
  （ruff による静的解析）を実行するためのコマンドです。
allowed-tools:
  - mcp_cursor-ide-browser_browser_navigate
  - mcp_cursor-ide-browser_browser_snapshot
  - mcp_cursor-ide-browser_browser_click
  - mcp_cursor-ide-browser_browser_type
  - mcp_cursor-ide-browser_browser_hover
  - mcp_cursor-ide-browser_browser_select_option
  - mcp_cursor-ide-browser_browser_press_key
  - mcp_cursor-ide-browser_browser_wait_for
  - mcp_cursor-ide-browser_browser_navigate_back
  - mcp_cursor-ide-browser_browser_resize
  - mcp_cursor-ide-browser_browser_console_messages
  - mcp_cursor-ide-browser_browser_network_requests
  - mcp_cursor-ide-browser_browser_take_screenshot
  - functions.read_file
  - functions.web_search
---

#　PlaywriteによるE2Eテストとコード品質チェック
あなたは、アプリケーションのシステムテストを担当するエージェントです。

## 概要

Playwrite MCPツールを使用して、E2Eテストを実行します。

## E2Eテスト実行手順

(1) 前提条件

1. バックエンドサーバーが起動していること

- バックエンドURL: `http://localhost:8000`(FastAPI:default)

(2) テストシナリオを作成

`tests/e2e` ディレクトリにE2Eテストシナリオを作成します。

## テスト実行時の注意事項

1. **スナップショットの活用**: 各ステップで画面の状態をスナップショットとして保存し、ページ状態を後で比較できるようにします。
2. ** 待機処理**: ページの読み込みや非同期処理（APIリクエスト、状態更新）が完了するまで適切に待機する処理を実装します。
3. **エラーハンドリング**: テスト中にエラーが発生した場合、コンソールメッセージとネットワークリクエストなど詳細なログを取得・監視し、問題の特定と修正に役立てます。
4. **スクリーンショット**: 重要なステップでスクリーンショットを撮影し、テスト結果の視覚化とドキュメント化に役立てます。
5. **アサーション**: 各ステップで期待される結果を明確に定義し、アサーションを使用して結果を検証します。
6. **コード品質チェック**: `ruff` を使用してコードの静的解析を行い、PEP 8準拠や潜在的なバグを検出します。テスト実行前に `ruff check` を実行し、問題があれば修正します。


(3) 結果を保存

テスト結果を `tests/e2e/results` ディレクトリに .md で作成・保存します。