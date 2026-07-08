import http_client


def test_fetch_data_exists():
    assert callable(http_client.fetch_data)


def test_retry_count_default():
    assert http_client.MAX_RETRIES == 3
