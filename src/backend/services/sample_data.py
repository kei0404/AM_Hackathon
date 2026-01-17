"""
サンプルデータ - ベクトルDB初期化用
訪問履歴データ形式: 日時、住所、場所の名前、感想

データフロー:
1. このファイル(sample_data.py)の VISIT_RECORDS がマスターデータ
2. Start時: VISIT_RECORDS → data/user_data/user_data.json に保存
3. ベクトル化: data/user_data/*.json → ChromaDB に登録
4. Stop時: data/user_data/*.json と ChromaDB のデータを削除

データファイル形式:
- 1ファイルあたり最大5000件
- user_data.json, user_data_1.json, user_data_2.json, ...
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# データ保存ディレクトリ
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "user_data"

# 1ファイルあたりの最大レコード数
MAX_RECORDS_PER_FILE = 5000

# 訪問履歴のサンプルデータ
VISIT_RECORDS = [
    {
        "id": "visit_001",
        "datetime": "2026-01-15 12:30",
        "address": "東京都江東区白河1-4-8",
        "place_name": "Blue Bottle Coffee 清澄白河",
        "impression": "静かで落ち着いた雰囲気。コーヒーの品質が高く、2時間ほど作業に集中できた。また来たい。",
    },
    {
        "id": "visit_002",
        "datetime": "2026-01-12 10:00",
        "address": "東京都渋谷区代々木神園町2-1",
        "place_name": "代々木公園",
        "impression": "天気が良くてピクニックに最適だった。緑が多くてリフレッシュできた。週末の散歩コースにしたい。",
    },
    {
        "id": "visit_003",
        "datetime": "2026-01-08 14:00",
        "address": "東京都港区六本木6-10-1",
        "place_name": "森美術館",
        "impression": "現代アート展がとても刺激的だった。展望台からの夜景も素晴らしい。デートにもおすすめ。",
    },
    {
        "id": "visit_004",
        "datetime": "2026-01-05 07:30",
        "address": "東京都中央区築地4-16-2",
        "place_name": "築地場外市場",
        "impression": "朝早く行ったので混雑を避けられた。新鮮な海鮮丼が美味しかった。外国人観光客も多かった。",
    },
    {
        "id": "visit_005",
        "datetime": "2025-12-28 11:00",
        "address": "東京都武蔵野市御殿山1-18-31",
        "place_name": "井の頭恩賜公園",
        "impression": "ボートに乗って楽しんだ。紅葉の時期は過ぎていたが、冬の景色も風情があった。",
    },
    {
        "id": "visit_006",
        "datetime": "2025-12-20 19:00",
        "address": "東京都新宿区新宿3-38-1",
        "place_name": "ルミネエスト新宿",
        "impression": "クリスマス前で混雑していたが、イルミネーションが綺麗だった。買い物も楽しめた。",
    },
    {
        "id": "visit_007",
        "datetime": "2025-12-15 13:00",
        "address": "東京都台東区上野公園7-7",
        "place_name": "国立科学博物館",
        "impression": "恐竜の展示が迫力満点。子供連れにも良さそう。丸一日かけてゆっくり見たい。",
    },
    {
        "id": "visit_008",
        "datetime": "2025-12-10 18:30",
        "address": "東京都渋谷区恵比寿4-20-3",
        "place_name": "恵比寿ガーデンプレイス",
        "impression": "バカラのシャンデリアが美しかった。冬のイルミネーションスポットとして最高。",
    },
    {
        "id": "visit_009",
        "datetime": "2025-12-05 15:00",
        "address": "神奈川県横浜市中区山下町279",
        "place_name": "横浜中華街",
        "impression": "食べ歩きが楽しかった。小籠包と肉まんが特に美味しかった。お土産も買えた。",
    },
    {
        "id": "visit_010",
        "datetime": "2025-11-30 09:00",
        "address": "神奈川県鎌倉市長谷4-2-28",
        "place_name": "鎌倉大仏",
        "impression": "朝早く行ったので空いていた。大仏の中にも入れて貴重な体験だった。周辺の寺社も散策した。",
    },
]


def ensure_data_dir() -> Path:
    """データディレクトリを作成して返す"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def save_sample_data_to_files() -> int:
    """
    サンプルデータを data/user_data に統合JSONファイルとして保存する
    5000件を超える場合はファイルを分割する

    Returns:
        保存したレコード数
    """
    data_dir = ensure_data_dir()

    # レコードを分割して保存
    total_records = len(VISIT_RECORDS)
    file_index = 0
    saved_count = 0

    for i in range(0, total_records, MAX_RECORDS_PER_FILE):
        chunk = VISIT_RECORDS[i : i + MAX_RECORDS_PER_FILE]

        # ファイル名を決定
        if file_index == 0:
            file_name = "user_data.json"
        else:
            file_name = f"user_data_{file_index}.json"

        file_path = data_dir / file_name

        # JSONファイルとして保存
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                {"records": chunk, "count": len(chunk), "file_index": file_index},
                f,
                ensure_ascii=False,
                indent=2,
            )

        saved_count += len(chunk)
        file_index += 1

    logger.info(f"サンプルデータを保存: {saved_count}件 -> {data_dir}")
    return saved_count


