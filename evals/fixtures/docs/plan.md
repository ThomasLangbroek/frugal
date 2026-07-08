# Plan

## Task 1: (done)
## Task 2: (done)

## Task 3: Add fetch_text helper

**Files:** modify `http_client.py`, add test to `tests/test_http_client.py`.

- [ ] Add `fetch_text(url)` to `http_client.py`: returns `fetch_data(url).decode("utf-8")`.
- [ ] Add test `test_fetch_text_exists`: assert `callable(http_client.fetch_text)`.
- [ ] Run `python3 -m pytest tests/ -q`; all tests must pass.
