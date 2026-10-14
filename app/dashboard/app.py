"""Dashboard CryptoPulse : lit les tables gold produites par dbt."""
import os

import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(page_title="CryptoPulse", layout="wide")


@st.cache_data(ttl=60)
def query(sql: str) -> pd.DataFrame:
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        dbname=os.environ.get("POSTGRES_DB", "cryptopulse"),
        user=os.environ.get("POSTGRES_USER", "cryptopulse"),
        password=os.environ["POSTGRES_PASSWORD"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=columns)
    finally:
        conn.close()


st.title("CryptoPulse")
st.caption("Prix crypto ingeres toutes les heures, transformes avec dbt, controles par Airflow.")

try:
    freshness = query("select * from marts.dim_data_freshness order by coin_id")
    indicators = query("select * from marts.fct_price_indicators order by price_date")
    quality = query(
        "select run_at, check_name, status, details from ops.quality_runs "
        "order by run_at desc limit 15"
    )
except Exception:
    st.info("Les donnees ne sont pas encore disponibles. Le premier run du DAG est en cours ou n'a pas eu lieu.")
    st.stop()

columns = st.columns(max(len(freshness), 1))
for col, (_, row) in zip(columns, freshness.iterrows(), strict=False):
    latest = indicators[indicators.coin_id == row.coin_id].tail(1)
    price = float(latest.close_usd.iloc[0]) if not latest.empty else None
    delta = latest.pct_change_1d.iloc[0] if not latest.empty else None
    col.metric(
        row.coin_id.capitalize(),
        f"{price:,.2f} USD" if price is not None else "n/a",
        None if delta is None or pd.isna(delta) else f"{float(delta):.2f} %",
    )

coin = st.selectbox("Crypto", sorted(indicators.coin_id.unique()))
selected = indicators[indicators.coin_id == coin].set_index("price_date")
st.subheader(f"Cours de cloture et moyennes mobiles : {coin}")
st.line_chart(selected[["close_usd", "ma_7d", "ma_30d"]])

left, right = st.columns(2)
with left:
    st.subheader("Volatilite sur 7 jours")
    st.line_chart(selected[["volatility_7d"]])
with right:
    st.subheader("Fraicheur des donnees")
    st.dataframe(freshness, use_container_width=True)

st.subheader("Derniers controles qualite")
st.dataframe(quality, use_container_width=True)
