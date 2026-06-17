"""
mailer.py — Rapport email de fin de run main.py

Envoie après chaque exécution :
  - Sujet : date + statut (OK / PARTIEL)
  - Corps : résumé + log complet
  - Pièce jointe : screenshot

Log des envois dans logs/mail.log (succès et échecs).
"""

import logging
import os
import smtplib
import subprocess
from datetime import date, datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
MAIL_LOG = os.path.join(LOGS_DIR, 'mail.log')

SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = 'pharmacie.depremont@gmail.com'
SMTP_PASS = 'ydwxwonvprwdezsj'
MAIL_TO   = 'pharmacie.depremont@gmail.com'

logger = logging.getLogger(__name__)

# Logger dédié mail.log (ne propage pas vers le log principal)
_mail_log = logging.getLogger('mwps.mail')
_mail_log.propagate = False


def _setup_mail_log():
    if _mail_log.handlers:
        return
    os.makedirs(LOGS_DIR, exist_ok=True)
    h = logging.FileHandler(MAIL_LOG, encoding='utf-8')
    h.setFormatter(logging.Formatter('%(asctime)s  %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    _mail_log.addHandler(h)
    _mail_log.setLevel(logging.INFO)


def take_screenshot() -> str | None:
    """Capture l'écran via PowerShell (.NET natif)."""
    try:
        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(LOGS_DIR, f'capture_run_{ts}.png')
        ps_script = (
            'Add-Type -AssemblyName System.Windows.Forms;'
            'Add-Type -AssemblyName System.Drawing;'
            '$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;'
            '$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height);'
            '$g = [System.Drawing.Graphics]::FromImage($bmp);'
            '$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size);'
            f"$bmp.Save('{path}');"
            '$g.Dispose(); $bmp.Dispose()'
        )
        subprocess.run(
            ['powershell', '-NonInteractive', '-Command', ps_script],
            timeout=15,
            capture_output=True,
        )
        if os.path.isfile(path):
            logger.info('Screenshot : %s', path)
            return path
        logger.warning('Screenshot : fichier non créé par PowerShell')
        return None
    except Exception as e:
        logger.warning('Screenshot échoué : %s', e)
        return None


def send_run_report(
    target_date: date,
    log_path: str,
    pushed: int,
    skipped: int,
    flags_ok: bool,
) -> None:
    """
    Envoie le rapport de fin de run.

    target_date : date cible du run
    log_path    : chemin vers le fichier log du run (inclus dans le corps)
    pushed      : lignes poussées dans Sheets
    skipped     : lignes skippées (déjà présentes)
    flags_ok    : True si compute_and_push_flags a réussi
    """
    _setup_mail_log()

    screenshot = take_screenshot()

    log_content = ''
    try:
        with open(log_path, encoding='utf-8', errors='replace') as f:
            log_content = f.read()
    except Exception as e:
        log_content = f'(log illisible : {e})'

    date_str = target_date.strftime('%d/%m/%Y')
    status   = 'OK' if flags_ok else 'PARTIEL — flags échoués'
    subject  = f'MWPS — Run {date_str} — {status}'

    body = (
        f'Run MWPS du {date_str}\n'
        f'Statut  : {status}\n'
        f'Sheets  : {pushed} ligne(s) pushée(s), {skipped} skippée(s)\n'
        f'Flags   : {"OK" if flags_ok else "ECHEC (429 ou autre erreur)"}\n'
        f'\n{"=" * 60}\n'
        f'LOG COMPLET\n'
        f'{"=" * 60}\n\n'
        f'{log_content}'
    )

    try:
        msg             = MIMEMultipart()
        msg['From']     = SMTP_USER
        msg['To']       = MAIL_TO
        msg['Subject']  = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        if screenshot and os.path.isfile(screenshot):
            with open(screenshot, 'rb') as f:
                img = MIMEImage(f.read())
                img.add_header(
                    'Content-Disposition', 'attachment',
                    filename=os.path.basename(screenshot),
                )
                msg.attach(img)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
            srv.starttls()
            srv.login(SMTP_USER, SMTP_PASS)
            srv.sendmail(SMTP_USER, MAIL_TO, msg.as_string())

        _mail_log.info('[OK]    Run %s — %d pushée(s) — flags=%s', date_str, pushed, 'OK' if flags_ok else 'ECHEC')
        logger.info('Rapport email envoyé (%s)', date_str)

    except Exception as e:
        _mail_log.error('[ECHEC] Run %s — %s', date_str, e)
        logger.warning('Rapport email échoué : %s', e)


# ── Test autonome ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    print('Test envoi mail MWPS...')
    send_run_report(
        target_date=date.today(),
        log_path=os.path.join(LOGS_DIR, f'mwps_{date.today().strftime("%Y%m%d")}.log'),
        pushed=4,
        skipped=0,
        flags_ok=True,
    )
    print('Terminé — vérifier mail.log et la boîte Gmail.')
