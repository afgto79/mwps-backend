# deploy.ps1 — Déploiement MWPS vers \\SERVEUR\mwps\
# Lancement : .\deploy.ps1
# Pré-requis : accès réseau à \\SERVEUR\mwps\ depuis ce PC

$src  = $PSScriptRoot
$dest = "\\SERVEUR\mwps"

# ── 1. Arborescence ────────────────────────────────────────────────
Write-Host "Création de l'arborescence..." -ForegroundColor Cyan
$dirs = @(
    $dest,
    "$dest\config"
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "  [créé]  $d"
    } else {
        Write-Host "  [ok]    $d"
    }
}

# ── 2. Copie des fichiers Python ───────────────────────────────────
Write-Host "`nCopie des fichiers Python..." -ForegroundColor Cyan
$pyFiles = @(
    "parser_xls.py",
    "parser_txt.py",
    "aggregator.py",
    "sheets_client.py",
    "sheets_push.py",
    "sheets_flags.py",
    "main.py"
)
foreach ($f in $pyFiles) {
    $from = "$src\$f"
    $to   = "$dest\$f"
    if (Test-Path $from) {
        Copy-Item -Path $from -Destination $to -Force
        Write-Host "  [copié] $f"
    } else {
        Write-Host "  [MANQUANT] $from" -ForegroundColor Red
    }
}

# ── 3. Copie des fichiers config ───────────────────────────────────
Write-Host "`nCopie des fichiers config..." -ForegroundColor Cyan
$configFiles = @(
    "operators.json",
    "credentials.json",
    "settings.json"
)
foreach ($f in $configFiles) {
    $from = "$src\config\$f"
    $to   = "$dest\config\$f"
    if (Test-Path $from) {
        Copy-Item -Path $from -Destination $to -Force
        Write-Host "  [copié] config\$f"
    } else {
        Write-Host "  [MANQUANT] $from" -ForegroundColor Yellow
    }
}

# ── 4. INSTALL_DEPS.bat ────────────────────────────────────────────
Write-Host "`nCréation de INSTALL_DEPS.bat..." -ForegroundColor Cyan
$batContent = @"
@echo off
echo Installation des dependances MWPS...
pip install xlrd openpyxl google-auth google-auth-oauthlib google-api-python-client
echo.
echo Installation terminee.
pause
"@
Set-Content -Path "$dest\INSTALL_DEPS.bat" -Value $batContent -Encoding ASCII
Write-Host "  [créé]  INSTALL_DEPS.bat"

# ── 5. README_DEPLOY.txt ──────────────────────────────────────────
Write-Host "`nCréation de README_DEPLOY.txt..." -ForegroundColor Cyan
$readmeContent = @"
MWPS — Guide de déploiement serveur
=====================================
Date de déploiement : $(Get-Date -Format "yyyy-MM-dd HH:mm")

ARBORESCENCE ATTENDUE
---------------------
\\SERVEUR\mwps\
  config\
    operators.json       — IDs et noms des opérateurs actifs
    credentials.json     — Clé Service Account Google (NE PAS partager)
    settings.json        — ID Sheets + chemin credentials
  parser_xls.py
  parser_txt.py
  aggregator.py
  sheets_client.py
  sheets_push.py
  sheets_flags.py
  main.py
  INSTALL_DEPS.bat

PRÉREQUIS
---------
- Python 3.10+ installé et dans le PATH
- Accès Internet (appels Google Sheets API)
- Exécuter INSTALL_DEPS.bat une seule fois avant premier lancement

VARIABLES À VÉRIFIER DANS config\settings.json
-----------------------------------------------
  "google_sheets_id"  : ID du Google Sheets cible
                        (visible dans l'URL : docs.google.com/spreadsheets/d/<ID>/)
  "credentials_path"  : Chemin ABSOLU vers credentials.json sur CE serveur
                        Exemple : "C:\\mwps\\config\\credentials.json"
                        ATTENTION : mettre le chemin du serveur, pas du PC de dev.

LANCEMENT QUOTIDIEN
-------------------
  python main.py
  ou avec date explicite :
  python main.py --date YYYYMMDD

PREMIER LANCEMENT
-----------------
  1. Vérifier settings.json (credentials_path en particulier)
  2. Exécuter INSTALL_DEPS.bat
  3. Initialiser les feuilles Sheets : python sheets_init.py
  4. Lancer : python main.py

LOGS
----
  Les erreurs sont affichées dans la console.
  Rediriger vers un fichier si besoin :
  python main.py >> C:\mwps\logs\mwps.log 2>&1
"@
Set-Content -Path "$dest\README_DEPLOY.txt" -Value $readmeContent -Encoding UTF8
Write-Host "  [créé]  README_DEPLOY.txt"

# ── Résumé ─────────────────────────────────────────────────────────
Write-Host "`n==================================================" -ForegroundColor Green
Write-Host "Déploiement terminé vers : $dest" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host "Prochaines étapes :"
Write-Host "  1. Vérifier credentials_path dans $dest\config\settings.json"
Write-Host "  2. Exécuter $dest\INSTALL_DEPS.bat"
Write-Host "  3. python sheets_init.py  (premier lancement uniquement)"
Write-Host "  4. python main.py"
