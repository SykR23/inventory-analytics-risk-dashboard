"""
Shared visual theme: brand palette, chart colorway, and modern CSS polish.

Call `apply_theme()` once at the top of every page (right after
st.set_page_config). It sets the Plotly colour defaults and injects the CSS
that gives the app its card-based, navy + lavender look.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

# --- brand palette ---------------------------------------------------------
NAVY = "#0D1B3D"
NAVY_2 = "#17264C"
LAVENDER = "#E6B6FA"
PERIWINKLE = "#8B9DE6"
TEAL = "#5BC0BE"
PINK = "#F2A6C2"
GOLD = "#F4C77B"
VIOLET = "#B89AF0"
TEXT = "#EAEAF5"

# Categorical colour order for multi-series charts.
COLORWAY = [LAVENDER, PERIWINKLE, TEAL, PINK, GOLD, VIOLET]

# Sequential scale (navy → lavender) for brand heatmaps.
SEQUENTIAL = [[0.0, "#16224A"], [0.5, "#6E63B6"], [1.0, LAVENDER]]

_CSS = """
<style>
/* ---------- layout ---------- */
.block-container { padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1320px; }
[data-testid="stHeader"] { background: transparent; }
.stApp {
  background:
    radial-gradient(1100px 520px at 12% -8%, #1B2B57 0%, rgba(13,27,61,0) 60%),
    radial-gradient(900px 500px at 110% 0%, #241A4D 0%, rgba(13,27,61,0) 55%),
    #0D1B3D;
}

/* ---------- headings ---------- */
.stApp h1 { font-weight: 800 !important; letter-spacing: -0.6px; color: #F6EEFF !important; }
.stApp h2 {
  color: #F3E9FF !important; font-weight: 700 !important; margin-top: 1.4rem;
  border-bottom: 2px solid rgba(230,182,250,0.22) !important; padding-bottom: 0.35rem;
}
.stApp h3 { color: #E9E1FB !important; font-weight: 650 !important; }

/* ---------- metric cards ---------- */
[data-testid="stMetric"] {
  background: linear-gradient(180deg, rgba(230,182,250,0.06), rgba(255,255,255,0.015));
  border: 1px solid rgba(230,182,250,0.18);
  border-radius: 16px; padding: 16px 18px;
  box-shadow: 0 4px 18px rgba(0,0,0,0.28);
}
[data-testid="stMetricValue"] { color: #E6B6FA; font-weight: 750; }
[data-testid="stMetricLabel"] p { color: #B7BFDC !important; font-weight: 600; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: #0A1530; border-right: 1px solid rgba(230,182,250,0.12); }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { border: none; }

/* ---------- buttons ---------- */
.stButton > button {
  border-radius: 10px; border: 1px solid rgba(230,182,250,0.40);
  background: rgba(230,182,250,0.08); color: #F3E9FF; font-weight: 600; transition: all .15s ease;
}
.stButton > button:hover { border-color: #E6B6FA; background: rgba(230,182,250,0.18); transform: translateY(-1px); }
[data-testid="stDownloadButton"] > button {
  border-radius: 10px; border: none; font-weight: 700;
  background: linear-gradient(90deg, #E6B6FA, #B89AF0); color: #15173A;
}
[data-testid="stDownloadButton"] > button:hover { filter: brightness(1.07); }

/* ---------- containers ---------- */
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid rgba(230,182,250,0.12); }
[data-testid="stExpander"] { border: 1px solid rgba(230,182,250,0.15); border-radius: 12px; background: rgba(255,255,255,0.015); }
[data-testid="stAlert"] { border-radius: 12px; }

/* ---------- misc ---------- */
a, a:visited { color: #E6B6FA; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #9AA3C4; }
hr { border-color: rgba(230,182,250,0.15); }
</style>
"""


def apply_theme() -> None:
    """Set Plotly colour defaults and inject the brand CSS. Idempotent."""
    px.defaults.color_discrete_sequence = COLORWAY
    st.markdown(_CSS, unsafe_allow_html=True)
