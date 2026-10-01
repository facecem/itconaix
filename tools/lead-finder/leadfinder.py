#!/usr/bin/env python3
"""IT conAIX Lead-Finder

Findet lokale Betriebe ohne oder mit schwacher Website und verwaltet sie in
einem kleinen Dashboard. Läuft komplett lokal, braucht nur Python 3.9+ und
keine zusätzlichen Pakete.

Start:  python leadfinder.py      -> öffnet http://127.0.0.1:8765
"""
import datetime as dt
import html
import json
import math
import os
import re
import socket
import sqlite3
import ssl
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "leads.db")
PORT = int(os.environ.get("LEADFINDER_PORT", "8765"))
USER_AGENT = "itconaix-leadfinder/1.0 (+https://itconaix.de; hallo@itconaix.de)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
# Öffentliche Overpass-Server; sind oft ausgelastet, daher mehrere der Reihe nach
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Branche -> OpenStreetMap-Tags (key, value); value None = jeder Wert
BRANCHEN = {
    "Alle Handwerker": [("craft", None)],
    "Dachdecker": [("craft", "roofer")],
    "Elektriker": [("craft", "electrician")],
    "Maler / Lackierer": [("craft", "painter")],
    "Tischler / Schreiner": [("craft", "carpenter"), ("craft", "joiner"), ("craft", "cabinet_maker")],
    "Sanitär / Heizung": [("craft", "plumber"), ("craft", "hvac"), ("craft", "heating_engineer")],
    "Fliesenleger": [("craft", "tiler")],
    "Metallbau / Schlosser": [("craft", "metal_construction"), ("craft", "locksmith")],
    "Garten- und Landschaftsbau": [("craft", "gardener"), ("craft", "landscaper")],
    "Bauunternehmen": [("craft", "builder"), ("office", "construction_company")],
    "Autowerkstatt": [("shop", "car_repair")],
    "Friseur": [("shop", "hairdresser")],
    "Kosmetik / Nagelstudio": [("shop", "beauty")],
    "Bäckerei": [("shop", "bakery")],
    "Metzgerei": [("shop", "butcher")],
    "Blumenladen": [("shop", "florist")],
    "Optiker": [("shop", "optician")],
    "Restaurant": [("amenity", "restaurant")],
    "Café": [("amenity", "cafe")],
    "Imbiss": [("amenity", "fast_food")],
    "Fahrschule": [("amenity", "driving_school")],
    "Physiotherapie": [("healthcare", "physiotherapist")],
    "Zahnarzt": [("amenity", "dentist")],
    "Arztpraxis": [("amenity", "doctors")],
    "Tierarzt": [("amenity", "veterinary")],
    "Steuerberater": [("office", "tax_advisor")],
    "Rechtsanwalt": [("office", "lawyer")],
    "Versicherungsagentur": [("office", "insurance")],
    "Immobilienmakler": [("office", "estate_agent")],
    "Fitnessstudio": [("leisure", "fitness_centre")],
}

STATUS = ["neu", "interessant", "angeschrieben", "termin", "kunde", "kein_interesse"]

DB_LOCK = threading.Lock()


# ---------------------------------------------------------------- Datenbank

