import pytest
from pydantic import ValidationError

from app.config import Settings


def test_the_database_url_escapes_the_password() -> None:
    settings = Settings(postgres_password="p@ss/word:%")

    url = settings.database_url

    assert url.password == "p@ss/word:%"
    assert "p%40ss%2Fword%3A%25" in url.render_as_string(hide_password=False)


def test_the_password_never_shows_in_repr() -> None:
    settings = Settings(postgres_password="p@ss/word:%")

    assert "p@ss" not in repr(settings)
    assert "p@ss" not in repr(settings.database_url)


def test_an_empty_password_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(postgres_password="")


def test_reads_sc_variables_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SC_POSTGRES_PASSWORD", "from-env")
    monkeypatch.setenv("SC_ENVIRONMENT", "development")

    settings = Settings()

    assert settings.postgres_password.get_secret_value() == "from-env"
    assert settings.environment == "development"


def test_service_urls_lose_a_trailing_slash() -> None:
    settings = Settings(postgres_password="test", ollama_url="http://host.docker.internal:11434/")

    assert settings.ollama_url == "http://host.docker.internal:11434"
