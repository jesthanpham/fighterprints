"""Fighterprints: pick two fighters, see their prints and how similar they are."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so "app" and "ufc" import when run by streamlit

from app.data import default_pair, has_data, list_fighters, print_payload, style_match
from app.render import show_prints
from ufc.db import connect

st.set_page_config(
    page_title="Fighterprints",
    page_icon=str(Path(__file__).parent / "static" / "favicon.png"),
    layout="centered",
)

# Hide Streamlit's own header, toolbar and footer so the page looks like a finished site.
st.markdown(
    """<style>
    header[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"],
    div[data-testid="stStatusWidget"], #MainMenu, footer { display: none !important; }
    .block-container { padding-top: 2.5rem !important; }
    </style>""",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_conn():
    conn = connect()
    conn.autocommit = True  # read-only page: no transactions left open
    return conn


conn = get_conn()

st.title("Fighterprints")

if not has_data(conn):
    st.info(
        "No fighter data yet. Run the pipeline first: open Dagster at http://localhost:3000, "
        "materialize all assets, then refresh this page."
    )
    st.stop()

fighters = list_fighters(conn)
ids = [fid for fid, _ in fighters]
labels = dict(fighters)
default_a, default_b = default_pair(conn)

left, right = st.columns(2)
a = left.selectbox("Fighter A", ids, index=ids.index(default_a), format_func=labels.get)
b = right.selectbox("Fighter B", ids, index=ids.index(default_b), format_func=labels.get)

show_prints(print_payload(conn, a), print_payload(conn, b), style_match(conn, a, b))
