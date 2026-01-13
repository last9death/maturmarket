from __future__ import annotations

import logging
from urllib.parse import quote_plus, urljoin

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from maturmarket_bot.config import Settings
from maturmarket_bot.models import AvailabilityStatus, Product
from maturmarket_bot.service import ProductService
from maturmarket_bot.storage import Storage

logger = logging.getLogger(__name__)

BASE_URL = "https://maturmarket.ru"
SEARCH_PATHS = [
    "/search/?q={query}",
    "/?s={query}",
]


def build_search_url(query: str) -> str:
    encoded = quote_plus(query)
    for path in SEARCH_PATHS:
        return urljoin(BASE_URL, path.format(query=encoded))
    return urljoin(BASE_URL, f"/search/?q={encoded}")


def availability_emoji(status: AvailabilityStatus) -> str:
    if status == AvailabilityStatus.IN_STOCK:
        return "✅"
    if status == AvailabilityStatus.OUT_OF_STOCK:
        return "❌"
    if status == AvailabilityStatus.PREORDER:
        return "🕒"
    return "❓"


def format_product(product: Product) -> str:
    price = "—"
    if product.price_current is not None:
        price = f"{product.price_current:.2f} ₽"
    return (
        f"<b>{product.title}</b>\n"
        f"Цена: {price}\n"
        f"Наличие: {availability_emoji(product.availability_status)} {product.availability_status.value}\n"
        f"Ссылка: {product.url}"
    )


def product_keyboard(product: Product) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Открыть товар", url=product.url)],
        [InlineKeyboardButton(text="Подписаться", callback_data=f"watch|{product.url}")],
        [InlineKeyboardButton(text="Проверить снова", callback_data=f"check|{product.url}")],
    ]
    return InlineKeyboardMarkup(buttons)


def list_keyboard(watch_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="Удалить подписку", callback_data=f"unwatch|{watch_id}")]]
    )


class TelegramBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = Storage(settings.database_path)
        self.service = ProductService(settings, self.storage)

    def build_app(self) -> Application:
        if not self.settings.telegram_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        application = ApplicationBuilder().token(self.settings.telegram_token).build()

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("check", self.check))
        application.add_handler(CommandHandler("find", self.find))
        application.add_handler(CommandHandler("watch", self.watch))
        application.add_handler(CommandHandler("watchlist", self.watchlist))
        application.add_handler(CommandHandler("unwatch", self.unwatch))
        application.add_handler(CommandHandler("stats", self.stats))
        application.add_handler(CommandHandler("scanout", self.scanout))
        application.add_handler(CallbackQueryHandler(self.handle_callback))

        application.job_queue.run_repeating(
            self.watch_job,
            interval=self.settings.watch_interval_minutes * 60,
            first=10,
        )

        return application

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user:
            self.storage.get_or_create_user(update.effective_user.id)
        text = (
            "Привет! Я бот для мониторинга товаров maturmarket.ru.\n"
            "Команды:\n"
            "/check <url> — проверить товар\n"
            "/find <запрос> — поиск товаров\n"
            "/watch <url> — подписаться\n"
            "/watchlist — список подписок\n"
            "/unwatch <id> — удалить подписку\n"
            "/stats — статистика (для админов)\n"
            "/scanout — проверить все товары и вывести отсутствие (для админов)"
        )
        await update.message.reply_text(text)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.start(update, context)

    async def check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if not context.args:
            await update.message.reply_text("Укажи ссылку: /check <url>")
            return
        url = context.args[0]
        user_id = self.storage.get_or_create_user(update.effective_user.id)
        result = self.service.check_product(user_id, url)
        if result.product:
            await update.message.reply_text(
                format_product(result.product),
                parse_mode=ParseMode.HTML,
                reply_markup=product_keyboard(result.product),
            )
            return
        await update.message.reply_text(self._format_error(result.status))

    async def find(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if not context.args:
            await update.message.reply_text("Укажи запрос: /find <текст>")
            return
        query = " ".join(context.args)
        search_url = build_search_url(query)
        user_id = self.storage.get_or_create_user(update.effective_user.id)
        results = self.service.find_products(user_id, query, search_url)
        if not results:
            await update.message.reply_text("Ничего не найдено или запрос ограничен.")
            return
        for product in results:
            await update.message.reply_text(
                format_product(product),
                parse_mode=ParseMode.HTML,
                reply_markup=product_keyboard(product),
            )

    async def watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if not context.args:
            await update.message.reply_text("Укажи ссылку: /watch <url>")
            return
        url = context.args[0]
        user_id = self.storage.get_or_create_user(update.effective_user.id)
        watch_id = self.storage.add_watch(user_id, url)
        await update.message.reply_text(
            f"Подписка добавлена (ID {watch_id}).",
            reply_markup=list_keyboard(watch_id),
        )

    async def watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        user_id = self.storage.get_or_create_user(update.effective_user.id)
        watches = self.storage.list_watches(user_id)
        if not watches:
            await update.message.reply_text("Подписок нет.")
            return
        for watch in watches:
            await update.message.reply_text(
                f"#{watch.id} — {watch.product_url}",
                reply_markup=list_keyboard(watch.id),
            )

    async def unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if not context.args:
            await update.message.reply_text("Укажи ID: /unwatch <id>")
            return
        user_id = self.storage.get_or_create_user(update.effective_user.id)
        try:
            watch_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("ID должен быть числом.")
            return
        removed = self.storage.remove_watch(watch_id, user_id)
        if removed:
            await update.message.reply_text("Подписка удалена.")
        else:
            await update.message.reply_text("Подписка не найдена.")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if update.effective_user.id not in self.settings.admin_tg_ids:
            await update.message.reply_text("Команда доступна только администратору.")
            return
        users_count = self.storage.count_users()
        watches_count = self.storage.count_active_watches()
        cache_count = self.storage.count_cached_products()
        await update.message.reply_text(
            "Статистика:\n"
            f"Пользователи: {users_count}\n"
            f"Активные подписки: {watches_count}\n"
            f"Кэш товаров: {cache_count}"
        )

    async def scanout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if update.effective_user.id not in self.settings.admin_tg_ids:
            await update.message.reply_text("Команда доступна только администратору.")
            return
        limit = None
        if context.args:
            try:
                limit = int(context.args[0])
            except ValueError:
                await update.message.reply_text("Лимит должен быть числом.")
                return
        await update.message.reply_text("Запускаю проверку товаров. Это может занять время.")
        user_id = self.storage.get_or_create_user(update.effective_user.id)
        out_of_stock = self.service.scan_out_of_stock(user_id, BASE_URL, limit=limit)
        if not out_of_stock:
            await update.message.reply_text("Товары без наличия не найдены или данные недоступны.")
            return
        lines = [
            f"{product.title or 'Без названия'} — {product.url}"
            for product in out_of_stock
        ]
        await self._send_chunked(update, "Товары без наличия:", lines)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.callback_query:
            return
        await update.callback_query.answer()
        data = update.callback_query.data or ""
        if "|" not in data:
            return
        action, value = data.split("|", 1)
        message = update.callback_query.message
        if not message or not update.effective_user:
            return
        user_id = self.storage.get_or_create_user(update.effective_user.id)
        if action == "check":
            result = self.service.check_product(user_id, value)
            if result.product:
                await message.reply_text(
                    format_product(result.product),
                    parse_mode=ParseMode.HTML,
                    reply_markup=product_keyboard(result.product),
                )
            else:
                await message.reply_text(self._format_error(result.status))
        if action == "watch":
            watch_id = self.storage.add_watch(user_id, value)
            await message.reply_text(
                f"Подписка добавлена (ID {watch_id}).",
                reply_markup=list_keyboard(watch_id),
            )
        if action == "unwatch":
            try:
                watch_id = int(value)
            except ValueError:
                return
            removed = self.storage.remove_watch(watch_id, user_id)
            if removed:
                await message.reply_text("Подписка удалена.")

    async def watch_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        for watch in self.storage.list_active_watches():
            result = self.service.check_product(watch.user_id, watch.product_url)
            if not result.product:
                continue
            product = result.product
            self.storage.update_watch_status(watch.id, product.availability_status, product.price_current)
            if self._should_notify(watch, product):
                text = self._format_notification(watch, product)
                tg_id = self.storage.get_user_tg_id(watch.user_id)
                if tg_id is None:
                    continue
                await context.bot.send_message(chat_id=tg_id, text=text)
                self.storage.update_watch_notified_status(watch.id, product.availability_status)

    def _format_error(self, status: AvailabilityStatus) -> str:
        if status == AvailabilityStatus.NOT_FOUND:
            return "Карточка не найдена (404)."
        if status == AvailabilityStatus.BLOCKED:
            return "Похоже, сайт ограничивает запросы. Попробуй позже."
        return "Ошибка запроса. Попробуй позже."

    def _should_notify(self, watch, product: Product) -> bool:
        status_changed = product.availability_status != watch.last_status
        price_changed = product.price_current != watch.last_price
        if status_changed:
            return True
        if price_changed and product.price_current is not None:
            return True
        return False

    def _format_notification(self, watch, product: Product) -> str:
        status_text = availability_emoji(product.availability_status)
        price = "—"
        if product.price_current is not None:
            price = f"{product.price_current:.2f} ₽"
        return (
            f"Товар обновился {status_text}\n"
            f"Наличие: {product.availability_status.value}\n"
            f"Цена: {price}\n"
            f"Ссылка: {product.url}"
        )

    async def _send_chunked(self, update: Update, title: str, lines: list[str], chunk_size: int = 20) -> None:
        if not update.message:
            return
        await update.message.reply_text(title)
        for i in range(0, len(lines), chunk_size):
            chunk = "\n".join(lines[i : i + chunk_size])
            await update.message.reply_text(chunk)


def run_bot(settings: Settings) -> None:
    logging.basicConfig(level=logging.INFO)
    bot = TelegramBot(settings)
    application = bot.build_app()
    application.run_polling()


if __name__ == "__main__":
    from maturmarket_bot.config import load_settings

    run_bot(load_settings())
