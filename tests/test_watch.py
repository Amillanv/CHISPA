"""Tests of the watch of the live poller: the texts that are due, for paper. No network."""

from datetime import UTC, datetime, timedelta

import pytest
import requests

from chispa import polls, watch

HEADER = "polled_at,source,item,result,new_rows\n"


def at(text):
    return datetime.fromisoformat(f"2026-11-25T{text}:00+00:00")


def write_polls(tmp_path, lines):
    folder = tmp_path / "live" / "polls"
    folder.mkdir(parents=True, exist_ok=True)
    rows = "".join(f"2026-11-25T{line}\n" for line in lines)
    (folder / "2026-11-25.csv").write_text(HEADER + rows)


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setattr("chispa.config.LIVE_START", datetime(2026, 11, 20, tzinfo=UTC))
    monkeypatch.setattr("chispa.config.LIVE_PASS_END_FROM", datetime(2026, 11, 20, tzinfo=UTC))
    monkeypatch.setattr("chispa.config.LIVE_POLL_LATE", timedelta(minutes=15))
    monkeypatch.setattr("chispa.config.LIVE_POLL_EACH", timedelta(minutes=5))
    monkeypatch.setattr("chispa.config.WATCH_REPORT_SPAN", timedelta(hours=1))
    monkeypatch.setattr("chispa.config.WATCH_ITEM_MARGIN", timedelta(minutes=30))
    # No report in the tests of the alarm: the hour of the report is the last hour of the day.
    monkeypatch.setattr("chispa.config.WATCH_TIME_ZONE", "UTC")
    monkeypatch.setattr("chispa.config.WATCH_REPORT_HOUR", 23)


def sends(result=True):
    return lambda text: (result, "a note")


def test_report_counts_the_passes_the_items_that_no_pass_read_and_the_new_rows(tmp_path):
    write_polls(
        tmp_path,
        [
            "09:20:00+00:00,firms,MODIS_NRT,ok,5",  # before the hour of the report
            "09:20:00+00:00,pass,end,ok,5",
            "10:00:00+00:00,firms,MODIS_NRT,ok,2",
            "10:00:00+00:00,goes,2026-11-25T09:40:00+00:00,ok,3",
            "10:00:00+00:00,inpe,focos_10min_20261125_0950.csv,ok,4",
            "10:00:00+00:00,pass,end,ok,9",
            "10:05:00+00:00,firms,MODIS_NRT,ok,0",
            "10:05:00+00:00,goes,2026-11-25T09:50:00+00:00,ok,1",
            "10:05:00+00:00,pass,end,ok,1",
            "10:10:00+00:00,firms,MODIS_NRT,failed: FIRMS request failed,0",
            "10:10:00+00:00,pass,end,ok,0",
            "10:15:00+00:00,firms,MODIS_NRT,ok,1",  # This pass stopped: it has no last row.
        ],
    )
    # One hour has 12 passes of the timer. 3 of the 4 passes after 09:30 are complete.
    # The times of 10 minutes from 09:30 to 10:00: GOES has 09:40 and 09:50, INPE has 09:50.
    assert watch.report_text(tmp_path, at("10:30"), False) == (
        "CHISPA 25 Nov 10:30 UTC: OK. 1 h: 3 of 12 passes, 1 with a failure. "
        "Not read: GOES 2, INPE 3. New rows: FIRMS 3, GOES 4, INPE 4."
    )