def db():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quelle TEXT NOT NULL,            -- osm | manuell
            osm_id TEXT UNIQUE,
            name TEXT NOT NULL,
            branche TEXT,
            strasse TEXT, plz TEXT, ort TEXT,
            telefon TEXT, email TEXT,
            website TEXT,                    -- aus Quelle oder manuell
            website_gefunden TEXT,           -- per Domain-Suche vermutet
            lat REAL, lon REAL,
            score INTEGER,                   -- 0-100, hoch = braucht neue Seite
            kategorie TEXT,                  -- keine | kein_impressum | veraltet | ok | ignoriert
            befunde TEXT,                    -- JSON-Liste
            impressum_fehlt INTEGER DEFAULT 0,
            veraltet INTEGER DEFAULT 0,
            geprueft_am TEXT,
            status TEXT NOT NULL DEFAULT 'neu',
            notiz TEXT DEFAULT '',
            erstellt_am TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);
        """)
        # Ältere Datenbanken nachrüsten; Prüfungen nach altem Schema neu durchführen lassen
        cols = {r["name"] for r in con.execute("PRAGMA table_info(leads)")}
        for c in ("impressum_fehlt", "veraltet"):
            if c not in cols:
                con.execute(f"ALTER TABLE leads ADD COLUMN {c} INTEGER DEFAULT 0")
        con.execute("""UPDATE leads SET kategorie=NULL, score=NULL, befunde=NULL, geprueft_am=NULL
                       WHERE kategorie IN ('schwach', 'unerreichbar')""")


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def row_to_dict(r):
    d = dict(r)
    d["befunde"] = json.loads(d["befunde"]) if d.get("befunde") else []
    return d


def get_settings():
    defaults = {"firma": "IT conAIX", "ansprechpartner": "", "telefon": "",
                "email": "hallo@itconaix.de", "web": "itconaix.de", "preis": "ab 500 €"}
    with db() as con:
        for r in con.execute("SELECT k, v FROM settings"):
            defaults[r["k"]] = r["v"]
    return defaults


# ---------------------------------------------------------------- HTTP-Helfer

def http_get(url, timeout=20, ua=USER_AGENT, data=None, max_bytes=3_000_000):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": ua, "Accept-Language": "de-DE,de;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(max_bytes)
        return resp.geturl(), resp.status, resp.headers, body


def geocode(ort):
    q = urllib.parse.urlencode({"q": ort, "format": "json", "limit": 1, "countrycodes": "de,at,ch"})
    _, _, _, body = http_get("https://nominatim.openstreetmap.org/search?" + q)
    res = json.loads(body)
    if not res:
        raise ValueError(f"Ort „{ort}“ nicht gefunden")
    return float(res[0]["lat"]), float(res[0]["lon"]), res[0].get("display_name", ort)


def overpass(query):
    fehler = []
    data = urllib.parse.urlencode({"data": query}).encode()
    for runde in range(2):
        for url in OVERPASS_URLS:
            try:
                _, _, _, body = http_get(url, timeout=40, data=data, max_bytes=50_000_000)
                return json.loads(body)["elements"]
            except Exception as e:  # nächsten Server versuchen
                fehler.append(f"{urllib.parse.urlparse(url).hostname}: {e}")
        time.sleep(3)
    raise RuntimeError("Die OpenStreetMap-Server sind gerade überlastet – bitte in ein paar Minuten "
                       "nochmal versuchen. (" + "; ".join(fehler[-len(OVERPASS_URLS):]) + ")")


def distanz_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12_742_000 * math.asin(math.sqrt(a))


def osm_search(branche, ort, radius_km):
    tags = BRANCHEN.get(branche)
    if not tags:
        raise ValueError("Unbekannte Branche")
    lat, lon, label = geocode(ort)
    r = int(float(radius_km) * 1000)
    # Bounding-Box statt around: deutlich schneller auf den Servern; Kreis danach selbst filtern
    dlat = r / 111_320
    dlon = r / (111_320 * max(0.2, math.cos(math.radians(lat))))
    bbox = f"{lat - dlat:.5f},{lon - dlon:.5f},{lat + dlat:.5f},{lon + dlon:.5f}"
    parts = []
    for k, v in tags:
        sel = f'["{k}"]' if v is None else f'["{k}"="{v}"]'
        parts.append(f'nwr{sel}["name"]({bbox});')
    q = f'[out:json][timeout:30];({"".join(parts)});out center tags;'
    found = []
    for e in overpass(q):
        t = e.get("tags", {})
        c = e.get("center") or e
        if c.get("lat") is not None and distanz_m(lat, lon, c["lat"], c["lon"]) > r:
            continue
        found.append({
            "osm_id": f'{e["type"]}/{e["id"]}',
            "name": t.get("name", "").strip(),
            "branche": branche,
            "strasse": " ".join(x for x in (t.get("addr:street"), t.get("addr:housenumber")) if x),
            "plz": t.get("addr:postcode", ""),
            "ort": t.get("addr:city", ""),
            "telefon": t.get("phone") or t.get("contact:phone") or "",
            "email": t.get("email") or t.get("contact:email") or "",
            "website": t.get("website") or t.get("contact:website") or t.get("url") or "",
            "lat": c.get("lat"), "lon": c.get("lon"),
        })
    return found, label


# ---------------------------------------------------------------- Website-Check

LEGAL_FORMS = r"\b(gmbh|ug|ag|kg|ohg|gbr|e\.?\s?k\.?|e\.?\s?v\.?|mbh|co|inh(aber)?\.?|haftungsbeschränkt|und|&)\b"


def slugify(s):
    s = s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s


def domain_guesses(name, ort):
    base = slugify(re.sub(LEGAL_FORMS, " ", name.lower()))
    words = [w for w in re.split(r"[^a-z0-9]+", base) if w]
    ortslug = re.sub(r"[^a-z0-9]+", "", slugify(ort or ""))
    if not words:
        return []
    cands = ["".join(words), "-".join(words)]
    if len(words) > 1:
        cands += ["".join(words[:2]), "-".join(words[:2])]
    if ortslug:
        cands += ["".join(words) + "-" + ortslug, words[0] + "-" + ortslug]
    seen, out = set(), []
    for c in cands:
        for tld in (".de", ".com"):
            d = c + tld
            if 4 < len(d) <= 63 and d not in seen:
                seen.add(d)
                out.append(d)
    return out[:10]


def name_tokens(name):
    base = slugify(re.sub(LEGAL_FORMS, " ", name.lower()))
    return [w for w in re.split(r"[^a-z0-9]+", base) if len(w) >= 4]


def find_website(name, ort):
    """Versucht, eine nicht eingetragene Website über naheliegende Domains zu finden."""
    tokens = name_tokens(name)
    for dom in domain_guesses(name, ort):
        try:
            socket.gethostbyname(dom)
        except OSError:
            continue
        for scheme in ("https://", "http://"):
            try:
                final, _, _, body = http_get(scheme + dom, timeout=10, ua=BROWSER_UA, max_bytes=400_000)
            except Exception:
                continue
            text = slugify(body.decode("utf-8", "ignore"))
            # Nur akzeptieren, wenn der Firmenname auf der Seite vorkommt (keine Domain-Parkseite)
            needed = len(tokens) if len(tokens) <= 2 else len(tokens) - 1
            if tokens and sum(t in text for t in tokens) >= needed \
                    and not re.search(r"domain (is )?for sale|domain kaufen|sedo|parked", text):
                return final
            break
    return ""


# Einträge, die keine eigene Website sind
KEINE_EIGENE_SEITE = re.compile(
    r"(^|\.)(facebook\.com|fb\.com|instagram\.com|linkedin\.com|xing\.com|tiktok\.com|youtube\.com|"
    r"linktr\.ee|wa\.me|gelbeseiten\.de|dasoertliche\.de|11880\.com|meinestadt\.de|yelp\.\w+|"
    r"tripadvisor\.\w+|google\.\w+|goo\.gl|business\.site|g\.page)$")
FEHLERSEITE = re.compile(r"404|nicht gefunden|not found|existiert nicht|page not found|fehlerseite|error")
KETTE_AB = 3  # gleiche Domain bei so vielen Betrieben = Filialkette


def fetch(url, timeout=20, max_bytes=2_000_000):
    """Lädt eine Seite. Liefert dict(final, status, html, cert) oder None bei Fehlern/Fehlerseiten."""
    cert = False
    for u in (url, re.sub(r"^https://", "http://", url)):
        try:
            final, status, headers, body = http_get(u, timeout=timeout, ua=BROWSER_UA, max_bytes=max_bytes)
        except urllib.error.HTTPError:
            return None  # 4xx/5xx = Fehlerseite
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLError):
                cert = True
                continue
            if u.startswith("https://"):
                continue
            return None
        except Exception:
            if u.startswith("https://"):
                continue
            return None
        page = body.decode("utf-8", "ignore")
        title = " ".join(t for _, t in re.findall(r"<(title|h1)[^>]*>(.*?)</\1>", page[:30000], re.I | re.S)).lower()
        if FEHLERSEITE.search(title) and len(sichtbarer_text(page)) < 1500:
            return None  # „Soft-404“: Fehlerseite mit Status 200
        return {"final": final, "status": status, "html": page, "cert": cert}
    return None


def sichtbarer_text(page):
    t = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return " ".join(html.unescape(t).split())


def startseite(url):
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


def host_of(url):
    if not re.match(r"^https?://", url or "", re.I):
        url = "https://" + (url or "")
    h = (urllib.parse.urlparse(url).netloc or "").lower().split("@")[-1]
    return h[4:] if h.startswith("www.") else h


def hat_impressum(seite):
    """True = gefunden, False = fehlt, None = nicht sicher prüfbar."""
    low = seite["html"].lower()
    if re.search(r"<a[^>]+href=[\"'][^\"']*(impressum|imprint|legal-notice|legal_notice)", low) or \
            re.search(r"<a[^>]*>[^<]{0,40}(impressum|imprint)", low):
        return True
    root = startseite(seite["final"])
    for pfad in ("impressum", "impressum/", "impressum.html", "impressum.htm", "impressum.php", "imprint", "kontakt-impressum"):
        s = fetch(root + pfad, timeout=10, max_bytes=500_000)
        if s and "impressum" in s["html"].lower() and s["final"].rstrip("/") != root.rstrip("/"):
            return True
    text = sichtbarer_text(seite["html"])
    if len(text) < 300 and "<script" in low:
        return None  # Inhalt wird per JavaScript nachgeladen – kein sicheres Urteil möglich
    return False


def design_befunde(seite):
    """Merkmale eines veralteten Designs. Liefert (punkte, liste, starkes_merkmal)."""
    page, low = seite["html"], seite["html"].lower()
    year = dt.date.today().year
    out, stark = [], False

    def add(p, text, strong=False):
        nonlocal stark
        out.append([p, text])
        stark = stark or strong

    if not re.search(r"<meta[^>]+name=[\"']?viewport", low):
        add(30, "Nicht für Smartphones gemacht – auf dem Handy winzig und schwer bedienbar", True)
    head = low[:600]
    if re.search(r"<!doctype html public \"-//w3c//dtd (html 4|xhtml 1\.0)", head):
        add(15, "Technik-Stand der 2000er Jahre (alter HTML-Standard)", True)
    elif "<!doctype" not in head:
        add(10, "Kein moderner HTML-Standard")
    if re.search(r"<frameset|<frame\s", low):
        add(25, "Aufgebaut mit Frames – Technik aus den 90ern", True)
    if re.search(r"\.swf[\"'?]|shockwave-flash", low):
        add(25, "Nutzt Flash – wird von keinem Browser mehr angezeigt", True)
    if re.search(r"<font[\s>]|<center>|<marquee|<blink", low):
        add(15, "Veraltete Gestaltungs-Befehle (Font-/Center-Tags)", True)
    if low.count("<table") >= 4 and low.count("<div") < 5:
        add(15, "Layout aus Tabellen gebaut – typisch für Seiten vor 2010", True)
    if re.search(r"bgcolor=|spacer\.gif|besucherz[äa]hler|g[äa]stebuch|best viewed|optimiert f[üu]r|sie sind besucher", low):
        add(10, "Typische Elemente alter Homepages (Besucherzähler, Gästebuch, Hintergrundfarben im HTML)")
    jahre = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(?:(?:19|20)\d{2}\s*[-–/]\s*)?((?:19|20)\d{2})", low)]
    if jahre:
        j = max(jahre)
        if j <= year - 5:
            add(20, f"Copyright von {j} – seit Jahren nicht mehr gepflegt", True)
        elif j <= year - 3:
            add(10, f"Copyright von {j} – länger nicht aktualisiert")
    if re.search(r"jquery[-.]?(1\.[0-9])\b|jquery/1\.[0-9]", low):
        add(10, "Sehr alte Script-Bibliothek (jQuery 1.x)")
    gen = re.search(r"<meta[^>]+name=[\"']generator[\"'][^>]+content=[\"']([^\"']+)", low)
    if gen:
        g = gen.group(1)
        m = re.search(r"wordpress\s+(\d+)", g)
        if (m and int(m.group(1)) < 5) or re.search(r"joomla! 1\.|joomla! 2\.|typo3 [4-6]\.|frontpage|netobjects|dreamweaver|website x5 (evolution|1[0-3])", g):
            add(15, f"Veraltetes System ({g}) – Sicherheitslücken wahrscheinlich", True)
    if seite["cert"]:
        add(15, "Sicherheitswarnung im Browser (Zertifikat ungültig)")
    elif seite["final"].lower().startswith("http://"):
        add(10, "Keine verschlüsselte Verbindung – Browser zeigen „Nicht sicher“")
    return min(60, sum(p for p, _ in out)), out, stark


def analyse_site(url):
    """Prüft die Startseite einer Website. Liefert (score, kategorie, befunde, impressum_fehlt, veraltet)."""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    # Immer die Startseite bewerten – eingetragene Unterseiten sind oft Filial- oder Fehlerseiten
    seite = fetch(startseite(url))
    if seite is None and url.rstrip("/") != startseite(url).rstrip("/"):
        seite = fetch(url)
    if seite is None:
        return 0, "ignoriert", [[0, "Website liefert nur eine Fehlerseite oder ist nicht erreichbar – ignoriert"]], 0, 0

    befunde = []
    imp = hat_impressum(seite)
    if imp is False:
        befunde.append([50, "Kein Impressum auffindbar – Pflicht nach § 5 DDG, fehlt es, drohen Abmahnungen"])
    elif imp is None:
        befunde.append([0, "Impressum nicht sicher prüfbar (Seite lädt Inhalte per JavaScript) – bitte selbst ansehen"])

    dpunkte, dbefunde, stark = design_befunde(seite)
    veraltet = 1 if (dpunkte >= 35 and stark) else 0
    befunde += dbefunde

    score = min(95, (50 if imp is False else 0) + (dpunkte if veraltet else dpunkte // 3))
    kategorie = "kein_impressum" if imp is False else "veraltet" if veraltet else "ok"
    befunde.sort(key=lambda b: -b[0])
    return score, kategorie, befunde, 1 if imp is False else 0, veraltet


def check_lead(lead_id):
    with db() as con:
        r = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not r:
        raise KeyError(lead_id)
    website, gefunden = (r["website"] or "").strip(), ""
    imp_fehlt = veraltet = 0
    if website and KEINE_EIGENE_SEITE.search(host_of(website)):
        score, kat = 100, "keine"
        befunde = [[100, f"Keine eigene Website – nur ein Eintrag auf {host_of(website)}"]]
    else:
        if not website:
            gefunden = find_website(r["name"], r["ort"])
        url = website or gefunden
        kette = 0
        if url:
            with db() as con:
                hosts = [host_of(x["website"]) for x in con.execute(
                    "SELECT website FROM leads WHERE website != '' AND id != ?", (lead_id,))]
            kette = hosts.count(host_of(url))
        if url and kette + 1 >= KETTE_AB:
            score, kat = 0, "ignoriert"
            befunde = [[0, f"Filiale einer Kette – {host_of(url)} gehört zu {kette + 1} Betrieben – ignoriert"]]
        elif url:
            score, kat, befunde, imp_fehlt, veraltet = analyse_site(url)
            if gefunden:
                befunde.insert(0, [0, f"Website nicht im Kartenverzeichnis eingetragen, aber unter {gefunden} gefunden – bitte kurz prüfen"])
        else:
            score, kat = 100, "keine"
            befunde = [[100, "Keine Website gefunden – wer online sucht, findet nur Mitbewerber"]]
    with DB_LOCK, db() as con:
        con.execute("""UPDATE leads SET score=?, kategorie=?, befunde=?, impressum_fehlt=?, veraltet=?,
                       website_gefunden=?, geprueft_am=? WHERE id=?""",
                    (score, kat, json.dumps(befunde, ensure_ascii=False), imp_fehlt, veraltet, gefunden, now(), lead_id))
        return row_to_dict(con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())


# ---------------------------------------------------------------- Bericht

def report_html(lead, s):
    e = html.escape
    adresse = ", ".join(x for x in (lead["strasse"], " ".join(x for x in (lead["plz"], lead["ort"]) if x)) if x)
    url = lead["website"] or lead["website_gefunden"]
    if lead["kategorie"] == "keine":
        intro = ("bei einer Suche nach Betrieben in Ihrer Gegend sind wir auf Sie gestoßen – und haben "
                 "festgestellt, dass Sie im Internet bisher keine eigene Website haben. Viele Kundinnen "
                 "und Kunden suchen heute zuerst online und entscheiden sich dann für den Betrieb, den sie dort finden.")
    else:
        intro = (f"wir haben uns Ihre Website {e(url)} einmal angesehen und einen kurzen, kostenlosen "
                 "Check gemacht. Dabei sind uns ein paar Punkte aufgefallen, die Sie wahrscheinlich Anfragen kosten:")
    punkte = "".join(f"<li>{e(t)}</li>" for p, t in lead["befunde"] if p > 0) or "<li>Keine größeren Probleme gefunden.</li>"
    kontakt = " · ".join(e(x) for x in (s["telefon"], s["email"], s["web"]) if x)
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>Website-Check {e(lead['name'])}</title>
<style>
@page{{size:A4;margin:22mm 20mm}}
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#0E1116;line-height:1.55;max-width:720px;margin:32px auto;padding:0 16px;font-size:15px}}
.head{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid #2E7C86;padding-bottom:10px}}
.logo{{font-weight:800;font-size:24px;letter-spacing:-.04em}} .logo span{{color:#2E7C86}}
.small{{color:#6B7280;font-size:12.5px}}
.to{{margin:34px 0 26px}}
h1{{font-size:22px;letter-spacing:-.02em;margin:0 0 14px}}
ul{{padding-left:1.1em}} li{{margin:6px 0}}
.box{{background:#F1F7F8;border-radius:12px;padding:14px 18px;margin:22px 0}}
.foot{{margin-top:36px;border-top:1px solid #E7E8EC;padding-top:10px}}
.noprint{{margin-bottom:20px}} @media print{{.noprint{{display:none}} body{{margin:0}}}}
button{{font:inherit;padding:8px 14px;border-radius:10px;border:1px solid #0E1116;background:#fff;cursor:pointer}}
</style></head><body>
<div class="noprint"><button onclick="print()">Drucken / als PDF speichern</button></div>
<div class="head"><div class="logo">IT con<span>AIX</span></div><div class="small">{e(s['firma'])}<br>{kontakt}</div></div>
<div class="to">{e(lead['name'])}<br>{e(adresse)}</div>
<div class="small" style="text-align:right">{dt.date.today().strftime('%d.%m.%Y')}</div>
<h1>Ihr kostenloser Website-Check</h1>
<p>Guten Tag,</p>
<p>{intro}</p>
<ul>{punkte}</ul>
<div class="box"><b>Unser Angebot:</b> Wir erstellen Ihnen eine moderne, schnelle Website, die auf jedem Handy gut aussieht
und bei Google gefunden wird – {e(s['preis'])}, inklusive Impressum und Datenschutz. Sie bekommen vorab einen
unverbindlichen Entwurf, damit Sie sehen, wie Ihre neue Seite aussehen würde.</div>
<p>Wenn das für Sie interessant ist, melden Sie sich gern{(' bei ' + e(s['ansprechpartner'])) if s['ansprechpartner'] else ''} – ein kurzes Gespräch ist kostenlos und unverbindlich.</p>
<p>Mit freundlichen Grüßen<br>{e(s['ansprechpartner'] or s['firma'])}</p>
<div class="foot small">Datenschutz-Hinweis: Ihre Firmendaten stammen aus öffentlich zugänglichen Verzeichnissen
(OpenStreetMap) bzw. Ihrer Website. Wir nutzen sie ausschließlich für diese einmalige Kontaktaufnahme (Art. 6 Abs. 1 lit. f DSGVO).
Wenn Sie keinen weiteren Kontakt wünschen, genügt eine kurze Nachricht an {e(s['email'])} – wir löschen Ihre Daten dann umgehend.
Weitere Informationen: {e(s['web'])}/datenschutz.html</div>
</body></html>"""


