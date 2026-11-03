import os
import socket
import subprocess
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from cli import web

_SOCKET_CONNECT = socket.socket.connect


def test_proposal_tab_updates_after_report_generation_and_on_next_session(
    tmp_path,
    monkeypatch,
    streamlit_testing,
):
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.reporting import write_report_tree

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))

    def save(folder, day, rating):
        state = {
            "trade_date": day,
            "final_trade_decision": f"**Rating**: {rating}",
            "instrument_context": (
                " Resolved identity: Company: NVIDIA Corporation. Do not substitute"
            ),
        }
        return write_report_tree(state, "NVDA", tmp_path / folder)

    def fake_run(request, *args):
        path = save("web/run/reports/new", "2026-01-02", "Underweight")
        yield web.RunUpdate(1.0, "Mock completed", path)

    monkeypatch.setattr(web, "run_web_analysis", fake_run)
    source = str(Path(__file__).parents[1] / "web_app.py")
    app = streamlit_testing.AppTest.from_file(source).run()
    assert [tab.label for tab in app.tabs] == ["New analysis", "Reports", "Proposal"]
    assert not app.dataframe
    app.checkbox[0].check()
    next(button for button in app.button if button.label == "Start analysis").click().run()
    assert not app.exception
    table = app.dataframe[0].value
    assert list(table.columns) == ["Ticker", "Name", "Date", "Proposal"]
    assert table.to_dict("records") == [
        {
            "Ticker": "NVDA",
            "Name": "NVIDIA Corporation",
            "Date": "2026-01-02",
            "Proposal": "Sell",
        }
    ]
    fresh = streamlit_testing.AppTest.from_file(source).run()
    assert fresh.dataframe[0].value.to_dict("records") == table.to_dict("records")
    save("reports/newer", "2026-01-04", "Buy")
    next(button for button in fresh.button if button.label == "Refresh proposals").click().run()
    assert fresh.dataframe[0].value.iloc[0]["Proposal"] == "Buy"


@pytest.fixture
def streamlit_testing(monkeypatch, _no_network):
    testing = pytest.importorskip("streamlit.testing.v1")

    def loopback_only(sock, address):
        # Windows implements asyncio's internal socketpair over loopback TCP.
        if address[0] in ("127.0.0.1", "::1"):
            return _SOCKET_CONNECT(sock, address)
        raise OSError("Web tests must not reach external services")

    monkeypatch.setattr(socket.socket, "connect", loopback_only)
    return testing


@pytest.fixture
def request_settings():
    return web.WebRequest(
        ticker="nvda",
        date=date.today().isoformat(),
        analysts=("market",),
        provider="google",
        quick_model="gemini-3.5-flash-lite",
        deep_model="gemini-3.5-flash-lite",
    )


def test_command_reuses_cli_validation_and_is_unattended(request_settings):
    command = web.build_command(request_settings)
    assert command[command.index("--ticker") + 1] == "NVDA"
    for flag in ("--save", "--no-show", "--html", "--no-checkpoint"):
        assert flag in command


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"ticker": ".."}, "ticker"),
        ({"analysts": ()}, "at least one"),
        ({"ticker": "BTC-USD", "analysts": ("fundamentals",)}, "crypto"),
        ({"quick_model": " "}, "both models"),
        ({"rounds": 0}, "between 1 and 5"),
        ({"date": (date.today() + timedelta(days=1)).isoformat()}, "future"),
    ],
)
def test_invalid_requests_are_refused(request_settings, overrides, message):
    with pytest.raises(ValueError, match=message):
        web.build_command(replace(request_settings, **overrides))


def test_child_environment_is_isolated_and_keeps_other_settings(request_settings, tmp_path):
    base = {"GOOGLE_API_KEY": "test-key", "TRADINGAGENTS_GOOGLE_THINKING_LEVEL": "low"}
    env = web.run_environment(request_settings, tmp_path, base)
    assert base == {"GOOGLE_API_KEY": "test-key", "TRADINGAGENTS_GOOGLE_THINKING_LEVEL": "low"}
    assert env["GOOGLE_API_KEY"] == "test-key"
    assert env["TRADINGAGENTS_RESULTS_DIR"] == str(tmp_path)
    assert env["TRADINGAGENTS_MAX_DEBATE_ROUNDS"] == "1"
    assert env["TRADINGAGENTS_MAX_RISK_ROUNDS"] == "1"
    assert env["TRADINGAGENTS_LLM_PROVIDER"] == "google"


