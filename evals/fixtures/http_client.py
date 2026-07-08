"""Tiny HTTP client used by the routing evals. Not production code."""
import time
import urllib.request

MAX_RETRIES = 3


def fetch_data(url, retries=MAX_RETRIES):
    """Fetch a URL with linear-backoff retry."""
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.read()
        except OSError as error:
            last_error = error
            time.sleep(attempt + 1)
    raise last_error


def fetch_json(url):
    import json
    return json.loads(fetch_data(url))
