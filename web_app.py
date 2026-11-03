"""Run from the checkout: python -m streamlit run web_app.py --server.address 127.0.0.1"""

import logging
import os
from datetime import date
from pathlib import Path

import requests
import streamlit as st

from cli.web import (
    WebRequest,
    WebRunError,
    build_command,
    list_reports,
    model_options,
    ollama_models,
    run_web_analysis,
)
from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

st.set_page_config(page_title="TradingAgents", layout="wide")
st.title("TradingAgents")
st.caption("Local AI-powered market research. Experimental output, not financial advice.")

results_dir = Path(DEFAULT_CONFIG["results_dir"])
configured_provider = DEFAULT_CONFIG["llm_provider"]


@st.cache_data(ttl=30, show_spinner=False)
def installed_ollama_models(url: str) -> list[str]:
    return ollama_models(url)


def select_model(label: str, provider: str, mode: str, default: str) -> str:
    options = model_options(provider, mode, default)
    labels = {value: text for text, value in options}
    values = list(labels)
    selected = st.selectbox(
        label,
        values,
        index=values.index(default) if default in values else 0,
        format_func=lambda value: labels[value],
        key=f"{provider}_{mode}_model",
    )
    if selected == "custom":
        return st.text_input(f"{label} ID", key=f"{provider}_{mode}_custom").strip()
    return selected


with st.sidebar:
    st.header("Model settings")
    providers = list(dict.fromkeys([configured_provider, "ollama"]))
    provider = st.selectbox(
        "LLM provider",
        providers,
        format_func=lambda value: (
            "Ollama (local / self-hosted)"
            if value == "ollama"
            else f"{value.title()} (configured API)"
        ),
    )
    backend_url = None
    models_ready = True
    if provider == "ollama":
        backend_url = st.text_input(
            "Ollama API URL",
            value=os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434/v1",
            help="OpenAI-compatible endpoint, including /v1. Model discovery uses /models.",
        ).strip()
        if st.button("Refresh Ollama models"):
            installed_ollama_models.clear()
        installed = []
        try:
            installed = installed_ollama_models(backend_url)
        except (requests.RequestException, ValueError) as exc:
            st.error(f"Could not load Ollama models: {exc}")
        if installed:
            quick_model = st.selectbox("Quick-thinking model", installed, key="ollama_quick")
            deep_model = st.selectbox("Deep-thinking model", installed, key="ollama_deep")
            st.caption("Use a model with tool-calling support. Both model tiers run on Ollama.")
        else:
            models_ready = False
            quick_model = deep_model = ""
            st.warning(
                "No Ollama models available. Start Ollama and install a tool-capable "
                "model, then refresh. Example: ollama pull qwen3:8b"
            )
    else:
        st.caption("API credentials are loaded server-side from your .env file.")
        st.caption(
            "Model choices come from the shared CLI catalog; availability depends on your account."
        )
        quick_model = select_model(
            "Quick-thinking model",
            provider,
            "quick",
            DEFAULT_CONFIG["quick_think_llm"],
        )
        deep_model = select_model(
            "Deep-thinking model",
            provider,
            "deep",
            DEFAULT_CONFIG["deep_think_llm"],
        )
    language = st.selectbox("Report language", ["English", "Norwegian"])
    st.caption("Restart the server after changing credentials or provider settings in .env.")

analysis_tab, history_tab = st.tabs(["New analysis", "Reports"])

with analysis_tab:
    st.subheader("Start an analysis")
    st.info(
        "Analyses call your configured LLM provider and may incur API charges. "
        "More analysts and debate rounds increase usage."
    )
    with st.form("analysis"):
        left, right = st.columns(2)
        ticker = left.text_input("Ticker", value="NVDA", help="Examples: NVDA, EQNR.OL, BTC-USD")
        analysis_date = right.date_input(
            "Analysis date", value=date.today(), max_value=date.today()
        )
        analysts = st.multiselect(
            "Analysts",
            ["market", "news", "fundamentals", "sentiment"],
            default=["market"],
            help="Fundamentals is not available for crypto. SEC filings may require SEC_EDGAR_USER_AGENT.",
        )
        rounds = st.slider("Debate and risk rounds", min_value=1, max_value=5, value=1)
        consent = st.checkbox("I understand that starting an analysis may incur API charges.")
        submitted = st.form_submit_button(
            "Start analysis", type="primary", disabled=not models_ready
        )

    if submitted:
        request = WebRequest(
            ticker=ticker,
            date=analysis_date.isoformat(),
            analysts=tuple(analysts),
            provider=provider,
            quick_model=quick_model,
            deep_model=deep_model,
            rounds=rounds,
            language=language,
            backend_url=backend_url,
        )
        valid = False
        if not consent:
            st.error("Please acknowledge API usage charges before starting.")
        else:
            try:
                build_command(request)
            except ValueError as exc:
                st.error(str(exc))
            else:
                valid = True
        if valid:
            st.session_state.pop("completed_report", None)
            with st.status("Starting analysis...", expanded=True) as status:
                st.caption(
                    "Keep this tab open. Elapsed time is shown below; agent messages "
                    "appear when the CLI emits them. Closing the tab is not a reliable "
                    "way to cancel provider calls."
                )
                elapsed = st.empty()
                with st.expander("Execution log", expanded=False):
                    log_display = st.empty()
                try:
                    for update in run_web_analysis(request, results_dir, os.environ):
                        elapsed.write(f"Elapsed: {update.elapsed:.0f} seconds")
                        log_display.code(update.log or "Waiting for the CLI...", language="text")
                        if update.report is not None:
                            st.session_state["completed_report"] = str(update.report)
                except (ValueError, OSError, WebRunError) as exc:
                    logger.exception("Web analysis failed")
                    st.error(str(exc))
                    status.update(label="Analysis failed. See the execution log.", state="error")
                else:
                    status.update(label="Analysis complete. Report saved.", state="complete")
    if st.session_state.get("completed_report"):
        st.success("Your report is available in the Reports tab.")

with history_tab:
    st.subheader("Saved reports")
    st.caption(
        "Includes previous terminal runs and web analyses. "
        "Reports can contain data gaps or contradictory AI-generated conclusions."
    )
    st.button("Refresh reports")
    try:
        reports = list_reports(results_dir)
        if reports:
            completed = st.session_state.get("completed_report")
            index = next((i for i, path in enumerate(reports) if str(path) == completed), 0)
            selected = st.selectbox(
                "Report",
                reports,
                index=index,
                format_func=lambda path: f"{path.parent.name} ({path.parent.parent.parent.name})",
            )
            markdown = selected.read_text(encoding="utf-8")
            st.download_button(
                "Download Markdown",
                markdown,
                file_name=f"{selected.parent.name}.md",
                mime="text/markdown",
            )
            html_path = selected.with_suffix(".html")
            if html_path.is_file():
                st.download_button(
                    "Download HTML",
                    html_path.read_bytes(),
                    file_name=f"{selected.parent.name}.html",
                    mime="text/html",
                )
            st.markdown(markdown, unsafe_allow_html=False)
        else:
            st.info("No saved reports yet. Start an analysis to create one.")
    except OSError as exc:
        logger.exception("Could not read saved reports")
        st.error(f"Could not read saved reports: {exc}")
