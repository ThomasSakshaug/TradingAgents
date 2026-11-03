"""Local web runs use the CLI in a separate process, with isolated run settings."""

import os
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import requests

from cli.prompts import detect_asset_type, parse_analysis_date, parse_analysts, parse_ticker
from tradingagents.llm_clients.model_catalog import get_model_options


@dataclass(frozen=True)
class WebRequest:
    ticker: str
    date: str
    analysts: tuple[str, ...]
    provider: str
    quick_model: str
    deep_model: str
    rounds: int = 1
    language: str = "English"
    backend_url: str | None = None


@dataclass(frozen=True)
class RunUpdate:
    elapsed: float
    log: str
    report: Path | None = None


class WebRunError(RuntimeError):
    """A failed run, whose diagnostic log remains on disk."""


def model_options(provider: str, mode: str, default: str = "") -> list[tuple[str, str]]:
    options = [
        (label, value) for label, value in get_model_options(provider, mode) if value != "custom"
    ]
    if default and default not in {value for _, value in options}:
        options.insert(0, (default, default))
    return [*options, ("Custom model ID", "custom")]


def ollama_models(backend_url: str) -> list[str]:
    """Query the same OpenAI-compatible endpoint used for Ollama inference."""
    parsed = urlsplit(backend_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Ollama URL must start with http:// or https://.")
    response = requests.get(f"{backend_url.rstrip('/')}/models", timeout=5)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Ollama returned an invalid model list.")
    models = payload["data"]
    if any(
        not isinstance(model, dict)
        or not isinstance(model.get("id"), str)
        or not model["id"].strip()
        for model in models
    ):
        raise ValueError("Ollama returned an invalid model ID.")
    return sorted({model["id"] for model in models})


def build_command(request: WebRequest) -> list[str]:
    ticker = parse_ticker(request.ticker)
    date = parse_analysis_date(request.date)
    analysts = parse_analysts(",".join(request.analysts), detect_asset_type(ticker))
    if not all(
        value.strip()
        for value in (
            request.provider,
            request.quick_model,
            request.deep_model,
            request.language,
        )
    ):
        raise ValueError("Provider, both models and output language are required.")
    if not 1 <= request.rounds <= 5:
        raise ValueError("Research depth must be between 1 and 5 rounds.")
    if request.provider == "ollama":
        parsed = urlsplit(request.backend_url or "")
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("An http:// or https:// Ollama endpoint is required.")
    return [
        sys.executable,
        "-u",
        "-m",
        "cli.main",
        "--ticker",
        ticker,
        "--date",
        date,
        "--analysts",
        ",".join(a.value for a in analysts),
        "--save",
        "--no-show",
        "--html",
        "--no-checkpoint",
    ]


def run_environment(request: WebRequest, run_dir: Path, base: Mapping[str, str]) -> dict[str, str]:
    env = dict(base)
    env.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "TRADINGAGENTS_LLM_PROVIDER": request.provider.strip(),
            "TRADINGAGENTS_QUICK_THINK_LLM": request.quick_model.strip(),
            "TRADINGAGENTS_DEEP_THINK_LLM": request.deep_model.strip(),
            "TRADINGAGENTS_OUTPUT_LANGUAGE": request.language.strip(),
            "TRADINGAGENTS_MAX_DEBATE_ROUNDS": str(request.rounds),
            "TRADINGAGENTS_MAX_RISK_ROUNDS": str(request.rounds),
            "TRADINGAGENTS_RESULTS_DIR": str(run_dir),
            "TRADINGAGENTS_NO_UPDATE_CHECK": "1",
        }
    )
    # Selecting Ollama must not retain API-backed tier/endpoint overrides from .env.
    if request.provider == "ollama":
        for tier in ("QUICK", "DEEP"):
            env[f"TRADINGAGENTS_{tier}_THINK_PROVIDER"] = "ollama"
            env[f"TRADINGAGENTS_{tier}_THINK_BACKEND_URL"] = request.backend_url or ""
        env["TRADINGAGENTS_LLM_BACKEND_URL"] = request.backend_url or ""
        env["OLLAMA_BASE_URL"] = request.backend_url or ""
    return env


def _log_tail(path: Path, env: Mapping[str, str]) -> str:
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - 16000))
        text = stream.read().decode("utf-8", errors="replace")
    for name, value in env.items():
        if value and any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            text = text.replace(value, "[REDACTED]")
    return text


def run_web_analysis(
    request: WebRequest,
    results_dir: Path,
    base_env: Mapping[str, str] | None = None,
) -> Iterator[RunUpdate]:
    command = build_command(request)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = results_dir / "web" / f"{stamp}_{uuid4().hex[:12]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    env = run_environment(request, run_dir, os.environ if base_env is None else base_env)
    log_path = run_dir / "console.log"
    started = time.monotonic()
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
        )
        try:
            while process.poll() is None:
                yield RunUpdate(time.monotonic() - started, _log_tail(log_path, env))
                time.sleep(1)
            output = _log_tail(log_path, env)
            yield RunUpdate(time.monotonic() - started, output)
            if process.returncode:
                raise WebRunError(
                    f"Analysis failed (exit code {process.returncode}). "
                    f"See the execution log below. Saved log: {log_path}"
                )
            reports = list((run_dir / "reports").glob("*/complete_report.md"))
            if len(reports) != 1:
                raise WebRunError(
                    f"The CLI finished without a unique saved report. Log: {log_path}"
                )
            yield RunUpdate(time.monotonic() - started, output, reports[0])
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def list_reports(results_dir: Path) -> list[Path]:
    """Include reports from the terminal and isolated web runs."""
    reports = [
        *results_dir.glob("reports/*/complete_report.md"),
        *results_dir.glob("web/*/reports/*/complete_report.md"),
    ]
    return sorted(reports, key=lambda path: path.stat().st_mtime_ns, reverse=True)
