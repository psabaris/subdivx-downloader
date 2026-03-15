#!/usr/bin/env python3
"""
subdivx.py - Buscador/descargador de subtitulos desde subdivx.com
Instalar: pip install playwright rich && playwright install chromium
Config:   ~/.config/subdivx.conf
"""

import os, re, sys, time, zipfile, shutil, tempfile, subprocess, configparser
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

BASE_URL    = "https://www.subdivx.com"
CONFIG_PATH = Path.home() / ".config" / "subdivx.conf"
CDP_PORT    = 9222
console     = Console() if HAS_RICH else None

# Rutas por defecto segun navegador
BROWSER_PATHS = {
    "brave-mac":    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "brave-linux":  "/usr/bin/brave-browser",
    "brave-win":    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "chrome-mac":   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "chrome-linux": "/usr/bin/google-chrome",
    "chrome-win":   r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}

COOKIE_PATHS = {
    "brave-mac":    Path.home() / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser" / "Default",
    "brave-linux":  Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "Default",
    "brave-win":    Path.home() / "AppData" / "Local" / "BraveSoftware" / "Brave-Browser" / "Default",
    "chrome-mac":   Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default",
    "chrome-linux": Path.home() / ".config" / "google-chrome" / "Default",
    "chrome-win":   Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default",
}

def load_config():
    cfg = configparser.ConfigParser()
    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH)
        if "subdivx" in cfg:
            u = cfg["subdivx"].get("username", "")
            p = cfg["subdivx"].get("password", "")
            if u: return u, p
    print(f"\nNo se encontro configuracion en {CONFIG_PATH}")
    u = input("Usuario de subdivx.com: ").strip()
    p = input("Contrasena: ").strip()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg["subdivx"] = {"username": u, "password": p}
    with open(CONFIG_PATH, "w") as f:
        cfg.write(f)
    return u, p

def clean_filename(name):
    name = re.sub(r'\.(mkv|mp4|avi|mov|ts)$', '', name, flags=re.IGNORECASE)
    m = re.match(r'^(.+?)[. _-]+(S\d{2}E\d{2})', name, re.IGNORECASE)
    if m:
        title = m.group(1).replace('.', ' ').replace('_', ' ').strip()
        return title, m.group(2).upper(), int(m.group(2)[1:3]), int(m.group(2)[4:6])
    m = re.match(r'^(.+?)[. _-]+(\d{4})', name)
    if m:
        return m.group(1).replace('.', ' ').strip(), m.group(2), None, None
    return re.sub(r'[._]', ' ', name).strip(), None, None, None

