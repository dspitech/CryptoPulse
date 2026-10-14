from cryptopulse_ingestion.config import DEFAULT_NEWS_FEEDS, get_settings


def test_settings_from_environment(monkeypatch):
    monkeypatch.setenv("COINS", "bitcoin, ethereum ,")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("STORAGE_ACCOUNT", "stcp")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("NEWS_FEEDS", raising=False)
    s = get_settings()
    assert s.coins == ("bitcoin", "ethereum")
    assert s.storage_url == "https://stcp.blob.core.windows.net"
    assert s.storage_connection_string is None
    assert s.news_feeds == DEFAULT_NEWS_FEEDS


def test_custom_feeds_and_connection_string(monkeypatch):
    monkeypatch.setenv("COINS", "bitcoin")
    monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    monkeypatch.setenv("NEWS_FEEDS", "https://a.example/rss, https://b.example/rss")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    s = get_settings()
    assert s.news_feeds == ("https://a.example/rss", "https://b.example/rss")
    assert s.storage_connection_string == "UseDevelopmentStorage=true"


def test_development_storage_shortcut_is_expanded():
    from cryptopulse_ingestion.clients import AZURITE_CONNECTION_STRING, resolve_connection_string

    assert resolve_connection_string("UseDevelopmentStorage=true") == AZURITE_CONNECTION_STRING
    assert resolve_connection_string("usedevelopmentstorage=TRUE") == AZURITE_CONNECTION_STRING
    custom = "DefaultEndpointsProtocol=http;AccountName=x;AccountKey=eA==;BlobEndpoint=http://azurite:10000/x;"
    assert resolve_connection_string(custom) == custom
