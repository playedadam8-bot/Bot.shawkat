import os
import time
import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

# -----------------------------------------------------------------------------
# CONFIGURATION & PAGE SETUP
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Trader Shawkat - Pro Binary Terminal",
    page_icon="⚡",
    layout="wide"
)

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stSelectbox, .stNumberInput { background-color: #151921; }
    .legend-box { background: #161b22; padding: 10px; border-radius: 6px; font-size: 13px; margin-bottom: 10px; border: 1px solid #30363d; }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# CONSTANTS & ASSET DEFINITIONS
# -----------------------------------------------------------------------------
PAIRS = {
    "EUR/USD": "EURUSD", "GBP/USD": "GBPUSD", "USD/JPY": "USDJPY", "AUD/USD": "AUDUSD",
    "USD/CAD": "USDCAD", "USD/CHF": "USDCHF", "NZD/USD": "NZDUSD", "EUR/GBP": "EURGBP",
    "EUR/JPY": "EURJPY", "GBP/JPY": "GBPJPY", "AUD/JPY": "AUDJPY", "EUR/AUD": "EURAUD",
    "GBP/AUD": "GBPAUD", "AUD/NZD": "AUDNZD", "EUR/CAD": "EURCAD", "GBP/CAD": "GBPCAD",
    "CHF/JPY": "CHFJPY", "NZD/JPY": "NZDJPY", "CAD/JPY": "CADJPY"
}

TIMEFRAMES = {
    "1 Minute": "1min",
    "2 Minutes": "2min",
    "5 Minutes": "5min",
    "15 Minutes": "15min"
}

# -----------------------------------------------------------------------------
# REAL-TIME DATA ENGINE (TWELVE DATA API + LIVE SIMULATION FALLBACK)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=15)
def fetch_market_data(symbol: str, interval: str = "1min", outputsize: int = 150) -> tuple[pd.DataFrame, bool]:
    api_key = os.getenv("TWELVEDATA_API_KEY", "")
    is_live_api = False
    
    if api_key:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={api_key}"
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            if "values" in data:
                df = pd.DataFrame(data["values"])
                df["datetime"] = pd.to_datetime(df["datetime"])
                for col in ["open", "high", "low", "close"]:
                    df[col] = df[col].astype(float)
                return df.sort_values("datetime").reset_index(drop=True), True
        except Exception:
            pass

    delta_mins = 1 if interval == "1min" else (2 if interval == "2min" else (5 if interval == "5min" else 15))
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=outputsize * delta_mins)
    dates = [start_time + timedelta(minutes=i * delta_mins) for i in range(outputsize)]
    
    base_price = 1.0850 if "EUR" in symbol else (1.3000 if "GBP" in symbol else 150.0 if "JPY" in symbol else 1.1000)
    np.random.seed(sum(map(ord, symbol)) + int(time.time() // 10))
    
    returns = np.random.normal(0.00002, 0.0007, outputsize)
    closes = base_price * np.cumprod(1 + returns)
    
    opens = np.empty_like(closes)
    opens[0] = closes[0]
    for i in range(1, outputsize):
        opens[i] = closes[i-1]
        
    highs = np.maximum(opens, closes) + np.abs(np.random.normal(0.0002, 0.00025, outputsize))
    lows = np.minimum(opens, closes) - np.abs(np.random.normal(0.0002, 0.00025, outputsize))
    
    df = pd.DataFrame({
        "datetime": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes
    })
    return df, False

# -----------------------------------------------------------------------------
# COMBINED INDICATOR ENGINE (SHAWKAT BOT + NEA PRO + S&R + FVG)
# -----------------------------------------------------------------------------
def calculate_all_indicators(df: pd.DataFrame):
    resistance = df["high"].iloc[-35:].max()
    support = df["low"].iloc[-35:].min()
    
    # Nea Pro Momentum Signal
    df["nea_data"] = ((df["close"].shift(3) > df["open"].shift(3)) == (df["close"].shift(1) > df["open"].shift(1)))
    df["nea_dir"] = df["close"].shift(3) < df["close"].shift(1)
    df["nea_buy"] = df["nea_data"] & df["nea_dir"]
    df["nea_sell"] = df["nea_data"] & (~df["nea_dir"])
    
    # S&R Zone Rejections
    df["resistance_touch"] = df["high"] >= (resistance * 0.9998)
    df["support_touch"] = df["low"] <= (support * 1.0002)

    df["EMA_200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["EMA_20"] = df["close"].ewm(span=20, adjust=False).mean()
    
    fvgs = []
    for i in range(2, len(df)):
        if df["low"].iloc[i] > df["high"].iloc[i-2]:
            fvgs.append({
                "type": "Bullish FVG",
                "start_time": df["datetime"].iloc[i-2],
                "bottom": df["high"].iloc[i-2],
                "top": df["low"].iloc[i]
            })
        elif df["high"].iloc[i] < df["low"].iloc[i-2]:
            fvgs.append({
                "type": "Bearish FVG",
                "start_time": df["datetime"].iloc[i-2],
                "top": df["low"].iloc[i-2],
                "bottom": df["high"].iloc[i]
            })
            
    current_close = df["close"].iloc[-1]
    status = "Consolidating in Range"
    if current_close >= resistance * 0.9998:
        status = "🚀 BULLISH BREAKOUT / RESISTANCE TEST"
    elif current_close <= support * 1.0002:
        status = "🔻 BEARISH BREAKDOWN / SUPPORT TEST"
        
    return resistance, support, fvgs, status, df

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ Pro Controls")
selected_pair_name = st.sidebar.selectbox("Asset Pair", list(PAIRS.keys()))
selected_tf_name = st.sidebar.selectbox("Timeframe", list(TIMEFRAMES.keys()))
symbol_code = PAIRS[selected_pair_name]
interval_code = TIMEFRAMES[selected_tf_name]

auto_refresh = st.sidebar.checkbox("Live Auto-Refresh (5s)", value=True)
if auto_refresh:
    time.sleep(5)
    st.rerun()

# Fetch & Compute
raw_df, is_live = fetch_market_data(symbol_code, interval_code, 120)
resistance, support, fvgs, market_status, df = calculate_all_indicators(raw_df)

current_price = df["close"].iloc[-1]
prev_price = df["close"].iloc[-2]
price_change = ((current_price - prev_price) / prev_price) * 100

# -----------------------------------------------------------------------------
# HEADER & METRICS
# -----------------------------------------------------------------------------
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    feed_badge = "🟢 Live API Feed" if is_live else "⚡ Live Simulated Feed (Add API Key for Broker Live)"
    st.markdown(f"## 📊 {selected_pair_name} [{selected_tf_name}]")
    st.caption(feed_badge)
with col2:
    st.metric("Live Price", f"{current_price:.5f}", f"{price_change:+.2f}%")
with col3:
    st.metric("Structure", market_status)

st.markdown("---")

# Legend Key Explaining the Arrows & Zones
st.markdown("""
    <div class="legend-box">
        <b>🧭 Chart Signal & Indicator Legend:</b><br>
        🟢 <span style="color:#00ff80;"><b>BUY (Nea Pro / Support Bounce)</b></span>: Green Up-Arrow pointing to Call entry.<br>
        🔴 <span style="color:#ff4b4b;"><b>SELL (Nea Pro / Resistance Rejection)</b></span>: Red Down-Arrow pointing to Put entry.<br>
        🟣 <b>EMA 200</b> (Purple) | 🟠 <b>EMA 20</b> (Orange) | 🟫 <b>FVG Boxes</b> (Fair Value Gaps)
    </div>
""", unsafe_allow_html=True)

# AI Signal Button
if st.button("⚡ GENERATE 1-MIN / EXPIRY AI SIGNAL", type="primary", use_container_width=True):
    near_resistance = current_price >= resistance * 0.9992
    near_support = current_price <= support * 1.0008
    
    if near_resistance or df["nea_sell"].iloc[-1]:
        action = "PUT (SELL) - RESISTANCE REJECTION"
        border_color = "#ef5350"
        bg_color = "rgba(255, 75, 75, 0.12)"
    elif near_support or df["nea_buy"].iloc[-1]:
        action = "CALL (BUY) - SUPPORT BOUNCE"
        border_color = "#26a69a"
        bg_color = "rgba(0, 255, 128, 0.12)"
    else:
        action = "CALL (BUY) MOMENTUM" if current_price > df["EMA_200"].iloc[-1] else "PUT (SELL) MOMENTUM"
        border_color = "#ffa500"
        bg_color = "rgba(255, 165, 0, 0.12)"
        
    st.markdown(f"""
        <div style="background-color: {bg_color}; border: 1px solid {border_color}; padding: 15px; border-radius: 8px; text-align: center;">
            <h3 style="color: {border_color}; margin: 0;">AI SIGNAL: {action}</h3>
            <p style="margin: 5px 0 0 0;"><b>Resistance:</b> {resistance:.5f} | <b>Support:</b> {support:.5f}</p>
        </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PROFESSIONAL PLOTLY CHART (PRICE AXIS ON RIGHT, STABLE ZOOM, CLEAR LABELS)
# -----------------------------------------------------------------------------
fig = go.Figure()

# Clean Professional Candlesticks
fig.add_trace(go.Candlestick(
    x=df["datetime"],
    open=df["open"], high=df["high"],
    low=df["low"], close=df["close"],
    name="Price Action",
    increasing=dict(line=dict(color='#26a69a', width=1), fillcolor='#26a69a'),
    decreasing=dict(line=dict(color='#ef5350', width=1), fillcolor='#ef5350')
))

# EMA Lines
fig.add_trace(go.Scatter(x=df["datetime"], y=df["EMA_200"], mode="lines", name="EMA 200", line=dict(color="#da70d6", width=1.5)))
fig.add_trace(go.Scatter(x=df["datetime"], y=df["EMA_20"], mode="lines", name="EMA 20", line=dict(color="#ffa500", width=1)))

# Support & Resistance Lines
fig.add_hline(y=resistance, line_dash="dash", line_color="#ef5350", annotation_text="Resistance Zone", annotation_position="top left")
fig.add_hline(y=support, line_dash="dash", line_color="#26a69a", annotation_text="Support Zone", annotation_position="bottom left")

# Shaded Fair Value Gaps (FVG)
for fvg in fvgs[-4:]:
    fvg_color = "rgba(38, 166, 154, 0.2)" if "Bullish" in fvg["type"] else "rgba(239, 83, 80, 0.2)"
    fig.add_shape(
        type="rect",
        x0=fvg["start_time"], x1=df["datetime"].iloc[-1],
        y0=fvg["bottom"], y1=fvg["top"],
        fillcolor=fvg_color, opacity=0.4, line=dict(width=0)
    )

# Distinct Signals with Clear Descriptions
buy_df = df[df["nea_buy"] | df["support_touch"]]
sell_df = df[df["nea_sell"] | df["resistance_touch"]]

if not buy_df.empty:
    fig.add_trace(go.Scatter(
        x=buy_df["datetime"], y=buy_df["low"] * 0.9993,
        mode="markers+text", name="BUY Signal (Call)",
        marker=dict(symbol="triangle-up", size=15, color="#00ff80", line=dict(width=1, color="#ffffff")),
        text=["CALL 🟢"] * len(buy_df), textposition="bottom center", textfont=dict(color="#00ff80", size=10, family="Arial Black")
    ))

if not sell_df.empty:
    fig.add_trace(go.Scatter(
        x=sell_df["datetime"], y=sell_df["high"] * 1.0007,
        mode="markers+text", name="SELL Signal (Put)",
        marker=dict(symbol="triangle-down", size=15, color="#ff4b4b", line=dict(width=1, color="#ffffff")),
        text=["PUT 🔴"] * len(sell_df), textposition="top center", textfont=dict(color="#ff4b4b", size=10, family="Arial Black")
    ))

# Chart Layout configured with Right-Side Y-Axis and Natural Zoom/Scroll
fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="#0b0e14",
    plot_bgcolor="#0b0e14",
    margin=dict(l=10, r=50, t=10, b=10), # Extra right margin for price scale
    height=600,
    xaxis_rangeslider_visible=False,
    dragmode="zoom", # Standard natural chart zoom & selection
    yaxis=dict(side="right", showgrid=True, gridcolor="#161b22", zeroline=False), # Price axis explicitly on RIGHT
    xaxis=dict(showgrid=True, gridcolor="#161b22", zeroline=False),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
