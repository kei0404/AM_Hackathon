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
from .audio_player_service import audio_player_service
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

    def _generate_audio(self, text: str, play_on_server: bool = True) -> tuple[Optional[str], bool]:
        """
        テキストから音声データを生成し、サーバー側で再生する

        Args:
            text: 音声に変換するテキスト
            play_on_server: サーバー側で再生するかどうか

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
                logger.info(f"TTS音声生成完了: {len(audio_bytes)} bytes")

                # サーバー側で音声を再生
                if play_on_server:
                    logger.info("サーバー側で音声を再生します")
                    audio_player_service.play_audio(audio_bytes, audio_format="mp3")

                audio_data = base64.b64encode(audio_bytes).decode("utf-8")
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

    def _build_conversation_context(self, context: ConversationContext) -> str:
        """会話コンテキストをテキスト形式で構築"""
        context_parts = []

        # 基本情報
        context_parts.append("【セッション情報】")
        context_parts.append(f"- ターン数: {context.turn_count}")
        context_parts.append(f"- 現在のフェーズ: {context.phase.value}")

        # ルート情報
        if context.current_location or context.destination:
            context_parts.append("\n【ルート情報】")
            if context.current_location:
                context_parts.append(f"- 現在地: {context.current_location}")
            if context.destination:
                context_parts.append(f"- 目的地: {context.destination}")

        # ユーザーの希望
        if context.additional_preferences:
            context_parts.append(f"\n【ユーザーの希望】\n{context.additional_preferences}")

        # 提案中の場所
        if context.suggestions_list:
            context_parts.append("\n【提案中の立ち寄り場所】")
            for i, suggestion in enumerate(context.suggestions_list):
                marker = "→ " if i == context.current_suggestion_index else "  "
                context_parts.append(f"{marker}{i+1}. {suggestion.get('place_name', '不明')}")
                if suggestion.get('impression'):
                    context_parts.append(f"     感想: {suggestion.get('impression', '')[:50]}")

        # 会話履歴（最新5件）
        if context.messages:
            context_parts.append("\n【最近の会話履歴】")
            for msg in context.messages[-5:]:
                role = "ユーザー" if msg.role == MessageRole.USER else "AI"
                content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                context_parts.append(f"{role}: {content}")

        return "\n".join(context_parts)

    def _generate_llm_response(
        self,
        context: ConversationContext,
        user_message: str,
        rag_results: Optional[list[dict]] = None,
    ) -> tuple[str, list[str]]:
        """
        LLMを使用して応答を生成

        Args:
            context: 会話コンテキスト
            user_message: ユーザーのメッセージ
            rag_results: RAG検索結果

        Returns:
            (応答メッセージ, 選択肢リスト)
        """
        # システムプロンプトを構築
        system_prompt = """あなたは「Data Plug Copilot」のAIアシスタントです。
車のナビゲーションを支援し、ユーザーが目的地と立ち寄り場所を決める手助けをします。

【最重要ルール】
★ 1回の応答で質問は必ず1つだけにしてください。2つ以上の質問を同時にしないでください。
★ 応答は短く、1-2文以内に収めてください。

【その他のルール】
1. 運転中のユーザーに話しかけるため、応答は簡潔で分かりやすくしてください
2. 選択肢を提示する場合は、必ず以下の形式で出力してください：
   [選択肢]
   1. 選択肢1
   2. 選択肢2
3. 最大3つの選択肢のみ提示してください
4. ユーザーの過去の訪問履歴や感想を参考に、パーソナライズされた提案をしてください

【現在のフェーズに応じた対応】
- ASKING_DESTINATION: 目的地を聞く（1つの質問のみ）
- ASKING_PREFERENCES: 立ち寄りたい場所や希望を聞く（1つの質問のみ）
- SUGGESTING_*: 1つの場所を提案し、行くかどうか確認する（1つの質問のみ）
- ASKING_OTHER_PREFERENCES: 他の希望を聞く（1つの質問のみ）

