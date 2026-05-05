import streamlit as st

# ── THEMES ──────────────────────────────────────────────────────────
# Switch between "apple", "inner_peace", "hyperrealism"
THEME = "apple"


def apply_global_styles():
    if THEME == "apple":
        _apple()
    elif THEME == "hyperrealism":
        _hyperrealism()
    else:
        _inner_peace()


def _apple():
    st.markdown("""
    <style>
    /* ── FONT: SF Pro system stack ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    html, body, [class*="css"] {
        font-family: -apple-system, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Inter, Arial, sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    /* ── HIDE STREAMLIT CHROME ── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }

    /* ── PAGE: pure white ── */
    .stApp { background: #ffffff; }
    .main .block-container {
        background: #ffffff;
        padding-top: 2rem;
        padding-bottom: 4rem;
        max-width: 1100px;
    }

    /* ── SIDEBAR: deep black with frosted sections ── */
    [data-testid="stSidebar"] {
        background: #000000 !important;
        border-right: none;
        box-shadow: 1px 0 0 rgba(255,255,255,0.06);
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 0;
    }
    [data-testid="stSidebar"] * { color: rgba(255,255,255,0.82) !important; }

    /* sidebar top logo/brand band */
    [data-testid="stSidebarHeader"] {
        background: rgba(255,255,255,0.03) !important;
        border-bottom: 1px solid rgba(255,255,255,0.07) !important;
        padding: 18px 20px 18px !important;
        backdrop-filter: blur(20px);
    }

    /* nav links */
    [data-testid="stSidebar"] a {
        color: rgba(255,255,255,0.65) !important;
        font-size: 13px;
        font-weight: 400;
        padding: 8px 14px;
        border-radius: 8px;
        transition: background 0.15s, color 0.15s;
        display: block;
        letter-spacing: -0.01em;
    }
    [data-testid="stSidebar"] a:hover {
        background: rgba(255,255,255,0.09) !important;
        color: #ffffff !important;
    }

    /* sidebar section labels */
    [data-testid="stSidebar"] p {
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.07em !important;
        text-transform: uppercase !important;
        color: rgba(255,255,255,0.3) !important;
        padding: 18px 14px 6px !important;
    }

    /* sidebar divider lines */
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.07) !important;
        margin: 8px 14px !important;
    }

    /* ── BUTTONS ── */
    /* Primary: solid blue pill */
    .stButton > button {
        background: #0071e3 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 980px;
        padding: 10px 22px;
        font-size: 15px;
        font-weight: 400;
        letter-spacing: -0.01em;
        transition: background 0.2s, opacity 0.2s;
        box-shadow: none;
        font-family: inherit !important;
    }
    .stButton > button:hover {
        background: #0077ed !important;
        box-shadow: none !important;
        transform: none;
    }
    .stButton > button:active {
        background: #006edb !important;
        opacity: 0.9;
    }

    /* Ghost/secondary button — outlined */
    .stButton > button[kind="secondary"] {
        background: transparent !important;
        color: #0071e3 !important;
        border: 1px solid rgba(0,113,227,0.35) !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: rgba(0,113,227,0.06) !important;
        border-color: #0071e3 !important;
    }

    /* ── METRIC CARDS: bento style ── */
    div[data-testid="stMetric"] {
        background: #f5f5f7;
        border-radius: 20px;
        padding: 26px 28px;
        border: 1px solid rgba(0,0,0,0.04);
        box-shadow: none;
        transition: transform 0.25s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.25s ease;
        cursor: default;
        position: relative;
        overflow: hidden;
    }
    div[data-testid="stMetric"]::before {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: 20px;
        background: linear-gradient(145deg, rgba(255,255,255,0.6) 0%, transparent 60%);
        pointer-events: none;
    }
    div[data-testid="stMetric"]:hover {
        transform: scale(1.015);
        box-shadow: 0 8px 28px rgba(0,0,0,0.07);
    }
    div[data-testid="stMetric"] label {
        color: #6e6e73 !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.07em !important;
        text-transform: uppercase !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #1d1d1f !important;
        font-size: 30px !important;
        font-weight: 700 !important;
        letter-spacing: -0.03em !important;
        line-height: 1.1 !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        font-size: 13px !important;
        font-weight: 500 !important;
        letter-spacing: -0.01em !important;
    }

    /* ── HEADERS ── */
    h1 {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.028em !important;
        color: #1d1d1f !important;
        line-height: 1.05 !important;
        margin-bottom: 0.2em !important;
    }
    h2 {
        font-size: 1.9rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.022em !important;
        color: #1d1d1f !important;
        line-height: 1.1 !important;
    }
    h3 {
        font-size: 1.15rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.015em !important;
        color: #1d1d1f !important;
    }
    h4, h5 {
        font-size: 0.95rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        color: #0071e3 !important;
    }

    /* ── BODY TEXT ── */
    p, .stMarkdown p {
        color: #1d1d1f;
        font-size: 15px;
        line-height: 1.6;
        font-weight: 400;
    }
    .stMarkdown p + p { margin-top: 0.5em; }

    /* section eyebrow label — use ##### for this */
    h5 {
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.09em !important;
        text-transform: uppercase !important;
        color: #0071e3 !important;
        margin-bottom: 0.3em !important;
    }

    /* ── INPUTS ── */
    input, textarea {
        border-radius: 10px !important;
        border: 1px solid #d2d2d7 !important;
        background: #ffffff !important;
        font-family: inherit !important;
        font-size: 15px !important;
        color: #1d1d1f !important;
        transition: border-color 0.15s, box-shadow 0.15s;
    }
    input:focus, textarea:focus {
        border-color: #0071e3 !important;
        box-shadow: 0 0 0 3px rgba(0,113,227,0.16) !important;
        outline: none !important;
    }
    /* selectbox / dropdown */
    [data-baseweb="select"] > div {
        border-radius: 10px !important;
        border: 1px solid #d2d2d7 !important;
        background: #ffffff !important;
        font-family: inherit !important;
    }
    [data-baseweb="select"] > div:focus-within {
        border-color: #0071e3 !important;
        box-shadow: 0 0 0 3px rgba(0,113,227,0.16) !important;
    }

    /* ── TABLE / DATAFRAME ── */
    [data-testid="stDataFrame"] {
        border-radius: 16px !important;
        overflow: hidden;
        border: 1px solid rgba(0,0,0,0.08) !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.04);
    }
    [data-testid="stDataFrame"] thead tr th {
        background: #f5f5f7 !important;
        color: #6e6e73 !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        border-bottom: 1px solid #d2d2d7 !important;
    }
    [data-testid="stDataFrame"] tbody tr:hover td {
        background: #f0f0f2 !important;
    }

    /* ── TABS: underline style with blue indicator ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background: transparent;
        border-radius: 0;
        padding: 0;
        box-shadow: none;
        border-bottom: 1px solid #d2d2d7 !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 0;
        font-size: 14px;
        font-weight: 400;
        color: #6e6e73 !important;
        padding: 10px 20px;
        border: none !important;
        letter-spacing: -0.01em;
        transition: color 0.15s;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #1d1d1f !important;
        background: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        background: transparent !important;
        color: #0071e3 !important;
        font-weight: 500 !important;
        border-bottom: 2px solid #0071e3 !important;
    }

    /* ── EXPANDER ── */
    [data-testid="stExpander"] {
        border: 1px solid rgba(0,0,0,0.08) !important;
        border-radius: 14px !important;
        overflow: hidden;
        box-shadow: none;
    }
    [data-testid="stExpander"] summary {
        font-weight: 500;
        font-size: 15px;
        letter-spacing: -0.01em;
        padding: 14px 18px;
        background: #fafafa;
    }
    [data-testid="stExpander"] summary:hover { background: #f5f5f7; }

    /* ── ALERTS / BANNERS ── */
    [data-testid="stAlert"] {
        border-radius: 12px !important;
        border: none !important;
        font-size: 14px !important;
    }
    /* success: Apple green tint */
    [data-testid="stAlert"][data-baseweb="notification"][kind="positive"] {
        background: rgba(48,209,88,0.1) !important;
        color: #248a3d !important;
    }
    /* error: Apple red tint */
    [data-testid="stAlert"][data-baseweb="notification"][kind="negative"] {
        background: rgba(255,59,48,0.08) !important;
        color: #c0392b !important;
    }
    /* info: Apple blue tint */
    [data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
        background: rgba(0,113,227,0.08) !important;
        color: #0058b3 !important;
    }
    /* warning: Apple yellow tint */
    [data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
        background: rgba(255,159,10,0.10) !important;
        color: #b36200 !important;
    }

    /* ── DIVIDERS ── */
    hr {
        border: none !important;
        border-top: 1px solid #d2d2d7 !important;
        margin: 2rem 0 !important;
    }

    /* ── SPINNER / PROGRESS ── */
    [data-testid="stSpinner"] { color: #0071e3 !important; }

    /* ── RADIO / CHECKBOX ── */
    [data-baseweb="radio"] [data-testid="stMarkdownContainer"] p,
    [data-baseweb="checkbox"] [data-testid="stMarkdownContainer"] p {
        font-size: 14px !important;
        color: #1d1d1f !important;
    }

    /* ── DARK BAND helper class — wrap with st.container + custom html ── */
    .apple-dark-band {
        background: #000000;
        border-radius: 22px;
        padding: 40px 36px;
        margin: 24px 0;
        color: white;
    }
    .apple-dark-band h1,
    .apple-dark-band h2,
    .apple-dark-band h3 { color: white !important; }
    .apple-dark-band p { color: rgba(255,255,255,0.65) !important; }

    /* ── GRADIENT TEXT helper ── */
    .gradient-text {
        background: linear-gradient(135deg, #2af598 0%, #009efd 50%, #a855f7 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    /* ── CAPTION / SUBTITLE ── */
    [data-testid="stCaptionContainer"] p,
    .stCaption p {
        color: #6e6e73 !important;
        font-size: 17px !important;
        font-weight: 300 !important;
        letter-spacing: -0.01em !important;
        line-height: 1.5 !important;
    }

    /* ── SCROLLBAR ── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #d2d2d7; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #b0b0b6; }
    </style>
    """, unsafe_allow_html=True)


