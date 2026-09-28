import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen

CODES_FILE = "codes.json"

SOURCES = [
    {
        "name": "Pocket Tactics",
        "url": "https://www.pockettactics.com/fc-mobile/codes",
    },
    {
        "name": "Radio Times",
        "url": "https://www.radiotimes.com/technology/gaming/fc-mobile-redeem-codes/",
    },
    {
        "name": "GamesRadar+",
        "url": "https://www.gamesradar.com/games/ea-sports-fc/fc-mobile-codes/",
    },
]


class CodeListParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pending_context = None
        self.list_context = None
        self.list_depth = 0
        self.current_li = None
        self.current_li_parts = []

        self.current_block = None
        self.current_block_parts = []

        self.active_codes = []
        self.expired_codes = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}:
            if self.current_block is None:
                self.current_block = tag
                self.current_block_parts = []

        if tag in {"ul", "ol"}:
            if self.list_depth == 0:
                self.list_context = self.pending_context
                self.pending_context = None
            self.list_depth += 1

        if tag == "li" and self.list_depth == 1:
            self.current_li = True
            self.current_li_parts = []

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag == "li" and self.list_depth == 1 and self.current_li:
            text = self.clean_text(" ".join(self.current_li_parts))
            item = self.parse_code(text)

            if item and self.list_context == "active":
                self.active_codes.append(item)

            if item and self.list_context == "expired":
                self.expired_codes.append(item)

            self.current_li = None
            self.current_li_parts = []

        if tag in {"ul", "ol"} and self.list_depth > 0:
            self.list_depth -= 1

            if self.list_depth == 0:
                self.list_context = None

        if (
            self.current_block == tag
            and tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}
        ):
            text = self.clean_text(" ".join(self.current_block_parts))
            self.update_context(text)

            self.current_block = None
            self.current_block_parts = []

    def handle_data(self, data):
        if self.current_li and self.list_depth == 1:
            self.current_li_parts.append(data)

        if self.current_block is not None:
            self.current_block_parts.append(data)

    def update_context(self, text):
        lower = text.lower()

        if (
            "following fc mobile redemption codes are active" in lower
            or "here are the active fc mobile codes" in lower
            or "latest codes" in lower
        ):
            self.pending_context = "active"
            return

        if (
            "expired fc mobile codes" in lower
            or lower.strip() == "expired codes"
            or lower.strip().startswith("expired codes:")
        ):
            self.pending_context = "expired"

    @staticmethod
    def clean_text(text):
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def parse_code(text):
        text = text.strip()

        match = re.match(
            r"^([A-Z0-9][A-Z0-9_-]{5,39})"
            r"(?:\s*\(NEW!\))?"
            r"(?:\s*[-–—:]\s*(.*))?$",
            text,
            re.IGNORECASE,
        )

        if not match:
            return None

        code = match.group(1).strip().upper()
        reward = (match.group(2) or "").strip()

        if len(code) < 6:
            return None

        return {
            "code": code,
            "reward": reward,
        }


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


def fetch_html(url):
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
        return response.read().decode("utf-8", errors="ignore")


def scan_source(source):
    html = fetch_html(source["url"])

    parser = CodeListParser()
    parser.feed(html)

    active = {}
    expired = {}

    for item in parser.active_codes:
        active[item["code"]] = item

    for item in parser.expired_codes:
        expired[item["code"]] = item

    return list(active.values()), list(expired.values())


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
            active_codes, expired_codes = scan_source(source)

            successful_sources.append(source["name"])

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

                if code not in found_expired:
                    found_expired[code] = {
                        "code": code,
                        "reward": item["reward"],
                        "sources": [],
                    }

                if source["name"] not in found_expired[code]["sources"]:
                    found_expired[code]["sources"].append(source["name"])

            print(
                f"  Active: {len(active_codes)} | "
                f"Expired listed: {len(expired_codes)}"
            )

        except Exception as error:
            print(f"  Source failed: {error}")

    if not successful_sources:
        print("No sources succeeded. Existing data kept.")
        return

    for code, item in found_active.items():
        record = existing_by_code.get(code)

        if record is None:
            record = {
                "code": code,
                "reward": item["reward"],
                "source": "",
                "sources": [],
                "foundAt": scan_time,
                "lastSeenAt": scan_time,
                "status": "active",
            }
            existing_by_code[code] = record

        record["reward"] = item["reward"]
        record["source"] = ", ".join(item["sources"])
        record["sources"] = item["sources"]
        record["lastSeenAt"] = scan_time
        record["status"] = "active"

        record.pop("expiredAt", None)
        record.pop("expiredSources", None)

    for code, item in found_expired.items():
        record = existing_by_code.get(code)

        if record is None:
            existing_by_code[code] = {
                "code": code,
                "reward": item["reward"],
                "source": ", ".join(item["sources"]),
                "sources": item["sources"],
                "foundAt": scan_time,
                "status": "expired",
                "expiredAt": scan_time,
                "expiredSources": item["sources"],
            }
        else:
            if code not in found_active:
                record["reward"] = item["reward"]
                record["source"] = ", ".join(item["sources"])
                record["sources"] = item["sources"]
                record["status"] = "expired"
                record["expiredAt"] = record.get("expiredAt", scan_time)
                record["expiredSources"] = item["sources"]

    result = list(existing_by_code.values())

    active = [
        item for item in result
        if item.get("status") == "active"
    ]

    expired = [
        item for item in result
        if item.get("status") == "expired"
    ]

    active.sort(
        key=lambda item: item.get("foundAt", ""),
        reverse=True,
    )

    expired.sort(
        key=lambda item: item.get("foundAt", ""),
        reverse=True,
    )

    result = active + expired

    save_codes(result)

    print()
    print(f"Successful sources: {len(successful_sources)}/{len(SOURCES)}")
    print(f"Active codes: {len(active)}")
    print(f"History codes: {len(result)}")

    print()
    print("ACTIVE CODES:")
    for item in active:
        print(
            f"  {item['code']} -> "
            f"{item.get('reward', '')}"
        )


if __name__ == "__main__":
    main()
