import pytest

from cli.web import latest_proposals
from tradingagents.agents.context import build_instrument_context
from tradingagents.reporting import write_report_tree


def report(
    root,
    folder,
    ticker="NVDA",
    day="2026-01-02",
    generated="2026-01-03 12:00:00",
    rating="Buy",
    name="NVIDIA Corporation",
):
    path = root / folder / "complete_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Trading Analysis Report: {ticker}\n\n- Name: {name}\n"
        f"- Analysis date: {day}\n- Rating: {rating}\n- Generated: {generated}\n\n"
        "## III. Trading Team Plan\nFINAL TRANSACTION PROPOSAL: SELL\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "rating,expected",
    [
        ("Buy", "Buy"),
        ("Overweight", "Buy"),
        ("Hold", "Hold"),
        ("Underweight", "Sell"),
        ("Sell", "Sell"),
    ],
)
def test_final_rating_mapping_and_exact_row_shape(tmp_path, rating, expected):
    report(tmp_path, "reports/one", rating=rating)
    rows, warnings = latest_proposals(tmp_path)
    assert not warnings
    assert rows == [
        {
            "Ticker": "NVDA",
            "Name": "NVIDIA Corporation",
            "Date": "2026-01-02",
            "Proposal": expected,
        }
    ]


def test_latest_analysis_date_wins_not_file_creation_or_generation_date(tmp_path):
    report(tmp_path, "reports/latest_analysis", day="2026-01-03", rating="Hold")
    report(
        tmp_path,
        "web/run/reports/recent_generation",
        day="2026-01-01",
        generated="2026-02-01 12:00:00",
        rating="Sell",
    )
    rows, warnings = latest_proposals(tmp_path)
    assert not warnings
    assert len(rows) == 1
    assert rows[0]["Proposal"] == "Hold"
    assert rows[0]["Date"] == "2026-01-03"


def test_generation_time_breaks_ties_and_tickers_are_deduplicated(tmp_path):
    report(tmp_path, "reports/early", ticker="nvda", rating="Buy")
    report(tmp_path, "web/run/reports/late", generated="2026-01-03 13:00:00", rating="Sell")
    report(tmp_path, "reports/other", ticker="MSFT", name="Microsoft", rating="Hold")
    rows, warnings = latest_proposals(tmp_path)
    assert not warnings
    assert [row["Ticker"] for row in rows] == ["MSFT", "NVDA"]
    assert rows[1]["Proposal"] == "Sell"


def test_latest_unreadable_rating_does_not_restore_stale_buy(tmp_path):
    report(tmp_path, "reports/old", rating="Buy")
    report(tmp_path, "reports/new", day="2026-01-03", rating="REVIEW")
    rows, warnings = latest_proposals(tmp_path)
    assert not rows
    assert len(warnings) == 1
    assert "no readable final rating" in warnings[0]


def test_invalid_reports_are_warned_and_empty_history_is_supported(tmp_path):
    assert latest_proposals(tmp_path) == ([], [])
    report(tmp_path, "reports/invalid_date", day="bad-date")
    report(tmp_path, "reports/invalid_generation", generated="bad-time")
    rows, warnings = latest_proposals(tmp_path)
    assert not rows
    assert len(warnings) == 2
    assert all("Could not read proposal" in warning for warning in warnings)


@pytest.mark.parametrize("day,kind", [("2026-01-01", "stock"), (None, "stock"), (None, "crypto")])
def test_writer_records_resolved_name_without_extra_lookup(tmp_path, day, kind):
    state = {
        "trade_date": day,
        "final_trade_decision": "**Rating**: Hold",
        "instrument_context": build_instrument_context(
            "NVDA",
            kind,
            {"company_name": "Example Inc.", "sector": "Tech"},
            day,
        ),
    }
    text = write_report_tree(state, "NVDA", tmp_path).read_text(encoding="utf-8")
    assert "- Name: Example Inc.\n" in text
    assert "Name: Example Inc. (its current" not in text


def test_writer_with_no_identity_does_not_invent_a_name(tmp_path):
    text = write_report_tree({}, "NVDA", tmp_path).read_text(encoding="utf-8")
    assert "- Name:" not in text
