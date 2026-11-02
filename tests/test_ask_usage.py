from types import SimpleNamespace as NS

from app import ask


def test_ask_prints_usage_without_changing_answer(monkeypatch, capsys):
    monkeypatch.setattr(ask, "get_api_key", lambda: "test-only")
    response = NS(text="テスト回答", usage_metadata=NS(prompt_token_count=12, candidates_token_count=34))
    class Client:
        models = NS(generate_content=lambda **kwargs: response)
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(ask.genai, "Client", lambda **kwargs: Client())
    assert ask.ask("質問") == "テスト回答"
    out = capsys.readouterr().out
    assert "12" in out and "34" in out


def test_ask_missing_usage_prints_unknown(monkeypatch, capsys):
    monkeypatch.setattr(ask, "get_api_key", lambda: "test-only")
    class Client:
        models = NS(generate_content=lambda **kwargs: NS(text="回答", usage_metadata=None))
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(ask.genai, "Client", lambda **kwargs: Client())
    ask.ask("質問")
    assert "不明" in capsys.readouterr().out
