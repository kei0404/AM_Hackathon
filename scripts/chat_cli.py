#!/usr/bin/env python3
"""
Qwen API チャット CLI

対話形式でAIと会話できるCLIツール

使用方法:
    source .venv/bin/activate
    python scripts/chat_cli.py
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.config import settings
from src.backend.models.chat import ChatRequest
from src.backend.services.conversation_service import conversation_service


def print_header() -> None:
    """ヘッダーを表示"""
    print()
    print("╔" + "═" * 48 + "╗")
    print("║" + " Data Plug Copilot - AI Chat ".center(48) + "║")
    print("╚" + "═" * 48 + "╝")
    print()
    print("AIと会話して目的地を決めましょう！")
    print("終了するには 'quit' または 'exit' と入力してください。")
    print("-" * 50)


def print_ai_message(message: str, suggestions: list[str]) -> None:
    """AIのメッセージを表示"""
    print()
    print("🤖 AI:")
    for line in message.split("\n"):
        print(f"   {line}")

    if suggestions:
        print()
        print("   💡 選択肢:")
        for i, suggestion in enumerate(suggestions, 1):
            print(f"      {i}. {suggestion}")


def print_user_prompt() -> str:
    """ユーザー入力を取得"""
    print()
    return input("👤 あなた: ").strip()


def main() -> None:
    """メイン関数"""
    print_header()

    # 設定検証
    try:
        settings.validate()
    except ValueError as e:
        print(f"❌ エラー: {e}")
        print("'.env'ファイルに DASHSCOPE_API_KEY を設定してください")
        return

    # サンプルのユーザー情報
    session_id = conversation_service.create_session(
        user_preferences={
            "genres": ["カフェ", "レストラン", "自然"],
            "atmosphere": "静か",
            "price_range": "中",
        },
        favorite_spots=[
            {"name": "Blue Bottle Coffee 清澄白河", "category": "カフェ"},
            {"name": "代々木公園", "category": "公園"},
            {"name": "東京国立博物館", "category": "美術館"},
        ],
    )

    # ウェルカムメッセージ
    welcome = conversation_service.get_welcome_message(session_id)
    print_ai_message(welcome.message, welcome.suggestions)
    print()
    print(f"📊 進捗: {welcome.turn_count}/{settings.MAX_CONVERSATION_TURNS}")

    # 会話ループ
    while True:
        user_input = print_user_prompt()

        if not user_input:
            continue

        if user_input.lower() in ["quit", "exit", "終了", "q"]:
            print()
            print("👋 ご利用ありがとうございました！")
            # セッション削除
            conversation_service.delete_session(session_id)
            print("🗑️ セッションデータを消去しました。")
            break

        # メッセージ送信
        try:
            request = ChatRequest(
                message=user_input,
                session_id=session_id,
            )
            response = conversation_service.process_message(request)

            print_ai_message(response.message, response.suggestions)
            print()
            print(
                f"📊 進捗: {response.turn_count}/{settings.MAX_CONVERSATION_TURNS}"
            )

            if response.is_complete:
                print()
                print("🎉 目的地が決定しました！")
                print("セッションを終了します...")
                conversation_service.delete_session(session_id)
                print("🗑️ セッションデータを消去しました。")
                break

        except Exception as e:
            print(f"\n❌ エラーが発生しました: {e}")
            print("もう一度お試しください。")


if __name__ == "__main__":
    main()
