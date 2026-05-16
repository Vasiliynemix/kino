import asyncio
from aiohttp import web
from loguru import logger
from maxapi.enums import ParseMode
from maxapi.types import Attachment

from config import bot, WEBHOOK_HOST  # можно оставить общий конфиг


async def send_message_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()

        chat_id = data["chat_id"]
        user_id = data["user_id"]
        text = data.get("text", "")
        attachments = data.get("attachments")
        if attachments:
            attachments = [
                Attachment.model_validate(a)
                for a in attachments
            ]

        await bot.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=attachments,
            parse_mode=ParseMode.HTML,
        )

        return web.json_response({"status": "ok"})

    except Exception:
        logger.exception("send_message_handler error")
        return web.json_response({"status": "error"}, status=500)


async def start_send_server():
    app = web.Application()

    app.router.add_post("/send_message", send_message_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=8001
    )

    await site.start()

    logger.info("SendMessage server started on :8001")


async def main():
    await start_send_server()

    # держим процесс живым
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
