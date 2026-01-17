"""
サンプルデータ - ベクトルDB初期化用
"""

# お気に入りスポットのサンプルデータ
FAVORITE_SPOTS = [
    {
        "id": "spot_001",
        "name": "Blue Bottle Coffee 清澄白河",
        "description": "静かで落ち着いた雰囲気のカフェ。コーヒーの品質が高く、ゆっくり作業できる。",
        "category": "favorite_spot",
        "tags": ["カフェ", "コーヒー", "静か", "作業向け"],
        "location": {"lat": 35.6812, "lng": 139.7996},
        "rating": 4.5,
    },
    {
        "id": "spot_002",
        "name": "代々木公園",
        "description": "都心にある広大な公園。自然を楽しめる。散歩やピクニックに最適。",
        "category": "favorite_spot",
        "tags": ["公園", "自然", "散歩", "リラックス"],
        "location": {"lat": 35.6716, "lng": 139.6949},
        "rating": 4.3,
    },
    {
        "id": "spot_003",
        "name": "森美術館",
        "description": "六本木ヒルズにある現代アート美術館。展望台も併設。",
        "category": "favorite_spot",
        "tags": ["美術館", "アート", "展望台", "六本木"],
        "location": {"lat": 35.6604, "lng": 139.7292},
        "rating": 4.4,
    },
    {
        "id": "spot_004",
        "name": "築地場外市場",
        "description": "新鮮な海鮮や食材が楽しめる市場。朝食や食べ歩きに人気。",
        "category": "favorite_spot",
        "tags": ["市場", "海鮮", "グルメ", "朝食"],
        "location": {"lat": 35.6654, "lng": 139.7707},
        "rating": 4.2,
    },
    {
        "id": "spot_005",
        "name": "井の頭恩賜公園",
        "description": "吉祥寺にある人気の公園。池でボートも楽しめる。",
        "category": "favorite_spot",
        "tags": ["公園", "自然", "ボート", "吉祥寺"],
        "location": {"lat": 35.7003, "lng": 139.5746},
        "rating": 4.4,
    },
]

# ユーザー嗜好のサンプルデータ
USER_PREFERENCES = [
    {
        "id": "pref_001",
        "description": "静かな場所が好き。騒がしいところは苦手。",
        "category": "preference",
        "type": "atmosphere",
    },
    {
        "id": "pref_002",
        "description": "コーヒーが好き。特に浅煎りのスペシャルティコーヒーを好む。",
        "category": "preference",
        "type": "food",
    },
    {
        "id": "pref_003",
        "description": "自然の中でリラックスするのが好き。緑が多い場所を好む。",
        "category": "preference",
        "type": "environment",
    },
    {
        "id": "pref_004",
        "description": "アートや文化的な体験を楽しむのが好き。",
        "category": "preference",
        "type": "interest",
    },
    {
        "id": "pref_005",
        "description": "混雑を避けたい。平日や早朝を好む。",
        "category": "preference",
        "type": "timing",
    },
]

# 訪問履歴のサンプルデータ
VISIT_HISTORY = [
    {
        "id": "history_001",
        "description": "先週Blue Bottle Coffeeで2時間作業した。とても集中できた。",
        "category": "history",
        "spot_id": "spot_001",
        "date": "2026-01-10",
        "duration_minutes": 120,
        "satisfaction": 5,
    },
    {
        "id": "history_002",
        "description": "先月代々木公園でピクニックをした。天気が良くて気持ちよかった。",
        "category": "history",
        "spot_id": "spot_002",
        "date": "2025-12-15",
        "duration_minutes": 180,
        "satisfaction": 4,
    },
    {
        "id": "history_003",
        "description": "森美術館で現代アート展を鑑賞。刺激的な展示だった。",
        "category": "history",
        "spot_id": "spot_003",
        "date": "2025-11-20",
        "duration_minutes": 150,
        "satisfaction": 5,
    },
]


def get_all_sample_data() -> list[dict]:
    """すべてのサンプルデータを取得"""
    all_data = []

    for spot in FAVORITE_SPOTS:
        all_data.append(
            {
                "id": spot["id"],
                "text": f"{spot['name']}: {spot['description']} タグ: {', '.join(spot['tags'])}",
                "metadata": {
                    "category": spot["category"],
                    "name": spot["name"],
                    "rating": spot["rating"],
                },
            }
        )

    for pref in USER_PREFERENCES:
        all_data.append(
            {
                "id": pref["id"],
                "text": pref["description"],
                "metadata": {
                    "category": pref["category"],
                    "type": pref["type"],
                },
            }
        )

    for history in VISIT_HISTORY:
        all_data.append(
            {
                "id": history["id"],
                "text": history["description"],
                "metadata": {
                    "category": history["category"],
                    "spot_id": history["spot_id"],
                    "satisfaction": history["satisfaction"],
                },
            }
        )

    return all_data
