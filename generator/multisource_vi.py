"""
Multi-source templates T7/T8 (knn+name+multi_source1/2).

Upstream semantics: the gold SQL is the plain nearest-category KNN; the
Wikipedia/Wikidata content only shapes the question. T7 asks an infobox
attribute OF THE ANSWER (e.g. "when was the nearest museum established?"), so
the answer row carries multi_source_* fields. T8 replaces the anchor's display
name with an infobox descriptor ("the museum established in 1976") while the
answer stays the plain KNN row.

External values are frozen into the question records; a QID-keyed fetch cache
(`wikipedia_cache_vi.json`) exists only so regeneration avoids re-downloading.
"""

import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import psycopg
from generator_vi import (
    MAX_CONSECUTIVE_FAILURES,
    POIS_SELECTOR,
    display_name,
    load_templates,
    nfc,
    run_sql,
    surfaces,
    vn_label,
)
from tqdm import tqdm

CACHE_PATH = os.path.join(os.path.dirname(__file__), "wikipedia_cache_vi.json")
USER_AGENT = "ViGSQA-benchmark-generator/2.0 (coursework; contact: repo maintainer)"
# Wikimedia burst-limits anonymous API clients; the wikidata pool is tiny
# (~50 QIDs), so a conservative pace costs little and avoids 429 spirals.
HTTP_SLEEP_S = 2.0
HTTP_STATUS_RATE_LIMITED = 429
HTTP_RETRIES = 3
# Upstream truncation ceiling for infobox answer fragments.
MAX_VALUE_CHARS = 60

# Infobox attribute registry: canonical key -> definition. `keys` are matched
# against normalized (lowercase, collapsed, nbsp-stripped) infobox labels on
# both viwiki and enwiki. `cats` limits which POI categories may use it.
ATTRIBUTES = {
    "established": {
        "label_vi": "thành lập",
        "q": "[1] gần [2] nhất được thành lập vào năm nào?",
        "desc": "{cat} được thành lập vào {v}",
        "keys": [
            "thành lập",
            "ngày thành lập",
            "năm thành lập",
            "established",
            "founded",
            "formation",
        ],
        "cats": None,
    },
    "built": {
        "label_vi": "xây dựng",
        "q": "[1] gần [2] nhất được xây dựng khi nào?",
        "desc": "{cat} được xây dựng vào {v}",
        "keys": [
            "khởi công",
            "xây dựng",
            "khai công",
            "began",
            "built",
            "start date",
            "start_date",
        ],
        "cats": None,
    },
    "architect": {
        "label_vi": "kiến trúc sư",
        "q": "Kiến trúc sư nào thiết kế [1] gần [2] nhất?",
        "desc": "{cat} do kiến trúc sư {v} thiết kế",
        "keys": ["kiến trúc sư", "kiến trúc", "architect", "architects"],
        "cats": [
            "museum",
            "university",
            "stadium",
            "hospital",
            "attraction",
            "hotel",
            "place_of_worship",
            "school",
        ],
    },
    "founder": {
        "label_vi": "người sáng lập",
        "q": "Ai là người sáng lập [1] gần [2] nhất?",
        "desc": "{cat} do {v} sáng lập",
        "keys": [
            "người sáng lập",
            "sáng lập",
            "người thành lập",
            "founder",
            "founders",
            "founded by",
        ],
        "cats": ["museum", "university", "hospital", "hotel", "school"],
    },
    "director": {
        "label_vi": "giám đốc",
        "q": "[1] gần [2] nhất hiện do ai làm giám đốc?",
        "desc": "{cat} hiện do {v} làm giám đốc",
        "keys": ["giám đốc", "director"],
        "cats": ["museum", "hospital", "university"],
    },
    "opened": {
        "label_vi": "khánh thành",
        "q": "[1] gần [2] nhất được khánh thành khi nào?",
        "desc": "{cat} được khánh thành vào {v}",
        "keys": [
            "khai trương",
            "khánh thành",
            "mở cửa",
            "opened",
            "opening date",
            "date opened",
            "inaugurated",
        ],
        "cats": None,
    },
    "capacity": {
        "label_vi": "sức chứa",
        "q": "[1] gần [2] nhất có sức chứa bao nhiêu người?",
        "desc": "{cat} có sức chứa {v}",
        "keys": ["sức chứa", "capacity"],
        "cats": ["stadium", "attraction", "museum", "university"],
    },
    "designed": {
        "label_vi": "thiết kế",
        "q": "[1] gần [2] nhất do ai thiết kế?",
        "desc": "{cat} do {v} thiết kế",
        "keys": ["thiết kế bởi", "thiết kế", "designed by", "designed"],
        "cats": ["museum", "stadium", "attraction", "university"],
    },
}

