"""Reusable Plotly Chart Components for Streamlit Dashboard."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from streamlit_app.config import (
    COLOR_FRAUDULENT,
    COLOR_LEGITIMATE,
    COLOR_RISK_HIGH,
    COLOR_RISK_LOW,
    COLOR_RISK_MEDIUM,
)


def plot_shap_contributions(top_reasons: list[dict], title: str = "Key Feature Influences (SHAP)") -> go.Figure:
    """Create a horizontal bar chart displaying SHAP feature attributions."""
    if not top_reasons:
        fig = go.Figure()
        fig.update_layout(title="No SHAP contribution data available")
        return fig

    # Reverse so top feature is at the top of the chart
    reasons = list(reversed(top_reasons))
    features = [r.get("feature", "Unknown") for r in reasons]
    contribs = [float(r.get("contribution", 0.0)) for r in reasons]
    directions = [r.get("direction", "UNKNOWN") for r in reasons]

    colors = [
        COLOR_RISK_HIGH if d == "INCREASES_RISK" or c > 0 else COLOR_RISK_LOW
        for c, d in zip(contribs, directions)
    ]

    fig = go.Figure(
        go.Bar(
            x=contribs,
            y=features,
            orientation="h",
            marker=dict(color=colors, line=dict(color="#333333", width=1)),
            text=[f"{c:+.4f}" for c in contribs],
            textposition="auto",
        )
    )

    fig.update_layout(
        title=dict(text=title, font=dict(size=15, family="Arial", color="#1f1f1f")),
        xaxis=dict(
            title="SHAP Impact on Fraud Probability",
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor="#666666",
            gridcolor="#eeeeee",
        ),
        yaxis=dict(title="", tickfont=dict(size=12)),
        margin=dict(l=10, r=20, t=40, b=40),
        height=320,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    return fig


def plot_risk_distribution(counts: dict[str, int]) -> go.Figure:
    """Create donut chart for Risk Status distribution."""
    labels = ["LOW", "MEDIUM", "HIGH"]
    values = [counts.get("LOW", 0), counts.get("MEDIUM", 0), counts.get("HIGH", 0)]
    colors = [COLOR_RISK_LOW, COLOR_RISK_MEDIUM, COLOR_RISK_HIGH]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                textinfo="label+percent",
            )
        ]
    )
    fig.update_layout(
        title=dict(text="Risk Status Breakdown", font=dict(size=14)),
        margin=dict(l=10, r=10, t=35, b=10),
        height=260,
        showlegend=True,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    return fig


def plot_transaction_volume(df: pd.DataFrame, time_col: str = "timestamp") -> go.Figure:
    """Create volume area/bar chart over time."""
    if df.empty or time_col not in df.columns:
        fig = go.Figure()
        fig.update_layout(title="No transaction timeline data available")
        return fig

    df_plot = df.copy()
    df_plot[time_col] = pd.to_datetime(df_plot[time_col])
    # Group by date
    df_plot["date"] = df_plot[time_col].dt.date
    daily = df_plot.groupby("date").size().reset_index(name="count")

    fig = px.bar(
        daily,
        x="date",
        y="count",
        labels={"date": "Transaction Date", "count": "Transactions"},
        title="Transaction Activity Over Time",
        color_discrete_sequence=["#1f77b4"],
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=35, b=20),
        height=260,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        xaxis=dict(gridcolor="#f0f0f0"),
        yaxis=dict(gridcolor="#f0f0f0"),
    )
    return fig


def plot_amount_distribution(amounts: list[float]) -> go.Figure:
    """Create histogram of transaction amounts."""
    if not amounts:
        fig = go.Figure()
        fig.update_layout(title="No amount data available")
        return fig

    fig = go.Figure(
        data=[
            go.Histogram(
                x=amounts,
                nbinsx=30,
                marker=dict(color="#2ca02c", line=dict(color="#ffffff", width=1)),
            )
        ]
    )
    fig.update_layout(
        title=dict(text="Transaction Amount Distribution", font=dict(size=14)),
        xaxis=dict(title="Amount (₹)", gridcolor="#f0f0f0"),
        yaxis=dict(title="Count", gridcolor="#f0f0f0"),
        margin=dict(l=10, r=10, t=35, b=20),
        height=260,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    return fig