class SubDivXClient:
    def __init__(self, username, password, browser_path=None, cookie_path=None):
        self.username    = username
        self.password    = password
        self.browser_path = browser_path or BROWSER_PATHS["brave-mac"]
        self.cookie_path  = cookie_path  or COOKIE_PATHS["brave-mac"]
        self._pw = self._browser = self._ctx = self._page = self._proc = None

    def start(self):
        os.system(f"lsof -ti tcp:{CDP_PORT} | xargs kill -9 2>/dev/null")
        time.sleep(1)
        profile = Path.home() / ".config" / "subdivx_brave_profile"
        profile.mkdir(parents=True, exist_ok=True)

        self._proc = subprocess.Popen([
            self.browser_path,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            BASE_URL + "/",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)
        self._pw = sync_playwright().start()
        for _ in range(10):
            try:
                self._browser = self._pw.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
                break
            except Exception:
                time.sleep(1)
        else:
            print("[X] No se pudo conectar"); sys.exit(1)
        self._ctx  = self._browser.contexts[0]
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        print("  Esperando Cloudflare...", end="", flush=True)
        deadline = time.time() + 15
        while time.time() < deadline:
            t = self._page.title()
            if "momento" not in t.lower() and "moment" not in t.lower():
                break
            time.sleep(1)
        # Si Cloudflare no paso solo, pedir que lo resuelva manualmente
        t = self._page.title()
        if "momento" in t.lower() or "moment" in t.lower():
            print()
            print("  Cloudflare necesita verificacion manual.")
            print("  Completa el check en la ventana de Brave y presiona ENTER.")
            input("  ENTER: ")
            time.sleep(1)
        print(f" OK ({self._page.title()})")

    def login(self):
        logged = self._page.evaluate(
            "() => document.body.innerText.includes('Mis sub') || document.body.innerText.includes('Mis subtitulos')"
        )
        if logged:
            return
        print()
        print("  Primera vez: hace login en la ventana de Brave.")
        print("  La sesion se guarda y las proximas veces entra solo.")
        input("  Presiona ENTER cuando estes logueado: ")
        time.sleep(2)

    def _get_page(self):
        """Retorna la pagina activa, reconectando si fue cerrada."""
        try:
            _ = self._page.url  # test si sigue viva
            return self._page
        except Exception:
            # La pagina se cerro, tomar la primera disponible o abrir una nueva
            try:
                pages = self._ctx.pages
                if pages:
                    self._page = pages[0]
                else:
                    self._page = self._ctx.new_page()
            except Exception:
                self._page = self._ctx.new_page()
            return self._page

    def search(self, query):
        for attempt in range(3):
            try:
                return self._do_search(query)
            except Exception as e:
                if "TargetClosed" in str(e) or "closed" in str(e).lower():
                    if attempt < 2:
                        print(f"  Browser cerrado, reconectando (intento {attempt+2}/3)...")
                        time.sleep(2)
                        # Reconectar pagina
                        try:
                            pages = self._ctx.pages
                            self._page = pages[0] if pages else self._ctx.new_page()
                        except Exception:
                            pass
                    else:
                        print(f"  Error: {e}")
                        return []
                else:
                    print(f"  Error en busqueda: {e}")
                    return []
        return []

    def _do_search(self, query):
        page = self._get_page()
        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)
        # Llenar #buscar y hacer click en #btnSrch
        page.evaluate(f"""
            () => {{
                const campo = document.querySelector('#buscar');
                if (campo) {{
                    campo.value = {repr(query)};
                    campo.dispatchEvent(new Event('input', {{bubbles:true}}));
                }}
            }}
        """)
        time.sleep(0.3)
        page.evaluate("""
            () => {
                const btn = document.querySelector('#btnSrch');
                if (btn) btn.click();
            }
        """)
        # Esperar que DataTables cargue los resultados
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('#resultados tbody tr:not(.dt-empty)').length > 0 ||"
                "      document.querySelector('#resultados tbody tr.dt-empty') !== null",
                timeout=15000
            )
        except Exception:
            pass
        time.sleep(1)

        rows = page.evaluate("""
            () => {
                try {
                    const dt = $('#resultados').DataTable();
                    const data = dt.rows().data().toArray();
                    if (data && data.length > 0) return data;
                } catch(e) {}
                return [];
            }
        """)
        return self._parse_rows(rows or [])

    def _parse_rows(self, rows):
        results = []
        seen = set()
        for row in rows:
            if isinstance(row, list):
                # Filas HTML: buscar ID en cualquier celda
                full = " ".join(str(c) for c in row)
                m = re.search(r'["\'](\d{5,})["\'"]', full) or re.search(r'id=(\d+)', full)
                if not m:
                    continue
                sub_id = m.group(1)
                if sub_id in seen: continue
                seen.add(sub_id)
                titulo = re.sub(r'<[^>]+>', '', str(row[1] if len(row) > 1 else "")).strip()
                desc   = re.sub(r'<[^>]+>', '', str(row[2] if len(row) > 2 else "")).strip()[:100]
                user   = re.sub(r'<[^>]+>', '', str(row[7] if len(row) > 7 else "")).strip()
                fecha  = str(row[8] if len(row) > 8 else "")[:10]
                results.append({
                    "id": sub_id, "titulo": titulo or f"Sub #{sub_id}",
                    "descripcion": desc, "usuario": user,
                    "descargas": row[3] if len(row) > 3 else 0, "fecha": fecha,
                    "url_descarga": f"{BASE_URL}/descargar.php?f=1&id={sub_id}",
                })
                continue
            if not isinstance(row, dict):
                continue
            sub_id = str(row.get("id", ""))
            if not sub_id or sub_id in seen:
                continue
            seen.add(sub_id)
            results.append({
                "id":           sub_id,
                "titulo":       re.sub(r'<[^>]+>', '', str(row.get("titulo", ""))).strip(),
                "descripcion":  re.sub(r'<[^>]+>', '', str(row.get("descripcion", ""))).strip()[:100],
                "usuario":      re.sub(r'<[^>]+>', '', str(row.get("nick", ""))).strip(),
                "descargas":    row.get("descargas", 0),
                "fecha":        str(row.get("fecha_subida", ""))[:10],
                "url_descarga": f"{BASE_URL}/descargar.php?f=1&id={sub_id}",
            })
        return results

    def download(self, subtitle, dest_dir, mkv_stem):
        sub_id = str(subtitle["id"])
        url    = f"{BASE_URL}/descargar.php?f=1&id={sub_id}"
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._page.evaluate(f"""
                async () => {{
                    const r = await fetch({repr(url)}, {{
                        credentials: 'include',
                        headers: {{'Referer': {repr(BASE_URL + "/")}}}
                    }});
                    if (!r.ok) return {{error: r.status}};
                    const buf = await r.arrayBuffer();
                    const ct  = r.headers.get('content-type') || '';
                    const cd  = r.headers.get('content-disposition') || '';
                    return {{bytes: Array.from(new Uint8Array(buf)), ct, cd}};
                }}
            """)
            if not result or result.get("error"):
                print(f"  Error descarga: {result}")
                return None
            ct     = result.get("ct", "")
            cd     = result.get("cd", "")
            suffix = ".rar" if ("rar" in ct or ".rar" in cd) else ".zip"
            tmp_path = Path(tmpdir) / f"sub{suffix}"
            tmp_path.write_bytes(bytes(result["bytes"]))
            srt_files = []
            if suffix == ".zip":
                try:
                    with zipfile.ZipFile(tmp_path) as z:
                        z.extractall(tmpdir)
                    srt_files = list(Path(tmpdir).glob("**/*.srt")) + list(Path(tmpdir).glob("**/*.SRT"))
                except zipfile.BadZipFile:
                    srt_files = self._rar(tmp_path, tmpdir)
            else:
                srt_files = self._rar(tmp_path, tmpdir)
            srt_files = [f for f in srt_files if f.suffix.lower() == ".srt"]
            if not srt_files:
                print("  No se encontro .srt"); return None
            src = srt_files[0]
            if len(srt_files) > 1:
                print("  Multiples .srt:")
                for i, f in enumerate(srt_files, 1):
                    print(f"    [{i}] {f.name}")
                while True:
                    try:
                        ch = int(input(f"  Elegir [1-{len(srt_files)}]: "))
                        if 1 <= ch <= len(srt_files):
                            src = srt_files[ch-1]; break
                    except (ValueError, EOFError): pass
            dest = dest_dir / f"{mkv_stem}.srt"
            shutil.copy2(src, dest)
            return dest

    def _rar(self, path, dest):
        for cmd in [f"unrar e -y '{path}' '{dest}'", f"7z e -y '{path}' -o'{dest}'"]:
            if os.system(cmd + " >/dev/null 2>&1") == 0:
                return list(Path(dest).glob("**/*.srt"))
        print("  [!] brew install unrar")
        return []

    def close(self):
        for x in [self._browser, self._pw]:
            try: x and x.close()
            except: pass
        try: self._proc and self._proc.terminate()
        except: pass