WIKIDATA_POOL_SQL = """
    SELECT p.osm_id AS id,
           ST_AsText(ST_Transform(p.way,4326)) AS geo_wkt,
           p.name AS poi_name,
           p.addr_city,
           p.wikidata,
           p.amenity, p.tourism, p.shop, p.leisure
    FROM planet_osm_point p
    WHERE p.wikidata IS NOT NULL AND p.name IS NOT NULL
      AND (p.amenity IS NOT NULL OR p.tourism IS NOT NULL
           OR p.shop IS NOT NULL OR p.leisure IS NOT NULL)
    ORDER BY p.osm_id;
"""

# Anchor candidates near a wikidata POI, for T7 (the plain-KNN gold must
# return the wikidata POI itself, so the anchor is drawn in its vicinity).
NEAR_WIKIDATA_SQL = """
    SELECT p.osm_id AS id,
           ST_AsText(ST_Transform(p.way,4326)) AS geo_wkt,
           p.name AS poi_name,
           p.addr_city,
           p.amenity, p.tourism, p.shop, p.leisure
    FROM planet_osm_point p
    WHERE p.name IS NOT NULL
      AND (p.amenity IS NOT NULL OR p.tourism IS NOT NULL
           OR p.shop IS NOT NULL OR p.leisure IS NOT NULL)
      AND p.osm_id <> {w_id}
      AND ST_DWithin(ST_Transform(p.way,4326)::geography,
                     ST_GeomFromText('{w_wkt}',4326)::geography, 10000)
    ORDER BY p.way <-> ST_Transform(ST_GeomFromText('{w_wkt}',4326),3857)
    LIMIT 1 OFFSET {offset};
"""


def _http_get_json(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}", headers={"User-Agent": USER_AGENT}
    )
    # Wikimedia rate limits back off rather than fail the whole run.
    for attempt in range(HTTP_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == HTTP_STATUS_RATE_LIMITED and attempt < HTTP_RETRIES:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def wikidata_sitelink(qid: str, lang: str) -> str | None:
    data = _http_get_json(
        "https://www.wikidata.org/w/api.php",
        {
            "action": "wbgetentities",
            "ids": qid,
            "props": "sitelinks",
            "sitefilter": f"{lang}wiki",
            "format": "json",
        },
    )
    site = data.get("entities", {}).get(qid, {}).get("sitelinks", {}).get(f"{lang}wiki")
    return site["title"] if site and site.get("title") else None


def wikipedia_wikitext(title: str, lang: str) -> str:
    data = _http_get_json(
        f"https://{lang}.wikipedia.org/w/api.php",
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "section": 0,
            "format": "json",
        },
    )
    return data.get("parse", {}).get("wikitext", {}).get("*", "")


def _normalize_key(key: str) -> str:
    key = key.replace("\xa0", " ").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", key).strip().lower()


def _split_template_params(body: str) -> list[str]:
    """Split a template body on top-level '|' (nested {{}} and [[]] respected)."""
    parts, depth, current = [], 0, []
    for ch in body:
        if ch in {"{", "["}:
            depth += 1
        elif ch in {"}", "]"}:
            depth = max(0, depth - 1)
        if ch == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def parse_infobox(wikitext: str) -> dict[str, str]:
    """Extract the first infobox template's parameters from lead wikitext."""
    start = wikitext.find("{{")
    while start != -1:
        depth, i = 2, start + 2
        while i < len(wikitext) - 1 and depth:
            if wikitext[i : i + 2] == "{{":
                depth += 2
                i += 2
            elif wikitext[i : i + 2] == "}}":
                depth -= 2
                i += 2
            else:
                i += 1
        name = (
            wikitext[start + 2 : wikitext.find("|", start)]
            if "|" in wikitext[start:i]
            else ""
        )
        name_l = _normalize_key(name)
        if "infobox" in name_l or "hộp thông tin" in name_l:
            params = {}
            for part in _split_template_params(wikitext[start + 2 : i - 2])[1:]:
                if "=" not in part:
                    continue
                key, _, value = part.partition("=")
                params[_normalize_key(key)] = value.strip()
            return params
        start = wikitext.find("{{", i)
    return {}


