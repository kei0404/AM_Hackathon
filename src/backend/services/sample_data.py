"""
サンプルデータ - ベクトルDB初期化用
訪問履歴データ形式: 日時、住所、場所の名前、感想
"""

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


def get_all_sample_data() -> list[dict]:
    """すべてのサンプルデータを取得"""
    all_data = []

    for record in VISIT_RECORDS:
        # ベクトル検索用のテキストを生成
        text = (
            f"日時: {record['datetime']} "
            f"場所: {record['place_name']} "
            f"住所: {record['address']} "
            f"感想: {record['impression']}"
        )

        all_data.append(
            {
                "id": record["id"],
                "text": text,
                "metadata": {
                    "datetime": record["datetime"],
                    "address": record["address"],
                    "place_name": record["place_name"],
                    "impression": record["impression"],
                    "category": "visit_record",
                },
            }
        )

    return all_data