def _inner_peace():
    st.markdown("""
    <style>
    /* ── FONT: Segoe UI ── */
    html, body, [class*="css"] {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        -webkit-font-smoothing: antialiased;
    }

    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }

    /* ── PAGE: warm gray + geometric pattern ── */
    .stApp {
        background-color: #F7F7F7;
        background-image:
            repeating-linear-gradient(45deg, transparent, transparent 35px, rgba(45,90,135,0.03) 35px, rgba(45,90,135,0.03) 70px),
            repeating-linear-gradient(-45deg, transparent, transparent 35px, rgba(74,124,138,0.03) 35px, rgba(74,124,138,0.03) 70px);
    }

    /* ── SIDEBAR: deep blue gradient ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #2D5A87 0%, #1e3f5e 100%) !important;
        border-right: none;
    }
    [data-testid="stSidebar"] * { color: rgba(255,255,255,0.9) !important; }
    [data-testid="stSidebar"] a {
        color: rgba(255,255,255,0.75) !important;
        font-weight: 500;
        padding: 6px 12px;
        border-radius: 8px;
        transition: all 0.2s ease;
        display: block;
    }
    [data-testid="stSidebar"] a:hover {
        background: rgba(255,255,255,0.12) !important;
        color: white !important;
    }

    /* ── BUTTONS: blue-teal gradient ── */
    .stButton > button {
        background: linear-gradient(135deg, #2D5A87 0%, #4A7C8A 100%) !important;
        color: #ffffff !important;
        border: none;
        border-radius: 50px;
        padding: 10px 28px;
        font-size: 15px;
        font-weight: 600;
        letter-spacing: 0.3px;
        transition: all 0.3s ease;
        box-shadow: 0 5px 15px rgba(45,90,135,0.3);
    }
    .stButton > button:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 28px rgba(45,90,135,0.4) !important;
    }

    /* ── CARDS: white floating with accent border ── */
    div[data-testid="stMetric"] {
        background: white;
        border-radius: 20px;
        padding: 24px 28px;
        border: none;
        border-left: 4px solid #4A7C8A;
        box-shadow: 0 8px 25px rgba(45,90,135,0.10);
        transition: all 0.4s cubic-bezier(0.175,0.885,0.32,1.275);
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-6px);
        box-shadow: 0 16px 40px rgba(45,90,135,0.16);
    }
    div[data-testid="stMetric"] label {
        color: #6e6e73 !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #2D5A87 !important;
        font-size: 28px !important;
        font-weight: 700 !important;
    }

    /* ── HEADERS ── */
    h1 { font-size: 2.5rem !important; font-weight: 700 !important; color: #2A2A3E !important; }
    h2 { font-size: 1.8rem !important; font-weight: 700 !important; color: #2D5A87 !important; }
    h3 { font-size: 1.2rem !important; font-weight: 600 !important; color: #4A7C8A !important; }

    /* ── INPUTS ── */
    input, textarea, select {
        border-radius: 12px !important;
        border: 2px solid #dde3eb !important;
        background: white !important;
        font-family: inherit !important;
    }
    input:focus, textarea:focus {
        border-color: #2D5A87 !important;
        box-shadow: 0 0 0 4px rgba(45,90,135,0.12) !important;
    }

    /* ── TABLE ── */
    [data-testid="stDataFrame"] {
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 5px 20px rgba(45,90,135,0.08);
        border: none !important;
    }

    /* ── TABS: pill style ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: white;
        border-radius: 14px;
        padding: 6px;
        box-shadow: 0 3px 12px rgba(45,90,135,0.08);
        border-bottom: none !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        font-size: 14px;
        font-weight: 500;
        color: #6e6e73 !important;
        padding: 8px 18px;
        border: none !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #2D5A87 0%, #4A7C8A 100%) !important;
        color: white !important;
    }

    /* ── ALERTS ── */
    [data-testid="stAlert"] { border-radius: 14px; border: none; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }

    /* ── SCROLLBAR ── */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #F7F7F7; }
    ::-webkit-scrollbar-thumb { background: #4A7C8A; border-radius: 3px; }
    </style>
    """, unsafe_allow_html=True)