def clean_value(value: str) -> str | None:
    """Reduce an infobox value to a short plain answer fragment."""

    def _date_year(match: re.Match) -> str:
        # {{Start date and age|1988|09|13|df=yes}} and viwiki equivalents
        # carry the founding year as the first 4-digit number.
        years = re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", match.group(0))
        return years[0] if years else ""

    v = re.sub(r"<ref[^>]*/>", "", value)
    v = re.sub(r"<ref[^>]*>.*?</ref>", "", v, flags=re.DOTALL)
    v = re.sub(r"\{\{[^{}]*(?:[Dd]ate|[Nn]gày)[^{}]*\}\}", _date_year, v)
    v = re.sub(r"\[\[[^]|]*\|([^\]]*)\]\]", r"\1", v)  # [[a|b]] -> b
    v = re.sub(r"\[\[([^\]]*)\]\]", r"\1", v)  # [[a]] -> a
    v = re.sub(r"\{\{[^{}]*\}\}", "", v)  # leftover flag/format templates
    v = re.sub(r"<[^>]+>", "", v)
    v = v.replace("'''", "").replace("''", "").replace("\xa0", " ")
    # Upstream truncation heuristic: drop parentheticals/lists after the head.
    v = re.split(r"[;(\[]", v)[0]
    v = re.sub(r"\s+", " ", v).strip(" :.,")
    if not v or len(v) > MAX_VALUE_CHARS or not re.search(r"[\wÀ-ỹ]", v):
        return None
    return v


class WikipediaCache:
    """QID-keyed cache of parsed infoboxes; misses are fetched once."""

    def __init__(self, path: str = CACHE_PATH):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def infobox(self, qid: str) -> dict | None:
        if qid in self.data:
            return self.data[qid]["infobox"]
        infobox = None
        # `fetched` separates "confirmed no infobox" (cache the miss) from
        # transient HTTP failure (leave uncached so a later run retries).
        fetched = False
        for lang in ("vi", "en"):
            try:
                title = wikidata_sitelink(qid, lang)
            except (OSError, ValueError, KeyError):
                continue
            if not title:
                fetched = True
                continue
            time.sleep(HTTP_SLEEP_S)
            try:
                params = parse_infobox(wikipedia_wikitext(title, lang))
            except (OSError, ValueError, KeyError):
                continue
            fetched = True
            if params:
                infobox = params
                break
        if fetched:
            self.data[qid] = {"infobox": infobox}
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False)
            except OSError:
                pass
        return infobox


def attribute_for(sub_category: str, infobox: dict) -> tuple[str, str] | None:
    """First registered attribute whose key this category may use and that has
    a non-empty cleaned value in the infobox."""
    for key, spec in ATTRIBUTES.items():
        if spec["cats"] is not None and sub_category not in spec["cats"]:
            continue
        for infobox_key in spec["keys"]:
            if infobox_key in infobox:
                value = clean_value(infobox[infobox_key])
                if value:
                    return key, value
    return None


def load_wikidata_pool() -> list[dict]:
    pool = run_sql(WIKIDATA_POOL_SQL)
    for p in pool:
        p["poi_name"] = nfc(p["poi_name"])
    return pool


def _poi_sub_category(poi: dict) -> tuple[str, str] | None:
    for col in ("amenity", "tourism", "shop", "leisure"):
        if poi.get(col):
            return col, poi[col]
    return None


def _knn_sql(main_cat: str, sub_cat: str, anchor: dict) -> str:
    geom = f"ST_GeomFromText('{anchor['geo_wkt']}',4326)"
    return (
        f"SELECT id, geo_wkt, poi_name FROM pois\n"
        f"WHERE {main_cat} ILIKE '{sub_cat}' AND poi_name IS NOT NULL\n"
        f"  AND id <> {anchor['id']}\n"
        f"ORDER BY geometry <-> {geom}::geography LIMIT 1;"
    )


