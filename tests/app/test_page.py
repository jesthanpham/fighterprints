from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.conftest import TEST_DATABASE_URL

PAGE = Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py"


def test_page_renders(built_marts, monkeypatch):
    monkeypatch.setenv("UFC_DATABASE_URL", TEST_DATABASE_URL)
    at = AppTest.from_file(str(PAGE), default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.selectbox) == 2
