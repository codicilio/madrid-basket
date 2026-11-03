import html
import json
import os
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

BASE = "https://dbasket.net"
SEASON = "2026-27"
COMPS = {"acb": "Liga Endesa", "euro": "Euroliga"}
MONTHS = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
ACB_SCHEDULE = "https://acb.com/es/copa-del-rey/noticias/calendario-liga-endesa-2026-27-todas-las-fechas-y-horarios-145767"
EURO_SCHEDULE = "https://www.realmadrid.com/es-ES/noticias/baloncesto/primer-equipo/actualidad/el-calendario-del-real-madrid-para-la-euroliga-2026-27-29-07-2026"
HEADERS = {"User-Agent": "MadridBasketDashboard/1.0 (personal fan dashboard; with DBasket permission)"}

def get(url):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"DBasket returned HTTP {response.status}: {url}")
        return response.read().decode("utf-8", "replace")

def get_json(url):
    return json.loads(get(url))

def normalize_name(value):
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", str(value)).upper() if unicodedata.category(ch) != "Mn")

def slug(value):
    import unicodedata
    value = "".join(ch for ch in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")

def text_only(s):
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def table_rows(fragment):
    return re.findall(r"<tr\b[^>]*>(.*?)</tr\s*>", fragment, re.I | re.S)

def cells(row):
    return re.findall(r"<td\b[^>]*>(.*?)</td\s*>", row, re.I | re.S)

def attr(match, name):
    m = re.search(r"\b" + re.escape(name) + r"\s*=\s*['\"]([^'\"]+)['\"]", match, re.I)
    return html.unescape(m.group(1)) if m else ""

def live_period(status):
    value = re.sub(r"\s+", " ", status or "").strip()
    lower = value.lower()
    if re.search(r"descanso|half[ -]?time|halftime", lower):
        return "Descanso"
    overtime = re.search(r"(?:pr[oó]rroga|overtime|\bot\b)\s*(\d*)", lower)
    if overtime:
        return "Prórroga" + (f" {overtime.group(1)}" if overtime.group(1) else "")
    quarter = (re.search(r"(?:cuarto|periodo|per[ií]odo|quarter|period)\s*(?:n[ºo.]?\s*)?([1-4])", lower)
               or re.search(r"([1-4])\s*(?:[ºª°.]\s*)?(?:cuarto|periodo|per[ií]odo|quarter|period)", lower)
               or re.search(r"\bq\s*([1-4])\b", lower))
    if quarter:
        label = f"{quarter.group(1)}º cuarto"
        clock = re.search(r"\b([0-9]{1,2}:[0-9]{2})\b", value)
        return label + (f" · {clock.group(1)}" if clock else "")
    return "En juego · periodo no indicado por la fuente" if re.search(r"live|en directo|en juego|en curso|jugando", lower) else None


def parse_team(comp, page):
    marker = re.search(r'<div\s+id\s*=\s*["\']partido-a-partido["\']\s*>(.*?)(?:</table>)', page, re.I | re.S)
    if not marker:
        raise RuntimeError(f"Could not find game log for {comp}; refusing to publish partial data")
    rows = table_rows(marker.group(1))
    games = []
    for row in rows:
        td = cells(row)
        if len(td) < 7:
            continue
        round_no = text_only(td[0])
        if not round_no.isdigit():
            continue
        date_raw = text_only(td[1])
        m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", date_raw)
        if not m:
            continue
        day, month, year = map(int, m.groups())
        date_iso = f"{year:04d}-{month:02d}-{day:02d}"
        opponent_match = re.search(r"<a\b[^>]*>(.*?)</a>", td[2], re.I | re.S)
        opponent = text_only(opponent_match.group(1)) if opponent_match else text_only(td[2])
        venue = text_only(td[4])
        status = text_only(td[5])
        score_match = re.search(r"<a\b[^>]*>(.*?)</a>", td[6], re.I | re.S)
        score = text_only(score_match.group(1)) if score_match else text_only(td[6])
        game_href = attr(score_match.group(0), "href") if score_match else ""
        has_score = bool(re.search(r"\d+\s*-\s*\d+", score)) and score != "-"
        period_label = live_period(status)
        in_progress = bool(period_label)
        played = has_score and not in_progress and bool(re.search(r"victoria|derrota|final|finished|terminado", status, re.I))
        if venue not in ("Casa", "Fuera") or not opponent:
            continue
        home, away = ("Real Madrid", opponent) if venue == "Casa" else (opponent, "Real Madrid")
        games.append({
            "competition": comp,
            "competitionLabel": COMPS[comp],
            "round": int(round_no),
            "date": date_iso,
            "time": None,
            "home": home,
            "away": away,
            "venue": venue,
            "status": status,
            "played": played,
            "live": in_progress,
            "periodLabel": period_label,
            "score": re.sub(r"\s+", " ", score) if has_score else None,
            "boxscoreUrl": BASE + game_href if game_href else BASE + f"/seasons/{comp}/{SEASON}",
        })
    expected = 34 if comp == "acb" else 38
    if len(games) < expected:
        raise RuntimeError(f"Only {len(games)}/{expected} {comp} games parsed; refusing to publish partial data")
    return games

def schedule_text(page):
    page = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", page, flags=re.I | re.S)
    page = html.unescape(re.sub(r"<[^>]+>", " ", page))
    page = page.replace(r"\n", " ").replace(r"\u0026", "&")
    return re.sub(r"\s+", " ", page)

def schedule_times(url, comp):
    text = schedule_text(get(url))
    result = {}
    if comp == "acb":
        pattern = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s*\((\d{1,2}:\d{2})\)", re.I)
    else:
        pattern = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+),\s*(\d{1,2}:\d{2})\s*h", re.I)
    for mention in re.finditer(r"Real Madrid", text, re.I):
        prior = text[max(0, mention.start()-260):mention.start()]
        found = list(pattern.finditer(prior))
        if not found:
            continue
        m = found[-1]
        month = MONTHS.get(m.group(2).lower())
        if not month:
            continue
        day = int(m.group(1))
        year = 2026 if month >= 9 else 2027
        result[f"{year:04d}-{month:02d}-{day:02d}"] = m.group(3)
    if len(result) < (20 if comp == "acb" else 25):
        raise RuntimeError(f"Only {len(result)} kickoff times found in the {comp} published schedule")
    return result

