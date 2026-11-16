import httpx


class SeedError(RuntimeError):
    pass


class Gateway:
    """Thin wrapper over the gateway API: /api/v1/<service>/... with a bearer token."""

    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None):
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=20, transport=transport)

    def call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: object = None,
        idempotency_key: str | None = None,
        ok: tuple[int, ...] = (200, 201, 202, 204),
    ) -> httpx.Response:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        response = self.http.request(method, path, json=json, headers=headers)
        if response.status_code not in ok:
            raise SeedError(f"{method} {path} -> {response.status_code}: {response.text[:300]}")
        return response

    def login(self, phone: str, password: str) -> dict:
        return self.call(
            "POST", "/identity/login", json={"phone": phone, "password": password}
        ).json()
