"""
会話サービス - セッション管理と会話フローの制御（TTL付きキャッシュ）
"""

import base64
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
    PlaceInfo,
)
from .geocoding_service import geocoding_service
from .llm_service import llm_service
from .sample_data import (
    get_data_from_files,
    save_sample_data_to_files,
)
from .tts_service import tts_service
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

    def _generate_audio(self, text: str) -> tuple[Optional[str], bool]:
        """
        テキストから音声データを生成する

        Args:
            text: 音声に変換するテキスト

        Returns:
            (Base64エンコードされた音声データ, 音声があるかどうか)
        """
        if not tts_service.is_available():
            logger.warning("TTSサービスが利用できません")
            return None, False

        try:
            logger.info(f"TTS音声生成開始: {text[:50]}...")
            audio_bytes = tts_service.text_to_speech(text)
            if audio_bytes:
                audio_data = base64.b64encode(audio_bytes).decode("utf-8")
                logger.info(f"TTS音声生成完了: {len(audio_bytes)} bytes")
                return audio_data, True
        except Exception as e:
            logger.warning(f"TTS変換に失敗しました: {e}")

        return None, False

    def initialize_user_data(self) -> int:
        """
        ユーザーデータを初期化する（WebSocketセッション自動生成時に使用）

        処理フロー:
        1. VectorStoreを再初期化
        2. サンプルデータをファイルに保存
        3. ファイルからデータを読み込み、ベクトル化してChromaDBに登録

        Returns:
            登録されたドキュメント数
        """
        try:
            # VectorStoreを先に再初期化
            vector_store.reinitialize()
            logger.info("[WebSocket] VectorStore再初期化完了")

            # sample_data.py の VISIT_RECORDS を data/user_data/*.json に保存
            saved_count = save_sample_data_to_files()
            logger.info(f"[WebSocket] data/user_data に保存: {saved_count}件")

            # ファイルからデータを読み込み、ベクトル化してChromaDBに登録
            vector_data = get_data_from_files()
            logger.info(f"[WebSocket] ベクトル化対象: {len(vector_data)}件")

            if vector_data:
                doc_ids = [d["id"] for d in vector_data]
                texts = [d["text"] for d in vector_data]
                metadatas = [d["metadata"] for d in vector_data]

                vector_store.add_documents(
                    doc_ids=doc_ids,
                    texts=texts,
                    metadatas=metadatas,
                )

                count = vector_store.count()
                logger.info(f"[WebSocket] ChromaDB登録完了: {count}件")
                return count

            return 0

        except Exception as e:
            logger.error(f"[WebSocket] データ初期化エラー: {e}", exc_info=True)
            return 0

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

    def _is_affirmative_response(self, message: str) -> bool:
        """ユーザーの返答が肯定的かどうかを判定"""
        affirmative_words = [
            "はい", "yes", "ok", "okay", "オッケー", "おっけー",
            "いいね", "いい", "良い", "そこにする", "それにする",
            "行く", "行こう", "行きたい", "決まり", "決定",
            "うん", "ええ", "そうする", "お願い", "賛成",
            "了解", "りょうかい", "わかった", "オーケー"
        ]
        message_lower = message.lower().strip()
        return any(word in message_lower for word in affirmative_words)

    def _is_negative_response(self, message: str) -> bool:
        """ユーザーの返答が否定的かどうかを判定"""
        negative_words = [
            "いいえ", "no", "違う", "他の", "別の", "やめ",
            "ない", "なし", "だめ", "嫌", "いや", "結構です",
            "次", "他", "別"
        ]
        message_lower = message.lower().strip()
        return any(word in message_lower for word in negative_words)

    def _generate_single_suggestion(self, context: ConversationContext) -> str:
        """現在のインデックスの提案を1つ生成"""
        if not context.suggestions_list:
            return "提案がありません。"

        idx = context.current_suggestion_index
        if idx >= len(context.suggestions_list):
            return None

        suggestion = context.suggestions_list[idx]
        place_name = suggestion.get("place_name", "不明な場所")
        impression = suggestion.get("impression", "")
        address = suggestion.get("address", "")

        # 提案メッセージを生成
        total = len(context.suggestions_list)
        msg = f"{idx + 1}つ目の提案: {place_name}\n"
        if address:
            msg += f"住所: {address}\n"
        if impression:
            msg += f"前回の感想: 「{impression[:80]}」\n"
        msg += "\nここに行きますか？"

        return msg

    def process_message(self, request: ChatRequest) -> ChatResponse:
        """
        ユーザーメッセージを処理してレスポンスを生成する
        フェーズベースの会話フローで1つずつ提案を行う

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

        # 現在地・目的地を更新（リクエストに含まれている場合）
        if request.current_location:
            context.current_location = request.current_location
        if request.destination:
            context.destination = request.destination

        # ユーザーメッセージを履歴に追加
        user_message = ChatMessage(
            role=MessageRole.USER,
            content=request.message,
            timestamp=datetime.now(),
        )
        context.messages.append(user_message)

        # 応答メッセージと選択肢
        response_message = ""
        suggestions = []
        is_complete = False
        destination_info: Optional[PlaceInfo] = None
        stopover_info: Optional[PlaceInfo] = None

        # フェーズに応じた処理
        phase = context.phase

        if phase == ConversationPhase.WAITING_LOCATION:
            # 現在地を設定して目的地質問フェーズへ
            context.current_location = request.message
            context.phase = ConversationPhase.ASKING_DESTINATION
            response_message = "どこに行きたいですか？"

        elif phase == ConversationPhase.ASKING_DESTINATION:
            # 目的地を設定して希望質問フェーズへ
            context.destination = request.message
            context.phase = ConversationPhase.ASKING_PREFERENCES
            response_message = f"{request.message}ですね。他に行きたいところ、やってみたいことはありますか？"

        elif phase == ConversationPhase.ASKING_PREFERENCES:
            # 希望を保存してRAG検索を実行
            context.additional_preferences = request.message

            # RAG検索: ユーザーの希望に関連する訪問履歴を検索
            rag_results = self._search_relevant_places(request.message, n_results=3)

            if rag_results:
                # 提案リストを作成（最大3つ）
                context.suggestions_list = []
                for result in rag_results[:3]:
                    metadata = result.get("metadata", {})
                    context.suggestions_list.append({
                        "place_name": metadata.get("place_name", ""),
                        "address": metadata.get("address", ""),
                        "impression": metadata.get("impression", ""),
                    })

                context.current_suggestion_index = 0
                context.phase = ConversationPhase.SUGGESTING_FIRST

                # 1つ目の提案を生成
                response_message = self._generate_single_suggestion(context)
                suggestions = ["はい、そこに行きます", "いいえ、次の提案を見たい"]
            else:
                # 検索結果がない場合
                response_message = "申し訳ありません、訪問履歴から適切な場所が見つかりませんでした。\n他の希望はありますか？"

        elif phase in [
            ConversationPhase.SUGGESTING_FIRST,
            ConversationPhase.SUGGESTING_SECOND,
            ConversationPhase.SUGGESTING_THIRD,
        ]:
            # 提案に対するユーザーの返答を処理
            if self._is_affirmative_response(request.message):
                # 提案を受け入れた
                current_suggestion = context.suggestions_list[context.current_suggestion_index]
                context.selected_stopover = current_suggestion.get("place_name")

                # 緯度・経度を取得
                if context.destination:
                    destination_info = geocoding_service.geocode(context.destination)
                    context.destination_info = destination_info

                if context.selected_stopover:
                    stopover_info = geocoding_service.geocode(context.selected_stopover)
                    context.selected_stopover_info = stopover_info

                # 完了メッセージ
                response_message = (
                    f"了解しました。\n"
                    f"目的地: {context.destination}\n"
                    f"立ち寄り場所: {context.selected_stopover}\n"
                    f"ナビゲーションを開始します。"
                )
                is_complete = True
                context.phase = ConversationPhase.NAVIGATING

            elif self._is_negative_response(request.message):
                # 提案を拒否した → 次の提案へ
                context.current_suggestion_index += 1

                if context.current_suggestion_index < len(context.suggestions_list):
                    # 次の提案を表示
                    if context.current_suggestion_index == 1:
                        context.phase = ConversationPhase.SUGGESTING_SECOND
                    elif context.current_suggestion_index == 2:
                        context.phase = ConversationPhase.SUGGESTING_THIRD

                    response_message = self._generate_single_suggestion(context)

                    # 最後の提案かどうかで選択肢を変える
                    if context.current_suggestion_index == len(context.suggestions_list) - 1:
                        suggestions = ["はい、そこに行きます", "いいえ、他の希望を伝える"]
                    else:
                        suggestions = ["はい、そこに行きます", "いいえ、次の提案を見たい"]
                else:
                    # 全ての提案を拒否した
                    context.phase = ConversationPhase.ASKING_OTHER_PREFERENCES
                    response_message = "他に希望はありますか？"
            else:
                # 不明な返答
                response_message = "「はい」または「いいえ」でお答えください。\nここに行きますか？"
                suggestions = ["はい、そこに行きます", "いいえ、次の提案を見たい"]

        elif phase == ConversationPhase.ASKING_OTHER_PREFERENCES:
            # 他の希望がある場合 → 再度RAG検索
            if "ない" in request.message or "特に" in request.message or "なし" in request.message:
                # 希望なし → 直行
                if context.destination:
                    destination_info = geocoding_service.geocode(context.destination)
                    context.destination_info = destination_info

                response_message = (
                    f"了解しました。\n"
                    f"目的地: {context.destination}\n"
                    f"直行します。"
                )
                is_complete = True
                context.phase = ConversationPhase.NAVIGATING
            else:
                # 新しい希望で再検索
                context.additional_preferences = request.message
                rag_results = self._search_relevant_places(request.message, n_results=3)

                if rag_results:
                    context.suggestions_list = []
                    for result in rag_results[:3]:
                        metadata = result.get("metadata", {})
                        context.suggestions_list.append({
                            "place_name": metadata.get("place_name", ""),
                            "address": metadata.get("address", ""),
                            "impression": metadata.get("impression", ""),
                        })

                    context.current_suggestion_index = 0
                    context.phase = ConversationPhase.SUGGESTING_FIRST
                    response_message = self._generate_single_suggestion(context)
                    suggestions = ["はい、そこに行きます", "いいえ、次の提案を見たい"]
                else:
                    response_message = "申し訳ありません、適切な場所が見つかりませんでした。\n他の希望はありますか？"

        else:
            # その他のフェーズ（ナビゲーション中など）
            response_message = "現在ナビゲーション中です。何かお手伝いできることはありますか？"

        # AIメッセージを履歴に追加
        ai_message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=response_message,
            timestamp=datetime.now(),
        )
        context.messages.append(ai_message)

        # ターンカウントを更新
        context.turn_count += 1

        # セッションを更新（TTLも延長される）
        self._cache.set(session_id, context)

        # TTS音声生成
        audio_data, has_audio = self._generate_audio(response_message)

        # 提案関連の情報を設定
        suggestion_index = None
        suggestion_total = None
        if context.suggestions_list and not is_complete:
            suggestion_index = context.current_suggestion_index + 1  # 1-indexed
            suggestion_total = len(context.suggestions_list)

        return ChatResponse(
            message=response_message,
            session_id=session_id,
            turn_count=context.turn_count,
            is_complete=is_complete,
            suggestions=suggestions,
            suggestion_index=suggestion_index,
            suggestion_total=suggestion_total,
            destination=destination_info,
            stopover=stopover_info,
            audio_data=audio_data,
            has_audio=has_audio,
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

        context = self._cache.get(session_id)

        # フェーズを目的地質問に設定
        context.phase = ConversationPhase.ASKING_DESTINATION

        welcome_message = (
            "こんにちは！Data Plug Copilotです。\n"
            "どこに行きたいですか？"
        )

        ai_message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=welcome_message,
            timestamp=datetime.now(),
        )
        context.messages.append(ai_message)

        # セッションを更新
        self._cache.set(session_id, context)

        # TTS音声生成
        audio_data, has_audio = self._generate_audio(welcome_message)

        return ChatResponse(
            message=welcome_message,
            session_id=session_id,
            turn_count=0,
            is_complete=False,
            suggestions=[],
            audio_data=audio_data,
            has_audio=has_audio,
        )


# シングルトンインスタンス
conversation_service = ConversationService()
