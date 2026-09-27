import os
import urllib.request

import pytest


GATEWAY_BASE_URL = os.getenv("GW_BASE_URL", "").rstrip("/")


@pytest.mark.integration
@pytest.mark.skipif(not GATEWAY_BASE_URL, reason="GW_BASE_URL is not configured")
def test_gateway_health() -> None:
    with urllib.request.urlopen(
        f"{GATEWAY_BASE_URL}/health", timeout=10
    ) as response:
        body = response.read().decode("utf-8").strip()

    assert response.status == 200
    assert body == "ok"
