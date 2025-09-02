import fitz  # PyMuPDF
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# ---- CMAT Indicators ----
CMAT_INDICATORS = {
    "Finance": ["Total Budget", "Public", "Adaptation", "Mitigation"],
    "Sectors": ["Energy", "Agriculture", "Health", "Transport", "Water"],
}

# ---- PDF Extraction ----
def extract_text_from_pdf(uploaded_file, max_pages=None):
    text = []
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page_num, page in enumerate(doc):
            if max_pages and page_num >= max_pages:
                break
            text.append(page.get_text("text") or "")
    return "\n".join(text)

# ---- Agriculture Budget Extraction ----
def extract_agriculture_budget(text: str):
    """
    Extracts agriculture budget lines from text and returns DataFrame + totals.
    """
    rows = []
    pattern = re.compile(
        r"(?P<programme>[A-Za-z\s\-\(\)]+)\s+\d+\s+(?P<budget2024>[\d,]+)\s+(?P<budget2023>[\d,]+)\s+(?P<budget2022>[\d,]+)"
    )

    for match in pattern.finditer(text):
        prog = match.group("programme").strip()
        if "agric" in prog.lower():
            rows.append({
                "Programme": prog,
                "2024": float(match.group("budget2024").replace(",", "")),
                "2023": float(match.group("budget2023").replace(",", "")),
                "2022": float(match.group("budget2022").replace(",", "")),
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return None, None

    totals = df[["2022", "2023", "2024"]].sum().to_dict()
    return df, totals

def agriculture_bar_chart(df, totals, year=2024):
    """
    Simple bar chart for agriculture programmes in a given year.
    """
    fig = px.bar(
        df,
        x="Programme",
        y=str(year),
        title=f"Agriculture Budget {year}",
        text=str(year),
        template="plotly_white"
    )
    fig.update_traces(texttemplate="%{text}", textposition="outside")
    fig.update_layout(margin=dict(t=60, r=20, l=20, b=40))
    return fig


# ---- Generic Charts ----
def bar_chart(data_dict, title):
    df = pd.DataFrame({"Indicator": list(data_dict.keys()), "Value": list(data_dict.values())})
    fig = px.bar(df, x="Indicator", y="Value", text="Value", title=title, template="plotly_white")
    fig.update_traces(texttemplate="%{text}", textposition="outside")
    fig.update_layout(margin=dict(t=60, r=20, l=20, b=40))
    return fig

def radar_chart(data_dict, title):
    indicators = list(data_dict.keys())
    values = list(data_dict.values())
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=values, theta=indicators, fill="toself", name="Indicators"))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True)),
        showlegend=False,
        title=title,
        template="plotly_white"
    )
    return fig

# ---- Extract Numeric Values ----
def extract_numbers_from_text(text, keywords=None):
    results = {}
    if not text:
        return results

    if not keywords:
        keywords = ["total budget", "public", "adaptation", "mitigation"]

    clean_text = text.lower()
    for key in keywords:
        pattern = rf"{key}[^0-9]*([\d,\.]+)"
        match = re.search(pattern, clean_text)
        if match:
            num_str = match.group(1).replace(",", "")
            try:
                results[key] = float(num_str)
            except ValueError:
                results[key] = None
    return results

# ---- Map Extracted Values to Survey Defaults ----
def prepare_survey_defaults(extracted_numbers):
    return {
        "total_budget": extracted_numbers.get("total budget", None),
        "public": extracted_numbers.get("public", None),
        "adaptation": extracted_numbers.get("adaptation", None),
        "mitigation": extracted_numbers.get("mitigation", None),
    }

# ---- Percentage Calculations ----
def calc_percentages(total_budget: float, public: float, adaptation: float, mitigation: float):
    total_budget = float(total_budget or 0)
    public = float(public or 0)
    adaptation = float(adaptation or 0)
    mitigation = float(mitigation or 0)

    if total_budget <= 0:
        return [0.0, 0.0, 0.0]

    vals = [public, adaptation, mitigation]
    return [(v / total_budget) * 100 for v in vals]

