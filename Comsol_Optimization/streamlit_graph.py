import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
matplotlib.use("Agg")
import os
import io

st.set_page_config(page_title="Optimization Log Viewer", layout="wide")

st.title("COMSOL Optimization Log — Interactive Viewer")

# Path input / uploader
default_path = os.path.join(os.path.dirname(__file__), "optimization_log.csv")
path = st.text_input("Path to optimization_log.csv", value=default_path)

uploaded = st.file_uploader("Or upload a CSV file (overrides path)", type=["csv"]) 

@st.cache_data
def load_data_from_path(p):
    try:
        df = pd.read_csv(p)
        return df
    except Exception as e:
        st.error(f"Failed to read '{p}': {e}")
        return None

@st.cache_data
def load_data_from_buffer(buf):
    try:
        buf.seek(0)
        df = pd.read_csv(buf)
        return df
    except Exception as e:
        st.error(f"Failed to read uploaded CSV: {e}")
        return None

if uploaded is not None:
    df = load_data_from_buffer(uploaded)
    try:
        save_upload = st.checkbox("Save uploaded file to default path", value=True)
        if save_upload:
            # write uploaded bytes to the default path so other tools/scripts can use it
            try:
                with open(default_path, "wb") as out_f:
                    out_f.write(uploaded.getvalue())
                st.success(f"Uploaded file saved to: {default_path}")
            except Exception as e:
                st.error(f"Failed to save uploaded file to {default_path}: {e}")
    except Exception:
        # checkbox availability may vary in some Streamlit versions; ignore gracefully
        pass
else:
    df = load_data_from_path(path)

if df is None:
    st.stop()

# Ensure iteration/index column
if "iter" not in df.columns and "iteration" not in df.columns:
    df = df.reset_index(drop=True)
    df.insert(0, "iter", df.index + 1)
else:
    if "iter" not in df.columns and "iteration" in df.columns:
        df = df.rename(columns={"iteration": "iter"})

st.sidebar.header("Plot settings")

# Identify numeric columns
numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
if not numeric_cols:
    st.error("No numeric columns found in the CSV to plot.")
    st.stop()

y_cols = st.sidebar.multiselect("Y columns (lines)", options=numeric_cols, default=[c for c in ["score", "depth_eV", "P_est_mW"] if c in numeric_cols])
x_col = st.sidebar.selectbox("X axis", options=["iter"] + numeric_cols, index=0)
rolling = st.sidebar.slider("Rolling window (smoothing)", min_value=1, max_value=51, value=1, step=2)
show_points = st.sidebar.checkbox("Show markers/points", value=True)

st.sidebar.markdown("---")
scatter_x = st.sidebar.selectbox("Scatter: X", options=numeric_cols, index=0)
scatter_y = st.sidebar.selectbox("Scatter: Y", options=numeric_cols, index=min(1, max(0, len(numeric_cols)-1)))
color_col = st.sidebar.selectbox("Color (optional)", options=[None] + numeric_cols, index=0)

# Main layout
col1, col2 = st.columns([2, 1])

with col1:
    st.header("Line plot")
    if not y_cols:
        st.info("Select one or more Y columns from the sidebar to display their line plots.")
    else:
        plot_df = df[[x_col] + y_cols].copy()
        if rolling > 1:
            plot_df = plot_df.set_index(x_col).rolling(window=rolling, min_periods=1).mean().reset_index()
        fig, ax = plt.subplots(figsize=(10, 4))
        for col in y_cols:
            if show_points:
                ax.plot(plot_df[x_col], plot_df[col], marker='o', label=col)
            else:
                ax.plot(plot_df[x_col], plot_df[col], label=col)
        ax.set_xlabel(x_col)
        ax.set_ylabel("Value")
        ax.set_title("Metrics over Iterations")
        ax.grid(True)
        ax.legend()
        st.pyplot(fig)

    st.markdown("---")
    st.header("Scatter plot")
    fig2, ax2 = plt.subplots(figsize=(6, 4))
    if color_col and color_col in df.columns:
        sc = ax2.scatter(df[scatter_x], df[scatter_y], c=df[color_col], cmap='viridis', alpha=0.8)
        try:
            fig2.colorbar(sc, ax=ax2)
        except Exception:
            pass
    else:
        ax2.scatter(df[scatter_x], df[scatter_y], alpha=0.8)
    ax2.set_xlabel(scatter_x)
    ax2.set_ylabel(scatter_y)
    ax2.set_title(f"{scatter_y} vs {scatter_x}")
    ax2.grid(True)
    st.pyplot(fig2)

with col2:
    st.header("Data preview & controls")
    st.write(df.describe(include='all'))
    st.markdown("**Preview**")
    st.dataframe(df.head(200))

    st.markdown("---")
    st.header("Correlation matrix")
    corr = df[numeric_cols].corr()
    fig3, ax3 = plt.subplots(figsize=(6, 6))
    im = ax3.imshow(corr.values, cmap='coolwarm', vmin=-1, vmax=1)
    ax3.set_xticks(range(len(numeric_cols)))
    ax3.set_yticks(range(len(numeric_cols)))
    ax3.set_xticklabels(numeric_cols, rotation=90)
    ax3.set_yticklabels(numeric_cols)
    for (i, j), val in np.ndenumerate(corr.values):
        ax3.text(j, i, f"{val:.2f}", ha='center', va='center', color='black', fontsize=8)
    fig3.colorbar(im, ax=ax3)
    st.pyplot(fig3)

    st.markdown("---")
    st.header("Export / Download")
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button("Download CSV (filtered)", data=buf.getvalue(), file_name="optimization_log_export.csv", mime="text/csv")

st.markdown("---")
st.markdown("Tips: If columns look missing, verify `optimization_log.csv` contains those headers (e.g., `depth_eV`, `offset_mm`, `P_est_mW`, `score`).")

# Footer: quick summary stats
st.write("### Quick best result")
if "score" in df.columns:
    best_idx = df["score"].idxmax()
    st.write(df.loc[best_idx])
else:
    st.write("No `score` column found.")
