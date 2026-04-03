import streamlit as st
import pandas as pd

# =========================================
# 🎨 PAGE CONFIG
# =========================================
st.set_page_config(page_title="Shadowfax RTS Dashboard", layout="wide")

# =========================================
# 🎨 BRANDING
# =========================================
st.markdown("""
<style>
.main {background-color: #f4f6f8;}
h1, h2, h3 {color: #0f8a6c;}
.kpi {
    background: white;
    padding: 18px;
    border-radius: 12px;
    border-left: 5px solid #0f8a6c;
    box-shadow: 0px 3px 8px rgba(0,0,0,0.08);
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1,5])

with col1:
    st.image("logo.png", width=120)

with col2:
    st.markdown("<h1>RTS Loss Intelligence Dashboard</h1>", unsafe_allow_html=True)

# =========================================
# 📂 FILE UPLOAD
# =========================================
st.sidebar.header("📂 Upload Files")

freeze_file = st.sidebar.file_uploader("Freeze File")
manifest_file = st.sidebar.file_uploader("Manifest File")
awb_file = st.sidebar.file_uploader("AWB to DSP File")
mapping_file = st.sidebar.file_uploader("Mapping Master")
untraceable_file = st.sidebar.file_uploader("Untraceable File")

# =========================================
# 🚀 MAIN LOGIC
# =========================================
if freeze_file and manifest_file and awb_file and mapping_file:

    # -------------------------------
    # 🔹 LOAD FREEZE FILE (SAFE)
    # -------------------------------
    excel = pd.ExcelFile(freeze_file)

    sheet = None
    for s in excel.sheet_names:
        if "rts" in s.lower() and "raw" in s.lower():
            sheet = s
            break

    if sheet is None:
        st.error(f"❌ No valid sheet found. Available sheets: {excel.sheet_names}")
        st.stop()

    df = pd.read_excel(freeze_file, sheet_name=sheet)

    # -------------------------------
    # 🔹 LOAD OTHER FILES
    # -------------------------------
    manifest_df = pd.read_csv(manifest_file)
    awb_df = pd.read_csv(awb_file)
    mapping_df = pd.read_csv(mapping_file)

    if untraceable_file:
        untraceable_df = pd.read_csv(untraceable_file)
    else:
        untraceable_df = pd.DataFrame()

    AWB = "dsp_awb_number"

    # -------------------------------
    # 🔗 MERGE DATA
    # -------------------------------
    df = df.merge(manifest_df[[AWB, "Current Location"]], on=AWB, how="left")

    df = df.merge(
        awb_df[[AWB, "order_status", "attempt_number",
                "last_status_update", "received_at_hub_time"]],
        on=AWB,
        how="left"
    )

    df = df.merge(
        mapping_df,
        left_on="Current Location",
        right_on="location",
        how="left"
    )

    # -------------------------------
    # 🧠 DEDICATED HUB LOGIC
    # -------------------------------
    df.loc[
        df["Current Location"].str.endswith(("_FM", "_RTS", "_FMRTS"), na=False),
        ["AM", "SL"]
    ] = "Dedicated"

    # -------------------------------
    # 🧠 STATE FALLBACK
    # -------------------------------
    missing = df["AM"].isna()

    df.loc[missing, "State"] = df.loc[missing, "Current Location"].str.split("_").str[0]

    df = df.merge(
        mapping_df[["State", "AM", "SL"]],
        on="State",
        how="left",
        suffixes=("", "_state")
    )

    df["AM"] = df["AM"].combine_first(df["AM_state"])
    df["SL"] = df["SL"].combine_first(df["SL_state"])

    # -------------------------------
    # 🔹 UNTRACEABLE
    # -------------------------------
    if not untraceable_df.empty:
        df["Untraceable"] = df[AWB].isin(untraceable_df[AWB])
    else:
        df["Untraceable"] = False

    # -------------------------------
    # 🔥 LOSS BUCKET LOGIC
    # -------------------------------
    df["Updated Loss Bucket"] = ""

    df.loc[df["order_status"] == "DELIVERED", "Updated Loss Bucket"] = "Closed"

    df.loc[
        (df["Updated Loss Bucket"] == "") &
        (df["attempt_number"] > 0),
        "Updated Loss Bucket"
    ] = "Salvaged"

    df.loc[
        (df["Updated Loss Bucket"] == "") &
        (df["Freeze- Loss Bucket 2"] == "Lost at RTS"),
        "Updated Loss Bucket"
    ] = "Lost at RTS Hub"

    df.loc[
        (df["Updated Loss Bucket"] == "") &
        (df["Freeze- Loss Bucket 2"].notna()),
        "Updated Loss Bucket"
    ] = df["Freeze- Loss Bucket 2"]

    df.loc[
        (df["Updated Loss Bucket"] == "") &
        (df["order_status"] != "IN_Manifest"),
        "Updated Loss Bucket"
    ] = "Lost at RTS Hub"

    df.loc[
        (df["Updated Loss Bucket"] == "") &
        (df["order_status"] == "IN_Manifest") &
        (df["Location Check"] == True),
        "Updated Loss Bucket"
    ] = "DC to RTS"

    df.loc[
        (df["Updated Loss Bucket"] == "") &
        (df["order_status"] == "IN_Manifest") &
        (df["Location Check"] == False),
        "Updated Loss Bucket"
    ] = "Lost at RTS Hub"

    # -------------------------------
    # 📊 KPIs
    # -------------------------------
    total = df["Debit Value"].sum()

    dc = df[df["Updated Loss Bucket"].isin([
        "DC - RTS Intransit",
        "DC to RTS Short",
        "RTS - PU Short"
    ])]["Debit Value"].sum()

    lost = df[df["Updated Loss Bucket"] == "Lost at RTS Hub"]["Debit Value"].sum()

    col1, col2, col3 = st.columns(3)

    col1.markdown(f'<div class="kpi">Total Debit<br><b>{int(total)}</b></div>', unsafe_allow_html=True)
    col2.markdown(f'<div class="kpi">DC to RTS<br><b>{int(dc)}</b></div>', unsafe_allow_html=True)
    col3.markdown(f'<div class="kpi">Lost at RTS<br><b>{int(lost)}</b></div>', unsafe_allow_html=True)

    # -------------------------------
    # 📅 MONTH COLUMN
    # -------------------------------
    df["Month"] = pd.to_datetime(df["last_status_update"], errors="coerce").dt.strftime("%b'%y")

    # -------------------------------
    # 🏆 AM PERFORMANCE
    # -------------------------------
    st.subheader("🏆 AM Performance")
    st.dataframe(
        df.groupby("AM")["Debit Value"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
    )

    # -------------------------------
    # 🔵 DC TO RTS VIEW
    # -------------------------------
    st.subheader("🔵 DC to RTS")

    dc_df = df[df["Updated Loss Bucket"].isin([
        "DC - RTS Intransit",
        "DC to RTS Short",
        "RTS - PU Short"
    ])]

    for am in dc_df["AM"].dropna().unique():
        with st.expander(f"📁 {am}"):
            temp = dc_df[dc_df["AM"] == am]

            pivot = temp.pivot_table(
                index="Current Location",
                columns="Month",
                values="Debit Value",
                aggfunc="sum",
                fill_value=0
            )

            pivot["Total"] = pivot.sum(axis=1)
            st.dataframe(pivot)

    # -------------------------------
    # 🟡 LOST AT RTS VIEW
    # -------------------------------
    st.subheader("🟡 Lost at RTS")

    lost_df = df[df["Updated Loss Bucket"] == "Lost at RTS Hub"]

    for am in lost_df["AM"].dropna().unique():
        with st.expander(f"📁 {am}"):
            temp = lost_df[lost_df["AM"] == am]

            pivot = temp.pivot_table(
                index="Current Location",
                columns="Month",
                values="Debit Value",
                aggfunc="sum",
                fill_value=0
            )

            pivot["Total"] = pivot.sum(axis=1)
            st.dataframe(pivot)

    # -------------------------------
    # 📥 DOWNLOAD
    # -------------------------------
    st.download_button(
        "⬇️ Download Final Data",
        df.to_csv(index=False),
        "final_output.csv"
    )