# ---- Simple Bar Chart ----
def bar_chart(data_dict, title):
    df = pd.DataFrame({"Indicator": list(data_dict.keys()), "Value": list(data_dict.values())})
    fig = px.bar(df, x="Indicator", y="Value", text="Value", title=title, template="plotly_white")
    fig.update_traces(texttemplate="%{text}", textposition="outside")
    fig.update_layout(margin=dict(t=60, r=20, l=20, b=40))
    return fig

# ---- Radar Chart ----
def radar_chart(data_dict, title):
    indicators = list(data_dict.keys())
    values = list(data_dict.values())

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=values, theta=indicators, fill="toself", name="Indicators"))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True)),
        showlegend=False,
        title=title,
        template="plotly_white"
    )
    return fig

# ---- Bar Chart with Country Targets ----
def bar_percent_chart(labels, percentages, title, country="Default"):
    thresholds = COUNTRY_THRESHOLDS.get(country, DEFAULT_THRESHOLDS)

    df = pd.DataFrame({"Indicator": labels, "Percent": [round(p, 2) for p in percentages]})

    colors = []
    for label, val in zip(df["Indicator"], df["Percent"]):
        threshold = thresholds.get(label, None)
        if threshold is not None:
            colors.append("green" if val >= threshold else "red")
        else:
            colors.append("gray")

    top = max([0] + percentages)
    max_y = 100 if top <= 100 else min(120, top + 10)

    fig = px.bar(df, x="Indicator", y="Percent", text="Percent", color=colors, color_discrete_map="identity")
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(
        title=title,
        yaxis_title="Percentage of Total Budget (%)",
        xaxis_title="",
        template="plotly_white",
        margin=dict(t=60, r=20, l=20, b=40),
        showlegend=False
    )
    fig.update_yaxes(range=[0, max_y])
    return fig


def extract_climate_programmes(text: str):
    """
    Extracts 2023 and 2024 budget allocations for climate-related programmes
    (07, 17, 18, 41, 61).
    Handles line breaks and ensures correct year mapping.
    """
    rows = []
    climate_codes = {
        "07": "Irrigation Development",
        "17": "Irrigation Development Support Programme",
        "18": "Farming Systems / SCRALA",
        "41": "Chiansi Water Development Project",
        "61": "Programme for Adaptation of Climate Change (PIDACC) Zambezi",
    }

    # Normalize text: collapse multiple spaces and join broken lines
    clean_text = re.sub(r"\s+", " ", text)

    for code, name in climate_codes.items():
        # Look for the programme code followed by at least 3 numbers on the same logical line
        pattern = re.compile(rf"\b{code}\b\s+([\d,]+)\s+([\d,]+).*?([\d,]+)")
        match = pattern.search(clean_text)
        if match:
            try:
                budget2022 = float(match.group(1).replace(",", ""))
                budget2023 = float(match.group(2).replace(",", ""))
                budget2024 = float(match.group(3).replace(",", ""))
            except ValueError:
                continue

            rows.append({
                "Programme": f"{code} - {name}",
                "2023": budget2023,
                "2024": budget2024
            })

    df = pd.DataFrame(rows)
    return df if not df.empty else None


def extract_total_budget(text: str):
    """
    Extracts the overall total 2024 budget value.
    Looks for the biggest number near the word 'Total'.
    """
    pattern = re.compile(r"Total.*?([\d,]+)", re.IGNORECASE)
    matches = pattern.findall(text)
    if matches:
        # take the largest number (total is usually the biggest figure)
        numbers = [float(m.replace(",", "")) for m in matches]
        return max(numbers)
    return None


