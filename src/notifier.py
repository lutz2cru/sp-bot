import json
import smtplib
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any, Optional

from src.tracker import RestockEvent
from src.config import Config, EmailConfig, NtfyConfig

class EmailNotifier:
    """Notificateur E-mail (SMTP) optimisé avec mise en page HTML épurée et boutons Waze/Maps."""
    def __init__(self, config: EmailConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "E-mail (SMTP)"

    def send_restock_event(self, event: RestockEvent) -> bool:
        if not self.config.to_addrs or not self.config.smtp_host:
            return False

        from_addr = self.config.from_addr or self.config.username
        subject = f"⛽ {event.status_badge} : {event.brand} ({event.city} - {event.distance_km} km)"

        # Corps texte brut
        text = (
            f"RÉAPPROVISIONNEMENT DÉTECTÉ !\n\n"
            f"Statut : {event.status_badge}\n"
            f"Station : {event.brand} ({event.distance_km} km)\n"
            f"Adresse : {event.address}, {event.postal_code} {event.city}\n\n"
            f"Carburants en stock :\n"
        )
        for f in event.fuels_restocked:
            time_str = f"({f.relative_time})" if f.relative_time else ""
            p_str = f"{f.price:.3f} €/L" if f.price else "Prix non précisé"
            text += f"- {f.fuel} : {p_str} {time_str}\n"

        if event.alternatives:
            text += f"\nAlternatives : {', '.join(event.alternatives)}\n"
        text += f"\nGoogle Maps : {event.google_maps_url}\n"
        text += f"Waze : {event.waze_url}\n"

        # Corps HTML compact et responsive
        fuels_html = "".join([
            f"<li><b>{f.fuel}</b> : {f'{f.price:.3f} €/L' if f.price else '<i>Prix non précisé</i>'} <span style='color: #666;'>({f.relative_time})</span></li>"
            for f in event.fuels_restocked
        ])
        alts_html = f"<p><b>🔄 Alternatives en stock :</b> {', '.join(event.alternatives)}</p>" if event.alternatives else ""
        color_hex = "#2ecc71" if event.status == "DISPONIBLE" else "#e67e22"

        html = f"""<!DOCTYPE html>
<html><body style="font-family: Arial, sans-serif; line-height: 1.5; color: #222; max-width: 600px; margin: auto; padding: 15px;">
<div style="background-color: {color_hex}; color: white; padding: 12px 16px; border-radius: 6px;">
    <h2 style="margin: 0; font-size: 1.25rem;">⛽ {event.status_badge}</h2>
</div>
<div style="padding: 15px 0;">
    <p style="font-size: 1.1rem; margin-top: 0;"><b>{event.brand}</b> (à <b>{event.distance_km} km</b>)</p>
    <p style="color: #555;">📍 {event.address}, {event.postal_code} {event.city}</p>
    <h3>✨ Carburants de nouveau disponibles :</h3>
    <ul>{fuels_html}</ul>
    {alts_html}
    <p><b>Tous les carburants disponibles :</b> {', '.join(event.all_available)}</p>
    <div style="margin-top: 25px;">
        <a href="{event.google_maps_url}" style="background-color: #3498db; color: white; padding: 10px 18px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-right: 10px; display: inline-block;">🗺️ Google Maps</a>
        <a href="{event.waze_url}" style="background-color: #33ccff; color: #111; padding: 10px 18px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">🚗 Waze</a>
    </div>
</div>
</body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"SP-Bot Carburant <{from_addr}>"
        msg["To"] = ", ".join(self.config.to_addrs)
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            if self.config.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=10)
                if self.config.use_tls:
                    server.starttls()

            if self.config.username and self.config.password:
                server.login(self.config.username, self.config.password)

            server.sendmail(from_addr, self.config.to_addrs, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"[!] Erreur d'envoi e-mail SMTP : {e}")
            return False

    def send_test_message(self) -> bool:
        subject = "✅ SP-Bot : Test d'envoi d'e-mail réussi"
        text = "Votre configuration e-mail est opérationnelle et prête à recevoir les alertes de réapprovisionnement."
        html = f"""<!DOCTYPE html>
<html><body style="font-family: Arial, sans-serif; padding: 20px;">
<h3 style="color: #2ecc71;">✅ Test d'envoi réussi !</h3>
<p>{text}</p>
</body></html>"""

        from_addr = self.config.from_addr or self.config.username
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"SP-Bot Carburant <{from_addr}>"
        msg["To"] = ", ".join(self.config.to_addrs)
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            if self.config.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=10)
                if self.config.use_tls:
                    server.starttls()
            if self.config.username and self.config.password:
                server.login(self.config.username, self.config.password)
            server.sendmail(from_addr, self.config.to_addrs, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"[!] Erreur test e-mail : {e}")
            return False


class NtfyNotifier:
    """Notificateur push mobile ultra-efficient (sans compte, zéro overhead, instantané)."""
    def __init__(self, config: NtfyConfig):
        self.config = config
        self.server = config.server.rstrip("/")
        self.topic = config.topic

    @property
    def name(self) -> str:
        return "Ntfy (Push Mobile)"

    def _post(self, payload: dict) -> bool:
        url = self.server
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8", "User-Agent": "SP-Bot/1.0"}
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            print(f"[!] Erreur Ntfy : {e}")
            return False

    def send_restock_event(self, event: RestockEvent) -> bool:
        title = f"⛽ {event.brand} ({event.city} - {event.distance_km} km)"
        lines = [
            f"📍 {event.address} ({event.distance_km} km)",
            f"Statut : {event.status_badge}",
            "",
            "✨ Carburants en stock :"
        ]
        for f in event.fuels_restocked:
            p_str = f"{f.price:.3f} €/L" if f.price else "Prix non précisé"
            rel_str = f"({f.relative_time})" if f.relative_time else ""
            lines.append(f"  • {f.fuel} : {p_str} {rel_str}".strip())

        if event.alternatives:
            lines.append(f"\n🔄 Alternatives : {', '.join(event.alternatives)}")

        payload = {
            "topic": self.topic,
            "title": title,
            "message": "\n".join(lines),
            "priority": self.config.priority,
            "tags": ["fuelpump", "white_check_mark"],
            "click": event.google_maps_url,
            "actions": [
                {"action": "view", "label": "Google Maps", "url": event.google_maps_url},
                {"action": "view", "label": "Waze", "url": event.waze_url}
            ]
        }
        return self._post(payload)

    def send_test_message(self) -> bool:
        payload = {
            "topic": self.topic,
            "title": "✅ SP-Bot : Test notification réussi !",
            "message": "Connexion push opérationnelle. Vos alertes arriveront instantanément sur ce téléphone.",
            "priority": 3,
            "tags": ["tada", "fuelpump"]
        }
        return self._post(payload)


class NotificationManager:
    """Gestionnaire centralisé pour expédier les alertes vers les canaux actifs."""
    def __init__(self, config: Config):
        self.notifiers = []
        if config.email.enabled and config.email.to_addrs:
            self.notifiers.append(EmailNotifier(config.email))
        if config.ntfy.enabled and config.ntfy.topic:
            self.notifiers.append(NtfyNotifier(config.ntfy))

    @property
    def active_channels(self) -> List[str]:
        return [n.name for n in self.notifiers]

    def broadcast_restock(self, event: RestockEvent) -> int:
        success = 0
        for n in self.notifiers:
            try:
                if n.send_restock_event(event):
                    success += 1
            except Exception as e:
                print(f"[!] Erreur ({n.name}): {e}")
        return success

    def send_test_all(self) -> Dict[str, bool]:
        results = {}
        for n in self.notifiers:
            try:
                results[n.name] = n.send_test_message()
            except Exception:
                results[n.name] = False
        return results
