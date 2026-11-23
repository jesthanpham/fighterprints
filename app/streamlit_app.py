"""UFC Style Fingerprints: pick two fighters, compare their generated prints and stats."""

import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so "app" and "ufc" import when run by streamlit

from app.data import default_pair, has_data, list_fighters, print_payload, stat_rows
from app.render import prints_html
from ufc.db import connect

st.set_page_config(page_title="UFC Style Fingerprints", layout="wide")


@st.cache_resource
def get_conn():
    conn = connect()
    conn.autocommit = True  # read-only page: no transactions left open
    return conn


conn = get_conn()

st.title("Style Fingerprints")
st.caption("Every print is grown from a fighter's UFC stats and fight history. Same fighter, same print.")

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

components.html(prints_html(print_payload(conn, a), print_payload(conn, b)), height=600)

st.subheader("Head to head")
mark = {"a": ("◀", ""), "b": ("", "▶"), "even": ("", "")}
st.table([
    {"Stat": r["label"], labels[a]: f"{mark[r['edge']][0]} {r['a']}".strip(), labels[b]: f"{r['b']} {mark[r['edge']][1]}".strip()}
    for r in stat_rows(conn, a, b)
])
st.caption("Data: UFCStats, via the community extract github.com/Greco1899/scrape_ufc_stats (GPL-3.0).")