def parse_standings(page):
    sec = re.search(r'<div\s+id\s*=\s*["\']clasificacion["\']\s*>(.*?)(?:</div>\s*</div>\s*</div>)', page, re.I | re.S)
    if not sec:
        # The page structure can change; report a hard error rather than publish an empty table.
        raise RuntimeError("Could not find standings section")
    result = []
    for row in table_rows(sec.group(1)):
        td = cells(row)
        if len(td) < 7:
            continue
        pos = text_only(td[0])
        if not pos.isdigit():
            continue
        team_anchor = re.search(r"<a\b[^>]*>(.*?)</a>", td[1], re.I | re.S)
        result.append({
            "position": int(pos),
            "team": text_only(team_anchor.group(1)) if team_anchor else text_only(td[1]),
            "played": text_only(td[2]), "wins": text_only(td[3]), "losses": text_only(td[4]),
            "pointsFor": text_only(td[5]), "pointsAgainst": text_only(td[6]),
            "difference": text_only(td[7]) if len(td) > 7 else "",
        })
    if len(result) < 10:
        raise RuntimeError(f"Only {len(result)} standings entries parsed")
    return result


# ---------------------------------------------------------------------------
# Fuentes oficiales (Euroliga y ACB): horario exacto, TV y marcador en directo.
# Si fallan, se conserva lo que da DBasket: nunca impiden publicar.
# ---------------------------------------------------------------------------
MADRID_TZ = ZoneInfo("Europe/Madrid")
EURO_GAMES = "https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games"
EURO_HEADER = "https://live.euroleague.net/api/Header?gamecode={code}&seasoncode=E2026"
ACB_CALENDAR = "https://api2.acb.com/api/seasondata/Calendar/season-calendar?season=2027&competitionId=1"
ACB_MADRID_CLUB_ID = 9


