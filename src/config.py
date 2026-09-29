import json
import os
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class LocationConfig:
    mode: str = "gps"  # "gps", "city", or "department"
    latitude: float = 47.6397
    longitude: float = 6.8638
    radius_km: int = 20
    city: str = "Belfort"
    department: str = "90"

@dataclass
class FiltersConfig:
    brands: List[str] = field(default_factory=lambda: ["Total", "Total Access", "TotalEnergies"])
    fuels: List[str] = field(default_factory=lambda: ["Gazole", "SP95", "E10", "SP98", "E85", "GPLc"])

@dataclass
class NtfyConfig:
    enabled: bool = True
    topic: str = "sp-bot-alert-total-belfort"
    server: str = "https://ntfy.sh"
    priority: int = 4  # 4 = High, 5 = Urgent

@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""

@dataclass
class DiscordConfig:
    enabled: bool = False
    webhook_url: str = ""

@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    use_tls: bool = True
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to_addrs: List[str] = field(default_factory=list)

@dataclass
class Config:
    location: LocationConfig = field(default_factory=LocationConfig)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    ntfy: NtfyConfig = field(default_factory=NtfyConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    check_interval_seconds: int = 300
    notify_on_startup: bool = False

def geocode_city_gouv(city_name: str) -> Optional[tuple[float, float, str]]:
    """Résout une ville ou adresse en coordonnées GPS via l'API officielle api-adresse.data.gouv.fr."""
    try:
        params = urllib.parse.urlencode({'q': city_name, 'limit': 1})
        url = f"https://api-adresse.data.gouv.fr/search/?{params}"
        req = urllib.request.Request(url, headers={'User-Agent': 'TotalStationBot/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            features = data.get('features', [])
            if features:
                coords = features[0]['geometry']['coordinates']  # [lon, lat]
                label = features[0]['properties']['label']
                return float(coords[1]), float(coords[0]), label
    except Exception as e:
        print(f"[!] Erreur lors du géocodage de '{city_name}': {e}")
    return None

def load_config(config_path: str = "config.json") -> Config:
    """Charge la configuration depuis le fichier JSON ou retourne les valeurs par défaut."""
    if not os.path.isabs(config_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, config_path)

    if not os.path.exists(config_path):
        cfg = Config()
        save_config(cfg, config_path)
        return cfg

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    loc_data = data.get("location", {})
    loc = LocationConfig(
        mode=loc_data.get("mode", "gps"),
        latitude=float(loc_data.get("latitude", 47.6397)),
        longitude=float(loc_data.get("longitude", 6.8638)),
        radius_km=int(loc_data.get("radius_km", 20)),
        city=loc_data.get("city", "Belfort"),
        department=str(loc_data.get("department", "90"))
    )

    # Si le mode est "city" et les coordonnées GPS ne sont pas fixées manuellement ou changées
    if loc.mode == "city" and loc.city:
        geo = geocode_city_gouv(loc.city)
        if geo:
            loc.latitude, loc.longitude, _ = geo

    filt_data = data.get("filters", {})
    filters = FiltersConfig(
        brands=filt_data.get("brands", ["Total", "Total Access", "TotalEnergies"]),
        fuels=filt_data.get("fuels", ["Gazole", "SP95", "E10", "SP98", "E85", "GPLc"])
    )

    notif_data = data.get("notifications", {})
    ntfy_data = notif_data.get("ntfy", {})
    tg_data = notif_data.get("telegram", {})
    disc_data = notif_data.get("discord", {})
    mail_data = notif_data.get("email", {})

    ntfy = NtfyConfig(
        enabled=ntfy_data.get("enabled", True),
        topic=ntfy_data.get("topic", "sp-bot-alert-total-belfort"),
        server=ntfy_data.get("server", "https://ntfy.sh"),
        priority=int(ntfy_data.get("priority", 4))
    )

    telegram = TelegramConfig(
        enabled=tg_data.get("enabled", False),
        bot_token=tg_data.get("bot_token", ""),
        chat_id=tg_data.get("chat_id", "")
    )

    discord = DiscordConfig(
        enabled=disc_data.get("enabled", False),
        webhook_url=disc_data.get("webhook_url", "")
    )

    # Surcharges par variables d'environnement (pour GitHub Actions / Cloud / Docker)
    env_email_enabled = os.environ.get("EMAIL_ENABLED")
    if env_email_enabled is not None:
        email_enabled = env_email_enabled.lower() in ("true", "1", "yes")
    else:
        email_enabled = mail_data.get("enabled", False)

    env_email_user = os.environ.get("EMAIL_USER") or os.environ.get("MAIL_USERNAME")
    env_email_pass = os.environ.get("EMAIL_PASS") or os.environ.get("MAIL_PASSWORD")
    env_email_to = os.environ.get("EMAIL_TO") or os.environ.get("MAIL_TO")
    env_smtp_host = os.environ.get("SMTP_HOST")
    env_smtp_port = os.environ.get("SMTP_PORT")

    to_addrs_list = mail_data.get("to_addrs", [])
    if env_email_to:
        to_addrs_list = [addr.strip() for addr in env_email_to.split(",") if addr.strip()]

    email = EmailConfig(
        enabled=email_enabled or bool(env_email_user and to_addrs_list),
        smtp_host=env_smtp_host or mail_data.get("smtp_host", "smtp.gmail.com"),
        smtp_port=int(env_smtp_port or mail_data.get("smtp_port", 587)),
        use_tls=mail_data.get("use_tls", True),
        username=env_email_user or mail_data.get("username", ""),
        password=env_email_pass or mail_data.get("password", ""),
        from_addr=mail_data.get("from_addr", "") or env_email_user or "",
        to_addrs=to_addrs_list
    )

    env_ntfy_topic = os.environ.get("NTFY_TOPIC")
    if env_ntfy_topic:
        ntfy.topic = env_ntfy_topic
        ntfy.enabled = True
    elif os.environ.get("NTFY_ENABLED") is not None:
        ntfy.enabled = os.environ.get("NTFY_ENABLED").lower() in ("true", "1", "yes")

    return Config(
        location=loc,
        filters=filters,
        ntfy=ntfy,
        telegram=telegram,
        discord=discord,
        email=email,
        check_interval_seconds=int(os.environ.get("CHECK_INTERVAL", data.get("check_interval_seconds", 300))),
        notify_on_startup=bool(data.get("notify_on_startup", False))
    )

def save_config(config: Config, config_path: str = "config.json") -> None:
    """Sauvegarde la configuration dans le fichier JSON."""
    data = {
        "location": {
            "mode": config.location.mode,
            "latitude": config.location.latitude,
            "longitude": config.location.longitude,
            "radius_km": config.location.radius_km,
            "city": config.location.city,
            "department": config.location.department
        },
        "filters": {
            "brands": config.filters.brands,
            "fuels": config.filters.fuels
        },
        "notifications": {
            "ntfy": {
                "enabled": config.ntfy.enabled,
                "topic": config.ntfy.topic,
                "server": config.ntfy.server,
                "priority": config.ntfy.priority
            },
            "telegram": {
                "enabled": config.telegram.enabled,
                "bot_token": config.telegram.bot_token,
                "chat_id": config.telegram.chat_id
            },
            "discord": {
                "enabled": config.discord.enabled,
                "webhook_url": config.discord.webhook_url
            },
            "email": {
                "enabled": config.email.enabled,
                "smtp_host": config.email.smtp_host,
                "smtp_port": config.email.smtp_port,
                "use_tls": config.email.use_tls,
                "username": config.email.username,
                "password": config.email.password,
                "from_addr": config.email.from_addr,
                "to_addrs": config.email.to_addrs
            }
        },
        "check_interval_seconds": config.check_interval_seconds,
        "notify_on_startup": config.notify_on_startup
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
