from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
    _PARIS = ZoneInfo("Europe/Paris")
except Exception:  # Windows sans le paquet tzdata
    _PARIS = None

def _last_sunday(year: int, month: int) -> datetime:
    d = datetime(year, month, 31, 1, 0, 0)
    return d - timedelta(days=(d.weekday() + 1) % 7)

def paris_now() -> datetime:
    """Heure légale française (naïve). Les horodatages du flux officiel sont exprimés dans ce fuseau,
    alors que le runner GitHub Actions tourne en UTC."""
    utc = datetime.now(timezone.utc)
    if _PARIS is not None:
        return utc.astimezone(_PARIS).replace(tzinfo=None)
    naive = utc.replace(tzinfo=None)
    # Règle UE : heure d'été du dernier dimanche de mars au dernier dimanche d'octobre (01:00 UTC)
    summer = _last_sunday(naive.year, 3) <= naive < _last_sunday(naive.year, 10)
    return naive + timedelta(hours=2 if summer else 1)

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")

def normalize_ts(value: Optional[str]) -> str:
    """Ramène un horodatage du flux ('2026-10-09 14:52:22' ou '2026-10-09T14:52:22+00:00')
    au format comparable 'YYYY-MM-DD HH:MM:SS'. Retourne '' s'il est invalide."""
    if not value:
        return ""
    s = str(value)[:19].replace("T", " ")
    try:
        datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""
    return s

def parse_ts(value: Optional[str]) -> Optional[datetime]:
    s = normalize_ts(value)
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if s else None

def minutes_since_utc_iso(value: Optional[str]) -> float:
    """Minutes écoulées depuis un horodatage produit par utc_now_iso()."""
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return 0.0
    return (datetime.now(timezone.utc).replace(tzinfo=None) - dt).total_seconds() / 60.0

def format_relative_time(dt_str: str) -> str:
    dt = parse_ts(dt_str)
    if dt is None:
        return ""
    diff = (paris_now() - dt).total_seconds()
    if diff < 60:
        return "à l'instant"
    mins = int(diff // 60)
    if mins < 60:
        return f"il y a {mins} min"
    hours = mins // 60
    if hours < 24:
        return f"il y a {hours}h"
    days = hours // 24
    return "hier" if days == 1 else f"il y a {days}j"
