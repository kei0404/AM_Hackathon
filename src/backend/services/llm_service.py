"""
LLMサービス - Qwen API (DashScope) との連携
"""

import logging
from typing import Optional

from openai import OpenAI

from ..config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Qwen API を使用したLLMサービス"""

    def __init__(self) -> None:
        """LLMサービスの初期化"""
        self.demo_mode = False
        try:
            settings.validate()
            self.client = OpenAI(
                api_key=settings.DASHSCOPE_API_KEY,
                base_url=settings.QWEN_BASE_URL,
            )
            self.model = settings.QWEN_MODEL
        except ValueError as e:
            logger.warning(f"LLM API設定エラー: {e} - デモモードで動作します")
            self.demo_mode = True
            self.client = None
            self.model = None

    def generate_response(
        self,
        messages: list[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        LLMからレスポンスを生成する

        Args:
            messages: 会話履歴（role, content を含む辞書のリスト）
            max_tokens: 最大トークン数
            temperature: 生成の多様性（0.0-1.0）

        Returns:
            LLMからの応答テキスト
        """
        if self.demo_mode:
            logger.info("デモモード: 固定レスポンスを返します")
            return self._generate_demo_response(messages)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens or settings.MAX_TOKENS,
                temperature=temperature or settings.TEMPERATURE,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM API呼び出しエラー: {e}")
            logger.info("フォールバック: デモモードレスポンスを使用")
            return self._generate_demo_response(messages)

    def _generate_demo_response(self, messages: list[dict]) -> str:
        """デモモード用の固定レスポンスを生成"""
        user_message = messages[-1]["content"] if messages else ""
        user_lower = user_message.lower()

        if "カフェ" in user_message or "コーヒー" in user_message:
            return """静かなカフェがお好みですね！

あなたのお気に入りを参考に、いくつか候補があります。

[選択肢]
1. Blue Bottle Coffee 清澄白河（お気に入り）
2. 新しいカフェを探す
3. もう少し条件を絞る"""

        elif "新しい" in user_message or "探" in user_message:
            return """新しい場所を探しましょう！

どんな雰囲気がいいですか？

[選択肢]
1. おしゃれで落ち着いた雰囲気
2. 自然の中でリラックス
3. アートや文化を楽しめる場所"""

        elif "自然" in user_message or "公園" in user_message:
            return """自然を楽しみたいですね！

代々木公園がお気に入りに登録されていますね。

[選択肢]
1. 代々木公園に行く（お気に入り）
2. 新しい公園を探す
3. 海や山など遠出する"""

        elif "決" in user_message or "行く" in user_message or "1" in user_message:
            return """素敵な選択ですね！

目的地が決まりました：Blue Bottle Coffee 清澄白河

【スケジュール提案】
- 出発: 現在地から車で約15分
- 到着予定: 10:30頃
- おすすめ滞在時間: 1時間30分

ナビゲーションを開始しますか？

[選択肢]
1. ナビを開始する
2. 別の場所を探す
3. スケジュールを調整する"""

        else:
            return """なるほど、今日はどんな場所に行きたいですか？

[選択肢]
1. カフェでゆっくりしたい
2. 自然の中でリラックス
3. 新しい場所を発見したい"""

    def generate_destination_question(
        self,
        user_message: str,
        turn_count: int,
        user_preferences: Optional[dict] = None,
        favorite_spots: Optional[list[dict]] = None,
    ) -> dict:
        """
        目的地を絞り込むための質問を生成する

        Args:
            user_message: ユーザーからのメッセージ
            turn_count: 現在の質問回数
            user_preferences: ユーザーの嗜好設定
            favorite_spots: お気に入りスポットのリスト

        Returns:
            LLMの応答と選択肢を含む辞書
        """
        system_prompt = self._build_system_prompt(
            turn_count, user_preferences, favorite_spots
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        response = self.generate_response(messages)
        return self._parse_response(response, turn_count)

    def generate_stopover_suggestion(
        self,
        user_message: str,
        turn_count: int,
        current_location: Optional[str] = None,
        destination: Optional[str] = None,
        rag_results: Optional[list[dict]] = None,
        user_preferences: Optional[dict] = None,
    ) -> dict:
        """
        立ち寄り場所の提案を生成する（RAG検索結果を使用）

        Args:
            user_message: ユーザーからのメッセージ
            turn_count: 現在の質問回数
            current_location: 現在地
            destination: 目的地
            rag_results: RAG検索結果（訪問履歴など）
            user_preferences: ユーザーの嗜好設定

        Returns:
            LLMの応答と選択肢を含む辞書
        """
        system_prompt = self._build_stopover_prompt(
            turn_count=turn_count,
            current_location=current_location,
            destination=destination,
            rag_results=rag_results,
            user_preferences=user_preferences,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        if self.demo_mode:
            response = self._generate_stopover_demo_response(
                user_message, rag_results, current_location, destination
            )
        else:
            response = self.generate_response(messages)

        return self._parse_response(response, turn_count)

    def _build_stopover_prompt(
        self,
        turn_count: int,
        current_location: Optional[str] = None,
        destination: Optional[str] = None,
        rag_results: Optional[list[dict]] = None,
        user_preferences: Optional[dict] = None,
    ) -> str:
        """立ち寄り場所提案用のシステムプロンプトを構築する"""
        remaining_turns = settings.MAX_CONVERSATION_TURNS - turn_count

        prompt = f"""あなたは「Data Plug Copilot」のAIアシスタントです。
ユーザーが車で移動中に立ち寄りたい場所を提案します。

【ルート情報】
- 現在地: {current_location or "未設定"}
- 目的地: {destination or "未設定"}

【重要なルール】
- ユーザーの過去の訪問履歴や感想を参考に、ルート上で立ち寄れる場所を提案してください
- 残り{remaining_turns}回の会話で立ち寄り場所を1つに絞り込んでください
- 選択肢は必ず3つ以内で提示してください
- 回答は簡潔に、運転中でも理解しやすいようにしてください
- 提案する場所は、ユーザーの過去の感想を引用して説明してください

【選択肢の出力形式】
[選択肢]
1. 選択肢1
2. 選択肢2
3. 選択肢3

"""
        # RAG検索結果（訪問履歴）をコンテキストとして追加
        if rag_results:
            prompt += "【ユーザーの訪問履歴（参考情報）】\n"
            for i, result in enumerate(rag_results, 1):
                metadata = result.get("metadata", {})
                place_name = metadata.get("place_name", "不明")
                address = metadata.get("address", "")
                impression = metadata.get("impression", "")
                visit_datetime = metadata.get("datetime", "")

                prompt += f"{i}. {place_name}\n"
                if address:
                    prompt += f"   住所: {address}\n"
                if visit_datetime:
                    prompt += f"   訪問日時: {visit_datetime}\n"
                if impression:
                    prompt += f"   感想: {impression}\n"
                prompt += "\n"

        # ユーザー嗜好
        if user_preferences:
            pref_str = ", ".join(f"{k}: {v}" for k, v in user_preferences.items())
            prompt += f"\n【ユーザーの嗜好】\n{pref_str}\n"

        if turn_count >= settings.MAX_CONVERSATION_TURNS - 1:
            prompt += """
【最終確認】
これが最後の質問です。具体的な立ち寄り場所を1つ提案し、確認してください。
"""
        return prompt

    def _generate_stopover_demo_response(
        self,
        user_message: str,
        rag_results: Optional[list[dict]] = None,
        current_location: Optional[str] = None,
        destination: Optional[str] = None,
    ) -> str:
        """デモモード用の立ち寄り提案レスポンスを生成"""
        # RAG検索結果から場所を抽出
        places = []
        if rag_results:
            for result in rag_results[:3]:
                metadata = result.get("metadata", {})
                place_name = metadata.get("place_name", "")
                impression = metadata.get("impression", "")
                if place_name:
                    places.append({"name": place_name, "impression": impression})

        route_info = ""
        if current_location and destination:
            route_info = f"【ルート】{current_location} → {destination}\n\n"

        if not places:
            return f"""{route_info}申し訳ありません、訪問履歴から適切な立ち寄り場所が見つかりませんでした。

どんな場所に立ち寄りたいですか？

[選択肢]
1. カフェで休憩したい
2. 食事をしたい
3. 観光スポットに寄りたい"""

        # 検索結果を使って提案を生成
        response = f"""{route_info}あなたの過去の訪問履歴から、ルート上でおすすめの立ち寄りスポットを見つけました！

"""
        for i, place in enumerate(places, 1):
            response += f"**{i}. {place['name']}**\n"
            if place['impression']:
                response += f"   前回の感想: 「{place['impression'][:50]}...」\n\n"

        response += """どの場所に立ち寄りますか？

[選択肢]
"""
        for i, place in enumerate(places, 1):
            response += f"{i}. {place['name']}\n"

        return response

    def _build_system_prompt(
        self,
        turn_count: int,
        user_preferences: Optional[dict] = None,
        favorite_spots: Optional[list[dict]] = None,
    ) -> str:
        """システムプロンプトを構築する"""
        remaining_turns = settings.MAX_CONVERSATION_TURNS - turn_count

        base_prompt = f"""あなたは「Data Plug Copilot」のAIアシスタントです。
ユーザーが行きたい場所を決める手助けをします。

【重要なルール】
- 残り{remaining_turns}回の質問で目的地を1つに絞り込んでください
- 選択肢は必ず3つ以内で提示してください
- 回答は簡潔に、フレンドリーな口調で話してください
- 選択肢を提示する場合は、以下の形式で出力してください：
  [選択肢]
  1. 選択肢1
  2. 選択肢2
  3. 選択肢3

【ユーザー情報】
"""
        if user_preferences:
            pref_str = ", ".join(
                f"{k}: {v}" for k, v in user_preferences.items()
            )
            base_prompt += f"- 嗜好: {pref_str}\n"

        if favorite_spots:
            spots_str = ", ".join(
                spot.get("name", "不明") for spot in favorite_spots[:5]
            )
            base_prompt += f"- お気に入り: {spots_str}\n"

        if turn_count >= settings.MAX_CONVERSATION_TURNS - 1:
            base_prompt += """
【最終質問】
これが最後の質問です。具体的な目的地を1つ提案し、確認してください。
"""
        return base_prompt

    def _parse_response(self, response: str, turn_count: int) -> dict:
        """LLMの応答をパースして構造化する"""
        suggestions = []

        # [選択肢] セクションを探す
        if "[選択肢]" in response:
            lines = response.split("\n")
            in_choices = False
            for line in lines:
                if "[選択肢]" in line:
                    in_choices = True
                    continue
                if in_choices and line.strip():
                    # 番号付きの選択肢を抽出
                    if line.strip()[0].isdigit():
                        choice = line.strip()[2:].strip()  # "1. " を除去
                        if choice:
                            suggestions.append(choice)

        is_complete = turn_count >= settings.MAX_CONVERSATION_TURNS

        return {
            "message": response,
            "suggestions": suggestions[:3],  # 最大3つ
            "is_complete": is_complete,
            "turn_count": turn_count + 1,
        }


# シングルトンインスタンス
llm_service = LLMService()