def print_results(results):
    if HAS_RICH:
        t = Table(box=box.ROUNDED, header_style="bold cyan", expand=True)
        t.add_column("#",           width=4,  justify="right", style="bold yellow")
        t.add_column("Titulo",      ratio=3,  style="white")
        t.add_column("Usuario",     ratio=1,  style="green")
        t.add_column("Descargas",   width=10, justify="right", style="magenta")
        t.add_column("Fecha",       width=12, style="cyan")
        t.add_column("Descripcion", ratio=2,  style="white")
        for i, s in enumerate(results, 1):
            t.add_row(str(i), s["titulo"][:55], s["usuario"][:20],
                      str(s["descargas"]), s["fecha"], s["descripcion"][:60])
        console.print(t)
    else:
        print(f"\n{'#':>3}  {'Titulo':<45} {'Usuario':<18} {'DL':>6}  Fecha")
        print("-"*82)
        for i, s in enumerate(results, 1):
            print(f"{i:>3}  {s['titulo'][:44]:<45} {s['usuario'][:17]:<18} {s['descargas']:>6}  {s['fecha']}")
        print()

def pick(results):
    n = len(results)
    while True:
        try:
            ch = int(input(f"Elegir [1-{n}] (0=cancelar): ").strip())
            if ch == 0: return None
            if 1 <= ch <= n: return results[ch-1]
        except (ValueError, EOFError): pass

