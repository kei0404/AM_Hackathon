"""
ジオコーディングサービス - 場所名から緯度・経度を取得
"""

import logging
from typing import Optional

import requests

from ..models.chat import PlaceInfo

logger = logging.getLogger(__name__)


class GeocodingService:
    """OpenStreetMap Nominatim APIを使用したジオコーディングサービス"""

    def __init__(self) -> None:
        """ジオコーディングサービスの初期化"""
        self.base_url = "https://nominatim.openstreetmap.org/search"
        self.headers = {
            "User-Agent": "DataPlugCopilot/1.0"
        }

    def geocode(self, place_name: str) -> Optional[PlaceInfo]:
        """
        場所名から緯度・経度を取得する

        Args:
            place_name: 場所名（例: "東京駅", "横浜駅"）

        Returns:
            PlaceInfo（緯度・経度付き）、または取得できない場合はNone
        """
        if not place_name or not place_name.strip():
            return None

        try:
            # 日本の場所を優先して検索
            params = {
                "q": place_name,
                "format": "json",
                "limit": 1,
                "countrycodes": "jp",
            }

            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()

            results = response.json()

            if results and len(results) > 0:
                result = results[0]
                latitude = float(result.get("lat", 0))
                longitude = float(result.get("lon", 0))

                logger.info(
                    f"ジオコーディング成功: {place_name} -> "
                    f"lat={latitude}, lon={longitude}"
                )

                return PlaceInfo(
                    name=place_name,
                    latitude=latitude,
                    longitude=longitude,
                )

            logger.warning(f"ジオコーディング結果なし: {place_name}")
            return PlaceInfo(name=place_name, latitude=None, longitude=None)

        except requests.RequestException as e:
            logger.error(f"ジオコーディングAPIエラー: {e}")
            return PlaceInfo(name=place_name, latitude=None, longitude=None)

        except Exception as e:
            logger.error(f"ジオコーディングエラー: {e}")
            return PlaceInfo(name=place_name, latitude=None, longitude=None)

    def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
    ) -> Optional[str]:
        """
        緯度・経度から住所を取得する（逆ジオコーディング）

        Args:
            latitude: 緯度
            longitude: 経度

        Returns:
            住所文字列、または取得できない場合はNone
        """
        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                "lat": latitude,
                "lon": longitude,
                "format": "json",
            }

            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()

            result = response.json()
            address = result.get("display_name")

            if address:
                logger.info(f"逆ジオコーディング成功: ({latitude}, {longitude}) -> {address}")
                return address

            return None

        except Exception as e:
            logger.error(f"逆ジオコーディングエラー: {e}")
            return None


# シングルトンインスタンス
geocoding_service = GeocodingService()