【禁止事項】
- 「〇〇ですか？それとも△△ですか？」のような複数の質問を含む応答
- 長い説明文の後に質問を付ける応答
"""

        # コンテキストを構築
        conversation_context = self._build_conversation_context(context)

        # RAG検索結果を追加
        if rag_results:
            conversation_context += "\n\n【ユーザーの訪問履歴（RAG検索結果）】"
            for i, result in enumerate(rag_results, 1):
                metadata = result.get("metadata", {})
                conversation_context += f"\n{i}. {metadata.get('place_name', '不明')}"
                if metadata.get('address'):
                    conversation_context += f"\n   住所: {metadata.get('address')}"
                if metadata.get('impression'):
                    conversation_context += f"\n   感想: {metadata.get('impression')}"

        # メッセージを構築
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"【コンテキスト】\n{conversation_context}\n\n【ユーザーの発言】\n{user_message}"},
        ]

        # LLM応答を生成
        response_text = llm_service.generate_response(messages)

        # 選択肢を抽出
        suggestions = []
        if "[選択肢]" in response_text:
            lines = response_text.split("\n")
            in_choices = False
            for line in lines:
                if "[選択肢]" in line:
                    in_choices = True
                    continue
                if in_choices and line.strip():
                    if line.strip()[0].isdigit():
                        choice = line.strip()[2:].strip() if len(line.strip()) > 2 else ""
                        if choice:
                            suggestions.append(choice)

        return response_text, suggestions[:3]

    def _classify_user_response_with_llm(
        self,
        user_message: str,
        current_suggestion: dict,
    ) -> str:
        """
        LLMを使用してユーザーの返答が肯定か否定かを判定

        Returns:
            "affirmative" または "negative"
        """
        suggestion_context = f"提案: {current_suggestion.get('place_name', '不明な場所')}"
        if current_suggestion.get('impression'):
            suggestion_context += f"\n感想: {current_suggestion.get('impression', '')[:50]}"

        return llm_service.classify_user_response(user_message, suggestion_context)

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
        is_llm_generated = False  # LLM生成フラグ（TTS出力判定用）
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

                # LLMを使用して1つ目の提案を生成
                logger.info(f"LLM応答生成: コンテキストとRAG結果を使用")
                response_message, suggestions = self._generate_llm_response(
                    context, request.message, rag_results
                )
                is_llm_generated = True
                if not suggestions:
                    suggestions = ["はい、そこに行きます", "いいえ、次の提案を見たい"]
            else:
                # 検索結果がない場合もLLMで応答生成
                response_message, suggestions = self._generate_llm_response(
                    context, request.message, None
                )
                is_llm_generated = True
                if not response_message:
                    response_message = "申し訳ありません、訪問履歴から適切な場所が見つかりませんでした。\n他の希望はありますか？"

        elif phase in [
            ConversationPhase.SUGGESTING_FIRST,
            ConversationPhase.SUGGESTING_SECOND,
            ConversationPhase.SUGGESTING_THIRD,
        ]:
            # 提案に対するユーザーの返答を処理
            current_suggestion = context.suggestions_list[context.current_suggestion_index]

            # LLMを使用してユーザーの返答を判定
            logger.info(f"LLMでユーザー返答を判定: {request.message}")
            classification = self._classify_user_response_with_llm(
                request.message, current_suggestion
            )
            logger.info(f"判定結果: {classification}")

            if classification == "affirmative":
                # 提案を受け入れた
                context.selected_stopover = current_suggestion.get("place_name")

                # 緯度・経度を取得
                if context.destination:
                    destination_info = geocoding_service.geocode(context.destination)
                    context.destination_info = destination_info

                if context.selected_stopover:
                    stopover_info = geocoding_service.geocode(context.selected_stopover)
                    context.selected_stopover_info = stopover_info

                # LLMで完了メッセージを生成
                response_message, _ = self._generate_llm_response(
                    context, f"ユーザーが{context.selected_stopover}に行くことを決定しました。完了メッセージを生成してください。", None
                )
                is_llm_generated = True
                if not response_message:
                    response_message = (
                        f"了解しました。"
                        f"目的地は{context.destination}、"
                        f"立ち寄り場所は{context.selected_stopover}です。"
                        f"ナビゲーションを開始します。"
                    )
                is_complete = True
                context.phase = ConversationPhase.NAVIGATING

            else:  # negative
                # 提案を拒否した → 次の提案へ
                context.current_suggestion_index += 1

                if context.current_suggestion_index < len(context.suggestions_list):
                    # 次の提案を表示
                    if context.current_suggestion_index == 1:
                        context.phase = ConversationPhase.SUGGESTING_SECOND
                    elif context.current_suggestion_index == 2:
                        context.phase = ConversationPhase.SUGGESTING_THIRD

                    # LLMで次の提案を生成
                    response_message, suggestions = self._generate_llm_response(
                        context, f"ユーザーが前の提案を断りました。次の提案「{context.suggestions_list[context.current_suggestion_index].get('place_name')}」を紹介してください。", None
                    )
                    is_llm_generated = True
                    if not response_message:
                        response_message = self._generate_single_suggestion(context)

                    # 最後の提案かどうかで選択肢を変える
                    if not suggestions:
                        if context.current_suggestion_index == len(context.suggestions_list) - 1:
                            suggestions = ["はい、そこに行きます", "いいえ、他の希望を伝える"]
                        else:
                            suggestions = ["はい、そこに行きます", "いいえ、次の提案を見たい"]
                else:
                    # 全ての提案を拒否した
                    context.phase = ConversationPhase.ASKING_OTHER_PREFERENCES
                    response_message, suggestions = self._generate_llm_response(
                        context, "ユーザーがすべての提案を断りました。他の希望を聞いてください。", None
                    )
                    is_llm_generated = True
                    if not response_message:
                        response_message = "他に希望はありますか？"

        elif phase == ConversationPhase.ASKING_OTHER_PREFERENCES:
            # LLMでユーザーの返答を判定（希望なしかどうか）
            is_no_preference = any(word in request.message for word in ["ない", "特に", "なし", "いらない", "直行"])

            if is_no_preference:
                # 希望なし → 直行
                if context.destination:
                    destination_info = geocoding_service.geocode(context.destination)
                    context.destination_info = destination_info

                # LLMで完了メッセージを生成
                response_message, _ = self._generate_llm_response(
                    context, f"ユーザーが立ち寄り場所は不要と言いました。目的地{context.destination}に直行する旨を伝えてください。", None
                )
                is_llm_generated = True
                if not response_message:
                    response_message = (
                        f"了解しました。"
                        f"目的地は{context.destination}です。"
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

                    # LLMで提案を生成
                    response_message, suggestions = self._generate_llm_response(
                        context, request.message, rag_results
                    )
                    is_llm_generated = True
                    if not suggestions:
                        suggestions = ["はい、そこに行きます", "いいえ、次の提案を見たい"]
                else:
                    response_message, suggestions = self._generate_llm_response(
                        context, request.message, None
                    )
                    is_llm_generated = True
                    if not response_message:
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

        # タイムアウト管理用：最後のAIメッセージを記録
        context.last_ai_message = response_message
        context.last_ai_message_time = datetime.now()

        # ターンカウントを更新
        context.turn_count += 1

        # セッションを更新（TTLも延長される）
        self._cache.set(session_id, context)

        # TTS音声生成（LLM生成メッセージのみ音声を生成）
        audio_data = None
        has_audio = False
        if is_llm_generated:
            logger.info(f"TTS生成開始（LLM生成）: is_complete={is_complete}, message={response_message[:50]}...")
            audio_data, has_audio = self._generate_audio(response_message)
            logger.info(f"TTS生成結果: has_audio={has_audio}, audio_size={len(audio_data) if audio_data else 0}")
        else:
            logger.info(f"TTS生成スキップ（非LLM生成）: message={response_message[:50]}...")

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

        # TTS音声生成（ウェルカムメッセージも音声出力する）
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

    def generate_timeout_response(self, session_id: str) -> Optional[ChatResponse]:
        """
        タイムアウト時にLLMで応答を再生成する

        ベクトルデータと会話キャッシュをコンテキストとして使用し、
        質問を再度行う応答を生成する。

        Args:
            session_id: セッションID

        Returns:
            ChatResponse または セッションが存在しない場合はNone
        """
        context = self._cache.get(session_id)
        if not context:
            logger.warning(f"タイムアウト応答生成: セッションが見つかりません: {session_id}")
            return None

        logger.info(f"タイムアウト応答生成開始: session={session_id}, phase={context.phase.value}")

        # RAG検索: 会話コンテキストに基づいて関連する場所を検索
        rag_results = []
        if context.additional_preferences:
            rag_results = self._search_relevant_places(context.additional_preferences, n_results=3)
            logger.info(f"タイムアウト時RAG検索結果: {len(rag_results)}件")

        # タイムアウト用のシステムプロンプトを構築
        timeout_system_prompt = """あなたは「Data Plug Copilot」のAIアシスタントです。
