"""
会話サービス - セッション管理と会話フローの制御（TTL付きキャッシュ）
"""

import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Optional

from ..config import settings
from ..models.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationContext,
    ConversationPhase,
    MessageRole,
)
from .llm_service import llm_service
from .vector_store import vector_store

logger = logging.getLogger(__name__)


class SessionCache:
    """TTL付きセッションキャッシュ"""

    def __init__(
        self,
        ttl_seconds: int = 1800,
        max_sessions: int = 1000,
        cleanup_interval: int = 300,
    ) -> None:
        """
        セッションキャッシュの初期化

        Args:
            ttl_seconds: セッションの有効期限（秒）
            max_sessions: 最大セッション数
            cleanup_interval: クリーンアップ間隔（秒）
        """
        self._cache: dict[str, dict] = {}
        self._lock = threading.RLock()
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.cleanup_interval = cleanup_interval
        self._last_cleanup = datetime.now()

        logger.info(
            f"SessionCache初期化: TTL={ttl_seconds}秒, "
            f"最大セッション数={max_sessions}, クリーンアップ間隔={cleanup_interval}秒"
        )

    def set(self, key: str, value: ConversationContext) -> None:
        """
        セッションをキャッシュに保存

        Args:
            key: セッションID
            value: 会話コンテキスト
        """
        with self._lock:
            # 定期的なクリーンアップ
            self._lazy_cleanup()

            # 最大セッション数チェック
            if len(self._cache) >= self.max_sessions and key not in self._cache:
                self._evict_oldest()

            self._cache[key] = {
                "data": value,
                "created_at": datetime.now(),
                "last_accessed": datetime.now(),
            }

    def get(self, key: str) -> Optional[ConversationContext]:
        """
        セッションをキャッシュから取得

        Args:
            key: セッションID

        Returns:
            会話コンテキスト、または期限切れ/存在しない場合はNone
        """
        with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]

            # TTLチェック
            if self._is_expired(entry):
                del self._cache[key]
                logger.debug(f"セッション期限切れ: {key}")
                return None

            # 最終アクセス時刻を更新
            entry["last_accessed"] = datetime.now()
            return entry["data"]

    def delete(self, key: str) -> bool:
        """
        セッションを削除

        Args:
            key: セッションID

        Returns:
            削除成功の場合True
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        """セッションが存在し、有効かどうかをチェック"""
        with self._lock:
            if key not in self._cache:
                return False
            if self._is_expired(self._cache[key]):
                del self._cache[key]
                return False
            return True

    def get_ttl(self, key: str) -> Optional[int]:
        """
        セッションの残りTTL（秒）を取得

        Args:
            key: セッションID

        Returns:
            残りTTL秒数、または存在しない場合はNone
        """
        with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]
            elapsed = (datetime.now() - entry["last_accessed"]).total_seconds()
            remaining = self.ttl_seconds - int(elapsed)

            return max(0, remaining)

    def extend_ttl(self, key: str) -> bool:
        """
        セッションのTTLを延長（アクセス時刻を更新）

        Args:
            key: セッションID

        Returns:
            延長成功の場合True
        """
        with self._lock:
            if key in self._cache and not self._is_expired(self._cache[key]):
                self._cache[key]["last_accessed"] = datetime.now()
                return True
            return False

    def count(self) -> int:
        """有効なセッション数を取得"""
        with self._lock:
            return sum(1 for entry in self._cache.values() if not self._is_expired(entry))

    def get_stats(self) -> dict:
        """キャッシュ統計情報を取得"""
        with self._lock:
            total = len(self._cache)
            active = self.count()
            return {
                "total_entries": total,
                "active_sessions": active,
                "expired_sessions": total - active,
                "max_sessions": self.max_sessions,
                "ttl_seconds": self.ttl_seconds,
            }

    def cleanup(self) -> int:
        """期限切れセッションを強制クリーンアップ"""
        with self._lock:
            return self._cleanup_expired()

    def _is_expired(self, entry: dict) -> bool:
        """エントリが期限切れかどうかをチェック"""
        elapsed = (datetime.now() - entry["last_accessed"]).total_seconds()
        return elapsed > self.ttl_seconds

    def _lazy_cleanup(self) -> None:
        """クリーンアップ間隔が経過していればクリーンアップを実行"""
        elapsed = (datetime.now() - self._last_cleanup).total_seconds()
        if elapsed >= self.cleanup_interval:
            self._cleanup_expired()
            self._last_cleanup = datetime.now()

    def _cleanup_expired(self) -> int:
        """期限切れエントリを削除"""
        expired_keys = [
            key for key, entry in self._cache.items() if self._is_expired(entry)
        ]
        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(f"期限切れセッションをクリーンアップ: {len(expired_keys)}件")

        return len(expired_keys)

    def _evict_oldest(self) -> None:
        """最も古いセッションを削除"""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k]["last_accessed"],
        )
        del self._cache[oldest_key]
        logger.debug(f"最大セッション数超過のため削除: {oldest_key}")


class ConversationService:
    """会話管理サービス（TTL付きキャッシュ）"""

    def __init__(self) -> None:
        """会話サービスの初期化"""
        self._cache = SessionCache(
            ttl_seconds=settings.SESSION_TTL_SECONDS,
            max_sessions=settings.MAX_SESSIONS,
            cleanup_interval=settings.SESSION_CLEANUP_INTERVAL,
        )

    def create_session(
        self,
        user_preferences: Optional[dict] = None,
        favorite_spots: Optional[list[dict]] = None,
        visit_history: Optional[list[dict]] = None,
    ) -> str:
        """
        新しい会話セッションを作成する

        Args:
            user_preferences: ユーザーの嗜好設定
            favorite_spots: お気に入りスポットのリスト
            visit_history: 訪問履歴

        Returns:
            セッションID
        """
        session_id = str(uuid.uuid4())
        context = ConversationContext(
            session_id=session_id,
            messages=[],
            turn_count=0,
            user_preferences=user_preferences,
            favorite_spots=favorite_spots or [],
            visit_history=visit_history or [],
        )
        self._cache.set(session_id, context)
        logger.info(f"新しいセッションを作成: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[ConversationContext]:
        """セッションを取得する"""
        return self._cache.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """セッションを削除する"""
        if self._cache.delete(session_id):
            logger.info(f"セッションを削除: {session_id}")
            return True
        return False

    def get_session_ttl(self, session_id: str) -> Optional[int]:
        """セッションの残りTTL（秒）を取得"""
        return self._cache.get_ttl(session_id)

    def extend_session(self, session_id: str) -> bool:
        """セッションのTTLを延長"""
        return self._cache.extend_ttl(session_id)

    def get_cache_stats(self) -> dict:
        """キャッシュ統計情報を取得"""
        return self._cache.get_stats()

    def cleanup_expired_sessions(self) -> int:
        """期限切れセッションをクリーンアップ"""
        return self._cache.cleanup()

    def _search_relevant_places(self, query: str, n_results: int = 5) -> list[dict]:
        """
        ベクトルDBから関連する場所を検索する（RAG検索）

        Args:
            query: 検索クエリ
            n_results: 結果の最大数

        Returns:
            検索結果のリスト
        """
        try:
            results = vector_store.search(query=query, n_results=n_results)
            logger.info(f"RAG検索結果: {len(results)}件")
            return results
        except Exception as e:
            logger.error(f"RAG検索エラー: {e}")
            return []

    def _is_affirmative(self, message: str, suggestion_context: Optional[str] = None) -> bool:
        """
        ユーザーの返答が肯定的かどうかを判定（LLMを使用）

        Args:
            message: ユーザーのメッセージ
            suggestion_context: 提案内容のコンテキスト（LLM判定に使用）

        Returns:
            肯定的な場合True
        """
        if suggestion_context:
            # LLMを使用して判定
            result = llm_service.classify_user_response(message, suggestion_context)
            logger.info(f"LLM賛否判定: message='{message}', result='{result}'")
            return result == "affirmative"
        else:
            # コンテキストがない場合はキーワードベースのフォールバック
            return self._is_affirmative_keyword(message)

    def _is_affirmative_keyword(self, message: str) -> bool:
        """キーワードベースの肯定判定（フォールバック用）"""
        message_lower = message.lower().strip()

        # まず否定的な言葉をチェック（「いいえ」が「いい」と誤マッチしないように）
        negative_words = ["いいえ", "no", "違う", "他の", "別の", "やめ", "ない", "なし", "だめ"]
        if any(word in message_lower for word in negative_words):
            return False

        affirmative_words = [
            "はい", "yes", "ok", "okay", "オッケー", "おっけー",
            "いいね", "いい", "良い", "そこにする", "それにする",
            "行く", "行こう", "行きたい", "決まり", "決定",
            "1", "うん", "ええ", "そうする", "お願い",
            "賛成", "了解", "りょうかい", "わかった", "オーケー"
        ]
        return any(word in message_lower for word in affirmative_words)

    def _is_negative(self, message: str) -> bool:
        """ユーザーの返答が否定的かどうかを判定"""
        negative_words = ["いいえ", "no", "違う", "他", "別", "やめ", "ない", "なし", "2", "ダメ", "却下"]
        message_lower = message.lower().strip()
        return any(word in message_lower for word in negative_words)

    def _wants_stopover_change(self, message: str) -> bool:
        """立ち寄り場所の追加・変更を希望しているかを判定"""
        stopover_keywords = [
            "寄りたい", "立ち寄り", "寄って", "寄る",
            "カフェ", "休憩", "食事", "ランチ", "ディナー", "買い物",
            "観光", "見たい", "食べたい", "飲みたい", "したい"
        ]
        message_lower = message.lower().strip()
        return any(word in message_lower for word in stopover_keywords)

    def _wants_destination_change(self, message: str) -> bool:
        """目的地の変更を希望しているかを判定"""
        destination_keywords = [
            "目的地を変更", "目的地変更", "行き先を変更", "行き先変更",
            "目的地を変えて", "行き先を変えて"
        ]
        message_lower = message.lower().strip()
        return any(word in message_lower for word in destination_keywords)

    def _format_suggestion(self, suggestion: dict, index: int) -> str:
        """提案をフォーマットしてメッセージを生成"""
        place_name = suggestion.get("place_name", "不明")
        address = suggestion.get("address", "")
        impression = suggestion.get("impression", "")

        message = f"**提案{index + 1}: {place_name}**\n"
        if address:
            message += f"住所: {address}\n"
        if impression:
            message += f"前回の感想: 「{impression[:80]}」\n"
        message += "\nここに行きますか？"

        return message

    def process_message(self, request: ChatRequest) -> ChatResponse:
        """
        ユーザーメッセージを処理してレスポンスを生成する

        会話フロー:
        1. WAITING_LOCATION: 現在地を受け取り → 「どこに行きたいですか？」
        2. ASKING_DESTINATION: 目的地を受け取り → 「他に行きたいところ、やってみたいことはありますか？」
        3. ASKING_PREFERENCES: 追加希望を受け取り → RAG検索 → 1つ目の提案
        4. SUGGESTING_FIRST: 1つ目の提案に対する反応 → 賛成なら完了、否定なら2つ目
        5. SUGGESTING_SECOND: 2つ目の提案に対する反応 → 賛成なら完了、否定なら3つ目
        6. SUGGESTING_THIRD: 3つ目の提案に対する反応 → 賛成なら完了、否定なら他の希望を質問
        7. ASKING_OTHER_PREFERENCES: 他の希望がある→ASKING_PREFERENCES、ない→目的地直行

        Args:
            request: チャットリクエスト

        Returns:
            チャットレスポンス
        """
        # セッションの取得または作成
        session_id = request.session_id
        if not session_id or not self._cache.exists(session_id):
            session_id = self.create_session(
                user_preferences=request.context.get("preferences")
                if request.context
                else None,
                favorite_spots=request.context.get("favorite_spots")
                if request.context
                else None,
            )

        context = self._cache.get(session_id)

        # ユーザーメッセージを履歴に追加
        user_message = ChatMessage(
            role=MessageRole.USER,
            content=request.message,
            timestamp=datetime.now(),
        )
        context.messages.append(user_message)

        # フェーズに応じた処理
        response_message = ""
        suggestions = []
        is_complete = False

        if context.phase == ConversationPhase.WAITING_LOCATION:
            # 現在地を受け取り、目的地を質問
            context.current_location = request.message
            context.phase = ConversationPhase.ASKING_DESTINATION
            response_message = "どこに行きたいですか？"
            suggestions = []
            logger.info(f"現在地を受信: {context.current_location}")

        elif context.phase == ConversationPhase.ASKING_DESTINATION:
            # 目的地を受け取り、追加の希望を質問
            context.destination = request.message
            context.phase = ConversationPhase.ASKING_PREFERENCES
            response_message = "他に行きたいところ、やってみたいことはありますか？"
            suggestions = ["カフェで休憩したい", "美味しいものが食べたい", "特にない"]
            logger.info(f"目的地を受信: {context.destination}")

        elif context.phase == ConversationPhase.ASKING_PREFERENCES:
            # 追加希望を受け取り、RAG検索して提案リストを取得
            context.additional_preferences = request.message

            # 「特にない」の場合は目的地直行
            if "特にない" in request.message or "ない" in request.message.lower():
                context.phase = ConversationPhase.NAVIGATING
                response_message = f"目的地は{context.destination}です。立ち寄り場所はありません。\n\nナビゲーションを開始します。\n\n（ナビ中も行きたい場所や目的地の変更があればお知らせください）"
                is_complete = True
                logger.info("立ち寄りなしで目的地直行")
            else:
                # RAG検索: 目的地と追加希望を組み合わせて検索
                search_query = f"{context.destination} {request.message}"
                rag_results = self._search_relevant_places(search_query, n_results=3)
                logger.info(f"RAG検索実行: query='{search_query}', 結果={len(rag_results)}件")

                # 提案リストを保存（最大3つ）
                context.suggestions_list = []
                for result in rag_results[:3]:
                    metadata = result.get("metadata", {})
                    context.suggestions_list.append({
                        "place_name": metadata.get("place_name", "不明"),
                        "address": metadata.get("address", ""),
                        "impression": metadata.get("impression", ""),
                    })

                if context.suggestions_list:
                    # 1つ目の提案を表示
                    context.current_suggestion_index = 0
                    context.phase = ConversationPhase.SUGGESTING_FIRST
                    response_message = self._format_suggestion(context.suggestions_list[0], 0)
                    suggestions = ["はい", "他の場所を見る"]
                else:
                    # 提案がない場合
                    context.phase = ConversationPhase.NAVIGATING
                    response_message = f"申し訳ありません、ご希望に合う場所が見つかりませんでした。\n\n目的地は{context.destination}です。\n\nナビゲーションを開始します。\n\n（ナビ中も行きたい場所や目的地の変更があればお知らせください）"
                    is_complete = True

        elif context.phase == ConversationPhase.SUGGESTING_FIRST:
            # 1つ目の提案に対する反応
            suggestion = context.suggestions_list[0]
            suggestion_context = self._format_suggestion(suggestion, 0)
            if self._is_affirmative(request.message, suggestion_context):
                # 賛成 → ナビゲーション開始
                context.selected_stopover = suggestion["place_name"]
                context.phase = ConversationPhase.NAVIGATING
                response_message = f"目的地は{context.destination}、立ち寄る場所は{context.selected_stopover}です。\n\nナビゲーションを開始します。\n\n（ナビ中も行きたい場所や目的地の変更があればお知らせください）"
                is_complete = True
                logger.info(f"立ち寄り先決定: {context.selected_stopover}")
            else:
                # 否定 → 2つ目の提案
                if len(context.suggestions_list) > 1:
                    context.current_suggestion_index = 1
                    context.phase = ConversationPhase.SUGGESTING_SECOND
                    response_message = self._format_suggestion(context.suggestions_list[1], 1)
                    suggestions = ["はい", "他の場所を見る"]
                else:
                    # 2つ目がない場合
                    context.phase = ConversationPhase.ASKING_OTHER_PREFERENCES
                    response_message = "他に希望はありますか？"
                    suggestions = ["はい", "いいえ（目的地に直行）"]

        elif context.phase == ConversationPhase.SUGGESTING_SECOND:
            # 2つ目の提案に対する反応
            suggestion = context.suggestions_list[1]
            suggestion_context = self._format_suggestion(suggestion, 1)
            if self._is_affirmative(request.message, suggestion_context):
                # 賛成 → ナビゲーション開始
                context.selected_stopover = suggestion["place_name"]
                context.phase = ConversationPhase.NAVIGATING
                response_message = f"目的地は{context.destination}、立ち寄る場所は{context.selected_stopover}です。\n\nナビゲーションを開始します。\n\n（ナビ中も行きたい場所や目的地の変更があればお知らせください）"
                is_complete = True
                logger.info(f"立ち寄り先決定: {context.selected_stopover}")
            else:
                # 否定 → 3つ目の提案
                if len(context.suggestions_list) > 2:
                    context.current_suggestion_index = 2
                    context.phase = ConversationPhase.SUGGESTING_THIRD
                    response_message = self._format_suggestion(context.suggestions_list[2], 2)
                    suggestions = ["はい", "他の場所を見る"]
                else:
                    # 3つ目がない場合
                    context.phase = ConversationPhase.ASKING_OTHER_PREFERENCES
                    response_message = "他に希望はありますか？"
                    suggestions = ["はい", "いいえ（目的地に直行）"]

        elif context.phase == ConversationPhase.SUGGESTING_THIRD:
            # 3つ目の提案に対する反応
            suggestion = context.suggestions_list[2]
            suggestion_context = self._format_suggestion(suggestion, 2)
            if self._is_affirmative(request.message, suggestion_context):
                # 賛成 → ナビゲーション開始
                context.selected_stopover = suggestion["place_name"]
                context.phase = ConversationPhase.NAVIGATING
                response_message = f"目的地は{context.destination}、立ち寄る場所は{context.selected_stopover}です。\n\nナビゲーションを開始します。\n\n（ナビ中も行きたい場所や目的地の変更があればお知らせください）"
                is_complete = True
                logger.info(f"立ち寄り先決定: {context.selected_stopover}")
            else:
                # 否定 → 他の希望を質問
                context.phase = ConversationPhase.ASKING_OTHER_PREFERENCES
                response_message = "他に希望はありますか？"
                suggestions = ["はい", "いいえ（目的地に直行）"]

        elif context.phase == ConversationPhase.ASKING_OTHER_PREFERENCES:
            # 他の希望があるかの確認
            other_pref_context = "他に希望はありますか？（はい/いいえ）"
            if self._is_affirmative(request.message, other_pref_context):
                # 他の希望がある → もう一度質問
                context.phase = ConversationPhase.ASKING_PREFERENCES
                context.suggestions_list = []
                context.current_suggestion_index = 0
                response_message = "行きたいところ・やりたいことはありますか？"
                suggestions = ["カフェで休憩したい", "美味しいものが食べたい", "景色を楽しみたい"]
            else:
                # 希望がない → 目的地直行
                context.phase = ConversationPhase.NAVIGATING
                response_message = f"目的地は{context.destination}です。立ち寄り場所はありません。\n\nナビゲーションを開始します。\n\n（ナビ中も行きたい場所や目的地の変更があればお知らせください）"
                is_complete = True
                logger.info("立ち寄りなしで目的地直行")

        elif context.phase == ConversationPhase.NAVIGATING:
            # ナビゲーション中の変更リクエスト処理
            if self._wants_destination_change(request.message):
                # 目的地変更の希望
                context.phase = ConversationPhase.CONFIRMING_DESTINATION_CHANGE
                response_message = "目的地を変更しますね。新しい目的地を教えてください。"
                suggestions = []
                logger.info("目的地変更リクエスト")
            elif self._wants_stopover_change(request.message):
                # 立ち寄り場所の追加・変更の希望
                context.additional_preferences = request.message
                # RAG検索で新しい提案を取得
                search_query = f"{context.destination} {request.message}"
                rag_results = self._search_relevant_places(search_query, n_results=3)
                logger.info(f"立ち寄り変更RAG検索: query='{search_query}', 結果={len(rag_results)}件")

                context.suggestions_list = []
                for result in rag_results[:3]:
                    metadata = result.get("metadata", {})
                    context.suggestions_list.append({
                        "place_name": metadata.get("place_name", "不明"),
                        "address": metadata.get("address", ""),
                        "impression": metadata.get("impression", ""),
                    })

                if context.suggestions_list:
                    context.current_suggestion_index = 0
                    context.phase = ConversationPhase.CONFIRMING_STOPOVER_CHANGE
                    response_message = f"立ち寄り場所を変更しますね。\n\n{self._format_suggestion(context.suggestions_list[0], 0)}"
                    suggestions = ["はい", "他の場所を見る"]
                else:
                    response_message = "申し訳ありません、ご希望に合う場所が見つかりませんでした。現在のルートを継続します。"
                    suggestions = []
            else:
                # その他のメッセージ
                response_message = f"現在のルート: 目的地は{context.destination}"
                if context.selected_stopover:
                    response_message += f"、立ち寄り場所は{context.selected_stopover}"
                response_message += "です。\n\n行きたい場所や目的地の変更があればお知らせください。"
                suggestions = ["立ち寄り場所を追加", "目的地を変更"]

        elif context.phase == ConversationPhase.CONFIRMING_DESTINATION_CHANGE:
            # 新しい目的地を受け取り
            context.destination = request.message
            context.phase = ConversationPhase.NAVIGATING
            response_message = f"目的地を{context.destination}に変更しました。"
            if context.selected_stopover:
                response_message += f"\n立ち寄り場所は{context.selected_stopover}です。"
            response_message += "\n\nナビゲーションを更新します。"
            suggestions = []
            logger.info(f"目的地変更: {context.destination}")

        elif context.phase == ConversationPhase.CONFIRMING_STOPOVER_CHANGE:
            # 立ち寄り場所変更の確認
            suggestion = context.suggestions_list[context.current_suggestion_index]
            suggestion_context = self._format_suggestion(suggestion, context.current_suggestion_index)
            if self._is_affirmative(request.message, suggestion_context):
                # 新しい立ち寄り場所を確定
                context.selected_stopover = suggestion["place_name"]
                context.phase = ConversationPhase.NAVIGATING
                response_message = f"立ち寄り場所を{context.selected_stopover}に変更しました。\n目的地は{context.destination}です。\n\nナビゲーションを更新します。"
                suggestions = []
                logger.info(f"立ち寄り先変更: {context.selected_stopover}")
            else:
                # 次の提案を表示
                next_index = context.current_suggestion_index + 1
                if next_index < len(context.suggestions_list):
                    context.current_suggestion_index = next_index
                    response_message = self._format_suggestion(context.suggestions_list[next_index], next_index)
                    suggestions = ["はい", "他の場所を見る"]
                else:
                    # 提案が尽きた
                    context.phase = ConversationPhase.NAVIGATING
                    response_message = "他の候補がありません。現在のルートを継続します。\n\n"
                    response_message += f"目的地は{context.destination}"
                    if context.selected_stopover:
                        response_message += f"、立ち寄り場所は{context.selected_stopover}"
                    response_message += "です。"
                    suggestions = []

        # ターンカウントを更新
        context.turn_count += 1

        # AIメッセージを履歴に追加
        ai_message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=response_message,
            timestamp=datetime.now(),
        )
        context.messages.append(ai_message)

        # セッションを更新（TTLも延長される）
        self._cache.set(session_id, context)

        return ChatResponse(
            message=response_message,
            session_id=session_id,
            turn_count=context.turn_count,
            is_complete=is_complete,
            suggestions=suggestions,
        )

    def get_welcome_message(self, session_id: Optional[str] = None) -> ChatResponse:
        """
        ウェルカムメッセージを取得する

        Args:
            session_id: 既存のセッションID（オプション）

        Returns:
            ウェルカムメッセージを含むチャットレスポンス
        """
        if not session_id or not self._cache.exists(session_id):
            session_id = self.create_session()

        welcome_message = (
            "こんにちは！Data Plug Copilotです。\n"
            "あなたの訪問履歴を参考に、おすすめの立ち寄りスポットをご提案します。\n\n"
            "まず、現在地を教えてください。"
        )

        context = self._cache.get(session_id)
        # フェーズを初期状態に設定
        context.phase = ConversationPhase.WAITING_LOCATION

        ai_message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=welcome_message,
            timestamp=datetime.now(),
        )
        context.messages.append(ai_message)

        # セッションを更新
        self._cache.set(session_id, context)

        return ChatResponse(
            message=welcome_message,
            session_id=session_id,
            turn_count=0,
            is_complete=False,
            suggestions=[],
        )


# シングルトンインスタンス
conversation_service = ConversationService()
