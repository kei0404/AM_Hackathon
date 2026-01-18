"""
位置情報サービス - サーバー側の現在位置取得
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Location:
    """位置情報"""
    latitude: float
    longitude: float
    address: Optional[str] = None
    source: str = "unknown"


class LocationService:
    """位置情報サービス"""

    def __init__(self) -> None:
        self._cached_location: Optional[Location] = None

    def get_current_location(self) -> Optional[Location]:
        """
        サーバーの現在位置を取得

        取得方法の優先順位:
        1. macOS CoreLocation (whereami コマンド)
        2. IP ベースの位置情報
        3. デフォルト位置（東京駅）
        """
        # キャッシュがあれば返す
        if self._cached_location:
            return self._cached_location

        # macOS CoreLocation を試行
        location = self._get_macos_location()
        if location:
            self._cached_location = location
            return location

        # IP ベースの位置情報を試行
        location = self._get_ip_location()
        if location:
            self._cached_location = location
            return location

        # デフォルト位置（東京駅）
        logger.warning("位置情報を取得できませんでした。デフォルト位置を使用します")
        return Location(
            latitude=35.6812,
            longitude=139.7671,
            address="東京都千代田区丸の内1丁目（東京駅）",
            source="default",
        )

    def _get_macos_location(self) -> Optional[Location]:
        """macOS CoreLocation から位置情報を取得"""
        try:
            # CoreLocationCLI または whereami コマンドを使用
            result = subprocess.run(
                ["CoreLocationCLI", "-once", "-format", "%latitude,%longitude"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                if len(parts) == 2:
                    lat, lng = float(parts[0]), float(parts[1])
                    logger.info(f"macOS位置情報取得成功: {lat}, {lng}")
                    return Location(
                        latitude=lat,
                        longitude=lng,
                        source="macos_corelocation",
                    )
        except FileNotFoundError:
            logger.debug("CoreLocationCLI が見つかりません")
        except subprocess.TimeoutExpired:
            logger.warning("macOS位置情報取得タイムアウト")
        except Exception as e:
            logger.debug(f"macOS位置情報取得エラー: {e}")

        return None

    def _get_ip_location(self) -> Optional[Location]:
        """IP アドレスベースの位置情報を取得"""
        try:
            import requests

            # ipinfo.io API を使用（無料、APIキー不要）
            response = requests.get("https://ipinfo.io/json", timeout=5)
            if response.status_code == 200:
                data = response.json()
                loc = data.get("loc", "")
                if loc:
                    parts = loc.split(",")
                    if len(parts) == 2:
                        lat, lng = float(parts[0]), float(parts[1])
                        city = data.get("city", "")
                        region = data.get("region", "")
                        logger.info(f"IP位置情報取得成功: {lat}, {lng} ({city}, {region})")
                        return Location(
                            latitude=lat,
                            longitude=lng,
                            address=f"{city}, {region}",
                            source="ip_geolocation",
                        )
        except Exception as e:
            logger.debug(f"IP位置情報取得エラー: {e}")

        return None

    def clear_cache(self) -> None:
        """キャッシュをクリア"""
        self._cached_location = None


# シングルトンインスタンス
location_service = LocationService()