ユーザーが180秒間応答していないため、再度質問を行います。

【最重要ルール】
★ 1回の応答で質問は必ず1つだけにしてください。
★ 応答は短く、1-2文以内に収めてください。
★ ユーザーがまだそこにいるか確認しつつ、前回の質問を繰り返してください。

【タイムアウト時の対応】
- まず「まだそこにいますか？」などの確認を行う
- その後、現在のフェーズに応じた質問を1つだけ再度行う
- 選択肢がある場合は、必ず以下の形式で出力：
   [選択肢]
   1. 選択肢1
   2. 選択肢2
"""

        # コンテキストを構築
        conversation_context = self._build_conversation_context(context)

        # RAG検索結果を追加
        if rag_results:
            conversation_context += "\n\n【ユーザーの訪問履歴（RAG検索結果）】"
            for i, result in enumerate(rag_results, 1):
                metadata = result.get("metadata", {})
                conversation_context += f"\n{i}. {metadata.get('place_name', '不明')}"
                if metadata.get('address'):
                    conversation_context += f"\n   住所: {metadata.get('address')}"
                if metadata.get('impression'):
                    conversation_context += f"\n   感想: {metadata.get('impression')}"

        # メッセージを構築
        messages = [
            {"role": "system", "content": timeout_system_prompt},
            {"role": "user", "content": f"【コンテキスト】\n{conversation_context}\n\n【状況】\nユーザーが180秒間応答していません。現在のフェーズは「{context.phase.value}」です。再度質問を行ってください。"},
        ]

        # LLM応答を生成
        response_text = llm_service.generate_response(messages)

        # 選択肢を抽出
        suggestions = []
        if "[選択肢]" in response_text:
            lines = response_text.split("\n")
            in_choices = False
            for line in lines:
                if "[選択肢]" in line:
                    in_choices = True
                    continue
                if in_choices and line.strip():
                    if line.strip()[0].isdigit():
                        choice = line.strip()[2:].strip() if len(line.strip()) > 2 else ""
                        if choice:
                            suggestions.append(choice)
        suggestions = suggestions[:3]

        # AIメッセージを履歴に追加
        ai_message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=response_text,
            timestamp=datetime.now(),
        )
        context.messages.append(ai_message)

        # タイムアウト管理用：最後のAIメッセージを記録
        context.last_ai_message = response_text
        context.last_ai_message_time = datetime.now()

        # セッションを更新
        self._cache.set(session_id, context)

        # TTS音声生成（LLM生成メッセージなので音声出力）
        logger.info(f"タイムアウト応答TTS生成: {response_text[:50]}...")
        audio_data, has_audio = self._generate_audio(response_text)

        # 提案関連の情報を設定
        suggestion_index = None
        suggestion_total = None
        if context.suggestions_list:
            suggestion_index = context.current_suggestion_index + 1
            suggestion_total = len(context.suggestions_list)

        return ChatResponse(
            message=response_text,
            session_id=session_id,
            turn_count=context.turn_count,
            is_complete=False,
            suggestions=suggestions,
            suggestion_index=suggestion_index,
            suggestion_total=suggestion_total,
            audio_data=audio_data,
            has_audio=has_audio,
        )


# シングルトンインスタンス
conversation_service = ConversationService()