def test_success_requires_a_persisted_report_and_does_not_pass_keys_as_arguments(
    request_settings,
    tmp_path,
    monkeypatch,
):
    children = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            children.append(kwargs["env"]["TRADINGAGENTS_RESULTS_DIR"])
            assert "private-test-key" not in command
            assert kwargs["stdin"] == subprocess.DEVNULL
            run_dir = Path(kwargs["env"]["TRADINGAGENTS_RESULTS_DIR"])
            report_dir = run_dir / "reports" / "NVDA_test"
            report_dir.mkdir(parents=True)
            (report_dir / "complete_report.md").write_text("# Test report", encoding="utf-8")
            kwargs["stdout"].write(b"diagnostic private-test-key")
            kwargs["stdout"].flush()

        def poll(self):
            return self.returncode

    monkeypatch.setattr(web.subprocess, "Popen", Process)
    env = {"GOOGLE_API_KEY": "private-test-key"}
    for _ in range(2):
        updates = list(web.run_web_analysis(request_settings, tmp_path, env))
        assert updates[-1].report.is_file()
        assert "private-test-key" not in updates[-1].log
        assert "[REDACTED]" in updates[-1].log
    assert len(set(children)) == 2
    assert len(web.list_reports(tmp_path)) == 2


@pytest.mark.parametrize("returncode", [0, 1])
def test_failed_or_missing_reports_never_look_like_success(
    request_settings,
    tmp_path,
    monkeypatch,
    returncode,
):
    class Process:
        def __init__(self, *args, **kwargs):
            self.returncode = returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(web.subprocess, "Popen", Process)
    with pytest.raises(web.WebRunError, match="failed|without a unique"):
        list(web.run_web_analysis(request_settings, tmp_path, {}))
    assert len(list(tmp_path.glob("web/*/console.log"))) == 1


def test_interrupted_generator_terminates_only_its_child(request_settings, tmp_path, monkeypatch):
    class Process:
        returncode = None
        terminated = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = 1

        def wait(self, timeout=None):
            return self.returncode

    process = Process()
    monkeypatch.setattr(web.subprocess, "Popen", lambda *args, **kwargs: process)
    updates = web.run_web_analysis(request_settings, tmp_path, {})
    next(updates)
    updates.close()
    assert process.terminated


def test_history_includes_terminal_and_web_reports(tmp_path):
    terminal = tmp_path / "reports" / "NVDA_test" / "complete_report.md"
    browser = tmp_path / "web" / "run1" / "reports" / "SPY_test" / "complete_report.md"
    for path in (terminal, browser):
        path.parent.mkdir(parents=True)
        path.write_text("# Report", encoding="utf-8")
    os.utime(terminal, ns=(1, 1))
    assert web.list_reports(tmp_path) == [browser, terminal]
    assert web.list_reports(tmp_path / "missing") == []


def test_web_form_and_history_without_live_model_calls(tmp_path, monkeypatch, streamlit_testing):
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    calls = []

    def fake_run(request, results_dir, base_env):
        calls.append(request)
        report = tmp_path / "web" / "run1" / "reports" / "NVDA_test" / "complete_report.md"
        report.parent.mkdir(parents=True)
        report.write_text("# Mock NVDA report", encoding="utf-8")
        yield web.RunUpdate(1.0, "Mock completed", report)

    monkeypatch.setattr(web, "run_web_analysis", fake_run)
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "web_app.py")).run()
    assert not app.exception
    assert not calls
    assert any("No saved reports" in item.value for item in app.info)
    app.button[0].click().run()
    assert not calls
    assert any("acknowledge" in item.value for item in app.error)
    app.checkbox[0].check()
    app.button[0].click().run()
    assert not app.exception
    assert len(calls) == 1, [item.value for item in app.error]
    assert any("Mock NVDA report" in item.value for item in app.markdown)
    app.button[1].click().run()
    assert not app.exception
    assert len(calls) == 1


def test_web_run_failure_is_visible(tmp_path, monkeypatch, streamlit_testing):
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))

    def fail(*args):
        raise web.WebRunError("Provider unavailable")
        yield  # make this a generator, like the real runner

    monkeypatch.setattr(web, "run_web_analysis", fail)
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "web_app.py")).run()
    app.checkbox[0].check()
    app.button[0].click().run()
    assert not app.exception
    assert any("Provider unavailable" in item.value for item in app.error), [
        item.value for item in app.error
    ]
    assert not app.success


def test_model_catalog_preserves_custom_defaults_and_custom_entry():
    options = web.model_options("google", "quick", "my-custom-gemini")
    values = [value for _, value in options]
    assert values[0] == "my-custom-gemini"
    assert "gemini-3.8-flash" in values
    assert values[-1] == "custom"
    assert len(values) == len(set(values))


def test_ollama_discovery_uses_inference_endpoint(monkeypatch):
    seen = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"id": "qwen3:8b"}, {"id": "llama3.1:8b"}, {"id": "qwen3:8b"}]}

    def get(url, timeout):
        seen.append((url, timeout))
        return Response()

    monkeypatch.setattr(web.requests, "get", get)
    assert web.ollama_models("http://localhost:11434/v1/") == ["llama3.1:8b", "qwen3:8b"]
    assert seen == [("http://localhost:11434/v1/models", 5)]