def utc_to_madrid(value):
    """'2026-11-04T19:45:00Z' -> (fecha 'YYYY-MM-DD', hora 'HH:MM') en hora de Madrid."""
    moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(MADRID_TZ)
    return local.date().isoformat(), local.strftime("%H:%M")


def near_kickoff(game, now=None, before_min=20, after_hours=3.5):
    if not game.get("kickoffUtc"):
        return False
    now = now or datetime.now(timezone.utc)
    start = datetime.fromisoformat(game["kickoffUtc"].replace("Z", "+00:00"))
    delta = (now - start).total_seconds()
    return -before_min * 60 <= delta <= after_hours * 3600


def quarter_label(quarter, clock=""):
    q = str(quarter or "").strip()
    if not q:
        return None
    if q.isdigit():
        n = int(q)
        label = f"{n}º cuarto" if n <= 4 else ("Prórroga" if n == 5 else f"Prórroga {n - 4}")
    else:
        label = q
    clock = str(clock or "").strip()
    return label + (f" · {clock}" if clock else "")


def enrich_euro(games, now=None):
    raw = get_json(EURO_GAMES)
    entries = raw if isinstance(raw, list) else raw.get("data", raw.get("games", []))
    madrid = [x for x in entries
              if "MAD" in (((x.get("local") or {}).get("club") or {}).get("code"),
                           ((x.get("road") or {}).get("club") or {}).get("code"))]
    for game in games:
        if game["competition"] != "euro":
            continue
        found = next((x for x in madrid if int(x.get("round") or 0) == game["round"]), None)
        if not found:
            found = next((x for x in madrid if str(x.get("localDate", ""))[:10] == game["date"]), None)
        if not found:
            continue
        game["liveGameCode"] = found.get("gameCode")
        game["liveStatsUrl"] = "https://www.euroleaguebasketball.net/euroleague/game-center/"
        if found.get("utcDate"):
            game["kickoffUtc"] = str(found["utcDate"]).replace("+00:00", "Z")
            game["date"], game["time"] = utc_to_madrid(found["utcDate"])
        if not game["played"] and near_kickoff(game, now):
            try:
                header = get_json(EURO_HEADER.format(code=game["liveGameCode"]))
                a, b = int(header.get("ScoreA") or 0), int(header.get("ScoreB") or 0)
                if header.get("Live"):
                    game["live"] = True
                    game["score"] = f"{a} - {b}"
                    game["periodLabel"] = quarter_label(header.get("Quarter"), header.get("RemainingPartialTime")) or "En juego"
                elif a + b > 0:
                    game["score"] = f"{a} - {b}"
                    game["live"] = False
                    game["periodLabel"] = "Final"
            except Exception as error:
                print(f"Aviso: marcador Euroliga no disponible: {error}")


def enrich_acb(games, now=None):
    calendar = get_json(ACB_CALENDAR)
    teams = {int(t["id"]): t for t in calendar.get("teams", [])}
    real = next((t for t in teams.values() if int(t.get("clubId", 0)) == ACB_MADRID_CLUB_ID), None)
    if not real:
        raise RuntimeError("Real Madrid no aparece en el calendario ACB")
    madrid_id = int(real["id"])
    matches = []
    for rnd in calendar.get("rounds", []):
        for m in rnd.get("matches", []):
            if madrid_id in (int(m.get("homeTeamId", -1)), int(m.get("awayTeamId", -1))):
                m = dict(m)
                m.setdefault("roundNumber", rnd.get("roundNumber"))
                matches.append(m)
    for game in games:
        if game["competition"] != "acb":
            continue
        found = next((m for m in matches if int(m.get("roundNumber") or 0) == game["round"]), None)
        if not found:
            continue
        game["liveMatchId"] = found.get("id")
        home = (teams.get(int(found.get("homeTeamId", -1))) or {}).get("fullName") or game["home"]
        away = (teams.get(int(found.get("awayTeamId", -1))) or {}).get("fullName") or game["away"]
        game["liveStatsUrl"] = f"https://live.acb.com/es/partidos/{slug(home)}-vs-{slug(away)}-{found.get('id')}/estadisticas"
        start = found.get("delayedStartDateTime") or found.get("startDateTime")
        if start:
            game["kickoffUtc"] = str(start).replace("+00:00", "Z")
            game["date"], game["time"] = utc_to_madrid(start)
        tv = [c.get("broadcaster") for c in sorted(found.get("broadcastChannels") or [], key=lambda c: c.get("order") or 99)
              if c.get("broadcaster") and c.get("primary", True)]
        if tv:
            game["tv"] = tv
        status = str(found.get("matchStatus") or "").upper()
        hs, as_ = found.get("homeScore"), found.get("awayScore")
        if not game["played"] and hs is not None and as_ is not None:
            if status == "FINALIZED":
                game["score"] = f"{hs} - {as_}"
                game["periodLabel"] = "Final"
                game["live"] = False
            elif status not in ("", "SCHEDULED", "PENDING", "NOT_STARTED", "POSTPONED", "CANCELLED") or (int(hs) + int(as_) > 0):
                game["live"] = True
                game["score"] = f"{hs} - {as_}"
                game["periodLabel"] = "Descanso" if found.get("isOnHalfTime") else (quarter_label(found.get("currentQuarter")) or "En juego")


