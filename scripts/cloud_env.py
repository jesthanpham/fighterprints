"""Print `export` lines that point the pipeline and Dagster at the Railway database.

Run inside `railway run --service Postgres`, which provides DATABASE_PUBLIC_URL (the database's
password-protected, SSL public address). Used by cloud-dashboard.sh.
"""

import os
import shlex
import sys
from urllib.parse import unquote, urlparse

url = os.environ.get("DATABASE_PUBLIC_URL")
if not url:
    sys.exit(
        "DATABASE_PUBLIC_URL isn't set: the Railway Postgres has no public address.\n"
        "Enable it in Railway: Postgres → Settings → Networking → Public access."
    )
u = urlparse(url)
exports = {
    "DAGSTER_PG_URL": url,
    "UFC_DATABASE_URL": url,
    "UFC_DB_HOST": u.hostname,
    "UFC_DB_PORT": u.port,
    "UFC_DB_USER": unquote(u.username or ""),
    "UFC_DB_PASSWORD": unquote(u.password or ""),
    "UFC_DB_NAME": u.path.lstrip("/"),
}
for key, value in exports.items():
    print(f"export {key}={shlex.quote(str(value))}")