def climate_bar_chart(df, total_budget=None):
    """
    Bar chart for climate programmes (2023 vs 2024 budgets).
    If total_budget is provided, also show % share.
    """
    melted = df.melt(id_vars=["Programme"], value_vars=["2023", "2024"], var_name="Year", value_name="Budget")

    fig = px.bar(
        melted,
        x="Programme",
        y="Budget",
        color="Year",
        barmode="group",
        text="Budget",
        title="🌍 Climate-Tagged Programmes Budget (2023 vs 2024)",
        template="plotly_white"
    )
    fig.update_traces(texttemplate="%{text}", textposition="outside")
    fig.update_layout(margin=dict(t=60, r=20, l=20, b=40), yaxis_title="Budget (ZMW)")

    # Add % share annotations if total provided
    if total_budget:
        annotations = []
        for _, row in df.iterrows():
            share = (row["2024"] / total_budget) * 100 if total_budget else 0
            annotations.append(dict(
                x=row["Programme"],
                y=row["2024"],
                text=f"{share:.2f}%",
                showarrow=False,
                yshift=20,
                font=dict(color="blue", size=12)
            ))
        fig.update_layout(annotations=annotations)

    return fig

def climate_2024_vs_total_chart(df, total_budget=10222074515):
    """
    Bar chart for climate programmes (2024 only) vs. total 2024 national budget.
    """
    # Build dataframe with climate 2024 figures
    df_2024 = df[["Programme", "2024"]].copy()

    fig = px.bar(
        df_2024,
        x="Programme",
        y="2024",
        text="2024",
        title="🌍 Climate-Tagged Programmes (2024 vs Total Budget)",
        template="plotly_white"
    )

    # Add total budget reference line
    fig.add_hline(
        y=total_budget,
        line_dash="dash",
        line_color="red",
        annotation_text=f"Total Budget: {total_budget:,.0f} ZMW",
        annotation_position="top left",
        annotation_font=dict(color="red", size=12)
    )

    # Show budget figures on bars
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")

    # Format y-axis with commas
    fig.update_layout(
        yaxis_title="Budget (ZMW)",
        yaxis_tickformat=",",
        margin=dict(t=60, r=20, l=20, b=40)
    )

    return fig

def climate_multi_year_chart(df, total_budget=None):
    """
    Grouped bar chart (2022 vs 2023 vs 2024) for climate programmes
    (codes 07, 17, 18, 41, 61).
    Y-axis = average total of 2022, 2023, 2024 budgets.
    """
    # Ensure 2022 is included
    if "2022" not in df.columns:
        df["2022"] = 0

    melted = df.melt(
        id_vars=["Programme"],
        value_vars=["2022", "2023", "2024"],
        var_name="Year",
        value_name="Budget"
    )

    avg_total = melted.groupby("Year")["Budget"].sum().mean()

    fig = px.bar(
        melted,
        x="Programme",
        y="Budget",
        color="Year",
        barmode="group",
        text="Budget",
        title="🌍 Climate Programmes (2022 vs 2023 vs 2024)",
        template="plotly_white"
    )

    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")

    # Average line
    fig.add_hline(
        y=avg_total,
        line_dash="dot",
        line_color="blue",
        annotation_text=f"Avg 2022–2024 Total: {avg_total:,.0f} ZMW",
        annotation_position="top left",
        annotation_font=dict(color="blue", size=12)
    )

    fig.update_layout(
        yaxis_title="Budget (ZMW)",
        yaxis_tickformat=",",
        margin=dict(t=60, r=20, l=20, b=40)
    )
    return fig


def climate_2024_vs_total_chart(df, total_budget=10222074515):
    """
    Bar chart for climate programmes (2024 only) vs. total 2024 national budget.
    Handles NoneType total_budget safely.
    """
    df_2024 = df[["Programme", "2024"]].copy()

    fig = px.bar(
        df_2024,
        x="Programme",
        y="2024",
        text="2024",
        title="🌍 Climate Programmes (2024 vs Total Budget)",
        template="plotly_white"
    )

    # Ensure total_budget is a number
    if total_budget is None:
        total_budget = 0

    # Add total budget reference line
    fig.add_hline(
        y=total_budget,
        line_dash="dash",
        line_color="red",
        annotation_text=f"Total Budget: {total_budget:,.0f} ZMW" if total_budget else "Total Budget: N/A",
        annotation_position="top left",
        annotation_font=dict(color="red", size=12)
    )

    # Show budget figures on bars
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")

    # Format y-axis with commas
    fig.update_layout(
        yaxis_title="Budget (ZMW)",
        yaxis_tickformat=",",
        margin=dict(t=60, r=20, l=20, b=40)
    )

    return fig