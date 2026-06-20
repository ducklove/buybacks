from __future__ import annotations

import argparse
import json
import os
import sys
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks.dart_client import OpenDartClient
    from scripts.buybacks.models import Company, to_jsonable
    from scripts.buybacks.parsers import normalize_date
else:
    from .dart_client import OpenDartClient
    from .models import Company, to_jsonable
    from .parsers import normalize_date


def parse_corp_code_zip(payload: bytes) -> list[Company]:
    with ZipFile(BytesIO(payload)) as archive:
        xml_name = next((name for name in archive.namelist() if name.lower().endswith(".xml")), None)
        if xml_name is None:
            raise ValueError("corpCode zip did not contain XML")
        xml_payload = archive.read(xml_name)

    root = ElementTree.fromstring(xml_payload)
    companies: list[Company] = []
    for item in root.findall("list"):
        stock_code = text(item, "stock_code")
        if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
            continue
        companies.append(
            Company(
                corp_code=text(item, "corp_code"),
                stock_code=stock_code,
                corp_name=text(item, "corp_name"),
                market="OTHER",
                sector=None,
                last_updated=normalize_date(text(item, "modify_date")) or text(item, "modify_date"),
            )
        )
    return companies


def fetch_corp_codes(api_key: str, output: Path | None = None) -> list[Company]:
    client = OpenDartClient(api_key)
    companies = parse_corp_code_zip(client.request_bytes("corpCode.xml"))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(to_jsonable(companies), ensure_ascii=False, indent=2), encoding="utf-8")
    return companies


def text(item: ElementTree.Element, tag: str) -> str:
    found = item.find(tag)
    return (found.text or "").strip() if found is not None else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/raw/buybacks/corp_codes.json"))
    args = parser.parse_args()
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        raise SystemExit("DART_API_KEY is required to fetch corp codes")
    companies = fetch_corp_codes(api_key, args.output)
    print(f"wrote {len(companies)} listed companies to {args.output}")


if __name__ == "__main__":
    main()