def test_alarm_goes_out_one_time_when_the_poller_is_late_and_one_time_when_it_is_back(tmp_path):
    good = ["10:00:00+00:00,firms,MODIS_NRT,ok,0", "10:00:00+00:00,pass,end,ok,0"]
    write_polls(tmp_path, good)
    assert watch.due(tmp_path, at("10:10")) == []
    # 15 minutes after the newest good pass the poller is late.
    assert watch.due(tmp_path, at("10:20")) == [
        (
            "late",
            "CHISPA ALARM 25 Nov 10:20 UTC: the poller is late. "
            "Newest good pass: 25 Nov 10:00 UTC. No pass ended.",
        )
    ]
    assert watch.run(tmp_path, at("10:20"), sends()) == [("late", True)]
    assert watch.due(tmp_path, at("10:25")) == []  # The alarm does not go out again.
    write_polls(
        tmp_path, [*good, "10:30:00+00:00,firms,MODIS_NRT,ok,0", "10:30:00+00:00,pass,end,ok,0"]
    )
    assert watch.due(tmp_path, at("10:32")) == [
        (
            "back",
            "CHISPA 25 Nov 10:32 UTC: the poller is good again. It was late from 25 Nov 10:20 UTC.",
        )
    ]
    assert watch.run(tmp_path, at("10:32"), sends()) == [("back", True)]
    assert watch.due(tmp_path, at("10:34")) == []


def test_alarm_names_the_source_that_failed(tmp_path):
    write_polls(
        tmp_path,
        [
            "10:00:00+00:00,firms,MODIS_NRT,ok,0",
            "10:00:00+00:00,pass,end,ok,0",
            "10:20:00+00:00,firms,MODIS_NRT,ok,0",
            "10:20:00+00:00,inpe,request,failed: ConnectionError,0",
            "10:20:00+00:00,pass,end,ok,0",
        ],
    )
    ((kind, text),) = watch.due(tmp_path, at("10:21"))
    assert kind == "late"
    assert text.endswith("Newest good pass: 25 Nov 10:00 UTC. Failed in the newest pass: INPE.")


def test_report_goes_out_one_time_on_each_local_day_from_its_hour(tmp_path, monkeypatch):
    monkeypatch.setattr("chispa.config.WATCH_TIME_ZONE", "America/New_York")
    monkeypatch.setattr("chispa.config.WATCH_REPORT_HOUR", 8)

    def kinds(now):
        return [kind for kind, _ in watch.due(tmp_path, now) if kind == "report"]

    # 12:59 UTC is 07:59 in New York in November. 13:00 UTC is 08:00.
    assert kinds(at("12:59")) == []
    assert kinds(at("13:00")) == ["report"]
    # A text that failed is due again. A text that went out is not.
    watch.run(tmp_path, at("13:00"), sends(False))
    assert kinds(at("13:05")) == ["report"]
    watch.run(tmp_path, at("13:05"), sends())
    assert kinds(at("13:10")) == []
    assert kinds(at("13:00") + timedelta(days=1)) == ["report"]


def test_log_of_the_texts_has_each_text_with_its_result(tmp_path):
    write_polls(tmp_path, ["10:00:00+00:00,firms,MODIS_NRT,ok,0", "10:00:00+00:00,pass,end,ok,0"])
    watch.run(tmp_path, at("10:20"), sends(False))
    (row,) = polls.read_rows(tmp_path / "live" / "texts" / "2026-11-25.csv")
    assert (row["sent_at"], row["kind"], row["result"], row["note"]) == (
        "2026-11-25T10:20:00+00:00",
        "late",
        "failed",
        "a note",
    )
    assert row["text"].startswith("CHISPA ALARM 25 Nov 10:20 UTC")


def test_text_goes_to_textbelt_and_the_note_has_no_key_and_no_number(monkeypatch):
    posted, answers = [], [{"success": True, "quotaRemaining": 49}]

    class Answer:
        def json(self):
            return answers[0]

    def post(url, data, timeout):
        posted.append((url, data))
        return Answer()

    monkeypatch.setattr("chispa.watch.requests.post", post)
    assert watch.send_text("a text", "5551234567", "abc") == (True, "texts left: 49")
    assert posted == [
        ("https://textbelt.com/text", {"phone": "5551234567", "message": "a text", "key": "abc"})
    ]
    answers[0] = {"success": False, "error": "Bad key abc for 5551234567"}
    assert watch.send_text("a text", "5551234567", "abc") == (False, "Bad key [key] for [number]")

    def fail(url, data, timeout):
        raise requests.ConnectionError("no network for key abc")

    monkeypatch.setattr("chispa.watch.requests.post", fail)
    assert watch.send_text("a text", "5551234567", "abc") == (False, "ConnectionError")
