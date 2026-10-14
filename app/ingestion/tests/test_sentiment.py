from datetime import UTC, datetime

import pytest
from cryptopulse_ingestion import sentiment
from cryptopulse_ingestion.config import Settings

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Bitcoin surges to record high as investors celebrate</title>
        <link>https://news.example/a</link>
        <description>&lt;p&gt;Great gains and strong optimism for BTC.&lt;/p&gt;</description>
        <pubDate>Thu, 09 Oct 2026 10:00:00 GMT</pubDate></item>
  <item><title>Ethereum crashes amid fears and heavy losses</title>
        <link>https://news.example/b</link>
        <pubDate>Thu, 09 Oct 2026 09:00:00 GMT</pubDate></item>
  <item><title>Ada Lovelace exhibition opens in London</title>
        <link>https://news.example/c</link>
        <pubDate>Thu, 09 Oct 2026 08:00:00 GMT</pubDate></item>
  <item><title>Old Bitcoin story</title>
        <link>https://news.example/old</link>
        <pubDate>Mon, 01 Jan 2024 08:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Solana network is stable</title><link href="https://atom.example/1"/>
         <updated>2026-10-09T11:00:00Z</updated><summary>calm</summary></entry>
</feed>"""

EVIL = b"""<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><rss><channel>
<item><title>&b;</title><link>https://x</link></item></channel></rss>"""


def settings(feeds=("https://news.example/rss",)):
    return Settings(coins=("bitcoin", "ethereum", "cardano", "solana"), pg_host="h", pg_port=5432,
                    pg_db="d", pg_user="u", pg_password="p", news_feeds=feeds)


def test_parse_rss_and_atom():
    items = sentiment.parse_feed(RSS, "news.example", NOW)
    assert len(items) == 4 and items[0]["published_at"].year == 2026
    assert "<p>" not in items[0]["summary"]
    atom = sentiment.parse_feed(ATOM, "atom.example", NOW)
    assert atom[0]["link"] == "https://atom.example/1"
    assert atom[0]["published_at"] == datetime(2026, 10, 9, 11, 0, tzinfo=UTC)


def test_xml_entity_bombs_are_rejected():
    from defusedxml import EntitiesForbidden

    with pytest.raises(EntitiesForbidden):
        sentiment.parse_feed(EVIL, "evil", NOW)


def test_coin_matching_avoids_common_words():
    p = sentiment.build_patterns(["bitcoin", "ethereum", "cardano", "ripple"])
    assert sentiment.match_coins("BTC rallies while ETH lags", p) == ["bitcoin", "ethereum"]
    assert sentiment.match_coins("Ada Lovelace and the Dotty song", p) == []
    assert sentiment.match_coins("Bitcoins everywhere", p) == []  # pas de faux positif sur un mot voisin
    assert sentiment.match_coins("XRP news", p) == ["ripple"]


def test_labels():
    assert sentiment.label(0.6) == "positive"
    assert sentiment.label(-0.6) == "negative"
    assert sentiment.label(0.0) == "neutral"
    assert sentiment.score("What a wonderful, fantastic result") > 0.5
    assert sentiment.score("A terrible disaster and awful losses") < -0.5


def test_collect_filters_old_and_unrelated_articles():
    rows = sentiment.collect(settings(), NOW, fetch=lambda url: RSS)
    by_link = {r["link"]: r for r in rows}
    assert set(by_link) == {"https://news.example/a", "https://news.example/b"}
    assert by_link["https://news.example/a"]["label"] == "positive"
    assert by_link["https://news.example/b"]["label"] == "negative"
    assert by_link["https://news.example/a"]["coin_id"] == "bitcoin"


def test_one_failing_feed_is_tolerated_but_not_all():
    def fetch(url):
        if "bad" in url:
            raise OSError("down")
        return RSS

    rows = sentiment.collect(settings(("https://bad.example", "https://ok.example")), NOW, fetch=fetch)
    assert rows
    with pytest.raises(RuntimeError):
        sentiment.collect(settings(("https://bad.example",)), NOW, fetch=fetch)


def test_fear_greed_parsing_and_bounds():
    payload = {"data": [{"value": "73", "value_classification": "Greed", "timestamp": "1760000000"}]}
    rows = sentiment.parse_fear_greed(payload)
    assert rows[0][1:] == (73, "Greed")
    with pytest.raises(ValueError):
        sentiment.parse_fear_greed({"data": [{"value": "150", "value_classification": "x", "timestamp": "1"}]})
    with pytest.raises(ValueError):
        sentiment.parse_fear_greed({"data": []})
