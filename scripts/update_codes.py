import json
from datetime import datetime, timezone

CODES_FILE = "codes.json"

def load_codes():
    try:
        with open(CODES_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_codes(codes):
    with open(CODES_FILE, "w", encoding="utf-8") as file:
        json.dump(codes, file, ensure_ascii=False, indent=2)

def main():
    codes = load_codes()
    scan_time = datetime.now(timezone.utc).isoformat()

    print(f"FC Mobile scan: {scan_time}")
    print(f"Known codes: {len(codes)}")

    save_codes(codes)

if __name__ == "__main__":
    main()
