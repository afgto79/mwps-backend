"""
watchdog.py — MWPS fallback automatique
Planifié à 01h00 via Tâche Windows (même poste que main.py).

Logique :
  1. Vérifie si les fichiers J-1 (990, 991) sont présents dans /input
  2. Si manquants :
     a. Capture écran AVANT relance
     b. Relance l'AHK compilé
     c. Attend fin AHK (poll ahk.log, timeout 5 min)
     d. Revérifie les fichiers
     e. Si encore manquants : capture écran APRÈS relance
     f. Envoie email dans tous les cas (succès ou échec)
"""

import os
import time
import subprocess
import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage


# ── Configuration ────────────────────────────────────────────────
BASE_INPUT   = r"C:\Users\operateur\Documents\PLANIFICATEUR\Macro et automatismes\MWPS\input"
LOGS_DIR     = r"C:\Users\operateur\Documents\PLANIFICATEUR\Macro et automatismes\MWPS\logs"
AHK_EXE      = r"C:\Users\operateur\Documents\PLANIFICATEUR\Macro et automatismes\MWPS_Phase_v5.exe"
AHK_LOG      = os.path.join(LOGS_DIR, "ahk.log")
WATCHDOG_LOG = os.path.join(LOGS_DIR, "watchdog.log")

SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 587
SMTP_USER  = "pharmacie.depremont@gmail.com"
SMTP_PASS  = "ydwxwonvprwdezsj"   # ← Mot de passe d'application Gmail (MailPMHO)
MAIL_TO    = "pharmacie.depremont@gmail.com"

AHK_TIMEOUT = 300   # secondes max d'attente fin AHK

# ── Logging ──────────────────────────────────────────────────────
os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    filename=WATCHDOG_LOG,
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.info


# ── Helpers ──────────────────────────────────────────────────────

def get_j1_paths():
    """Chemins attendus pour J-1."""
    j1 = datetime.now() - timedelta(days=1)
    date_short = j1.strftime("%d%m%Y")        # DDMMYYYY
    p990 = os.path.join(BASE_INPUT, f"990_{date_short}.TXT")
    p991 = os.path.join(BASE_INPUT, f"991_{date_short}.TXT")
    return p990, p991, j1.strftime("%d/%m/%Y")


def files_present(p990, p991):
    return os.path.isfile(p990) and os.path.isfile(p991)


def take_screenshot(label):
    """Capture l'écran via PowerShell (.NET natif, sans dépendance externe)."""
    try:
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(LOGS_DIR, f"capture_{label}_{ts}.png")
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            "$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
            "$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height);"
            "$g = [System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size);"
            f"$bmp.Save('{path}');"
            "$g.Dispose(); $bmp.Dispose()"
        )
        subprocess.run(
            ["powershell", "-NonInteractive", "-Command", ps_script],
            timeout=15,
            capture_output=True,
        )
        if os.path.isfile(path):
            log(f"[SCREENSHOT] {path}")
            return path
        log("[SCREENSHOT] Fichier non créé par PowerShell")
        return None
    except Exception as e:
        log(f"[SCREENSHOT] Erreur : {e}")
        return None


def get_ahk_log_size():
    try:
        return os.path.getsize(AHK_LOG)
    except Exception:
        return 0


def wait_for_ahk_end(size_before):
    """Poll ahk.log jusqu'à détecter '=== MWPS AHK terminé ===' après size_before."""
    deadline = time.time() + AHK_TIMEOUT
    while time.time() < deadline:
        time.sleep(5)
        try:
            with open(AHK_LOG, "r", encoding="utf-8", errors="replace") as f:
                f.seek(size_before)
                if "=== MWPS AHK terminé ===" in f.read():
                    return True
        except Exception:
            pass
    return False


def send_email(subject, body, attachments):
    """Envoie un email avec pièces jointes (liste de chemins PNG)."""
    try:
        msg              = MIMEMultipart()
        msg["From"]      = SMTP_USER
        msg["To"]        = MAIL_TO
        msg["Subject"]   = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        for path in attachments:
            if path and os.path.isfile(path):
                with open(path, "rb") as f:
                    img = MIMEImage(f.read())
                    img.add_header(
                        "Content-Disposition", "attachment",
                        filename=os.path.basename(path),
                    )
                    msg.attach(img)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
            srv.starttls()
            srv.login(SMTP_USER, SMTP_PASS)
            srv.sendmail(SMTP_USER, MAIL_TO, msg.as_string())
        log("[MAIL] Envoyé avec succès")
    except Exception as e:
        log(f"[MAIL] Erreur envoi : {e}")


# ── Main ─────────────────────────────────────────────────────────

def main():
    log("=== Watchdog démarré ===")
    p990, p991, date_label = get_j1_paths()
    log(f"Cible J-1 : {date_label} | {os.path.basename(p990)} | {os.path.basename(p991)}")

    if files_present(p990, p991):
        log("Fichiers présents — aucune action requise")
        log("=== Watchdog terminé ===")
        return

    log("Fichiers MANQUANTS — déclenchement du fallback")

    # 1. Screenshot avant relance
    screen_avant = take_screenshot("avant")

    # 2. Relance AHK
    log(f"Relance AHK : {AHK_EXE}")
    size_before = get_ahk_log_size()
    try:
        subprocess.Popen([AHK_EXE])
    except Exception as e:
        log(f"[AHK] Impossible de lancer : {e}")

    # 3. Attente fin AHK
    log("Attente fin AHK (timeout 5 min)...")
    ahk_done = wait_for_ahk_end(size_before)
    log(f"[AHK] {'Terminé (log détecté)' if ahk_done else 'Timeout 5 min dépassé'}")

    # 4. Revérification
    if files_present(p990, p991):
        log("Relance réussie — fichiers présents")
        send_email(
            subject=f"MWPS — Relance automatique réussie {date_label}",
            body=(
                f"La tâche MWPS du {date_label} avait échoué à 00h05.\n"
                f"Le watchdog (01h00) a relancé l'AHK avec succès.\n\n"
                f"Fichiers produits :\n"
                f"  {p990}\n"
                f"  {p991}\n\n"
                f"Capture d'écran avant relance en pièce jointe."
            ),
            attachments=[screen_avant],
        )
    else:
        log("Relance échouée — fichiers toujours absents")
        screen_apres = take_screenshot("apres")
        send_email(
            subject=f"MWPS — ÉCHEC PERSISTANT {date_label} — intervention requise",
            body=(
                f"La tâche MWPS du {date_label} a échoué deux fois :\n"
                f"  • 00h05 : échec initial (AHK planifié)\n"
                f"  • 01h00 : échec relance automatique (watchdog)\n\n"
                f"Fichiers manquants :\n"
                f"  {p990}\n"
                f"  {p991}\n\n"
                f"Relancer MWPS manuellement dès que possible.\n\n"
                f"Captures d'écran en pièces jointes :\n"
                f"  • avant relance (ce qui bloquait à 01h00)\n"
                f"  • après relance (état final)"
            ),
            attachments=[screen_avant, screen_apres],
        )

    log("=== Watchdog terminé ===")


if __name__ == "__main__":
    main()