def generate_multi_source1(tid: str, n: int = 100) -> list[dict]:
    """T7: ask an infobox attribute of the nearest [1] from [2]."""
    cache = WikipediaCache()
    pool = load_wikidata_pool()
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc=f"{tid} knn+name+multi_source1")
    while len(results) < n:
        if fails > MAX_CONSECUTIVE_FAILURES:
            break
        target = random.choice(pool)
        cat = _poi_sub_category(target)
        if not cat:
            fails += 1
            continue
        main_cat, sub_cat = cat
        attribute = attribute_for(sub_cat, cache.infobox(target["wikidata"]) or {})
        if not attribute:
            fails += 1
            continue
        attr_key, attr_value = attribute

        # Anchor drawn near the target so the plain-KNN gold returns it; the
        # SQL itself stays the unbiased nearest-category query (upstream shape).
        anchor = None
        for _ in range(10):
            rows = run_sql(
                NEAR_WIKIDATA_SQL.format(
                    w_id=target["id"],
                    w_wkt=target["geo_wkt"],
                    offset=random.randint(0, 200),
                )
            )
            if not rows:
                break
            candidate = rows[0]
            if _poi_sub_category(candidate) != cat:
                candidate["poi_name"] = nfc(candidate["poi_name"])
                anchor = candidate
                break
        if not anchor:
            fails += 1
            continue

        sql = _knn_sql(main_cat, sub_cat, anchor)
        try:
            answers = run_sql(sql)
        except psycopg.Error:
            fails += 1
            continue
        if not answers or answers[0].get("id") != target["id"]:
            fails += 1
            continue

        label = vn_label(sub_cat)
        spec = ATTRIBUTES[attr_key]
        q = nfc(spec["q"].replace("[1]", label).replace("[2]", display_name(anchor)))
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        answer_row = dict(answers[0])
        answer_row["multi_source_answer"] = attr_value
        answer_row["multi_source_attribute"] = attr_key
        answer_row["multi_source_long_answer"] = (
            f"{answer_row.get('poi_name', '')} ({spec['label_vi']}): {attr_value}"
        )
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": [answer_row],
                "answer_type": "name",
                "id": f"knn+name+multi_source1-{len(results) + 1:03d}",
                "tid": tid,
                "type": "knn+name+multi_source1",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {
                        "poi_name": anchor["poi_name"],
                        "id": anchor["id"],
                        "geo_wkt": anchor["geo_wkt"],
                    },
                    "attribute": attr_key,
                },
            }
        )
        fails = 0
        pbar.update(1)
    pbar.close()
    return results


def generate_multi_source2(tid: str, n: int = 100) -> list[dict]:
    """T8: anchor displayed as an infobox descriptor; answer = plain KNN."""
    cache = WikipediaCache()
    pool = load_wikidata_pool()
    tmpls = load_templates("knn+name+multi_source2")
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc=f"{tid} knn+name+multi_source2")
    while len(results) < n:
        if fails > MAX_CONSECUTIVE_FAILURES:
            break
        anchor = random.choice(pool)
        cat = _poi_sub_category(anchor)
        if not cat:
            fails += 1
            continue
        anchor_main_cat, anchor_sub_cat = cat
        attribute = attribute_for(
            anchor_sub_cat, cache.infobox(anchor["wikidata"]) or {}
        )
        if not attribute:
            fails += 1
            continue
        attr_key, attr_value = attribute
        descriptor = nfc(
            ATTRIBUTES[attr_key]["desc"].format(
                cat=vn_label(anchor_sub_cat), v=attr_value
            )
        )

        main_cat = random.choice(
            [c for c in POIS_SELECTOR if c != anchor_main_cat] or list(POIS_SELECTOR)
        )
        sub_cat = random.choice(POIS_SELECTOR[main_cat])
        if (main_cat, sub_cat) == (anchor_main_cat, anchor_sub_cat):
            fails += 1
            continue

        sql = _knn_sql(main_cat, sub_cat, anchor)
        try:
            answers = run_sql(sql)
        except psycopg.Error:
            fails += 1
            continue
        if not answers:
            fails += 1
            continue

        q = nfc(
            random.choice(tmpls)
            .replace("[1]", vn_label(sub_cat))
            .replace("[2]", descriptor)
        )
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": answers,
                "answer_type": "name",
                "id": f"knn+name+multi_source2-{len(results) + 1:03d}",
                "tid": tid,
                "type": "knn+name+multi_source2",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {
                        "poi_name": anchor["poi_name"],
                        "id": anchor["id"],
                        "geo_wkt": anchor["geo_wkt"],
                        "descriptor": descriptor,
                        "attribute": attr_key,
                    },
                },
            }
        )
        fails = 0
        pbar.update(1)
    pbar.close()
    return results
