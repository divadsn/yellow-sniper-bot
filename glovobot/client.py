import json

from datetime import datetime, timezone
from uuid import uuid4

import httpx


class GlovoAPIClient:
    def __init__(self, access_token: str, refresh_token: str, headers: dict):
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client = httpx.AsyncClient(base_url="https://api.glovoapp.com", headers=headers)
    
    async def fetch(self, method: str, url: str, headers: dict = None, auth: bool = True, **kwargs) -> dict:
        headers = headers or {}

        # Some requests don't require authentication
        if auth:
            headers["authorization"] = self._access_token
 
        # Glovo requires these headers to be present in every request
        headers.update({
            "date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "glovo-request-id": str(uuid4()).upper(),
        })

        response = await self._client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        
        if response.content:
            return response.json()
        
    async def refresh_token(self) -> None:
        response = await self.fetch("POST", "/oauth/refresh", json={"refreshToken": self._refresh_token}, auth=False)

        if "accessToken" not in response or "refreshToken" not in response:
            raise ValueError("Access token or refresh token not found in the response")

        self._access_token = response["accessToken"]
        self._refresh_token = response["refreshToken"]
    
    async def get_me(self) -> dict:
        return await self.fetch("GET", "/v3/couriers/me")
    
    async def get_calendar(self) -> dict:
        return await self.fetch("GET", "/v4/scheduling/calendar")
    
    async def book_slot(self, slot_id: int) -> dict:
        return await self.fetch("PUT", f"/v4/scheduling/slots/{slot_id}", json={"storeAddressId": None, "booked": True})

    def save(self, file_path: str) -> None:
        data = {
            "accessToken": self._access_token,
            "refreshToken": self._refresh_token,
            "headers": dict(sorted(dict(self._client.headers).items())),
        }

        with open(file_path, "w") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

    @classmethod
    def load(cls, file_path: str) -> "GlovoAPIClient":
        with open(file_path, "r") as file:
            data = json.load(file)

        return cls(data["accessToken"], data["refreshToken"], data["headers"])