def load_data_from_files() -> list[dict]:
    """
    data/user_data からJSONファイルを読み込む

    Returns:
        読み込んだレコードのリスト
    """
    if not DATA_DIR.exists():
        logger.warning(f"データディレクトリが存在しません: {DATA_DIR}")
        return []

    records = []

    # user_data.json, user_data_1.json, ... の順で読み込み
    main_file = DATA_DIR / "user_data.json"
    if main_file.exists():
        try:
            with open(main_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                records.extend(data.get("records", []))
        except Exception as e:
            logger.error(f"ファイル読み込みエラー: {main_file} - {e}")

    # 分割ファイルを読み込み
    file_index = 1
    while True:
        split_file = DATA_DIR / f"user_data_{file_index}.json"
        if not split_file.exists():
            break

        try:
            with open(split_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                records.extend(data.get("records", []))
        except Exception as e:
            logger.error(f"ファイル読み込みエラー: {split_file} - {e}")

        file_index += 1

    logger.info(f"データファイルを読み込み: {len(records)}件")
    return records


def get_user_data_summary() -> dict:
    """
    data/user_data のサマリ情報を取得する（UI表示用）

    Returns:
        サマリ情報の辞書
    """
    records = load_data_from_files()

    return {
        "total_count": len(records),
        "records": records,
        "file_count": len(list(DATA_DIR.glob("user_data*.json"))) if DATA_DIR.exists() else 0,
    }


def clear_data_files() -> int:
    """
    data/user_data 内のすべてのデータファイルを削除する

    Returns:
        削除したファイル数
    """
    if not DATA_DIR.exists():
        return 0

    deleted_count = 0
    for file_path in DATA_DIR.glob("user_data*.json"):
        try:
            file_path.unlink()
            deleted_count += 1
        except Exception as e:
            logger.error(f"ファイル削除エラー: {file_path} - {e}")

    logger.info(f"データファイルを削除: {deleted_count}件")
    return deleted_count


def convert_records_to_vector_format(records: list[dict]) -> list[dict]:
    """
    レコードをベクトルDB登録用の形式に変換する

    Args:
        records: 訪問履歴レコードのリスト

    Returns:
        ベクトルDB登録用のデータリスト
    """
    all_data = []

    for record in records:
        # ベクトル検索用のテキストを生成
        text = (
            f"日時: {record.get('datetime', '')} "
            f"場所: {record.get('place_name', '')} "
            f"住所: {record.get('address', '')} "
            f"感想: {record.get('impression', '')}"
        )

        all_data.append(
            {
                "id": record.get("id", ""),
                "text": text,
                "metadata": {
                    "datetime": record.get("datetime", ""),
                    "address": record.get("address", ""),
                    "place_name": record.get("place_name", ""),
                    "impression": record.get("impression", ""),
                    "category": "visit_record",
                },
            }
        )

    return all_data


def get_all_sample_data() -> list[dict]:
    """すべてのサンプルデータを取得（メモリ上のデータから）"""
    return convert_records_to_vector_format(VISIT_RECORDS)


def get_data_from_files() -> list[dict]:
    """ファイルからデータを読み込んでベクトルDB用形式に変換"""
    records = load_data_from_files()
    return convert_records_to_vector_format(records)