@pytest.mark.parametrize("payload", [{}, {"data": [{}]}, {"data": [{"id": ""}]}, []])
def test_ollama_invalid_model_list_is_explicit(monkeypatch, payload):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    monkeypatch.setattr(web.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match="invalid model"):
        web.ollama_models("http://localhost:11434/v1")


def test_ollama_request_overrides_api_tiers_without_mutating_base(request_settings, tmp_path):
    base = {
        "TRADINGAGENTS_DEEP_THINK_PROVIDER": "google",
        "TRADINGAGENTS_QUICK_THINK_PROVIDER": "openai",
        "TRADINGAGENTS_LLM_BACKEND_URL": "https://api.example.test/v1",
        "TRADINGAGENTS_DEEP_THINK_BACKEND_URL": "https://api.example.test/v1",
    }
    request = replace(
        request_settings,
        provider="ollama",
        quick_model="qwen3:8b",
        deep_model="qwen3:8b",
        backend_url="http://localhost:11434/v1",
    )
    web.build_command(request)
    env = web.run_environment(request, tmp_path, base)
    for tier in ("DEEP", "QUICK"):
        assert env[f"TRADINGAGENTS_{tier}_THINK_PROVIDER"] == "ollama"
        assert env[f"TRADINGAGENTS_{tier}_THINK_BACKEND_URL"] == request.backend_url
    assert env["TRADINGAGENTS_LLM_BACKEND_URL"] == request.backend_url
    assert env["OLLAMA_BASE_URL"] == request.backend_url
    assert base["TRADINGAGENTS_DEEP_THINK_PROVIDER"] == "google"
    with pytest.raises(ValueError, match="endpoint"):
        web.build_command(replace(request, backend_url=None))


def test_model_dropdown_switches_provider_and_passes_ollama_selection(
    tmp_path,
    monkeypatch,
    streamlit_testing,
):
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    monkeypatch.setitem(DEFAULT_CONFIG, "llm_provider", "google")
    monkeypatch.setitem(DEFAULT_CONFIG, "quick_think_llm", "gemini-3.5-flash-lite")
    calls = []

    def fake_run(request, *args):
        calls.append(request)
        yield web.RunUpdate(1, "mock")

    monkeypatch.setattr(web, "run_web_analysis", fake_run)
    monkeypatch.setattr(web, "ollama_models", lambda url: ["qwen3:8b", "llama3.1:8b"])
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "web_app.py")).run()
    assert not app.exception
    quick = next(item for item in app.selectbox if item.label == "Quick-thinking model")
    assert quick.value == "gemini-3.5-flash-lite"
    quick.select("custom").run()
    custom = next(item for item in app.text_input if item.label == "Quick-thinking model ID")
    custom.input("custom-gemini").run()
    next(item for item in app.selectbox if item.label == "LLM provider").select("ollama").run()
    assert not app.exception
    quick = next(item for item in app.selectbox if item.label == "Quick-thinking model")
    assert quick.options == ["qwen3:8b", "llama3.1:8b"]
    quick.select("llama3.1:8b").run()
    app.checkbox[0].check()
    next(item for item in app.button if item.label == "Start analysis").click().run()
    assert not app.exception
    assert len(calls) == 1
    assert calls[0].provider == "ollama"
    assert calls[0].quick_model == "llama3.1:8b"
    assert calls[0].deep_model == "qwen3:8b"
    assert calls[0].backend_url == "http://localhost:11434/v1"
    next(item for item in app.selectbox if item.label == "LLM provider").select("google").run()
    assert not app.exception
    assert not any(item.label == "Ollama API URL" for item in app.text_input)


@pytest.mark.parametrize("unreachable", [False, True])
def test_empty_or_unavailable_ollama_disables_start_but_keeps_reports(
    tmp_path,
    monkeypatch,
    streamlit_testing,
    unreachable,
):
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    monkeypatch.setitem(DEFAULT_CONFIG, "llm_provider", "google")

    def discover(url):
        if unreachable:
            raise web.requests.ConnectionError("Ollama not running")
        return []

    monkeypatch.setattr(web, "ollama_models", discover)
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "web_app.py")).run()
    # Clear the discovery cache shared with other AppTest sessions.
    next(item for item in app.selectbox if item.label == "LLM provider").select("ollama").run()
    next(item for item in app.button if item.label == "Refresh Ollama models").click().run()
    assert not app.exception
    assert next(item for item in app.button if item.label == "Start analysis").disabled
    assert any("No Ollama models" in item.value for item in app.warning)
    assert any("No saved reports" in item.value for item in app.info)
    if unreachable:
        assert any("Could not load Ollama" in item.value for item in app.error)
