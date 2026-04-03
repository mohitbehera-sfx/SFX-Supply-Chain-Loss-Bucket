import streamlit as st
import pandas as pd

st.set_page_config(page_title="Shadowfax RTS Dashboard", layout="wide")

# Branding
st.markdown("""
<style>
.main {background-color: #f4f6f8;}
h1, h2, h3 {color: #0f8a6c;}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1,5])
with col1:
    st.image("logo.png", width=120)
with col2:
    st.markdown("<h1>RTS Loss Intelligence Dashboard</h1>", unsafe_allow_html=True)

# Uploads
st.sidebar.header("Upload Files")
freeze_file = st.sidebar.file_uploader("Freeze File")
manifest_file = st.sidebar.file_uploader("Manifest File")
awb_file = st.sidebar.file_uploader("AWB File")
mapping_file = st.sidebar.file_uploader("Mapping File")
untraceable_file = st.sidebar.file_uploader("Untraceable File")

if freeze_file and manifest_file and awb_file and mapping_file:

    AWB = "dsp_awb_number"

    # -------------------------------
    # LOAD FREEZE FILE
    # -------------------------------
    excel = pd.ExcelFile(freeze_file)

    sheet = None
    for s in excel.sheet_names:
        if "rts" in s.lower() and "raw" in s.lower():
            sheet = s
            break

    if sheet is None:
        st.error(f"No valid sheet found: {excel.sheet_names}")
        st.stop()

    df = pd.read_excel(freeze_file, sheet_name=sheet)

    # -------------------------------
    # LOAD OTHER FILES
    # -------------------------------
    manifest_df = pd.read_csv(manifest_file)
    awb_df = pd.read_csv(awb_file)
    mapping_df = pd.read_csv(mapping_file)

    if untraceable_file:
        untraceable_df = pd.read_csv(untraceable_file)
    else:
        untraceable_df = pd.DataFrame()

    # -------------------------------
    # 🔥 FIX: MAKE AWB STRING
    # -------------------------------
    df[AWB] = df[AWB].astype(str)
    manifest_df[AWB] = manifest_df[AWB].astype(str)
    awb_df[AWB] = awb_df[AWB].astype(str)

    if not untraceable_df.empty:
        untraceable_df[AWB] = untraceable_df[AWB].astype(str)

    # -------------------------------
    # MANIFEST FIX
    # -------------------------------
    manifest_df.columns = manifest_df.columns.str.strip()

    manifest_df = manifest_df.rename(columns={
        "shipments_current_location": "Current Location"
    })

    df = df.merge(manifest_df[[AWB, "Current Location"]], on=AWB, how="left")

    # -------------------------------
    # AWB MERGE
    # -------------------------------
    df = df.merge(
        awb_df[[AWB, "order_status", "attempt_number",
                "last_status_update", "received_at_hub_time"]],
        on=AWB,
        how="left"
    )

    # -------------------------------
    # MAPPING
    # -------------------------------
    df = df.merge(mapping_df, left_on="Current Location", right_on="location", how="left")

    # Dedicated hubs
    df.loc[df["Current Location"].str.endswith(("_FM", "_RTS", "_FMRTS"), na=False),
           ["AM", "SL"]] = "Dedicated"

    # -------------------------------
    # LOSS BUCKET
    # -------------------------------
    df["Updated Loss Bucket"] = ""

    df.loc[df["order_status"] == "DELIVERED", "Updated Loss Bucket"] = "Closed"

    df.loc[(df["Updated Loss Bucket"] == "") & (df["attempt_number"] > 0),
           "Updated Loss Bucket"] = "Salvaged"

    df.loc[(df["Updated Loss Bucket"] == "") &
           (df["Freeze- Loss Bucket 2"] == "Lost at RTS"),
           "Updated Loss Bucket"] = "Lost at RTS Hub"

    df.loc[(df["Updated Loss Bucket"] == "") &
           (df["Freeze- Loss Bucket 2"].notna()),
           "Updated Loss Bucket"] = df["Freeze- Loss Bucket 2"]

    df.loc[(df["Updated Loss Bucket"] == "") &
           (df["order_status"] != "IN_Manifest"),
           "Updated Loss Bucket"] = "Lost at RTS Hub"

    df.loc[(df["Updated Loss Bucket"] == "") &
           (df["order_status"] == "IN_Manifest") &
           (df["Location Check"] == True),
           "Updated Loss Bucket"] = "DC to RTS"

    df.loc[(df["Updated Loss Bucket"] == "") &
           (df["order_status"] == "IN_Manifest") &
           (df["Location Check"] == False),
           "Updated Loss Bucket"] = "Lost at RTS Hub"

    # -------------------------------
    # KPIs
    # -------------------------------
    total = df["Debit Value"].sum()
    st.metric("Total Debit", int(total))

    # -------------------------------
    # VIEW
    # -------------------------------
    st.dataframe(df.head(100))
