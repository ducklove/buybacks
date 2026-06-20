from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)


class OpenDartError(RuntimeError):
    pass


class OpenDartNoData(OpenDartError):
    pass


class OpenDartClient:
    base_url = "https://opendart.fss.or.kr/api"

    def __init__(
        self,
        api_key: str,
        timeout: float | None = None,
        retries: int | None = None,
        rate_limit_seconds: float | None = None,
        raw_dir: str | Path | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout if timeout is not None else env_float("DART_TIMEOUT_SECONDS", 8.0)
        self.retries = retries if retries is not None else env_int("DART_RETRIES", 1)
        self.rate_limit_seconds = (
            rate_limit_seconds
            if rate_limit_seconds is not None
            else env_float("DART_RATE_LIMIT_SECONDS", 0.08)
        )
        self.raw_dir = Path(raw_dir) if raw_dir else None
        if self.raw_dir:
            self.raw_dir.mkdir(parents=True, exist_ok=True)

    def request_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {"crtfc_key": self.api_key, **params}
        url = f"{self.base_url}/{endpoint}?{urlencode(payload)}"
        response = self._request(url)
        data = json.loads(response.decode("utf-8"))
        self._save_raw(endpoint, params, data)
        status = data.get("status")
        if status == "000":
            return data
        message = data.get("message", "OpenDART error")
        if status == "013":
            raise OpenDartNoData(message)
        raise OpenDartError(f"{endpoint} returned status={status}: {message}")

    def request_bytes(self, endpoint: str, params: dict[str, Any] | None = None) -> bytes:
        payload = {"crtfc_key": self.api_key, **(params or {})}
        url = f"{self.base_url}/{endpoint}?{urlencode(payload)}"
        return self._request(url)

    def _request(self, url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                sleep_for = min(2.0, 0.5 * attempt)
                LOGGER.info("Retrying OpenDART request in %.1fs", sleep_for)
                time.sleep(sleep_for)
            try:
                request = Request(url, headers={"User-Agent": "value-invest-buybacks/0.1"})
                with urlopen(request, timeout=self.timeout) as response:
                    time.sleep(self.rate_limit_seconds)
                    return response.read()
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                LOGGER.warning("OpenDART request failed: %s", exc)
        raise OpenDartError(f"OpenDART request failed after retries: {last_error}")

    def _save_raw(self, endpoint: str, params: dict[str, Any], data: dict[str, Any]) -> None:
        if not self.raw_dir:
            return
        safe_key = "_".join([endpoint.replace(".", "_"), *[f"{k}-{v}" for k, v in params.items()]])
        path = self.raw_dir / f"{safe_key[:180]}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default
