"""Project-wide settings: the upstream source, its file contract, and the database URL."""

import os

SOURCE_REPO = "Greco1899/scrape_ufc_stats"
SOURCE_BASE_URL = f"https://raw.githubusercontent.com/{SOURCE_REPO}/main/"

FILES: tuple[str, ...] = (
    "ufc_event_details",
    "ufc_fight_details",
    "ufc_fight_results",
    "ufc_fight_stats",
    "ufc_fighter_details",
    "ufc_fighter_tott",
)

# The header contract: exact columns, in order, for each upstream file.
EXPECTED_COLUMNS: dict[str, list[str]] = {
    "ufc_event_details": ["EVENT", "URL", "DATE", "LOCATION"],
    "ufc_fight_details": ["EVENT", "BOUT", "URL"],
    "ufc_fight_results": [
        "EVENT", "BOUT", "OUTCOME", "WEIGHTCLASS", "METHOD", "ROUND", "TIME",
        "TIME FORMAT", "REFEREE", "DETAILS", "URL",
    ],
    "ufc_fight_stats": [
        "EVENT", "BOUT", "ROUND", "FIGHTER", "KD", "SIG.STR.", "SIG.STR. %", "TOTAL STR.",
        "TD", "TD %", "SUB.ATT", "REV.", "CTRL", "HEAD", "BODY", "LEG", "DISTANCE", "CLINCH", "GROUND",
    ],
    "ufc_fighter_details": ["FIRST", "LAST", "NICKNAME", "URL"],
    "ufc_fighter_tott": ["FIGHTER", "HEIGHT", "WEIGHT", "REACH", "STANCE", "DOB", "URL"],
}


def database_url() -> str:
    return os.environ.get("UFC_DATABASE_URL", "postgresql://ufc:ufc@localhost:5433/ufc")
