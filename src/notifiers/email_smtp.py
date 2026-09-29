import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.notifiers.base import BaseNotifier
from src.tracker import RestockEvent
from src.config import EmailConfig

class EmailNotifier(BaseNotifier):
    def __init__(self, config: EmailConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "E-mail (SMTP)"

    def _send_email(self, subject: str, text_content: str, html_content: str) -> bool:
        if not self.config.to_addrs or not self.config.smtp_host:
            print("[!] Configuration SMTP incomplète (destinataire ou serveur manquant).")
            return False

        from_addr = self.config.from_addr or self.config.username
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"SP-Bot Carburant <{from_addr}>"
        msg["To"] = ", ".join(self.config.to_addrs)

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        try:
            if self.config.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=15)
                if self.config.use_tls:
                    server.starttls()

            if self.config.username and self.config.password:
                server.login(self.config.username, self.config.password)

            server.sendmail(from_addr, self.config.to_addrs, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"[!] Erreur d'envoi d'e-mail SMTP : {e}")
            return False

    def send_restock_event(self, event: RestockEvent) -> bool:
        subject = f"⛽ {event.status_badge} : {event.brand} ({event.city} - {event.distance_km} km)"

        text = (
            f"RÉAPPROVISIONNEMENT DÉTECTÉ !\n\n"
            f"Statut : {event.status_badge}\n"
            f"Station : {event.brand} ({event.distance_km} km)\n"
            f"Adresse : {event.address}, {event.postal_code} {event.city}\n\n"
            f"Carburants de nouveau en stock :\n"
        )
        for f in event.fuels_restocked:
            time_str = f"({f.relative_time})" if f.relative_time else ""
            p_str = f"{f.price:.3f} €/L" if f.price else "Prix non précisé"
            text += f"- {f.fuel} : {p_str} {time_str}\n"

        if event.alternatives:
            text += f"\nAlternatives disponibles : {', '.join(event.alternatives)}\n"

        text += f"\nTous les carburants disponibles : {', '.join(event.all_available)}\n"
        text += f"Google Maps : {event.google_maps_url}\n"

        fuels_html = "".join([
            f"<li><b>{f.fuel}</b> : {f'{f.price:.3f} €/L' if f.price else '<i>Prix non précisé</i>'} <span style='color: #777;'>({f.relative_time})</span></li>"
            for f in event.fuels_restocked
        ])

        alts_html = ""
        if event.alternatives:
            alts_html = f"<p><b>🔄 Alternatives disponibles :</b> {', '.join(event.alternatives)}</p>"

        color_hex = "#2ecc71" if event.status == "DISPONIBLE" else "#e67e22"

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="background-color: {color_hex}; color: white; padding: 15px; border-radius: 8px;">
                <h2 style="margin: 0;">⛽ {event.status_badge}</h2>
            </div>
            <div style="padding: 15px 0;">
                <p><b>{event.brand}</b> (à <b>{event.distance_km} km</b>)</p>
                <p>📍 {event.address}, {event.postal_code} {event.city}</p>
                <h3>✨ Carburants de nouveau en stock :</h3>
                <ul>{fuels_html}</ul>
                {alts_html}
                <p><b>Tous les carburants en stock :</b> {', '.join(event.all_available)}</p>
                <div style="margin-top: 20px;">
                    <a href="{event.google_maps_url}" style="background-color: #3498db; color: white; padding: 10px 16px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-right: 10px; display: inline-block;">🗺️ Google Maps</a>
                    <a href="{event.waze_url}" style="background-color: #33ccff; color: #111; padding: 10px 16px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">🚗 Waze</a>
                </div>
            </div>
        </body>
        </html>
        """

        return self._send_email(subject, text, html)

    def send_test_message(self) -> bool:
        subject = "✅ SP-Bot : Test d'envoi d'e-mail réussi"
        text = "Votre configuration SMTP fonctionne parfaitement. Surveillance active selon le modèle Gasoil Now / Essence&CO."
        html = """
        <html><body>
            <h3>✅ Test d'envoi d'e-mail réussi !</h3>
            <p>Votre configuration SMTP fonctionne parfaitement. Surveillance active selon le modèle Gasoil Now / Essence&CO.</p>
        </body></html>
        """
        return self._send_email(subject, text, html)
