import html
import json
import os
import re
import time
from datetime import datetime, timezone
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


PUBLISHED_FIELDS = ("competition", "round", "date", "time", "home", "away", "venue",
                    "status", "played", "live", "periodLabel", "score", "boxscoreUrl")

def semantic_signature(payload):
    games = [{key: game.get(key) for key in PUBLISHED_FIELDS} for game in payload.get("games", [])]
    games.sort(key=lambda game: (game.get("date") or "", game.get("competition") or "", game.get("round") or 0))
    return json.dumps({"games": games, "standings": payload.get("standings", {})},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def should_publish(payload):
    published_url = os.environ.get("PUBLISHED_DATA_URL", "").strip()
    if not published_url:
        print("No hay URL publicada configurada; se publicará para evitar dejar datos sin actualizar.")
        changed = True
    else:
        url = published_url + ("&" if "?" in published_url else "?") + f"check={int(time.time())}"
        request = Request(url, headers={"User-Agent": HEADERS["User-Agent"], "Cache-Control": "no-cache"})
        try:
            with urlopen(request, timeout=15) as response:
                previous = json.loads(response.read().decode("utf-8", "replace"))
            changed = semantic_signature(payload) != semantic_signature(previous)
        except Exception as error:
            print(f"No se pudo comparar con la versión publicada ({error}); se publicará para proteger la actualización.")
            changed = True
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"publish={'true' if changed else 'false'}\n")
    print("Se publicará: hay cambios en los datos deportivos." if changed else "Sin cambios deportivos; se omite la publicación.")

def main():
    all_games, tables = [], {}
    times = {"acb": schedule_times(ACB_SCHEDULE, "acb"), "euro": schedule_times(EURO_SCHEDULE, "euro")}
    times["euro"]["2026-10-22"] = "20:05"  # actualizado en el calendario vigente del club
    for comp in COMPS:
        team_page = get(f"{BASE}/teams/RMA/{SEASON}/{comp}")
        league_page = get(f"{BASE}/seasons/{comp}/{SEASON}")
        games = parse_team(comp, team_page)
        for game in games:
            game["time"] = times[comp].get(game["date"])
        tables[comp] = parse_standings(league_page)
        all_games.extend(games)
        time.sleep(2)
    all_games.sort(key=lambda g: (g["date"], g["competition"], g["round"]))
    payload = {
        "season": SEASON,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "DBasket",
        "sourceUrl": "https://dbasket.net/terms-of-use",
        "games": all_games,
        "standings": tables,
    }
    with open("site/data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    should_publish(payload)
    print(f"Wrote {len(all_games)} games; ACB standings {len(tables['acb'])}, EuroLeague standings {len(tables['euro'])}")

if __name__ == "__main__":
    main()
