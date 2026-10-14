"""Client HTTP commun avec retries."""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "CryptoPulse/1.0 (projet pedagogique DataOps)"


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = USER_AGENT
    return s


def get(url: str, params: dict | None = None, timeout: int = 30) -> requests.Response:
    response = session().get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response
