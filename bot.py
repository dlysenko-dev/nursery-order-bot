import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from db.database import init_db
from handlers import cabinet, chat, start, catalog, cart, checkout, payment, info
from handlers.admin import chat_reply, orders, payment_check, shipping, catalog_mgmt, settings

logging.basicConfig(level=logging.INFO)

dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(catalog.router)
dp.include_router(cart.router)
dp.include_router(checkout.router)
dp.include_router(payment.router)
dp.include_router(info.router)
dp.include_router(chat.router)
dp.include_router(cabinet.router)
dp.include_router(chat_reply.router)
dp.include_router(orders.router)
dp.include_router(payment_check.router)
dp.include_router(shipping.router)
dp.include_router(catalog_mgmt.router)
dp.include_router(settings.router)


async def main() -> None:
    from aiogram.types import BotCommand
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
        BotCommand(command="admin", description="Панель администратора"),
    ])
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
