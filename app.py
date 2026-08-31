import os
import time
import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta

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
    "EUR/USD": "EUR/USD", "GBP/USD": "GBP/USD", "USD/JPY": "USD/JPY", "AUD/USD": "AUD/USD",
    "USD/CAD": "USD/CAD", "USD/CHF": "USD/CHF", "NZD/USD": "NZD/USD", "EUR/GBP": "EUR/GBP",
    "EUR/JPY": "EUR/JPY", "GBP/JPY": "GBP/JPY", "AUD/JPY": "AUD/JPY", "EUR/AUD": "EUR/AUD",
    "GBP/AUD": "GBP/AUD", "AUD/NZD": "AUD/NZD", "EUR/CAD": "EUR/CAD", "GBP/CAD": "GBP/CAD",
    "CHF/JPY": "CHF/JPY", "NZD/JPY": "NZD/JPY", "CAD/JPY": "CAD/JPY"
}

TIMEFRAMES = {
    "1 Minute": "1min",
    "5 Minutes": "5min",
    "15 Minutes": "15min"
}

# -----------------------------------------------------------------------------
# REAL MARKET DATA ENGINE (TWELVE DATA API)
# -----------------------------------------------------------------------------
def fetch_market_data(symbol: str, interval: str = "1min", outputsize: int = 120) -> tuple[pd.DataFrame, bool]:
    api_key = "5f31be72b0364e3e8c3d1281b4b388b2"
    
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

    # Fallback structure if network fails
    dates = [datetime.now() - timedelta(minutes=i) for i in range(outputsize, 0, -1)]
    dummy_df = pd.DataFrame({
        "datetime": dates,
        "open": 1.0900, "high": 1.0910, "low": 1.0890, "close": 1.0905
    })
    return dummy_df, False

# -----------------------------------------------------------------------------
# INDICATOR CALCULATIONS
# -----------------------------------------------------------------------------
def calculate_indicators(df: pd.DataFrame):
    resistance = df["high"].iloc[-35:].max()
    support = df["low"].iloc[-35:].min()
    
    df["nea_buy"] = (df["close"] > df["open"]) & (df["low"] <= support * 1.0005) & (df["close"].shift(1) < df["open"].shift(1))
    df["nea_sell"] = (df["close"] < df["open"]) & (df["high"] >= resistance * 0.9995) & (df["close"].shift(1) > df["open"].shift(1))

    df["EMA_200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["EMA_20"] = df["close"].ewm(span=20, adjust=False).mean()
    
    current_close = df["close"].iloc[-1]
    status = "Consolidating in Range"
    if current_close >= resistance * 0.9998:
        status = "🚀 BULLISH BREAKOUT / RESISTANCE TEST"
    elif current_close <= support * 1.0002:
        status = "🔻 BEARISH BREAKDOWN / SUPPORT TEST"
        
    return resistance, support, status, df

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ Pro Controls")
selected_pair_name = st.sidebar.selectbox("Asset Pair", list(PAIRS.keys()))
selected_tf_name = st.sidebar.selectbox("Timeframe", list(TIMEFRAMES.keys()))
symbol_code = PAIRS[selected_pair_name]
interval_code = TIMEFRAMES[selected_tf_name]

auto_refresh = st.sidebar.checkbox("Live Auto-Refresh (10s)", value=True)
if auto_refresh:
    time.sleep(10)
    st.rerun()

# Fetch Real Data
raw_df, is_live = fetch_market_data(symbol_code, interval_code, 100)
resistance, support, market_status, df = calculate_indicators(raw_df)

current_price = df["close"].iloc[-1]
prev_price = df["close"].iloc[-2]
price_change = ((current_price - prev_price) / prev_price) * 100

# -----------------------------------------------------------------------------
# HEADER & METRICS
# -----------------------------------------------------------------------------
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    feed_badge = "🟢 Live Market Data Feed Active" if is_live else "⚠️ Using Fallback Feed"
    st.markdown(f"## 📊 {selected_pair_name} [{selected_tf_name}]")
    st.caption(feed_badge)
with col2:
    st.metric("Live Price", f"{current_price:.5f}", f"{price_change:+.2f}%")
with col3:
    st.metric("Structure", market_status)

st.markdown("---")

# -----------------------------------------------------------------------------
# TRADINGVIEW STYLE PLOTLY CHART
# -----------------------------------------------------------------------------
fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=df["datetime"],
    open=df["open"], high=df["high"],
    low=df["low"], close=df["close"],
    name="Price Action",
    increasing=dict(line=dict(color='#26a69a', width=1), fillcolor='#26a69a'),
    decreasing=dict(line=dict(color='#ef5350', width=1), fillcolor='#ef5350')
))

fig.add_trace(go.Scatter(x=df["datetime"], y=df["EMA_200"], mode="lines", name="EMA 200", line=dict(color="#da70d6", width=1.5)))
fig.add_trace(go.Scatter(x=df["datetime"], y=df["EMA_20"], mode="lines", name="EMA 20", line=dict(color="#ffa500", width=1)))

fig.add_hline(y=resistance, line_dash="dash", line_color="#ef5350", annotation_text=f"Resistance: {resistance:.5f}", annotation_position="top left")
fig.add_hline(y=support, line_dash="dash", line_color="#26a69a", annotation_text=f"Support: {support:.5f}", annotation_position="bottom left")

buy_df = df[df["nea_buy"]]
sell_df = df[df["nea_sell"]]

if not buy_df.empty:
    fig.add_trace(go.Scatter(
        x=buy_df["datetime"], y=buy_df["low"] * 0.9993,
        mode="markers+text", name="CALL Signal",
        marker=dict(symbol="triangle-up", size=14, color="#00ff80", line=dict(width=1, color="#ffffff")),
        text=["CALL 🟢"] * len(buy_df), textposition="bottom center"
    ))

if not sell_df.empty:
    fig.add_trace(go.Scatter(
        x=sell_df["datetime"], y=sell_df["high"] * 1.0007,
        mode="markers+text", name="PUT Signal",
        marker=dict(symbol="triangle-down", size=14, color="#ff4b4b", line=dict(width=1, color="#ffffff")),
        text=["PUT 🔴"] * len(sell_df), textposition="top center"
    ))

fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="#0b0e14",
    plot_bgcolor="#0b0e14",
    margin=dict(l=10, r=60, t=10, b=10),
    height=600,
    xaxis_rangeslider_visible=False,
    dragmode="zoom",
    yaxis=dict(side="right", showgrid=True, gridcolor="#161b22", zeroline=False, tickformat=".5f"),
    xaxis=dict(showgrid=True, gridcolor="#161b22", zeroline=False),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displayModeBar": False})
