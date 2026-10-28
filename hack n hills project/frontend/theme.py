"""Shared light design tokens for the research interface and its charts."""

INK = "#172B4D"
MUTED = "#475467"
ACCENT = "#1D4E89"
SURFACE = "#FFFFFF"
CANVAS = "#F5F7FA"
BORDER = "#D0D5DD"
PALETTE = [ACCENT, "#8A6519", "#087E8B", "#6958A1", "#B54708"]
HEATMAP = [[0, "#B54708"], [0.5, "#F5F7FA"], [1, ACCENT]]

CSS = """<style>
.stApp {background: #F5F7FA; color: #172B4D;}
[data-testid="stSidebar"] {background: #FFFFFF; border-right: 1px solid #D0D5DD;}
.block-container {padding-top: 2.4rem; max-width: 1440px; padding-bottom: 3rem;}
h1 {font-size: 2.1rem !important; font-weight: 650 !important; letter-spacing: -.035rem; color: #172B4D;}
h2, h3, h4 {font-weight: 600 !important; color: #172B4D;}
.brand {font-size: 1.65rem; letter-spacing: .08rem; color: #172B4D; font-weight: 700;}
.brand-sub {font-size: .78rem; color: #475467; margin: .2rem 0 1.25rem;}
.section-label {color: #344054; font-size: .82rem; font-weight: 650; margin: 1.2rem 0 .65rem;}
.page-kicker {color: #475467; font-size: .8rem; font-weight: 500; margin-bottom: .6rem;}
.welcome-intro {max-width: 850px; color: #344054; font-size: 1rem; line-height: 1.7; margin-bottom: 1.5rem;}
.pipeline-step {padding: 1rem; border: 1px solid #D0D5DD; border-radius: 4px; background: #FFFFFF; min-height: 9rem;}
.pipeline-number {color: #1D4E89; font-size: .8rem; font-weight: 650;}
.pipeline-title {font-size: .95rem; font-weight: 650; color: #172B4D; margin: .5rem 0;}
.pipeline-description {font-size: .85rem; color: #475467; line-height: 1.5;}
.verdict-panel {padding: 1rem 1.2rem; border: 1px solid #D0D5DD; border-left: 4px solid #1D4E89; border-radius: 4px; background: #FFFFFF; color: #172B4D; margin-bottom: 1rem;}
[data-testid="stMetric"] {border: 1px solid #D0D5DD; border-radius: 4px; padding: 1rem; background: #FFFFFF;}
[data-testid="stMetricValue"] {font-size: 1.55rem; color: #172B4D;}
[data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] {color: #475467;}
[data-testid="stExpander"], [data-testid="stDataFrame"] {border: 1px solid #D0D5DD; border-radius: 4px; background: #FFFFFF;}
div.stButton > button, div.stDownloadButton > button, div.stFormSubmitButton > button {
    border-radius: 4px; font-weight: 500; box-shadow: none !important; transform: none !important; transition: none !important;
}
div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primaryFormSubmit"] {
    background: #1D4E89; border: 1px solid #1D4E89; color: #FFFFFF;
}
button:focus-visible, a:focus-visible, input:focus-visible {outline: 2px solid #1D4E89 !important; outline-offset: 3px;}
div[data-testid="stAlert"] {border-radius: 4px;}
@media (max-width: 768px) {
    .block-container {padding: 1.5rem 1rem;}
    h1 {font-size: 1.7rem !important;}
    .pipeline-step {min-height: auto;}
}
@media (prefers-reduced-motion: reduce) {*, *::before, *::after {animation: none !important; transition: none !important;}}
footer {visibility: hidden;}
</style>"""


def style_chart(fig, title=None, height=390):
    fig.update_layout(template="plotly_white", paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                      colorway=PALETTE, font=dict(family="Arial", color=INK, size=13),
                      margin=dict(l=24, r=24, t=55 if title else 24, b=40), height=height,
                      title=title, legend=dict(orientation="h", y=-0.2), hovermode="x unified")
    fig.update_xaxes(gridcolor="#E4E7EC", zerolinecolor="#98A2B3", automargin=True)
    fig.update_yaxes(gridcolor="#E4E7EC", zerolinecolor="#98A2B3", automargin=True)
    return fig