# ---------------------------------------------------------------- HTTP-Server

class Handler(BaseHTTPRequestHandler):
    server_version = "LeadFinder/1.0"

    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode() if "json" in ctype else str(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def guard(self):
        # Nur Anfragen vom eigenen Rechner/Dashboard annehmen
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        if host not in ("127.0.0.1", "localhost") or (origin and not re.match(r"^http://(127\.0\.0\.1|localhost):\d+$", origin)):
            self.send(403, {"error": "forbidden"})
            return False
        return True

    def route(self, method):
        if not self.guard():
            return
        path = urllib.parse.urlparse(self.path).path
        try:
            if method == "GET" and path in ("/", "/index.html"):
                with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if method == "GET" and path == "/api/meta":
                return self.send(200, {"branchen": list(BRANCHEN), "status": STATUS,
                                       "settings": get_settings()})
            if method == "GET" and path == "/api/leads":
                with db() as con:
                    rows = con.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
                return self.send(200, [row_to_dict(r) for r in rows])
            if method == "POST" and path == "/api/search":
                b = self.body_json()
                found, label = osm_search(b.get("branche"), (b.get("ort") or "").strip(), b.get("radius", 10))
                neu = 0
                with DB_LOCK, db() as con:
                    for f in found:
                        if not f["name"]:
                            continue
                        cur = con.execute("""INSERT OR IGNORE INTO leads
                            (quelle, osm_id, name, branche, strasse, plz, ort, telefon, email, website, lat, lon, erstellt_am)
                            VALUES ('osm', :osm_id, :name, :branche, :strasse, :plz, :ort, :telefon, :email, :website, :lat, :lon, :t)""",
                                          {**f, "t": now()})
                        neu += cur.rowcount
                return self.send(200, {"gefunden": len(found), "neu": neu, "ort": label})
            if method == "POST" and path == "/api/leads":
                items = self.body_json().get("items", [])
                ids = []
                with DB_LOCK, db() as con:
                    for it in items:
                        name = (it.get("name") or "").strip()
                        if not name:
                            continue
                        cur = con.execute("""INSERT INTO leads (quelle, name, branche, strasse, plz, ort, telefon, website, erstellt_am)
                            VALUES ('manuell', ?, ?, ?, ?, ?, ?, ?, ?)""",
                                          (name, it.get("branche", ""), it.get("strasse", ""), it.get("plz", ""),
                                           it.get("ort", ""), it.get("telefon", ""), (it.get("website") or "").strip(), now()))
                        ids.append(cur.lastrowid)
                return self.send(200, {"ids": ids})
            m = re.match(r"^/api/leads/(\d+)(/check|/report)?$", path)
            if m:
                lid, sub = int(m.group(1)), m.group(2)
                if method == "POST" and sub == "/check":
                    return self.send(200, check_lead(lid))
                if method == "GET" and sub == "/report":
                    with db() as con:
                        r = con.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()
                    if not r:
                        return self.send(404, {"error": "nicht gefunden"})
                    return self.send(200, report_html(row_to_dict(r), get_settings()), "text/html; charset=utf-8")
                if method == "PATCH" and not sub:
                    b = self.body_json()
                    fields = {k: b[k] for k in ("status", "notiz", "website", "telefon", "email", "name") if k in b}
                    if "status" in fields and fields["status"] not in STATUS:
                        return self.send(400, {"error": "ungültiger Status"})
                    if fields:
                        with DB_LOCK, db() as con:
                            con.execute(f"UPDATE leads SET {', '.join(k + '=?' for k in fields)} WHERE id=?",
                                        (*fields.values(), lid))
                    with db() as con:
                        return self.send(200, row_to_dict(con.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()))
                if method == "DELETE" and not sub:
                    with DB_LOCK, db() as con:
                        con.execute("DELETE FROM leads WHERE id=?", (lid,))
                    return self.send(200, {"ok": True})
            if method == "POST" and path == "/api/settings":
                b = self.body_json()
                with DB_LOCK, db() as con:
                    for k, v in b.items():
                        con.execute("INSERT OR REPLACE INTO settings (k, v) VALUES (?, ?)", (k, str(v)))
                return self.send(200, get_settings())
            if method == "GET" and path == "/api/export.csv":
                cols = ["name", "branche", "strasse", "plz", "ort", "telefon", "email", "website",
                        "website_gefunden", "score", "kategorie", "impressum_fehlt", "veraltet", "status", "notiz", "geprueft_am"]
                with db() as con:
                    rows = con.execute("SELECT * FROM leads ORDER BY score DESC").fetchall()

                def cell(v):
                    v = "" if v is None else str(v)
                    if v[:1] in ("=", "+", "-", "@"):
                        v = "'" + v
                    return '"' + v.replace('"', '""') + '"'
                lines = [";".join(cols)] + [";".join(cell(r[c]) for c in cols) for r in rows]
                return self.send(200, ("﻿" + "\r\n".join(lines)).encode("utf-8"), "text/csv; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="leads.csv"'})
            return self.send(404, {"error": "nicht gefunden"})
        except (ValueError, RuntimeError, KeyError) as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:
            return self.send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PATCH(self):
        self.route("PATCH")

    def do_DELETE(self):
        self.route("DELETE")


def main():
    init_db()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Lead-Finder läuft auf {url}  (Beenden mit Strg+C)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
