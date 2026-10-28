from aml_poc.mail import rfi_text, send_rfi, smtp_ready


def test_rfi_is_not_sent_without_app_password(monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert smtp_ready() is False
    result = send_rfi(
        "Casa Brisa Kitchen Inc.",
        "C002",
        "ALR-TEST",
        [{"title": "Outgoing check image", "artifact_type": "check"}],
    )
    assert result["sent"] is False
    assert "SMTP_PASSWORD" in result["detail"]
    assert "Casa Brisa Kitchen Inc." in result["body"]


def test_rfi_includes_period_amount_and_what_to_send():
    subject, body = rfi_text(
        "Sunnyvale Corner Quick Stop LLC",
        "C001",
        "ALR-B16AEA4A2499",
        [
            {
                "title": "Signed source-of-funds letter covering the cash deposits in this review period",
                "artifact_type": "letter",
            }
        ],
        alert={
            "family": "TM-01",
            "window_start": "2025-11-24T09:00:00",
            "window_end": "2025-11-29T16:00:00",
            "amount": 44415.7,
        },
        account_id="ACC-C001-01",
        episode_label="Episode 2 of 12",
    )
    assert "24–29 November 2025" in subject
    assert "Sunnyvale Corner Quick Stop LLC" in subject
    assert "TM-01" not in body
    assert "24–29 November 2025" in body
    assert "$44,415.70" in body
    assert "ACC-C001-01" in body
    assert "Episode 2 of 12" in body
    assert "who made each deposit" in body
    assert "different period" in body
