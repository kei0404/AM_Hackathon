---
description: プロジェクト内のドキュメントやソースコードを分析して、ToDoやNextActionを提示するためのコマンドです。プロジェクトの現状を理解し、完了していない作業を特定して、次のアクションを提案します。NextActionの実行前にユーザーの確認（yes/no）を取得します。
allowed-tools:
  - functions.read_file
  - functions.list_dir
  - functions.glob_file_search
  - functions.grep
---

# Tasks
このプロジェクト内のドキュメントやソースコードを理解して、次のアクションを提示してください。

# Actions
- ToDoの提示
- まだ完了していない作業
- NextActionの提案

# Conditions
- NextActionに同意するかをユーザーに確認してください。
- yse / no で回答し、no の場合は何も実行しない。