def enrich_official(games):
    for name, fn in (("Euroliga", enrich_euro), ("ACB", enrich_acb)):
        try:
            fn(games)
        except Exception as error:
            print(f"Aviso: datos oficiales de {name} no disponibles ({error}); se mantienen los de DBasket.")


PUBLISHED_FIELDS = ("competition", "round", "date", "time", "kickoffUtc", "home", "away", "venue",
                    "status", "played", "live", "periodLabel", "score", "boxscoreUrl", "tv",
                    "liveGameCode", "liveMatchId", "liveStatsUrl")


def semantic_signature(payload):
    games = [{key: game.get(key) for key in PUBLISHED_FIELDS} for game in payload.get("games", [])]
    games.sort(key=lambda game: (game.get("date") or "", game.get("competition") or "", game.get("round") or 0))
    return json.dumps({"games": games, "standings": payload.get("standings", {})},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def should_publish(payload):
    published_url = os.environ.get("PUBLISHED_DATA_URL", "").strip()
    changed = True
    if published_url:
        url = published_url + ("&" if "?" in published_url else "?") + f"check={int(time.time())}"
        request = Request(url, headers={"User-Agent": HEADERS["User-Agent"], "Cache-Control": "no-cache"})
        try:
            with urlopen(request, timeout=15) as response:
                previous = json.loads(response.read().decode("utf-8", "replace"))
            changed = semantic_signature(payload) != semantic_signature(previous)
        except Exception as error:
            print(f"No se pudo comparar con la versión publicada ({error}); se publicará.")
    if os.environ.get("FORCE_PUBLISH") == "true":
        changed = True
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"publish={'true' if changed else 'false'}\n")
    print("Se publicará: hay cambios." if changed else "Sin cambios deportivos; se omite la publicación.")


def main():
    all_games, tables = [], {}
    times = {}
    for comp, url in (("acb", ACB_SCHEDULE), ("euro", EURO_SCHEDULE)):
        try:
            times[comp] = schedule_times(url, comp)
        except Exception as error:
            print(f"Aviso: calendario publicado {comp} no disponible ({error}); se usarán los horarios oficiales.")
            times[comp] = {}
    for comp in COMPS:
        team_page = get(f"{BASE}/teams/RMA/{SEASON}/{comp}")
        league_page = get(f"{BASE}/seasons/{comp}/{SEASON}")
        games = parse_team(comp, team_page)
        for game in games:
            game["time"] = times[comp].get(game["date"])
        tables[comp] = parse_standings(league_page)
        all_games.extend(games)
        time.sleep(2)
    enrich_official(all_games)
    all_games.sort(key=lambda g: (g["date"], g["competition"], g["round"]))
    payload = {
        "season": SEASON,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "DBasket",
        "sourceUrl": "https://dbasket.net/terms-of-use",
        "games": all_games,
        "standings": tables,
    }
    os.makedirs("site", exist_ok=True)
    with open("site/data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    should_publish(payload)
    print(f"Partidos: {len(all_games)} · ACB {len(tables['acb'])} equipos · Euroliga {len(tables['euro'])} equipos")


if __name__ == "__main__":
    main()