def _hyperrealism():
    st.markdown("""
    <style>
    /* ── FONT ── */
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700;800&display=swap');
    html, body, [class*="css"] {
        font-family: 'DM Sans', -apple-system, sans-serif;
        -webkit-font-smoothing: antialiased;
    }

    /* ── HIDE STREAMLIT CHROME ── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }

    /* ── PAGE: deep dark blue ── */
    .stApp {
        background: #1a1a2e !important;
        color: #ffffff;
    }
    .main .block-container {
        background: transparent !important;
        padding-top: 2rem;
        padding-bottom: 4rem;
        max-width: 1100px;
    }

    /* ── AMBIENT GLOW ── */
    .stApp::before {
        content: '';
        position: fixed;
        width: 700px;
        height: 700px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(212,175,55,0.12) 0%, transparent 70%);
        top: 10%;
        left: 25%;
        pointer-events: none;
        z-index: 0;
        filter: blur(60px);
    }

    /* ── SIDEBAR: dark blue-black with gold accents ── */
    [data-testid="stSidebar"] {
        background: rgba(14, 14, 28, 0.97) !important;
        border-right: 1px solid rgba(212,175,55,0.12) !important;
    }
    [data-testid="stSidebarHeader"] {
        background: rgba(212,175,55,0.06) !important;
        border-bottom: 1px solid rgba(212,175,55,0.15) !important;
        padding: 18px 20px !important;
    }
    [data-testid="stSidebar"] * { color: rgba(255,255,255,0.75) !important; }
    [data-testid="stSidebar"] a {
        color: rgba(255,255,255,0.6) !important;
        font-size: 13px;
        font-weight: 500;
        padding: 8px 14px;
        border-radius: 8px;
        transition: background 0.2s, color 0.2s;
        display: block;
    }
    [data-testid="stSidebar"] a:hover {
        background: rgba(212,175,55,0.1) !important;
        color: #d4af37 !important;
    }
    [data-testid="stSidebar"] p {
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.09em !important;
        text-transform: uppercase !important;
        color: rgba(212,175,55,0.5) !important;
        padding: 16px 14px 4px !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: rgba(212,175,55,0.1) !important;
        margin: 8px 14px !important;
    }

    /* ── BUTTONS: gold 3D press ── */
    .stButton > button {
        background: linear-gradient(135deg, #f0d78c 0%, #d4af37 25%, #aa8c2c 50%, #d4af37 75%, #f0d78c 100%) !important;
        color: #1a1a2e !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 11px 24px;
        font-size: 15px;
        font-weight: 600;
        font-family: inherit !important;
        box-shadow: 0 4px 0 #7a6420, 0 8px 20px rgba(212,175,55,0.3) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 0 #7a6420, 0 12px 30px rgba(212,175,55,0.4) !important;
    }
    .stButton > button:active {
        transform: translateY(2px) !important;
        box-shadow: 0 2px 0 #7a6420, 0 4px 10px rgba(212,175,55,0.3) !important;
    }

    /* ── METRIC CARDS: dark floating with gold hover border ── */
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #252540, rgba(37,37,64,0.7));
        border-radius: 20px;
        padding: 26px 28px;
        border: 1px solid rgba(255,255,255,0.06);
        box-shadow: 0 10px 40px rgba(0,0,0,0.4);
        position: relative;
        overflow: hidden;
        transition: transform 0.35s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.35s ease;
        cursor: default;
    }
    div[data-testid="stMetric"]::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(135deg, #f0d78c 0%, #d4af37 50%, #f0d78c 100%);
        transform: scaleX(0);
        transform-origin: left;
        transition: transform 0.35s ease;
    }
    div[data-testid="stMetric"]::after {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: 20px;
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, transparent 60%);
        pointer-events: none;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-6px) rotateX(3deg);
        box-shadow: 0 20px 60px rgba(0,0,0,0.5), 0 0 40px rgba(212,175,55,0.08);
    }
    div[data-testid="stMetric"]:hover::before { transform: scaleX(1); }
    div[data-testid="stMetric"] label {
        color: rgba(255,255,255,0.45) !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.09em !important;
        text-transform: uppercase !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 30px !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        background: linear-gradient(135deg, #f0d78c 0%, #d4af37 50%, #f0d78c 100%);
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        background-clip: text !important;
    }

    /* ── HEADERS ── */
    h1 {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.025em !important;
        color: #ffffff !important;
        line-height: 1.05 !important;
    }
    h2 {
        font-size: 1.9rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        color: #ffffff !important;
    }
    h3 {
        font-size: 1.15rem !important;
        font-weight: 600 !important;
        color: #ffffff !important;
    }
    h4, h5 {
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.09em !important;
        text-transform: uppercase !important;
        background: linear-gradient(135deg, #f0d78c, #d4af37) !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        background-clip: text !important;
    }

    /* ── BODY TEXT ── */
    p, .stMarkdown p {
        color: rgba(255,255,255,0.72);
        font-size: 15px;
        line-height: 1.65;
    }

    /* ── CAPTION ── */
    [data-testid="stCaptionContainer"] p,
    .stCaption p {
        color: rgba(255,255,255,0.45) !important;
        font-size: 16px !important;
        font-weight: 300 !important;
        letter-spacing: -0.01em !important;
    }

    /* ── INPUTS ── */
    input, textarea {
        border-radius: 10px !important;
        border: 1px solid rgba(212,175,55,0.2) !important;
        background: rgba(37,37,64,0.8) !important;
        color: #ffffff !important;
        font-family: inherit !important;
        transition: border-color 0.15s, box-shadow 0.15s;
    }
    input:focus, textarea:focus {
        border-color: #d4af37 !important;
        box-shadow: 0 0 0 3px rgba(212,175,55,0.18) !important;
    }
    [data-baseweb="select"] > div {
        border-radius: 10px !important;
        border: 1px solid rgba(212,175,55,0.2) !important;
        background: rgba(37,37,64,0.8) !important;
        color: white !important;
    }

    /* ── TABLE ── */
    [data-testid="stDataFrame"] {
        border-radius: 16px !important;
        overflow: hidden;
        border: 1px solid rgba(212,175,55,0.12) !important;
        box-shadow: 0 10px 40px rgba(0,0,0,0.4);
    }
    [data-testid="stDataFrame"] thead tr th {
        background: rgba(37,37,64,0.9) !important;
        color: rgba(212,175,55,0.8) !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        border-bottom: 1px solid rgba(212,175,55,0.15) !important;
    }
    [data-testid="stDataFrame"] tbody tr:hover td {
        background: rgba(212,175,55,0.05) !important;
    }

    /* ── TABS ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: rgba(37,37,64,0.6);
        border-radius: 14px;
        padding: 6px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        border-bottom: none !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        font-size: 14px;
        font-weight: 500;
        color: rgba(255,255,255,0.5) !important;
        padding: 8px 18px;
        border: none !important;
        transition: color 0.2s;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: rgba(255,255,255,0.85) !important;
        background: rgba(255,255,255,0.05) !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #f0d78c 0%, #d4af37 50%, #aa8c2c 100%) !important;
        color: #1a1a2e !important;
        font-weight: 600 !important;
    }

    /* ── EXPANDER ── */
    [data-testid="stExpander"] {
        border: 1px solid rgba(212,175,55,0.15) !important;
        border-radius: 14px !important;
        background: rgba(37,37,64,0.5);
    }
    [data-testid="stExpander"] summary {
        font-weight: 500;
        font-size: 15px;
        color: rgba(255,255,255,0.85);
        padding: 14px 18px;
        background: transparent;
    }

    /* ── ALERTS ── */
    [data-testid="stAlert"] {
        border-radius: 12px !important;
        border: 1px solid rgba(212,175,55,0.15) !important;
        background: rgba(37,37,64,0.8) !important;
    }

    /* ── DIVIDERS ── */
    hr {
        border: none !important;
        border-top: 1px solid rgba(212,175,55,0.15) !important;
        margin: 2rem 0 !important;
    }

    /* ── METALLIC FRAME helper ── */
    .metallic-frame {
        background: linear-gradient(135deg, #fff 0%, #d0d0d0 20%, #a0a0a0 40%, #d0d0d0 60%, #fff 80%, #d0d0d0 100%);
        padding: 3px;
        border-radius: 20px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.5);
    }

    /* ── SCROLLBAR ── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: rgba(255,255,255,0.03); }
    ::-webkit-scrollbar-thumb { background: rgba(212,175,55,0.3); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(212,175,55,0.5); }
    </style>
    """, unsafe_allow_html=True)
