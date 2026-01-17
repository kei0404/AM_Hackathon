#!/usr/bin/env python3
"""
Qwen API チャット機能のテストスクリプト

使用方法:
    source .venv/bin/activate
    python scripts/test_chat.py
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.config import settings
from src.backend.models.chat import ChatRequest
from src.backend.services.conversation_service import conversation_service


def test_welcome_message() -> None:
    """ウェルカムメッセージのテスト"""
    print("=" * 50)
    print("テスト1: ウェルカムメッセージ")
    print("=" * 50)

    response = conversation_service.get_welcome_message()
    print(f"セッションID: {response.session_id}")
    print(f"メッセージ: {response.message}")
    print(f"選択肢: {response.suggestions}")
    print(f"ターン数: {response.turn_count}")
    print()


def test_conversation_flow() -> None:
    """会話フローのテスト"""
    print("=" * 50)
    print("テスト2: 会話フロー（3回の質問で絞り込み）")
    print("=" * 50)

    # セッション作成（ユーザー情報付き）
    session_id = conversation_service.create_session(
        user_preferences={
            "genres": ["カフェ", "自然"],
            "atmosphere": "静か",
        },
        favorite_spots=[
            {"name": "Blue Bottle Coffee 清澄白河", "category": "カフェ"},
            {"name": "代々木公園", "category": "公園"},
        ],
    )
    print(f"セッション作成: {session_id}")

    # ウェルカムメッセージ
    welcome = conversation_service.get_welcome_message(session_id)
    print(f"\n[AI]: {welcome.message}")
    print(f"選択肢: {welcome.suggestions}")

    # ユーザーからのメッセージをシミュレート
    user_messages = [
        "静かな場所でゆっくりしたいな",
        "カフェがいいかな",
        "いつもの場所がいい",
    ]

    for i, message in enumerate(user_messages, 1):
        print(f"\n--- ターン {i} ---")
        print(f"[ユーザー]: {message}")

        request = ChatRequest(
            message=message,
            session_id=session_id,
        )
        response = conversation_service.process_message(request)

        print(f"[AI]: {response.message}")
        if response.suggestions:
            print(f"選択肢: {response.suggestions}")
        print(f"ターン数: {response.turn_count}, 完了: {response.is_complete}")

        if response.is_complete:
            print("\n目的地が決定しました！")
            break

    print()


def test_session_management() -> None:
    """セッション管理のテスト"""
    print("=" * 50)
    print("テスト3: セッション管理")
    print("=" * 50)

    # セッション作成
    session_id = conversation_service.create_session()
    print(f"セッション作成: {session_id}")

    # セッション取得
    context = conversation_service.get_session(session_id)
    print(f"セッション取得: {context is not None}")

    # セッション削除
    deleted = conversation_service.delete_session(session_id)
    print(f"セッション削除: {deleted}")

    # 削除後の確認
    context = conversation_service.get_session(session_id)
    print(f"削除後のセッション: {context is None}")
    print()


def main() -> None:
    """メイン関数"""
    print("\n" + "=" * 50)
    print("Data Plug Copilot - チャット機能テスト")
    print("=" * 50)
    print(f"API Key設定: {'OK' if settings.DASHSCOPE_API_KEY else 'NG'}")
    print(f"モデル: {settings.QWEN_MODEL}")
    print(f"最大ターン数: {settings.MAX_CONVERSATION_TURNS}")
    print()

    try:
        # 設定検証
        settings.validate()
        print("設定検証: OK\n")
    except ValueError as e:
        print(f"設定エラー: {e}")
        print("'.env'ファイルに DASHSCOPE_API_KEY を設定してください")
        return

    # テスト実行
    test_welcome_message()
    test_session_management()

    # LLM呼び出しを含むテスト
    print("LLMを使用した会話テストを実行しますか？ (y/n): ", end="")
    answer = input().strip().lower()
    if answer == "y":
        test_conversation_flow()
    else:
        print("LLMテストをスキップしました")

    print("\nテスト完了！")


if __name__ == "__main__":
    main()
