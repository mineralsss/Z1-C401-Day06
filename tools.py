from __future__ import annotations

import json
import math
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func):
        return func


DB_PATH = Path(__file__).resolve().parent / "vinmec.sqlite3"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def get_user_location(location: str = "VinUni, Gia Lam, Ha Noi") -> str:
    """Geocode an input location and return "latitude,longitude"."""
    try:
        alias_map = {
            "vin uni": "VinUni, Gia Lam, Ha Noi",
            "vinuni": "VinUni, Gia Lam, Ha Noi",
            "vin university": "VinUni, Gia Lam, Ha Noi",
        }
        normalized = location.strip().lower()
        location = alias_map.get(normalized, location)

        query = urllib.parse.urlencode(
            {
                "q": location,
                "format": "jsonv2",
                "limit": 1,
            }
        )
        url = f"https://nominatim.openstreetmap.org/search?{query}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "vinmec-assistant/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data:
            lat = data[0]["lat"]
            lon = data[0]["lon"]
            return f"{lat},{lon}"
        return ""
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError):
        return ""


def get_branch_coordinates() -> dict[str, tuple[float, float]]:
    """Read all branch coordinates from the branches table."""
    try:
        with sqlite3.connect(DB_PATH) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT name, latitude, longitude FROM branches")
            rows = cursor.fetchall()
        return {name: (float(lat), float(lon)) for name, lat, lon in rows}
    except sqlite3.Error:
        return {}


@tool
def get_nearest_branch(location: str = "VinUni, Gia Lam, Ha Noi", max_results: int = 3) -> str:
    """Return nearest branch names with distances from an input location."""
    try:
        if isinstance(location, dict):
            location = (
                location.get("location")
                or location.get("address")
                or location.get("query")
                or "VinUni, Gia Lam, Ha Noi"
            )
        elif location is None:
            location = "VinUni, Gia Lam, Ha Noi"
        else:
            location = str(location).strip() or "VinUni, Gia Lam, Ha Noi"

        # Accept either "lat,lon" or a free-text address/place name.
        try:
            user_lat, user_lon = map(float, location.split(","))
        except ValueError:
            user_location = get_user_location(location)
            if not user_location:
                return "Khong geocode duoc dia chi."
            user_lat, user_lon = map(float, user_location.split(","))

        branch_coords = get_branch_coordinates()
        if not branch_coords:
            return "Khong tim thay toa do chi nhanh trong database."

        ranked: list[tuple[str, float]] = []
        for branch_name, (branch_lat, branch_lon) in branch_coords.items():
            distance = _haversine_km(user_lat, user_lon, branch_lat, branch_lon)
            ranked.append((branch_name, distance))

        ranked.sort(key=lambda item: item[1])
        top = ranked[: max(1, int(max_results))]
        return "\n".join(f"{name}: {distance:.1f} km" for name, distance in top)
    except (ValueError, KeyError):
        return "Toa do dau vao khong hop le."


if __name__ == "__main__":
    location_text = " ".join(sys.argv[1:]).strip() or "VinUni, Gia Lam, Ha Noi"
    if hasattr(get_nearest_branch, "invoke"):
        print(get_nearest_branch.invoke({"location": location_text, "max_results": 3}))
    else:
        print(get_nearest_branch(location_text, 3))