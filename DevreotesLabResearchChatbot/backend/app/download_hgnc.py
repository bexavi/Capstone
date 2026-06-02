import json
import requests

from .paths import HGNC_LOOKUP_PATH, resolve_project_path


HGNC_URL = "https://storage.googleapis.com/public-download-files/hgnc/json/json/hgnc_complete_set.json"


def download_hgnc(output_path: str | None = None) -> dict:
    print("Downloading HGNC dataset...")
    response = requests.get(HGNC_URL, timeout=60)
    response.raise_for_status()
    data = response.json()

    alias_to_hgnc = {}

    for gene in data.get("response", {}).get("docs", []):
        hgnc_id = gene.get("hgnc_id")
        symbol = gene.get("symbol")
        if not hgnc_id or not symbol:
            continue

        entry = {"hgnc_id": hgnc_id, "official_symbol": symbol}
        alias_to_hgnc[symbol.upper()] = entry

        for field in ["alias_symbol", "prev_symbol"]:
            for alias in gene.get(field, []) or []:
                if alias:
                    alias_to_hgnc[alias.upper()] = entry

    target = resolve_project_path(output_path, HGNC_LOOKUP_PATH)
    with target.open("w", encoding="utf-8") as f:
        json.dump(alias_to_hgnc, f)

    print(f"HGNC lookup built: {len(alias_to_hgnc)} aliases mapped -> {target}")
    return alias_to_hgnc


if __name__ == "__main__":
    download_hgnc()