def pick_mkv():
    current = Path.cwd()
    while True:
        mkvs = sorted(p for ext in ("*.mkv","*.mp4","*.avi") for p in current.glob(ext))
        dirs = sorted(d for d in current.iterdir() if d.is_dir() and not d.name.startswith("."))
        print(f"\n[DIR] {current}\n" + "-"*70)
        entries, idx = [], 1
        if current.parent != current:
            entries.append(("dir", current.parent))
            print(f"  {idx:>3}  [..] Subir un nivel"); idx += 1
        for d in dirs:
            entries.append(("dir", d)); print(f"  {idx:>3}  [D] {d.name}"); idx += 1
        for m in mkvs:
            entries.append(("file", m)); print(f"  {idx:>3}  [V] {m.name}"); idx += 1
        raw = input("\nNumero (0=salir): ").strip()
        if raw == "0": return None
        if "/" in raw or raw.startswith("~"):
            p = Path(raw).expanduser()
            if p.is_file(): return p
            if p.is_dir(): current = p; continue
        try:
            ch = int(raw)
            if 1 <= ch < idx:
                kind, path = entries[ch-1]
                if kind == "dir": current = path
                else: return path
        except ValueError: pass

def process_file(mkv_path, client):
    title, ep_tag, season, episode = clean_filename(mkv_path.name)
    label = f"{title} {ep_tag}" if ep_tag else title
    if HAS_RICH:
        console.print(f"\n[bold][V][/bold] [cyan]{mkv_path.name}[/cyan]")
        console.print(f"[bold][?] Buscando:[/bold] [yellow]{label}[/yellow]\n")
    else:
        print(f"\n[V] {mkv_path.name}\n[?] Buscando: {label}\n")
    results = client.search(label)
    if not results:
        print("No se encontraron resultados.")
        alt = input("Buscar con otro termino? (Enter=saltar): ").strip()
        if alt: results = client.search(alt)
        if not results: print("Sin resultados.\n"); return
    if season and episode:
        exact = [r for r in results if re.search(rf'S{season:02d}E{episode:02d}', r["titulo"], re.IGNORECASE)]
        if exact: results = exact
        else: print(f"  [!] No hay S{season:02d}E{episode:02d} exacto, mostrando todos.")
    print_results(results)
    chosen = pick(results)
    if not chosen: print("Cancelado.\n"); return
    print(f"\nDescargando: {chosen['titulo']}")
    dest = client.download(chosen, mkv_path.parent, mkv_path.stem)
    if dest: print(f"[OK] Guardado: {dest}\n")
    else:    print("[X]  Fallo la descarga.\n")

def parse_args():
    """Parsea argumentos: --brave, --chrome, --browser-path, y archivos MKV."""
    import platform
    browser_type = "brave"
    browser_path = None
    files = []

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--brave":
            browser_type = "brave"
        elif args[i] == "--chrome":
            browser_type = "chrome"
        elif args[i] == "--browser-path" and i + 1 < len(args):
            browser_path = args[i+1]
            i += 1
        else:
            files.append(args[i])
        i += 1

    # Detectar OS para elegir la ruta correcta
    os_name = platform.system().lower()
    if "darwin" in os_name:
        os_key = "mac"
    elif "windows" in os_name:
        os_key = "win"
    else:
        os_key = "linux"

    key = f"{browser_type}-{os_key}"
    if browser_path is None:
        browser_path = BROWSER_PATHS.get(key, BROWSER_PATHS["brave-mac"])
    cookie_path = COOKIE_PATHS.get(key, COOKIE_PATHS["brave-mac"])

    return browser_path, cookie_path, files


def main():
    browser_path, cookie_path, file_args = parse_args()
    username, password = load_config()
    client = SubDivXClient(username, password, browser_path, cookie_path)
    if HAS_RICH:
        console.print(Panel("[bold cyan]SubDivX Downloader[/bold cyan]", expand=False))
    else:
        print("="*40 + "\n  SubDivX Downloader\n" + "="*40)
    try:
        print("Iniciando Brave...")
        client.start()
        print("Login... ", end="", flush=True)
        client.login()
        print("[OK]")
        if file_args:
            for arg in file_args:
                path = Path(arg)
                if not path.exists(): print(f"[X] No existe: {arg}"); continue
                if path.is_dir():
                    for mkv in sorted(path.glob("*.mkv")):
                        if (mkv.parent / (mkv.stem+".srt")).exists():
                            print(f"[>>] Ya tiene sub: {mkv.name}"); continue
                        process_file(mkv, client)
                else:
                    process_file(path, client)
            return
        while True:
            mkv = pick_mkv()
            if mkv is None: print("Saliendo."); break
            srt = mkv.parent / (mkv.stem+".srt")
            if srt.exists():
                if input(f"Ya existe {srt.name}. Sobreescribir? [s/N]: ").strip().lower() != "s": continue
            process_file(mkv, client)
            if input("Buscar otro? [S/n]: ").strip().lower() == "n": break
    finally:
        client.close()

if __name__ == "__main__":
    main()
