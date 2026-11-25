"""The cloud setup: Dagster keeps run history in Postgres, and one image serves both Railway roles."""

import subprocess
from pathlib import Path

from dagster import DagsterInstance

from tests.conftest import TEST_DATABASE_URL

ROOT = Path(__file__).resolve().parents[1]
CLOUD_HOME = ROOT / "docker" / "dagster-cloud"
START = ROOT / "docker" / "start.sh"


def test_cloud_dagster_stores_runs_in_postgres(db, monkeypatch):
    monkeypatch.setenv("DAGSTER_PG_URL", TEST_DATABASE_URL)
    instance = DagsterInstance.from_config(str(CLOUD_HOME))
    try:
        assert type(instance.run_storage).__name__ == "PostgresRunStorage"
        assert type(instance.event_log_storage).__name__ == "PostgresEventLogStorage"
        assert type(instance.schedule_storage).__name__ == "PostgresScheduleStorage"
    finally:
        instance.dispose()


def _start_cmd(role: str) -> str:
    """What the start script would run for a role (dry run, nothing is executed)."""
    result = subprocess.run(
        ["sh", str(START)], check=False, env={"UFC_ROLE": role, "PORT": "1234", "UFC_DRY_RUN": "1", "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else f"exit {result.returncode}: {result.stderr}"


def test_start_script_web_serves_streamlit_on_railway_port():
    cmd = _start_cmd("web")
    assert cmd.startswith("streamlit run app/streamlit_app.py")
    assert "--server.port 1234" in cmd


def test_start_script_pipeline_materializes_everything():
    assert _start_cmd("pipeline") == "dagster asset materialize --select * -m ufc.orchestration.definitions"


def test_start_script_rejects_unknown_role():
    assert _start_cmd("nonsense").startswith("exit 1:")


def _railway_config(role: str) -> dict:
    import json

    return json.loads((ROOT / "deploy" / f"railway.{role}.json").read_text())


def test_pipeline_runs_weekly_and_never_restarts():
    deploy = _railway_config("pipeline")["deploy"]
    assert deploy["cronSchedule"] == "0 15 * * 0"  # Sundays 15:00 UTC = 10:00 Toronto (EST)
    assert deploy["restartPolicyType"] == "NEVER"  # a failed run waits for next week, no retry loop


def test_web_is_always_on_with_a_health_check():
    deploy = _railway_config("web")["deploy"]
    assert "cronSchedule" not in deploy
    assert deploy["healthcheckPath"] == "/_stcore/health"
    assert deploy["restartPolicyType"] == "ON_FAILURE"


def test_both_build_from_the_dockerfile():
    for role in ("web", "pipeline"):
        assert _railway_config(role)["build"] == {"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"}
