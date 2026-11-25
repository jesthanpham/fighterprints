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
    # just the pickers, the prints and the score: no stat table, no explainer text
    assert len(at.table) == 0
    assert len(at.subheader) == 0
    assert len(at.caption) == 0


def test_page_explains_when_there_is_no_data_yet(db, monkeypatch):
    """Fresh stack, pipeline not run yet: a friendly message, not a traceback."""
    monkeypatch.setenv("UFC_DATABASE_URL", TEST_DATABASE_URL)
    at = AppTest.from_file(str(PAGE), default_timeout=30)
    at.run()
    assert not at.exception
    assert any("No fighter data yet" in i.value for i in at.info)


def test_streamlit_chrome_is_hidden_and_favicon_exists(built_marts, monkeypatch):
    monkeypatch.setenv("UFC_DATABASE_URL", TEST_DATABASE_URL)
    at = AppTest.from_file(str(PAGE), default_timeout=30)
    at.run()
    css = " ".join(m.value for m in at.markdown)
    for hidden in ('stHeader', 'stToolbar', 'footer'):
        assert hidden in css
    assert (PAGE.parent / "static" / "favicon.png").exists()
