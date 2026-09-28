import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib.request import Request, urlopen

CODES_FILE = "codes.json"

SOURCES = [
    {
        "name": "Pocket Tactics",
        "url": "https://www.pockettactics.com/fc-mobile/codes",
        "active_start": "Here are the active FC Mobile codes:",
        "active_end": "Expired codes:",
        "expired_start": "Expired codes:",
        "expired_end": "There you have it",
    },
    {
        "name": "Radio Times",
        "url": "https://www.radiotimes.com/technology/gaming/fc-mobile-redeem-codes/",
        "active_start": "Latest codes",
        "active_end": "Expired codes",
        "expired_start": "Expired codes",
        "expired_end": "How to redeem codes in FC Mobile explained",
    },
    {
        "name": "GamesRadar+",
        "url": "https://www.gamesradar.com/games/ea-sports-fc/fc-mobile-codes/",
        "active_start": "The following FC Mobile redemption codes are active for rewards:",
        "active_end": "How to redeem codes",
        "expired_start": "Expired FC Mobile codes",
        "expired_end": "There are plenty of expired FC Mobile codes",
    },
]


def load_codes():
    try:
        with open(CODES_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_codes(codes):
    with open(CODES_FILE, "w", encoding="utf-8") as file:
        json.dump(codes, file, ensure_ascii=False, indent=2)


def fetch_text(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/153 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    with urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="ignore")

    raw = re.sub(
        r"(?is)<(script|style|noscript).*?>.*?</\1>",
        " ",
        raw,
    )

    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|li|div|h1|h2|h3|h4|section)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)

    text = unescape(raw)
    text = re.sub(r"\r", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)

    return text


def extract_section(text, start_marker, end_marker):
    start = text.lower().find(start_marker.lower())

    if start == -1:
        return ""

    start += len(start_marker)

    end = text.lower().find(end_marker.lower(), start)

    if end == -1:
        end = len(text)

    return text[start:end]


def extract_codes(section):
    results = []

    for raw_line in section.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()

        if not line:
            continue

        match = re.search(
            r"\b([A-Z0-9][A-Z0-9_-]{5,39})\b\s*[-–—:]\s*(.*)$",
            line,
            re.IGNORECASE,
        )

        if not match:
            continue

        code = match.group(1).strip().upper()
        reward = match.group(2).strip()

        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{5,39}", code):
            continue

        results.append(
            {
                "code": code,
                "reward": reward,
            }
        )

    unique = {}
    for item in results:
        unique[item["code"]] = item

    return list(unique.values())


def main():
    existing = load_codes()
    existing_by_code = {
        item.get("code", "").strip().upper(): item
        for item in existing
        if item.get("code")
    }

    scan_time = datetime.now(timezone.utc).isoformat()

    found_active = {}
    found_expired = {}
    successful_sources = []

    for source in SOURCES:
        print(f"Scanning: {source['name']}")

        try:
            text = fetch_text(source["url"])
            successful_sources.append(source["name"])

            active_section = extract_section(
                text,
                source["active_start"],
                source["active_end"],
            )

            expired_section = extract_section(
                text,
                source["expired_start"],
                source["expired_end"],
            )

            active_codes = extract_codes(active_section)
            expired_codes = extract_codes(expired_section)

            for item in active_codes:
                code = item["code"]

                if code not in found_active:
                    found_active[code] = {
                        "code": code,
                        "reward": item["reward"],
                        "sources": [],
                    }

                if source["name"] not in found_active[code]["sources"]:
                    found_active[code]["sources"].append(source["name"])

            for item in expired_codes:
                code = item["code"]
                found_expired.setdefault(code, []).append(source["name"])

            print(
                f"  Active: {len(active_codes)} | "
                f"Expired listed: {len(expired_codes)}"
            )

        except Exception as error:
            print(f"  Source failed: {error}")

    if not successful_sources:
        print("No sources could be scanned. Keeping existing data.")
        return

    changed = False

    for code, item in found_active.items():
        record = existing_by_code.get(code)

        sources_text = ", ".join(item["sources"])

        if record is None:
            existing_by_code[code] = {
                "code": code,
                "reward": item["reward"],
                "source": sources_text,
                "sources": item["sources"],
                "foundAt": scan_time,
                "lastSeenAt": scan_time,
                "status": "active",
            }
            changed = True
            print(f"NEW CODE: {code}")
            continue

        previous_status = record.get("status", "active")

        record["reward"] = item["reward"]
        record["source"] = sources_text
        record["sources"] = item["sources"]

        if previous_status != "active":
            record["status"] = "active"
            record["lastSeenAt"] = scan_time
            changed = True
            print(f"REACTIVATED: {code}")

    for code, source_names in found_expired.items():
        record = existing_by_code.get(code)

        if record is None:
            continue

        if code in found_active:
            continue

        if record.get("status") != "expired":
            record["status"] = "expired"
            record["expiredAt"] = scan_time
            record["expiredSources"] = source_names
            changed = True
            print(f"EXPIRED: {code}")

    result = list(existing_by_code.values())

    result.sort(
        key=lambda item: (
            0 if item.get("status") == "active" else 1,
            item.get("foundAt", ""),
        ),
        reverse=False,
    )

    active = [item for item in result if item.get("status") == "active"]
    expired = [item for item in result if item.get("status") != "active"]

    active.sort(key=lambda item: item.get("foundAt", ""), reverse=True)
    expired.sort(key=lambda item: item.get("foundAt", ""), reverse=True)

    result = active + expired

    if changed:
        save_codes(result)
        print(f"Saved {len(result)} codes.")
    else:
        print("No data changes.")

    print(f"Successful sources: {len(successful_sources)}/{len(SOURCES)}")
    print(f"Active codes: {len(active)}")
    print(f"History codes: {len(result)}")


if __name__ == "__main__":
    main()
