"""Refresh the small school-name snapshot used by community forms."""

import csv
import io
import json
import urllib.request
import zipfile
from pathlib import Path

SOURCE = (
    "https://ed-public-download.scorecard.network/downloads/"
    "Most-Recent-Cohorts-Institution_10152026.zip"
)
OUTPUT = Path(__file__).resolve().parents[1] / "src/frontend/static/schools.json"


def main() -> None:
    with urllib.request.urlopen(SOURCE, timeout=60) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    with archive, archive.open("Most-Recent-Cohorts-Institution.csv") as raw:
        rows = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        names = sorted(
            {
                row["INSTNM"].strip()
                for row in rows
                if row["CURROPER"] == "1" and row["INSTNM"].strip()
            },
            key=str.casefold,
        )
    OUTPUT.write_text(
        json.dumps(names, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {len(names)} operating US postsecondary institution names to {OUTPUT}"
    )


if __name__ == "__main__":
    main()
