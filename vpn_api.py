import aiohttp
from config import VPN_API_URL, VPN_API_TOKEN


class VPNAPIError(Exception):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {VPN_API_TOKEN}"}


async def _request(method: str, path: str, json: dict | None = None) -> dict:
    url = f"{VPN_API_URL}{path}"
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.request(method, url, json=json, headers=_headers()) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                text = await r.text()
                raise VPNAPIError(f"non-json response: {text[:200]}")
            if not data.get("ok"):
                raise VPNAPIError(data.get("error") or f"http {r.status}")
            return data


async def create_client(name: str, days: int) -> dict:
    return await _request("POST", "/create", {"name": name, "days": days})


async def extend_client(name: str, days: int) -> dict:
    return await _request("PATCH", "/edit", {"name": name, "days": days})


async def get_client(name: str) -> dict:
    return await _request("GET", f"/info?name={name}")


async def delete_client(name: str) -> dict:
    return await _request("DELETE", f"/clients/{name}")


async def list_clients() -> dict:
    return await _request("GET", "/clients")
