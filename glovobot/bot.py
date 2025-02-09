import asyncio
import logging
import random

from datetime import datetime, timezone

import httpx
import jwt

from glovobot.config import BOOKING_HOURS, BOOK_NO_BOOST, BOT_TOKEN, CHAT_ID, CHECK_INTERVAL
from glovobot.client import GlovoAPIClient

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("glovobot")

# Disable httpx logging
logging.getLogger("httpx").setLevel(logging.WARNING)


class GlovoBot:
    def __init__(self, client: GlovoAPIClient = None) -> None:
        self._client = client
        self._calendar = None
        self._last_slot_id = None

    async def run(self) -> None:
        while True:
            jwt_token = jwt.decode(self._client._access_token, options={"verify_signature": False})

            if jwt_token["exp"] < datetime.now(tz=timezone.utc).timestamp():
                logger.info("Token expired, refreshing...")

                try:
                    await self._client.refresh_token()
                except httpx.HTTPError as e:
                    logger.error(f"Failed to refresh token", exc_info=e)
                    await self.send_webhook_message(f"❌ Failed to refresh token:\n`{e}`")
                    break

                self._client.save("device.json")

            logger.info(f"Token valid until {datetime.fromtimestamp(jwt_token['exp'], tz=timezone.utc)}")

            try:
                if await self.check_slots():
                    logger.info("All required slots have been reserved, stopping...")
                    await self.send_webhook_message("🎉 All required slots have been reserved!")
                    break
            except Exception as e:
                logger.error(f"An error occurred while checking slots", exc_info=e)
                await self.send_webhook_message(f"❌ An error occurred while checking slots:\n`{e}`")

            await asyncio.sleep(CHECK_INTERVAL + random.randint(0, 10000) / 1000)


    async def check_slots(self) -> bool:
        logger.info("Pulling available calendar data from Glovo API")
        self._calendar = await self._client.get_calendar()

        booked_slots = []  # List of newly booked slots
        target_slots = 0  # Count total relevant slots (from BOOKING_HOURS)
        booked_target_slots = 0  # Count how many are already booked

        for day in self._calendar["days"]:
            current_date = datetime.fromtimestamp(day["date"], tz=timezone.utc)
            logger.info(f"Checking available slots for {current_date:%A, %d %B %Y}")

            for zone in day["zonesSchedule"]:
                zone_booking_hours = BOOKING_HOURS.get(zone["name"])

                if not zone_booking_hours:
                    continue

                for slot in zone["slots"]:
                    start_time = slot["startTimeFormatted"]

                    if start_time not in zone_booking_hours.get(day["name"], []):
                        continue

                    target_slots += 1

                    if slot["status"] == "BOOKED":
                        booked_target_slots += 1
                        continue

                    if slot["status"] != "AVAILABLE":
                        continue

                    if not BOOK_NO_BOOST and not any(tag_type == "RUSH" for tag_type in slot["tags"]["types"]):
                        continue

                    logger.info(f"Booking slot {slot['id']} on {current_date:%a, %d %B %Y} at {start_time}")

                    try:
                        await self._client.book_slot(slot["id"])
                    except Exception as e:
                        logger.error(f"An error occurred while booking slot {slot['id']}", exc_info=e)
                        self.send_webhook_message(f"❌ An error occurred while booking slot {slot['id']}:\n`{e}`")
                        continue

                    logger.info(f"Slot {slot['id']} on booked successfully")

                    booked_target_slots += 1
                    booked_slots.append({
                        "id": slot["id"],
                        "date": current_date.strftime("%a, %d %B %Y"),
                        "start_time": start_time,
                    })

                    await asyncio.sleep(random.randint(100, 250) / 100)

        if booked_slots:
            message = "✅ Following slots have been booked:\n"
            message += "\n".join([f"- {slot['id']}: *{slot['date']}* at *{slot['start_time']}*" for slot in booked_slots])
            await self.send_webhook_message(message)

        logger.info(f"Booked target slots: {booked_target_slots}/{target_slots}")
        return target_slots > 0 and target_slots == booked_target_slots

    async def send_webhook_message(self, message: str) -> None:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                    "chat_id": CHAT_ID,
                    "parse_mode": "Markdown",
                    "text": message,
                })
        except httpx.HTTPError as e:
            logger.error("Failed to send message to Telegram chat", exc_info=e)
