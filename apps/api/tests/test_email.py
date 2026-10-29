from app.emailer import confirm_email


def test_confirm_false_does_not_call_smtp():
    called = {"n": 0}

    def send(_body):
        called["n"] += 1

    result = confirm_email(False, {"SMTP_HOST": "smtp.example"}, "draft", send)
    assert result["ok"] is False
    assert result["smtp_attempted"] is False
    assert called["n"] == 0


def test_confirm_true_without_smtp_env_is_a_configuration_error():
    called = {"n": 0}

    def send(_body):
        called["n"] += 1

    result = confirm_email(True, {}, "draft body", send)
    assert result["ok"] is False
    assert result["smtp_attempted"] is False
    assert "not configured" in result["error"].lower()
    assert "SMTP_HOST" in result["error"]
    assert called["n"] == 0


def test_confirm_true_with_env_calls_send_once():
    env = {key: "x" for key in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "DATA_OWNER_EMAIL"
    )}
    seen = {}

    def send(body):
        seen["body"] = body

    result = confirm_email(True, env, "hello", send)
    assert result["ok"] is True
    assert result["smtp_attempted"] is True
    assert seen["body"] == "hello"
