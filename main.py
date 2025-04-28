import logging
from itertools import product
from logging.handlers import RotatingFileHandler
from venv import logger
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from dotenv import load_dotenv
from datetime import datetime
import asyncio
import json

from pyexpat.errors import messages

import database
import parserAnki
import random
import os
from redis_nikix import redis_connect, upload_users, check_and_add_user, cache_products, get_cached_products, \
    get_search_products, get_redis_brands, upload_user_index_brand, get_brand_and_index, redis_delete_all_products, \
    redis_delete_product, delete_redis_users, cache_sizes_length, get_sizes_length, cache_support_link, \
    get_support_link, cache_drop_access, get_drop_access, give_redis_drop_access, cache_drop_info, get_drop_info

# Логирование
logging.getLogger("aiogram").setLevel(logging.WARNING)
handler = RotatingFileHandler("bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8',)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[handler, logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_PARSING_ID = os.getenv("CHANNEL_PARSING_ID")
CHAT_ORDERS_ID = int(os.getenv("CHAT_ORDERS_ID"))
START_TEXT = "Стартовое сообщение"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage()) # память для хранения списка товаров
sizes_cache = {}
length_cache = {}
drop_password = ""

# Отправить сообщение админу
async def send_admin_message(message: str, is_log=False):
    if is_log == False:
        await bot.send_message(ADMIN_ID, f"⚠️ <b>Техническое сообщение:</b>\n{message}", parse_mode="HTML")
    logger.info(message)

# Работа с кэшом размеров
try:
    with open("sizes_cache.json", "r") as f:
        sizes_cache = json.load(f)
except FileNotFoundError:
    sizes_cache = {}

async def fetch_sizes():
    urls = await database.fetch_url_sizes()
    sizes = await parserAnki.get_all_sizes(urls)
    return sizes

async def update_cache():
    global sizes_cache
    time_flag = 0
    while True:
        current_time = int(str(datetime.now().time()).split(":")[0])
        if current_time >= 1 and current_time <= 22:
            time_flag = 0
            teh_text = "Парсинг закончен"
            sizes = await fetch_sizes() # Сам парсинг
            flag = 0
            # Обновление глобального списка
            for key in sizes:
                size = sizes[key]
                if size != -1:
                    sizes_cache[key] = size # Если нет ошибки берем новое значение
                else: # Если новое значение - ошибка, ничего не меняем
                    logger.error(f"Ошибка при парсинге размеров: {key}")
                    if key not in sizes_cache:
                        sizes_cache[key] = ["Не удалось проверить наличие"] # Если новое значение ошибка и его нет в глобальном словаре, ставим что размеров нет
                        logger.error(f"Нет в кэше размера: {key}")
                    teh_text += f"\nОшибка запроса: {key}"
                    flag = 1

            if flag == 0:
                teh_text += " без ошибок"

            # Сохранение в json на случай перезагрузки бота для быстрого доступа
            with open('sizes_cache.json', 'w') as f:
                json.dump(sizes_cache, f)

            wait_time = random.randint(40, 80) * 60 # Случайное время ожидания от 40 до 80 минут
            teh_text += f"\nСледующий через {int(wait_time/60)} минут"

            if flag == 0:
                await bot.send_message(CHANNEL_PARSING_ID, teh_text, parse_mode="HTML") # Если нет ошибок пишем в канал
                logger.info(teh_text)
            else:
                await send_admin_message(teh_text) # Если есть ошибки пишем в бота
                logger.error(teh_text)
        else:
            wait_time = 7200 # Спим 2 часа ночью
            if time_flag == 0:
                await send_admin_message(message=f"Парсинг выключен на ночь")
                logger.info(f"Парсинг выключен на ночь")
                time_flag = 1
        await asyncio.sleep(wait_time)


async def on_startup(bot: Bot):
    global drop_password
    #asyncio.create_task(update_cache())
    await database.init_db()
    message = await redis_connect()
    await send_admin_message(message)
    products = await database.fetch_products("all")
    await cache_products(products)
    user_ids = await database.fetch_users(onlyID=1)
    if not user_ids:
        user_ids = [0]
    await delete_redis_users()
    await upload_users(user_ids)  # Добавление списка пользователей в redis
    await cache_sizes_length() # Добавление длин размеров в redis
    with open("bot_settings.json", "r") as f:
        data = json.load(f)
        support = data["support_link"]
        drop_password = data["drop_password"]
    await cache_support_link(support)
    drop_access = await database.fetch_drop_access()
    await cache_drop_access(drop_access)
    await cache_drop_info()
    await send_admin_message(message="Бот запущен и задачи инициализированны")
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
dp.startup.register(on_startup)


async def start_handler(message: types.Message, isStart=True, isReboot=False):

    # Старт
    user_name = message.from_user.first_name or "Гость"
    if user_name == "Nikix (bot)":
        user_name = "Гость"

    if isReboot == False:
        text = (f'Привет, {user_name}!\n\nБот покажет тебе ассортимент магазина '
            f'<a href="https://t.me/+cbbL5zcx7jQyOWUy">Nikix.</a> Чтобы оформить заказ, пожалуйста, перейди в «Каталог», '
            f'выберите нужную модель кроссовок и укажите данные получателя. После этого ожидай сообщение от менеджера '
            f'для подтверждения заказа.\n\nПо вопросам пиши в специальный бот по кнопке «Поддержка».')
    else:
        text = f"Извини, бот был перезапущен, пожалуйста нажми «Каталог» ещё раз"

    support_link = await get_support_link()

    builder = InlineKeyboardBuilder()
    but_catalog = (InlineKeyboardButton(text="👟 Каталог", callback_data="catalog"))
    but_search = (InlineKeyboardButton(text="🔎 Поиск", callback_data="search"))
    # but_feedback = (InlineKeyboardButton(text="💬 Отзывы", callback_data="feedback"))
    but_support = (InlineKeyboardButton(text="💬 Поддержка", url=support_link))
    but_my_orders = (InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders:ed"))
    count_basket = await database.fetch_basket(user_id=message.chat.id, count=True)
    if count_basket != None and count_basket > 0:
        but_basket_text = f"🛒 Корзина [{count_basket}]"
    else:
        but_basket_text = "🛒 Корзина"
    but_basket = (InlineKeyboardButton(text=but_basket_text, callback_data="go_to_basket_from_menu"))
    builder.row(but_catalog)
    builder.row(but_search, but_support)
    builder.row(but_basket, but_my_orders)
    if message.from_user.id == ADMIN_ID:
        but_admin = InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin")
        builder.row(but_admin)

    if isStart == True:
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=builder.as_markup())
    else:
        await bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=message.message_id,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=builder.as_markup()
        )

class adminStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_mail_photo = State()
    waiting_for_mail_text = State()
    waiting_for_mail_but_text = State()
    waiting_for_csv_file = State()
    waiting_for_photos_csv_file = State()
    waiting_for_new_price = State()
    waiting_for_post_link = State()
    waiting_for_sizes_length = State()
    waiting_for_new_proxy = State()
    waiting_for_new_support = State()
    waiting_for_drop_password = State()
    waiting_for_drop_start_date = State()
    waiting_for_drop_stop_date = State()

@dp.message(Command(commands=["start"], ignore_case=True))
async def start(message: types.Message, command: types.BotCommand, state: FSMContext):
    arg = command.args
    # Проверка на спец символы для ссылок из корзины
    if (arg is not None) and ("art" in arg):
        # deep link из канала
        await start_check_user(message)
        art = arg.split("art")[1]
        watch_mode = "catalog"
        brand = "all"
        back_mode = "0"
        products = await get_products_from_index(watch_mode=watch_mode, brand=brand)
        i = 0
        flag = 0
        for product in products:
            if product["art"] == art:
                flag = 1
                current_index = i
                await upload_user_index_brand(user_id=message.from_user.id, current_index=current_index, brand=brand,
                                              watch_mode=watch_mode, back_mode=back_mode)
                await send_or_update_product(message.chat.id, message.message_id, product, current_index, len(products),
                                             is_edit=False, back_mode=back_mode)
            i += 1
        if flag == 0:
            # Если артикул не нашелся то просто удаляем команду старт и ничего не деалем
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    elif (arg is not None) and ("zov" in arg):
        data_arg = arg.split("zov")
        arg = data_arg[0]
        last_message_id = data_arg[1]
        back_mode = data_arg[2]
        basket_id_to_delete = int(data_arg[3])
        await state.update_data(basket_id_to_delete=basket_id_to_delete)
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
        products = await get_products_from_index(watch_mode="catalog", brand="all")
        i = 0
        flag = 0
        for product in products:
            if product["art"] == arg:
                flag = 1
                current_index = i
                await send_or_update_product(message.chat.id, message.message_id, product, current_index, len(products),
                                             is_edit=False, back_mode=back_mode)
            i += 1
        if flag == 0:
            await start_handler(message)
    elif (arg is not None) and ("show_order" in arg):
        data_arg = arg.split("show_order")
        order_id = data_arg[0]
        last_message_id = data_arg[1]
        await show_order(message, order_id, last_message_id)
        return
    elif (arg is not None) and ("admin_send" in arg):
        user_id = int(arg.replace("admin_send_", ""))
        if message.from_user.id == ADMIN_ID:
            builder = InlineKeyboardBuilder()
            builder.button(text="Отмена", callback_data="admin_send:0")
            await bot.delete_message(chat_id=ADMIN_ID, message_id=message.message_id)
            new_message = await bot.send_message(text=f"Сообщение для клиента {user_id}:", chat_id=ADMIN_ID, reply_markup=builder.as_markup())
            await state.update_data(last_message_id=new_message.message_id, user_id_for_admin=user_id)
            await state.set_state(adminStates.waiting_for_message)
        else:
            await message.answer(text="Ты не админ", show_alert=True)
        return
    elif (arg is not None) and ("photos" in arg):
        await show_all_photos(arg, message, state)
        return
    elif arg == "-1":
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        await start_handler(message)
    elif (arg is not None) and ("status" in arg):
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        if message.chat.id == ADMIN_ID:
            await choose_status(message, arg)
        else:
            await message.answer(text="Ты не админ", show_alert=True)
        return
    else:
        await start_check_user(message)
        await start_handler(message)

async def start_check_user(message):
    user_id = message.from_user.id
    username = message.from_user.username
    if username:
        username = f"@{username}"
    else:
        username = "Не указан"
    is_user_exist = await check_and_add_user(user_id)
    if is_user_exist is None:
        users = await database.fetch_users(onlyID=1)
        if user_id in users:
            is_user_exist = 1
        await upload_users(users)  # Добавление списка пользователей в redis
    if is_user_exist == 0:
        await database.add_user(user_id=user_id, user_name=username, first_name=message.from_user.first_name)
        newuser_text = f"Пользователь {username} с id: {user_id} теперь с нами!"
        await send_admin_message(message=newuser_text)


@dp.callback_query(lambda c: c.data in ['catalog', 'back_from_products'])
async def start_catalog(callback_query: types.CallbackQuery, state: FSMContext):
    # Извлечение брендов из redis
    brands = await get_redis_brands()
    brands = [brand.decode('utf-8') for brand in brands]
    # Извлечение брендов из базы данных
    if not brands:
        brands = await database.fetch_brands()
    if not brands:
        await callback_query.answer("Нет доступных товаров")
        await send_admin_message("Не находятся товары")
        return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Все бренды", callback_data="brand:all"))
    # builder.adjust(1)  # Количество кнопок в строке
    for i in range(0, len(brands), 3):
        but1 = InlineKeyboardButton(text=brands[i], callback_data=f"brand:{brands[i]}")
        if i < len(brands) - 2:
            but2 = InlineKeyboardButton(text=brands[i+1], callback_data=f"brand:{brands[i+1]}")
            but3 = InlineKeyboardButton(text=brands[i + 2], callback_data=f"brand:{brands[i + 2]}")
            builder.row(but1, but2, but3)
        elif i < len(brands) - 1:
            but2 = InlineKeyboardButton(text=brands[i + 1], callback_data=f"brand:{brands[i + 1]}")
            builder.row(but1, but2)
        else:
            builder.row(but1)
    builder.row(InlineKeyboardButton(text="◀️ Вернутся в меню", callback_data="catalog_back"))
    # builder.adjust(1)

    text = "Выбери бренд для просмотра кроссовок:"

    try:
        # Пытаемся редактировать сообщение как текст
        await bot.edit_message_text(
            text=text,
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        # Если редактирование не удалось (например, сообщение содержит фото), отправляем новое
        await bot.delete_message(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id
        )
        await bot.send_message(
            chat_id=callback_query.message.chat.id,
            text=text,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    # На всякий случай очищаем state
    await state.clear()



@dp.callback_query(lambda c: c.data == 'catalog_back')
async def back_from_catalog(callback_query: types.CallbackQuery):
    await start_handler(message=callback_query.message, isStart=False)



#Колбэк, который начинается с brand_:
@dp.callback_query(lambda c: c.data.startswith('brand:'))
async def show_products(callback_query: types.CallbackQuery):
    callback_data = callback_query.data.split(":")
    brand = callback_data[1]  # Извлекаем из колбэка название бренда или all
    products = await get_cached_products(brand)
    if products == [] or products is None:
        products_from_brand = await database.fetch_products(brand)
        products = products_from_brand[::-1]
    await upload_user_index_brand(user_id=callback_query.from_user.id, current_index=0, brand=brand, watch_mode="catalog", back_mode="0")
    if len(callback_data) > 2:
        if callback_data[2] == "from_mail":
            await send_or_update_product(callback_query.message.chat.id, callback_query.message.message_id, products[0], 0, len(products), is_edit=False)
            return
    await send_or_update_product(callback_query.message.chat.id, callback_query.message.message_id, products[0], 0,len(products), is_edit=True)



@dp.callback_query(lambda c: c.data in ['prev', 'next', 'same', 'same2'])
async def navigate_catalog(callback_query: types.CallbackQuery, state: FSMContext):
    index = await get_brand_and_index(callback_query.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    back_mode = index["back_mode"]
    products = await get_products_from_index(watch_mode, brand)
    total_products = len(products)

    if products == []:
        await start_handler(callback_query.message, isStart=False)
        return

    if callback_query.data == 'prev':
        if current_index > 0:
            current_index -= 1
        else:
            current_index = total_products-1
    elif callback_query.data == 'next':
        if current_index < total_products-1:
            current_index += 1
        else:
            current_index = 0

    await upload_user_index_brand(callback_query.from_user.id, current_index, brand, watch_mode, back_mode)
    await send_or_update_product(callback_query.message.chat.id, callback_query.message.message_id, products[current_index], current_index, total_products, is_edit=True, back_mode=back_mode)
    if callback_query.data == "same2":
        await state.clear()



async def get_products_from_index(watch_mode, brand):
    if watch_mode == "catalog":
        products = await get_cached_products(brand)
    elif "search" in watch_mode:
        search_data = watch_mode.split(":")
        search_mode = search_data[1]
        param = search_data[2]
        param2 = None
        if "size" in watch_mode:
            global sizes_cache
            param2 = sizes_cache
        products = await get_search_products(search_mode=search_mode, param=param, sizes_cache=param2)
    return products



async def create_navigative_keyboard(is_has, back_mode, is_one, is_admin, is_drop_close):
    keyboard = InlineKeyboardBuilder()
    if (back_mode == "0") or (back_mode == None) or ("search_from" in back_mode):
        if is_one == False:
            keyboard.button(text="⬅️", callback_data="prev")
            keyboard.button(text="➡️", callback_data="next")
        if is_admin == False:
            if not is_drop_close:
                if is_has == 1:
                    keyboard.button(text="📦 Заказать", callback_data="choose_size:for_order")
                    keyboard.button(text="🛒 Добавить в корзину", callback_data="choose_size:for_basket")
                else:
                    keyboard.button(text="✖️ Заказать", callback_data="popup_empty")
                    keyboard.button(text="✖️ Добавить в корзину", callback_data="popup_empty")
            else:
                keyboard.button(text="🧑‍💻 Ввести пароль", callback_data="enter_drop_password")
        else:
            keyboard.button(text="💵 Изменить цену", callback_data="change_price")
            keyboard.button(text="🖼 Изменить ссылку на пост", callback_data="change_post_link")
            keyboard.button(text="🗑 Удалить", callback_data="admin_delete_product")
    if back_mode == "0"  or back_mode == None:
        keyboard.button(text="◀️ Назад", callback_data="back_from_products")
        if is_one == False:
            keyboard.adjust(2, 1, 1, 1)
        else:
            keyboard.adjust(1)
    elif "search" in back_mode:
        keyboard.button(text="◀️ Назад", callback_data=back_mode)
        if is_one == False:
            keyboard.adjust(2, 1, 1, 1)
        else:
            keyboard.adjust(1)
    else:
        keyboard.button(text="📏 Изменить размер", callback_data=f"choose_size:for_edit_basket:{back_mode}")
        keyboard.button(text="❌ Убрать из корзины", callback_data=f"delete_product_basket:{back_mode}")
        keyboard.button(text="◀️ Назад в корзину", callback_data=back_mode)
        keyboard.adjust(1) # Количество кнопок в строке
    return keyboard.as_markup()



#Добавить пробелы в числах
async def format_number(number):
    return f"{number:,}".replace(',', ' ')

async def send_or_update_product(chat_id, message_id, product, current_index, total_products, is_edit=False, back_mode="0"):
    # Работа с размерами
    global sizes_cache
    if product["art"] in sizes_cache:
        sizes = sizes_cache[str(product["art"])]
    else:
        sizes = []
    if len(sizes) != 0:
        size_text = ""
        is_has = 1
    else:
        size_text = "Доступных размеров нет"
        is_has = 0
    for size in sizes:
        if len(size_text) == 0:
            size_text += f"Доступные размеры (EU): {size}" # Первый элемент без запятой
        else:
            size_text += f", {size}"

    # Проверка на то что товар не из дропа
    if product["is_drop"] == "0":
        # Если нет, то просто выводим ка обычно
        product_text = (
            f"{current_index + 1} из {total_products}\n"
            f"<b>{product['name']}</b>\n"
            f"Артикул: {product['art']}\n"
            # f"Производитель: {product['maker']}\n" в некоторых кроссовках производитель стоит none
            f"Материал: {product['material']}\n"
            f"Сезон: {product['season']}\n\n"
        )
        if is_has == 1:
            if product["price"] != 0:
                price = await format_number(product["price"])
                product_text += f"Цена: <b>{price}</b> ₽\n"
            else:
                await send_admin_message(message=f"Не указана цена на {product['name']}, артикул: {product['art']}")
                product_text += f"Цена не указана, пожалуйста обратитесь в поддержку\n"
        product_text += f"{size_text}\n"
        # Проверяем есть ли ссылка на пост (если её нет значит там стоит 0)
        if product["channel_url"] != "0":
            photos_link = product["channel_url"]
        else:
            # Если ссылки нет делаем ссылку на команду и в аргумент суем артикул
            photos_link = f"https://t.me/nikix_store_bot?start={product['art']}photos{message_id}"
        product_text += f"<a href='{photos_link}'>Ещё фото...</a>"
        is_drop_close = False
    else:
        # Если из дропа, то проверяем введён ли пароль у пользователя
        drop_info = await get_drop_info()
        drop_access = await get_drop_access(chat_id)
        if (drop_access == "0") or (drop_access is None):
            product_text = f"Для доступа к модели необходимо ввести ключ-пароль. Он появится в канале в <b>{drop_info['drop_start_date']}</b>"
            is_drop_close = True
        else:
            # Если пароль введён, то показываем товар со специальной ценой и информацией об ограниченности по времени
            is_drop_close = False
            product_text = (
                f"{current_index + 1} из {total_products}\n"
                f"<b>{product['name']}</b>\n"
                f"Артикул: {product['art']}\n"
                # f"Производитель: {product['maker']}\n" в некоторых кроссовках производитель стоит none
                f"Материал: {product['material']}\n"
                f"Сезон: {product['season']}\n\n"
            )
            if is_has == 1:
                if (product["drop_price"] != 0) and (product["price"] !=0):
                    old_price = await format_number(product["price"])
                    new_price = await format_number(product["drop_price"])
                    price = f"<s>{old_price} ₽</s> <b>{new_price}</b> ₽"
                    product_text += f"Цена: {price}\n"
                else:
                    await send_admin_message(message=f"Не указана цена на {product['name']}, артикул: {product['art']}")
                    product_text += f"Цена не указана, пожалуйста обратитесь в поддержку\n"
            product_text += f"{size_text}\n"
            # Проверяем есть ли ссылка на пост (если её нет значит там стоит 0)
            if product["channel_url"] != "0":
                photos_link = product["channel_url"]
            else:
                # Если ссылки нет делаем ссылку на команду и в аргумент суем артикул
                photos_link = f"https://t.me/nikix_store_bot?start={product['art']}photos{message_id}"
            product_text += f"<a href='{photos_link}'>Ещё фото...</a>"
            product_text += f"\n\nСпециальная стоимость для дропа действует до <b>{drop_info['drop_stop_date']}</b>"

    is_one = False
    if total_products == 1:
        is_one = True
    if chat_id == ADMIN_ID:
        is_admin = True
    else:
        is_admin = False
    keyboard = await create_navigative_keyboard(is_has=is_has, back_mode=back_mode, is_one=is_one, is_admin=is_admin, is_drop_close=is_drop_close)
    photo_url = product["photo_url"]
    photo_url = photo_url.strip()

    if is_edit:
        if message_id is None:
            logger.error("Ошибка, message_id не определён")
            return

        await bot.edit_message_media(
            media = types.InputMediaPhoto(media=photo_url, caption=product_text, parse_mode="HTML"),
            chat_id = chat_id,
            message_id = message_id,
            reply_markup = keyboard
        )
    else:
        await bot.send_photo(chat_id, photo=photo_url, caption=product_text, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(lambda c: c.data == "popup_empty")
async def show_popup_empty(callback: types.CallbackQuery):
    await callback.answer(text="Нет в наличии этой модели", show_alert=True)


class dropStates(StatesGroup):
    waiting_for_drop_password = State()

# Ввести пароль для дропа
@dp.callback_query(lambda c: c.data == "enter_drop_password")
async def ack_drop_password(callback: types.CallbackQuery, state: FSMContext):
    await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="same2")
    new_message = await bot.send_message(
        chat_id=callback.message.chat.id,
        text="Напиши код-пароль для доступа к дропу:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(dropStates.waiting_for_drop_password)
    await state.update_data(last_message_id=new_message.message_id)

@dp.message(dropStates.waiting_for_drop_password)
async def check_drop_password(message: types.Message, state: FSMContext):
    global drop_password
    user_password = message.text.strip()
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    builder = InlineKeyboardBuilder()
    if user_password == drop_password:
        await database.give_drop_access_to_user(message.from_user.id)
        await give_redis_drop_access(message.from_user.id)
        text = "✅ Пароль введён успешно.\nТеперь у тебя есть доступ к дропу."
        builder.button(text="Хорошо", callback_data="same2")
    else:
        text = "❌ Пароль не верный. Можешь попробовать ввести ещё раз:"
        builder.button(text="❌ Отмена", callback_data="same2")
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
    new_message = await bot.send_message(
        chat_id=message.chat.id,
        text=text,
        reply_markup=builder.as_markup()
    )
    await state.update_data(last_message_id=new_message.message_id)



@dp.callback_query(lambda c: c.data.startswith("choose_size:"))
async def choose_size_for_add_basket(callback_query: types.CallbackQuery):
    index = await get_brand_and_index(callback_query.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    back_mode = index["back_mode"]
    products = await get_products_from_index(watch_mode, brand)
    if products == []:
        await start_handler(message=callback_query.message, isStart=True, isReboot=True)
        return
    product = products[current_index]
    if not products:
        await callback_query.answer("Ошибка, перезапусти бота")
        return
    photo_url = product["photo_url"]

    global sizes_cache
    sizes = sizes_cache[product["art"]]

    builder = InlineKeyboardBuilder()

    callback_data = callback_query.data.split(":")[1]
    if callback_data == "for_basket":
        text = "Выбери размер (EU) для добавления в корзину:"
        for size in sizes:
            builder.button(text=size, callback_data=f"add_in_basket:{size}:normal")
        #buttons = [InlineKeyboardButton(text=size, callback_data=f"add_in_basket:{size}:normal") for size in sizes]
    elif callback_data == "for_order":
        text = "Выбери размер (EU) для оформления заказа:"
        for size in sizes:
            builder.button(text=size, callback_data=f"buy_from_catalog:{size}")
        #buttons = [InlineKeyboardButton(text=size, callback_data=f"buy_from_catalog:{size}") for size in sizes]
    elif callback_data == "for_edit_basket":
        text = "Выбери новый размер (EU):"
        back_mode = callback_query.data.split(":")[2]
        for size in sizes:
            builder.button(text=size, callback_data=f"add_in_basket:{size}:change:{back_mode}")
        #buttons = [InlineKeyboardButton(text=size, callback_data=f"add_in_basket:{size}:change:{back_mode}") for size in sizes]

    #builder.row(*buttons)
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="📏 Выбрать в мм", callback_data=f"mm{callback_query.data}"))
    if callback_data != "for_edit_basket":
        builder.row(InlineKeyboardButton(text="◀️ Вернутся к каталогу", callback_data="same"))
    else:
        arg = f"{product['art']}from_basket{callback_query.message.message_id}from_basket{back_mode}"
        builder.row(InlineKeyboardButton(text="◀️ Назад", url=f"https://t.me/nikix_store_bot?start={arg}"))

    await bot.edit_message_media(
        media=types.InputMediaPhoto(media=photo_url, caption=text, parse_mode="HTML"),
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        reply_markup=builder.as_markup()
    )



@dp.callback_query(lambda c: c.data.startswith("mm"))
async def choose_size_mm(callback_query: types.CallbackQuery):
    index = await get_brand_and_index(callback_query.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    back_mode = index["back_mode"]
    products = await get_products_from_index(watch_mode, brand)
    if products == []:
        await start_handler(message=callback_query.message, isStart=True, isReboot=True)
        return
    product = products[current_index]
    if not products:
        await callback_query.answer("Ошибка, перезапусти бота")
        return
    photo_url = product["photo_url"]

    global sizes_cache
    sizes = sizes_cache[product["art"]]
    builder = InlineKeyboardBuilder()
    callback_data = callback_query.data.split(":")[1]

    sizes_length = await get_sizes_length(product["art"])
    if callback_data == "for_basket":
        text = "Выбери размер (мм) для добавления в корзину:"
        for size in sizes:
            builder.button(text=sizes_length[str(size)], callback_data=f"add_in_basket:{size}:normal")
        # buttons = [InlineKeyboardButton(text=size, callback_data=f"add_in_basket:{size}:normal") for size in sizes]
    elif callback_data == "for_order":
        text = "Выбери размер (мм) для оформления заказа:"
        for size in sizes:
            builder.button(text=sizes_length[str(size)], callback_data=f"buy_from_catalog:{size}")
        # buttons = [InlineKeyboardButton(text=size, callback_data=f"buy_from_catalog:{size}") for size in sizes]
    elif callback_data == "for_edit_basket":
        text = "Выбери новый размер (мм):"
        back_mode = callback_query.data.split(":")[2]
        for size in sizes:
            builder.button(text=sizes_length[str(size)], callback_data=f"add_in_basket:{size}:change:{back_mode}")
        # buttons = [InlineKeyboardButton(text=size, callback_data=f"add_in_basket:{size}:change:{back_mode}") for size in sizes]

    # builder.row(*buttons)
    builder.adjust(3) 
    builder.row(InlineKeyboardButton(text="📏 Выбрать в EU", callback_data=callback_query.data.split("mm")[1]))
    if callback_data != "for_edit_basket":
        builder.row(InlineKeyboardButton(text="◀️ Вернутся к каталогу", callback_data="same"))
    else:
        arg = f"{product['art']}from_basket{callback_query.message.message_id}from_basket{back_mode}"
        builder.row(InlineKeyboardButton(text="◀️ Назад", url=f"https://t.me/nikix_store_bot?start={arg}"))

    await bot.edit_message_media(
        media=types.InputMediaPhoto(media=photo_url, caption=text, parse_mode="HTML"),
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        reply_markup=builder.as_markup()
    )



@dp.callback_query(lambda c: c.data.startswith("add_in_basket"))
async def add_in_basket_product(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    index = await get_brand_and_index(user_id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    back_mode = index["back_mode"]
    products = await get_products_from_index(watch_mode, brand)
    product = products[current_index]

    callback_data = callback_query.data.split(":")
    size = callback_data[1]
    product_name = product["name"]
    photo_url = product["photo_url"]

    await database.add_to_basket(user_id=user_id, art=product["art"], size=size)
    await callback_query.answer("Кроссовки добавлены в корзину")

    builder = InlineKeyboardBuilder()
    if callback_data[2] == "normal":
        text = f"✅ <b>{product_name}</b> {size}-го размера успешно добавлено в корзину"
        builder.button(text="🛒 Перейти в корзину", callback_data="go_to_basket_from_catalog")
        builder.button(text="◀️ Вернутся к каталогу", callback_data="same")
        builder.adjust(1)
    else:
        data = await state.get_data()
        back_mode = callback_data[3]
        basket_id_to_delete = data.get("basket_id_to_delete")
        text = f"✅ Размер <b>{product_name}</b> изменён на {size}"
        builder.button(text="Готово", callback_data=back_mode)
        await database.clear_basket(user_id=user_id, basket_id=basket_id_to_delete, is_all=0)

    await bot.edit_message_media(
        media=types.InputMediaPhoto(media=photo_url, caption=text, parse_mode="HTML"),
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        reply_markup=builder.as_markup()
    )
    logger.info(f"@{callback_query.from_user.username} добавил товар в корзину")



@dp.callback_query(lambda c: c.data in ["go_to_basket_from_catalog", "go_to_basket_from_menu"])
async def go_to_basket_callback(callback: types.CallbackQuery, state: FSMContext):
    await go_to_basket(callback, state)

async def go_to_basket(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    basket = await database.fetch_basket(user_id)
    back_mode = callback_query.data
    index = await get_brand_and_index(callback_query.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    back_mode_prob = index["back_mode"]
    if (back_mode_prob == "0") or ("search" in back_mode_prob):
        await upload_user_index_brand(user_id=user_id, current_index=current_index, brand=brand, watch_mode=watch_mode,
                                      back_mode=back_mode_prob)
        # Если перешли в корзину из каталога или поиска, то записываем back_mode в state, так как при просмотре корзины он может измениться
        await state.update_data(basket_back_mode=back_mode_prob)
    else:
        # Если же мы перешли в корзину из просмотра товара, то берем заранее записанный back_mode из state, потому что в redis храниться перезаписанный (для возврата в корзину)
        data = await state.get_data()
        basket_back_mode = data.get("basket_back_mode")
        await upload_user_index_brand(user_id=user_id, current_index=current_index, brand=brand, watch_mode=watch_mode,
                                      back_mode=basket_back_mode)
    builder = InlineKeyboardBuilder()

    flag = 0
    if basket:
        total_price_int = 0
        text = "<b>🛒 Твоя корзина:</b>\n\n"
        i = 1
        for item in basket:
            # price = await format_number(item["price"])
            sizes_length = await get_sizes_length(item["art"])
            if item['size'] in sizes_length:
                mm = f" ({sizes_length[(item['size'])]} мм)"
            else:
                mm = ""
            arg = f"{item["art"]}zov{callback_query.message.message_id}zov{back_mode}zov{item['basket_id']}"
            if item["is_drop"] == 0:
                price = item["price"]
            else:
                price = item["drop_price"]
            total_price_int += price
            price = await format_number(price)
            text += (
                f"{i}. <a href='https://t.me/nikix_store_bot?start={arg}'><b>{item['name']}</b></a>\n"
                f"Размер: {item['size']} EU {mm}\n"
                f"Стоимость: {price} ₽\n\n"
            )
            i += 1
        total_price = await format_number(total_price_int)
        text += f"Всего: <b>{total_price}</b> ₽\n"
        text += f"Выбери действие ниже:"

        builder.button(text="📦 Оформить заказ", callback_data=f"buy_from_basket:{back_mode}")
        builder.button(text="🗑 Очистить корзину", callback_data=f"clear_basket:{back_mode}")
    else:
        text = "Твоя корзина пуста"
        builder.button(text="👟 В каталог", callback_data="catalog")
        builder.button(text="◀️ Вернуться в меню", callback_data="back_to_start")
        flag = 1

    if callback_query.data == "go_to_basket_from_catalog" and flag == 0:
        builder.button(text="◀️ Вернуться к каталогу", callback_data="same")
        back_mode = "go_to_basket_from_catalog"
    elif callback_query.data == "go_to_basket_from_menu" and flag == 0:
        builder.button(text="◀️ Вернуться в меню", callback_data="back_to_start")
        back_mode = "go_to_basket_from_menu"
    builder.adjust(1)

    try:
        # Пытаемся редактировать сообщение как текст
        await bot.edit_message_text(
            text=text,
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        # Если редактирование не удалось (например, сообщение содержит фото), отправляем новое
        await bot.delete_message(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id
        )
        new_message = await bot.send_message(chat_id=callback_query.message.chat.id, text="Корзина")

        text = "<b>🛒 Твоя корзина:</b>\n\n"
        i = 1
        for item in basket:
            if item["is_drop"] == 0:
                price = item["price"]
            else:
                price = item["drop_price"]
            price = await format_number(price)
            sizes_length = await get_sizes_length(item["art"])
            if item['size'] in sizes_length:
                mm = f" ({sizes_length[(item['size'])]} мм)"
            else:
                mm = ""
            arg = f"{item["art"]}zov{new_message.message_id}zov{back_mode}zov{item['basket_id']}"
            text += (
                f"{i}. <a href='https://t.me/nikix_store_bot?start={arg}'><b>{item['name']}</b></a>\n"
                f"Размер: {item['size']} EU {mm}\n"
                f"Стоимость: {price} ₽\n\n"
            )
            i += 1
        text += f"Всего: <b>{total_price}</b> ₽\n"
        text += f"Выбери действие ниже:"

        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=new_message.message_id ,
            text=text,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )



@dp.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start_(callback_query: types.CallbackQuery):
    await start_handler(callback_query.message, isStart=False)



@dp.callback_query(lambda c: c.data.startswith("clear_basket:"))
async def clear_basket_to_user(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    await database.clear_basket(user_id=user_id, basket_id=0, is_all=1)

    back_mode = callback_query.data.split(":")[1]
    text = "🧹 Корзина очищена"
    builder = InlineKeyboardBuilder()
    if back_mode == "go_to_basket_from_catalog":
        builder.button(text="◀️ Вернуться к каталогу", callback_data="same")
    elif back_mode == "go_to_basket_from_menu":
        builder.button(text="👟 В каталог", callback_data="catalog")
        builder.button(text="◀️ Вернуться в меню", callback_data="back_to_start")
        builder.adjust(1)
    await bot.edit_message_text(
        text=text,
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )



@dp.callback_query(lambda c: c.data.startswith("delete_product_basket:"))
async def delete_product_basket(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = callback.data.split(":")
    back_mode = data[1]
    data = await state.get_data()
    basket_id = data.get("basket_id_to_delete")
    await database.clear_basket(user_id=user_id, basket_id=basket_id, is_all=0)
    text = "Пара убрана из корзины"
    builder = InlineKeyboardBuilder()
    builder.button(text="Готово", callback_data=back_mode)
    await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    await bot.send_message(
        text=text,
        chat_id=callback.message.chat.id,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    #await show_basket_settings(callback=callback)



# *************************************************************************************************************
# *************************************************************************************************************
# Мои заказы
@dp.callback_query(lambda c: c.data.startswith("my_orders"))
async def show_my_orders(callback: types.CallbackQuery):
    mode = callback.data.split(":")[1]
    if mode == "sd":
        new_message = await bot.send_message(text="Мои заказы", chat_id=callback.message.chat.id)
        message_id = new_message.message_id
    else:
        message_id = callback.message.message_id
    user_id = callback.from_user.id
    orders = await database.fetch_orders(user_id)
    orders = orders[::-1]
    builder = InlineKeyboardBuilder()
    if orders:
        text = "📦 <b>Твои заказы:</b>\n(Нажми на номер заказа, чтобы узнать о нём подробнее)\n\n"
        for order in orders:
            arg = f"{order['id']}show_order{message_id}"
            try:
                status = await decrypt_status(int(order["status"]))
            except Exception:
                status = "Неизвестен"
                logger.error(f"Неизвестен статус: {order['id']}")
                await send_admin_message(f"Неизвестен статус: {order['id']}")
            text += (f"<a href='https://t.me/nikix_store_bot?start={arg}'><b>№{order['id']}</b></a>\n"
                     f"<b>Статус:</b> {status}\n\n")
    else:
        text = "У тебя нет заказов"
    support_link = await get_support_link()
    builder.button(text="💬 Поддержка", url=support_link)
    builder.button(text="◀️ Вернуться в меню", callback_data="catalog_back")
    builder.adjust(1)
    await bot.edit_message_text(
        text=text,
        chat_id=callback.message.chat.id,
        message_id=message_id,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=builder.as_markup()
    )


async def show_order(message, order_id, last_message_id):
    id = int(order_id) - 2000
    orders = await database.fetch_orders(user_id=message.chat.id, id=id)
    order = orders[0]
    status = await decrypt_status(int(order["status"]))
    text = (f"Заказ №<b>{order_id}</b>\n"
            f"Статус: {status}\n\n"
            f"🚚 <b>Способ доставки:</b> {order['delivery_way']}\n"
            f"🏠 <b>Адрес:</b> {order['address']}\n"
            f"👟 <b>Примерка:</b> {order['preview']}\n"
            f"💵 <b>Оплата:</b> {order['pay_way']}\n"
            f"👤 <b>ФИО:</b> {order['fio']}\n"
            f"☎️ <b>Номер телефона:</b> {order['phone']}\n"
            f"💬 <b>Комментарий к заказу:</b> {order['comment']}\n\n")

    total_price = 0
    i = 1
    for product in order["products"]:
        price = await format_number(product['price'])
        total_price += product['price']
        sizes_length = await get_sizes_length(product["art"])
        text += (f"{i}. <a href='{product['channel_url']}'><b>{product['name']}</b></a>\n"
                 f"<b>Артикул:</b> {product['art']}\n"
                 f"<b>Размер:</b> {product['size']} (EU) ({sizes_length[product['size']]} мм)\n"
                 f"<b>Стоимость:</b> {price} ₽\n\n")
        i += 1

    total_price += order["delivery_price"]
    total_price = await format_number(total_price)
    text += (f"<b>Доставка:</b> {order["delivery_price"]} ₽\n"
             f"<b>Всего:</b> {total_price} ₽")

    builder = InlineKeyboardBuilder()
    support_link = await get_support_link()
    builder.button(text="💬 Поддержка", url=support_link)
    if order["status"] == '0':
        builder.button(text="❌ Отменить заказ", callback_data=f"sure_cancel:{id}")
    builder.button(text="◀️ Назад", callback_data="my_orders:ed")
    builder.adjust(1)

    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=last_message_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=builder.as_markup()
    )


@dp.callback_query(lambda c: c.data.startswith("sure_cancel"))
async def sure_to_cancel(callback: types.CallbackQuery):
    id = callback.data.split(":")[1]
    text = f"Ты уверен, что хочешь отменить заказ #{int(id) + 2000}?"
    builder = InlineKeyboardBuilder()
    builder.button(text="Нет", callback_data="my_orders:ed")
    builder.button(text="Да", callback_data=f"cancel_order:{id}")
    builder.adjust(2)
    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=text,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(lambda c: c.data.startswith("cancel_order"))
async def cancel_to_order(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1]) + 2000
    callback_data = f"set_order_status:4:{order_id}"
    await change_status(callback_data, 0)
    text = f"❌ Заказ #{order_id} отменён"
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Ок", callback_data="my_orders:ed")
    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )


# ***************************************************************************************************************
# ********************************Оформление заказа: из корзины и каталога***************************************
class OrderState(StatesGroup):
    waiting_for_client_fio = State()
    waiting_for_client_address = State()
    waiting_for_client_phone = State()
    waiting_for_client_comment = State()
    waiting_none = State()



@dp.callback_query(lambda c: c.data.startswith("buy_from_catalog") or c.data.startswith("buy_from_basket"))
async def buy(callback: types.CallbackQuery, state: FSMContext):
    global sizes_cache
    user_id = callback.from_user.id
    callback_data = callback.data.split(":")
    callback_mode = callback_data[0]
    back_mode = callback_data[1]

    if callback_mode == "buy_from_basket":
        basket = await database.fetch_basket(user_id=user_id)
        await state.update_data(last_message_id=callback.message.message_id, back_mode=back_mode, buy_from="b")
        error_text = "К сожалению, сейчас у нас нет в наличии "
        flag = 0
        for item in basket:
            if item["size"] not in sizes_cache[item["art"]]:
                flag = 1
                error_text += f"<a href='{item['channel_url']}'>{item['name']}</a> {item['size']}-го размера\n"
                await database.clear_basket(user_id=user_id, basket_id=item["basket_id"], is_all=0)
        if flag == 1:
            builder = InlineKeyboardBuilder()
            count = await database.fetch_basket(user_id=user_id, count=True)
            if count != 0:
                builder.button(text="📦 Всё равно сделать заказ", callback_data=f"order_anyway:{back_mode}")
            builder.button(text="👟 Найти замену", callback_data="catalog")
            builder.button(text="◀️ Назад", callback_data=back_mode)
            builder.adjust(1)
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=error_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=builder.as_markup()
            )
        else:
            await buy2(callback, state)
    else:
        await buy2(callback, state)
        await state.update_data(buy_from="c")
    await send_admin_message(f"@{callback.from_user.username} (id: {user_id}) начал оформлять заказ")

@dp.callback_query(lambda c: c.data.startswith("order_anyway"))
async def let_buy2(callback: types.CallbackQuery, state: FSMContext):
    await buy2(callback, state)



async def buy2(callback, state):
    callback_data = callback.data.split(":")
    mode = callback_data[0]

    text = "🚚 Выбери способ доставки:\n(Примерка есть только в СДЭК)"
    builder = InlineKeyboardBuilder()

    if mode == "buy_from_catalog":
        size = callback_data[1]
        index = await get_brand_and_index(callback.from_user.id)
        brand = index["brand"]
        current_index = int(index["current_index"])
        watch_mode = index["watch_mode"]
        products = await get_products_from_index(watch_mode, brand)
        product = products[current_index]
        if products == []:
            await start_handler(message=callback.message, isStart=True, isReboot=True)
            return
        if product["price"] == 0:
            err_text = "К сожалению стоимость не указана. Пожалуйста обратись в поддержку"
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="Ок", callback_data="same")
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
            await bot.send_message(chat_id=callback.message.chat.id, text=err_text, reply_markup=keyboard.as_markup())
            return
        if product["is_drop"] == "1":
            product["price"] = product["drop_price"]
        builder.button(text="СДЭК", callback_data="cdek")
        builder.button(text="Почта России", callback_data="pochta")
        builder.button(text="❌ Отмена", callback_data="same")
        builder.adjust(2, 1)
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        new_message = await bot.send_message(text="Оформление заказа ...", chat_id=callback.message.chat.id)
        new_message_id = new_message.message_id
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=new_message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        await state.update_data(product_buy={"product": product, "size": size},last_message_id=new_message_id, back_mode="same")
    else:
        back_mode = callback_data[1]
        builder.button(text="СДЭК", callback_data="cdek")
        builder.button(text="Почта России", callback_data="pochta")
        builder.button(text="❌ Отмена", callback_data=back_mode)
        builder.adjust(2, 1)
        await bot.edit_message_text(
        text=text,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        reply_markup=builder.as_markup()
        )



@dp.callback_query(lambda c: c.data == "cdek")
async def choose_preview(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        await callback.answer(text="Извини, бот был перезапущен. Пожалуйста начни оформлять заказ заново", show_alert=True)
        return
    back_mode = data.get("back_mode")
    if back_mode == "same":
        count = 1
        pynct_price = 300
        home_price = 500
    else:
        count = await database.fetch_basket(user_id=callback.from_user.id, count=True)
        pynct_price = 300
        home_price = 500
        for i in range(count-1):
            pynct_price += 150
            home_price += 200
    if count == 1:
        count_text = ""
    elif count <= 4:
        count_text = f" Стоимость доставки указана за {count} пары"
    elif count >= 5:
        count_text = f" Стоимость доставки указана за {count} пар"
    text = f"<b>Выбери куда доставить кроссовки:</b>\n(Доставку можно оплатить также при получении.{count_text})"
    builder = InlineKeyboardBuilder()
    builder.button(text=f"В пункт выдачи СДЕК ({pynct_price} ₽)", callback_data="pynktCDEK")
    builder.button(text=f"В постамат СДЕК ({pynct_price} ₽)", callback_data="postCDEK")
    builder.button(text=f"Курьером до дома ({home_price} ₽)", callback_data="deliver_to_home_CDEK")
    builder.button(text="❌ Отмена", callback_data=back_mode)
    builder.adjust(1)
    await bot.edit_message_text(
        text=text,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(lambda c: c.data in ["pynktCDEK", "deliver_to_home_CDEK", "postCDEK", "pochta"])
async def enter_address(callback: types.CallbackQuery, state: FSMContext):
    callback_data = callback.data
    builder = InlineKeyboardBuilder()
    if callback_data == "pynktCDEK":
        text = "🏠 Напиши адрес <b>пункта выдачи СДЕК</b> куда доставить кроссовки, в формате: Город, улица, дом\n"
        delivery_mode = "Пункт выдачи СДЕК"
        builder.button(text="🗺 Найти в Яндекс Картах", url="https://yandex.ru/maps/?mode=search&text=CDEK")
    elif callback_data == "deliver_to_home_CDEK":
        text = "🏠 Напиши адрес куда курьер доставит кроссовки в формате: Город, улица, дом, квартира"
        delivery_mode = "Курьерская доставка СДЕК"
    elif callback_data == "postCDEK":
        text = "🏠 Напиши адрес постамата СДЕК куда доставить кроссовки в формате: Город, улица, дом\n"
        delivery_mode = "Постамат СДЕК"
        builder.button(text="🗺 Найти в Яндекс Картах", url="https://yandex.ru/maps/?mode=search&text=CDEK")
    elif callback_data == "pochta":
        text = "🏠 Напиши адрес для доставки почтой в формате: Индекс, город, улица, дом, квартира\n(Индекс ближайшей почты можешь посмотреть в картах 👇)"
        delivery_mode = "Почта России"
        builder.button(text=" 🗺 Найти в Яндекс Картах", url="https://yandex.ru/maps/?mode=search&text=%D0%9F%D0%BE%D1%87%D1%82%D0%B0%D0%A0%D0%BE%D1%81%D1%81%D0%B8%D0%B8")
    data = await state.get_data()
    if not data:
        await callback.answer(text="Извини, бот был перезапущен. Пожалуйста начни оформлять заказ заново", show_alert=True)
        return
    back_mode = data.get("back_mode")
    builder.button(text="❌ Отмена", callback_data=back_mode)
    builder.adjust(1)
    await bot.edit_message_text(
        text=text,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await state.update_data(delivery_mode=delivery_mode, last_message_id=callback.message.message_id)
    await state.set_state(OrderState.waiting_for_client_address)

@dp.message(OrderState.waiting_for_client_address)
async def is_preview(message: types.Message, state: FSMContext):
    address = str(message.text)
    await state.update_data(address=address)
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    delivery_mode = data.get("delivery_mode")
    back_mode = data.get("back_mode")
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    if delivery_mode in ["Пункт выдачи СДЕК", "Курьерская доставка СДЕК"]:
        text = "👟 Нужна ли примерка?"
        builder = InlineKeyboardBuilder()
        builder.button(text="✔Да", callback_data="preview_yes")
        builder.button(text="✖Нет", callback_data="preview_no")
        builder.button(text="❌ Отмена", callback_data=back_mode)
        builder.adjust(2, 1)
        await bot.edit_message_text(
            text=text,
            chat_id=message.chat.id,
            message_id=last_message_id,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    elif delivery_mode == "Постамат СДЕК":
        await choose_paying_way(chat_id=message.chat.id, state=state)
    else:
        await enter_fio(message=message, state=state)

@dp.callback_query(lambda c: c.data in ["preview_yes", "preview_no"])
async def get_preview_info(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "preview_yes":
        primerka = "нужна"
    if callback.data == "preview_no":
        primerka = "не нужна"
    data = await state.get_data()
    if not data:
        await callback.answer(text="Извини, бот был перезапущен. Пожалуйста начни оформлять заказ заново",show_alert=True)
        return
    await state.update_data(is_preview=primerka)
    await choose_paying_way(chat_id=callback.message.chat.id, state=state)


async def choose_paying_way(chat_id, state):
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    back_mode = data.get("back_mode")

    text = "Выбери способ оплаты:\n(Доставка до пункта выдачи бесплатно, курьером - 200₽, если оплатишь сразу)"
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить сейчас", callback_data="pay_now")
    builder.button(text="🛍 Оплатить при получении", callback_data="pay_after_preview")
    builder.button(text="❌ Отмена", callback_data=back_mode)
    builder.adjust(1)
    await bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=last_message_id,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(lambda c: c.data.startswith("pay"))
async def get_paying_way(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "pay_now":
        pay_way = "сразу"
    else:
        pay_way = "при получении"
        data = await state.get_data()
        if not data:
            await callback.answer(text="Извини, бот был перезапущен. Пожалуйста начни оформлять заказ заново",show_alert=True)
            return
        buy_from = data.get("buy_from")
        basket_count = await database.fetch_basket(user_id=callback.from_user.id, count=True)
        if (buy_from == "b") and (basket_count > 3):
            text = "К сожалению, заказать с оплатой при получении можно максимум 3 пары"
            builder = InlineKeyboardBuilder()
            builder.button(text="💳 Оплатить сейчас", callback_data="pay_now")
            builder.button(text="🛒 Перейти в корзину", callback_data="go_to_basket_from_menu")
            builder.adjust(1)
            await bot.edit_message_text(
                text=text,
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
            return
    await state.update_data(pay_way=pay_way)
    await enter_fio(message=callback.message, state=state)


async def enter_fio(message, state):
    data = await state.get_data()
    last_message_id = data.get("last_message_id", 0)
    back_mode = data.get("back_mode")

    text = "👤 Напиши Твои ФИО для заказа:"
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=back_mode)
    await state.set_state(OrderState.waiting_for_client_fio)
    await bot.edit_message_text(
        text=text,
        chat_id=message.chat.id,
        message_id=last_message_id,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@dp.message(OrderState.waiting_for_client_fio)
async def enter_phone(message: types.Message, state: FSMContext):
    fio = message.text
    user_order_id = message.from_user.id
    data = await state.get_data()
    back_mode = data.get("back_mode")
    last_message_id = data.get("last_message_id")
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=back_mode)
    text = "☎️ Напиши Твой номер телефона для оформления заказа:"
    await bot.edit_message_text(
        text=text,
        chat_id=message.chat.id,
        message_id=last_message_id,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await state.update_data(fio=fio, user_order_id=user_order_id)
    await state.set_state(OrderState.waiting_for_client_phone)

@dp.message(OrderState.waiting_for_client_phone)
async def enter_comment(message: types.Message, state: FSMContext):
    phone = str(message.text)
    data = await state.get_data()
    back_mode = data.get("back_mode")
    last_message_id = data.get("last_message_id")

    text = "💬 Напиши, если нужно, комментарий к заказу или нажми «Пропустить комментарий»"
    builder = InlineKeyboardBuilder()
    builder.button(text="➡️ Пропустить комментарий", callback_data="check")
    builder.button(text="❌ Отмена", callback_data=back_mode)
    builder.adjust(1)
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    await bot.edit_message_text(
        text=text,
        chat_id=message.chat.id,
        message_id=last_message_id,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await state.set_state(OrderState.waiting_for_client_comment)
    await state.update_data(phone=phone)

@dp.message(OrderState.waiting_for_client_comment)
async def get_comment(message: types.Message, state: FSMContext):
    comment = str(message.text)
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    await state.update_data(comment=comment)
    await state.set_state(OrderState.waiting_none)
    await check_data(chat_id=message.chat.id, state=state, user_id=message.from_user.id)

@dp.callback_query(lambda c: c.data == "check")
async def check_data_no_comments(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        await callback.answer(text="Извини, бот был перезапущен. Пожалуйста начни оформлять заказ заново",
                              show_alert=True)
        return
    await check_data(chat_id=callback.message.chat.id, state=state, user_id=callback.from_user.id)
    await state.set_state(OrderState.waiting_none)



async def check_data(chat_id, state, user_id):
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    back_mode = data.get("back_mode")
    delivery_mode = data.get("delivery_mode")
    address = data.get("address")
    is_preview = data.get("is_preview")
    phone = data.get("phone")
    fio = data.get("fio")
    comment = data.get("comment", "нет")
    pay_way = data.get("pay_way")

    if delivery_mode == "Пункт выдачи СДЕК":
        delivery_price = 300
        address_data = f"<b>Адрес пункта:</b> {address}"
    elif delivery_mode == "Курьерская доставка СДЕК":
        delivery_price = 500
        address_data = f"<b>Адрес:</b> {address}"
    elif delivery_mode == "Постамат СДЕК":
        delivery_price = 300
        address_data = f"<b>Адрес постамата:</b> {address}"
        is_preview = "не доступна при заказе в постамат"
    else:
        delivery_price = 300
        address_data = f"<b>Адрес:</b> {address}"
        is_preview = "не доступна при заказе Почтой России"
        pay_way = "сразу, так как отправка Почтой"
    if pay_way == "сразу":
        if delivery_mode in ["Пункт выдачи СДЕК", "Постамат СДЕК", "Почта России"]:
            delivery_price = 0
        else:
            delivery_price = 200

    text = (f"<b>Проверь пожалуйста данные:</b>\n\n"
            f"🚚 <b>Способ доставки:</b> {delivery_mode}\n"
            f"🏠 {address_data}\n"
            f"👟 <b>Примерка:</b> {is_preview}\n"
            f"💵 <b>Оплата:</b> {pay_way}\n"
            f"👤 <b>ФИО:</b> {fio}\n"
            f"☎️ <b>Номер телефона:</b> {phone}\n"
            f"💬 <b>Комментарий к заказу:</b> {comment}\n\n")
    if back_mode == "same":
        product_buy = data.get("product_buy")
        buying_product = product_buy["product"]
        size = product_buy["size"]
        price = await format_number(buying_product['price'])
        total_price = await format_number(buying_product['price'] + delivery_price)
        if delivery_price == 0:
            delivery_price_text = "Бесплатно"
        else:
            delivery_price_text = f"{delivery_price} ₽"
        sizes_length = await get_sizes_length(buying_product["art"])
        text += (f"<a href='{buying_product['channel_url']}'><b>{buying_product['name']}</b></a>\n"
                 f"<b>Артикул:</b> {buying_product['art']}\n"
                 f"<b>Размер:</b> {size} (EU) ({sizes_length[size]} мм)\n"
                 f"<b>Стоимость:</b> {price} ₽\n\n"
                 f"<b>Доставка:</b> {delivery_price_text}\n"
                 f"<b>Итого:</b> {total_price} ₽")
        button_data = f"buy_from_catalog:{size}"
    else:
        basket = await database.fetch_basket(user_id)
        i = 1
        total_price = 0
        for product in basket:
            if product["is_drop"] == 0:
                price = await format_number(product['price'])
                total_price += product['price']
            else:
                price = await format_number(product['drop_price'])
                total_price += product['drop_price']
            sizes_length = await get_sizes_length(product["art"])
            text += (f"<b>{i}.</b> <a href='{product['channel_url']}'><b>{product['name']}</b></a>\n"
                     f"<b>Артикул:</b> {product['art']}\n"
                     f"<b>Размер:</b> {product['size']} (EU) ({sizes_length[product['size']]})\n"
                     f"<b>Стоимость:</b> {price} ₽\n\n")
            i += 1
        total_price += delivery_price
        total_price = await format_number(total_price)
        if delivery_price == 0:
            delivery_price_text = "бесплатно"
        else:
            delivery_price_text = f"{delivery_price} ₽"
        text += (f"<b>Доставка:</b> {delivery_price_text}\n"
                 f"<b>Итого:</b> {total_price} ₽")
        button_data = f"buy_from_basket:{back_mode}"

    builder = InlineKeyboardBuilder()
    support_link = await get_support_link()
    builder.button(text="✅ Данные верны", callback_data=f"order_is_ok")
    builder.button(text="🔄 Ввести заново", callback_data=button_data)
    builder.button(text="💬 Поддержка", url=support_link)
    builder.button(text="❌ Отмена", callback_data=back_mode)
    builder.adjust(1)
    await bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=last_message_id,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=builder.as_markup()
    )
    await state.update_data(delivery_price=delivery_price, is_preview=is_preview, pay_way=pay_way)



@dp.callback_query(lambda c: c.data == "order_is_ok")
async def make_order(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    if not data:
        await callback.answer(text="Извини, бот был перезапущен. Пожалуйста начни оформлять заказ заново",
                              show_alert=True)
        return
    back_mode = data.get("back_mode")
    delivery_mode = data.get("delivery_mode")
    address = data.get("address")
    is_preview = data.get("is_preview")
    phone = data.get("phone")
    fio = data.get("fio")
    comment = data.get("comment", "нет")
    pay_way = data.get("pay_way")
    delivery_price = data.get("delivery_price")
    builder = InlineKeyboardBuilder()
    if back_mode == "same":
        product_buy = data.get("product_buy")
        buying_product = product_buy["product"]
        buying_product["size"] = product_buy["size"]
        basket = []
        basket.append(buying_product)
    else:
        basket_db = await database.fetch_basket(user_id)
        basket = []
        for item in basket_db:
            if item["is_drop"] == 1:
                item["price"] = item["drop_price"]
            basket.append(item)
    builder.button(text="📦 Мои заказы", callback_data="my_orders:ed")
    builder.button(text="◀️ В меню", callback_data="catalog_back")
    builder.adjust(1)
    text = "✅ Заказ принят. Тебе ответят в ближайшее время.\nПо вопросам можешь писать в <a href='https://t.me/nikix_info'>поддержку</a>"
    order_id = await database.add_order(user_id=user_id, basket=basket, fio=fio, phone_number=phone, address=address, delivery_way=delivery_mode, preview=is_preview, pay_way=pay_way, status=0, comment=comment, delivery_price=delivery_price)
    await bot.edit_message_text(
        text=text,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=builder.as_markup()
    )
    user_info = await bot.get_chat(user_id)
    first_name = user_info.first_name
    username = user_info.username
    text_for_chat = (f"✅ Новый заказ! #<b>{order_id}</b>\n"
                     f"Статус: 📝 Оформлен\n\n"
                     f"Клиент: @{username}\n"
                     f"Имя: {first_name}\n"
                     f"ID: {user_id}\n\n")
    text_for_chat += callback.message.text
    keyboard = InlineKeyboardBuilder()
    arg = f"admin_send_{user_id}"
    keyboard.button(text="🔄 Изменить статус заказа", url=f"https://t.me/nikix_store_bot?start=status_{order_id}")
    keyboard.button(text="💬 Написать клиенту через бота", url=f"https://t.me/nikix_store_bot?start={arg}")
    keyboard.button(text="👤 Написать клиенту в лс", url=f"https://t.me/{username}")
    keyboard.adjust(1)
    channel_message = await bot.send_message(text=text_for_chat, chat_id=CHAT_ORDERS_ID, parse_mode="HTML", reply_markup=keyboard.as_markup())
    trying = await database.change_channel_id_for_order(order_id=(order_id-2000), message_id=channel_message.message_id)
    if trying != 1:
        await send_admin_message(message=f"Ошибка создания заказа {order_id}: {trying}, изменения статуса не будут видны")
    if back_mode != "same":
        await database.clear_basket(user_id=user_id, basket_id=0, is_all=1)



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Поиск
class SearchState(StatesGroup):
    waiting_for_art = State()
    waiting_none = State()



@dp.callback_query(lambda c: c.data == "search")
async def choose_search_way(callback: types.CallbackQuery, state: FSMContext):
    text = "Выбери вариант поиска:"
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🌤 Поиск по сезону", callback_data="search_from_season")
    keyboard.button(text="📏 Поиск по размеру", callback_data="search_from_size")
    keyboard.button(text="#️⃣ Поиск по артикулу", callback_data="search_from_art")
    keyboard.button(text="◀️ В меню", callback_data="catalog_back")
    keyboard.adjust(1)
    await bot.edit_message_text(
        text=text,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("search_from"))
async def choose_search_param(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data
    keyboard = InlineKeyboardBuilder()
    if mode == "search_from_season":
        text = "Выбери сезон для поиска:"
        keyboard.button(text="🌦 Демисезон", callback_data="choose_season:demi")
        keyboard.button(text="☀️ Лето", callback_data="choose_season:summer")
        keyboard.button(text="❄️ Зима", callback_data="choose_season:winter")
        keyboard.adjust(1)
    elif mode == "search_from_size":
        text = "Выбери размер для поиска (EU)"
        global sizes_cache
        sizes = []
        sizes_keys = {}
        for key in sizes_cache:
            for size in sizes_cache[key]:
                if size:
                    if "-" not in size:
                        sizes_keys[size] = float(size.split(" ")[0])
                    else:
                        size = size.split("-")[-1]
                        sizes_keys[size] = float(size.split("-")[-1])
        sorted_sizes = dict(sorted(sizes_keys.items(), key=lambda item: item[1]))
        for size in sorted_sizes:
            keyboard.button(text=f"{size}", callback_data=f"choose_size_search:{size}")
        keyboard.adjust(3)
    elif mode == "search_from_art":
        text = "Отправь артикул для поиска:"
        await state.set_state(SearchState.waiting_for_art)
    keyboard.row(InlineKeyboardButton(text="◀️ Назад", callback_data="search"))
    try:
        await bot.edit_message_text(
            text=text,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )
    except Exception:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        await bot.send_message(
            text=text,
            chat_id=callback.message.chat.id,
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )
    await state.update_data(search_back_mode=0, last_message_id=callback.message.message_id)

@dp.callback_query(lambda c: c.data.startswith("choose_season:"))
async def get_season(callback: types.CallbackQuery):
    season = callback.data.split(":")[1]
    if season == "demi":
        data = "демисезон"
        text_season = "демисезона"
    elif season == "summer":
        data = "лето"
        text_season = "летнего сезона"
    elif season == "winter":
        data = "зима"
        text_season = "зимнего сезона"
    else:
        print("Ошибка поиска")
        return
    #products = await database.fetch_products_from_search(mode=0, data=data)
    products = await get_search_products(search_mode="season", param=data)
    if products != []:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        back_mode = "search_from_season"
        await upload_user_index_brand(user_id=callback.from_user.id, current_index=0, brand="none", watch_mode=f"search:season:{data}", back_mode=back_mode)
        await send_or_update_product(callback.message.chat.id, callback.message.message_id, products[0], 0, len(products), is_edit=False, back_mode=back_mode)
    else:
        await callback.answer(text=f"Пока нет кроссовок для {text_season}", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("choose_size_search"))
async def choose_size_search(callback: types.CallbackQuery):
    global sizes_cache
    size = callback.data.split(":")[1]
    #products = await database.fetch_products_from_search(1, arts)
    products = await get_search_products("size", size, sizes_cache)
    if products != []:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        back_mode = "search_from_size"
        await upload_user_index_brand(user_id=callback.from_user.id, current_index=0, brand="all", watch_mode=f"search:size:{size}", back_mode=back_mode)
        await send_or_update_product(callback.message.chat.id, callback.message.message_id, products[0], 0, len(products), is_edit=False, back_mode=back_mode)
    else:
        await callback.answer(f"Пока нет кроссовок {size}-го размера", show_alert=True)
        await send_admin_message(f"Не найдены кроссовки {size} размера")

@dp.message(SearchState.waiting_for_art)
async def get_art_from_message(message: types.Message, state: FSMContext):
    art = message.text.strip().upper()
    products = await get_search_products(search_mode="art", param=art)
    if products != []:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        back_mode = "search_from_art"
        await send_or_update_product(message.chat.id, message.message_id, products[0], 0, len(products), is_edit=False, back_mode=back_mode)
        await state.clear()
    else:
        data = await state.get_data()
        last_message_id = data.get("last_message_id")
        text = f"Не удалось найти кроссовки с артикулом: {art}. Можешь попробовать отправить ещё раз:"
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="◀️ Назад", callback_data="search"))
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        await bot.edit_message_text(
            text=text,
            chat_id=message.chat.id,
            message_id=last_message_id,
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Админ панель
@dp.callback_query(lambda c: c.data == "admin")
async def callback_admin(callback: types.CallbackQuery):
    await admin_panel(callback)

async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id == ADMIN_ID:
        builder = InlineKeyboardBuilder()
        builder.button(text="👤 Пользователи", callback_data="admin_get_users")
        builder.button(text="💬 Рассылка", callback_data="make_mailing")
        builder.button(text="➕ Товары (csv)", callback_data="add_products")
        builder.button(text="🖼 Доп фото", callback_data="add_photo_links")
        builder.button(text="📦 Назначить дроп", callback_data="create_drop")
        builder.button(text="⛔️ Дроп окончен", callback_data="stop_drop")
        builder.button(text="🖥 Прокси", callback_data="edit_proxy")
        builder.button(text="👥 Поддержка", callback_data="edit_support")
        builder.button(text="🌐 Принудительный парсинг", callback_data="admin_parse")
        builder.button(text="📏 Загрузить таблицы размеров (txt)", callback_data="add_sizes_length")
        builder.button(text="👟 Список товаров", callback_data="get_current_product_list")
        builder.button(text="🗑 Удалить все товары", callback_data="sure_admin_delete")
        builder.button(text="◀️ Назад", callback_data="back_to_start")
        builder.adjust(2, 2, 2, 2, 1, 1, 1)
        try:
            await bot.edit_message_text(
                text="🛠 <b>Админ-панель</b>",
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                parse_mode="HTML",
                reply_markup = builder.as_markup()
            )
        except Exception:
            await bot.send_message(
                text="<b>Админ-панель</b>",
                chat_id=callback.message.chat.id,
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
    else:
        await send_admin_message(f"Долбаёб @{callback.from_user.username} с id: {callback.from_user.id} пытался зайти в админ-панель")


# Создание дропа
@dp.callback_query(lambda c: c.data == "create_drop")
async def make_drop(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(adminStates.waiting_for_drop_password)
    text = ("Бот всегда требует пароль, если в товаре is_drop равно 1. "
            "Это окно всего лишь меняет код доступа и дату (только для описания). Дроп появится в боте когда ты загрузишь кроссовки с is_drop равным 1. "
            "Далее просто отправишь пароль в канал в нужное время. "
            "Для выключения дропа нужно изменить параметр is_drop, для этого есть кнопка в админ-панели 'Остановить дроп'\n\n"
            "Отправь код-пароль для дропа. Советую использовать только большие буквы как в anki")
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin")
    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=text,
        reply_markup=builder.as_markup()
    )
    await state.update_data(last_message_id=callback.message.message_id)

@dp.message(adminStates.waiting_for_drop_password)
async def edit_drop_password(message: types.Message, state: FSMContext):
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    password = message.text.strip()
    global drop_password
    drop_password = password
    with open("bot_settings.json", "r") as f:
        jdata = json.load(f)
    jdata["drop_password"] = password
    with open("bot_settings.json", "w") as f:
        json.dump(jdata, f)
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin")
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=last_message_id,
        text=f"✅ Теперь отправь дату и время старта дропа. Это будет использоваться только для описания. Например '13:00 13 мая'",
        reply_markup=builder.as_markup()
    )
    await state.set_state(adminStates.waiting_for_drop_start_date)

@dp.message(adminStates.waiting_for_drop_start_date)
async def edit_drop_password(message: types.Message, state: FSMContext):
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    start_date = message.text.strip()
    with open("bot_settings.json", "r") as f:
        jdata = json.load(f)
    jdata["drop_start_date"] = start_date
    with open("bot_settings.json", "w") as f:
        json.dump(jdata, f)
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin")
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=last_message_id,
        text=f"✅ Хорошо, теперь отправь дату и время окончания дропа. Пример '13:00 14 мая'",
        reply_markup=builder.as_markup()
    )
    await state.set_state(adminStates.waiting_for_drop_stop_date)

@dp.message(adminStates.waiting_for_drop_stop_date)
async def edit_drop_password(message: types.Message, state: FSMContext):
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    stop_date = message.text.strip()
    with open("bot_settings.json", "r") as f:
        jdata = json.load(f)
    jdata["drop_stop_date"] = stop_date
    with open("bot_settings.json", "w") as f:
        json.dump(jdata, f)
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    builder = InlineKeyboardBuilder()
    builder.button(text="Хорошо", callback_data="admin")
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=last_message_id,
        text=f"✅ Пароль и даты установлены. Удачного дропа!",
        reply_markup=builder.as_markup()
    )
    await cache_drop_info()
    await state.clear()
    await database.delete_drop_access()
    drop_access = await database.fetch_drop_access()
    await cache_drop_access(drop_access)


@dp.callback_query(lambda c: c.data == "stop_drop")
async def sure_stop_drop(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="Да", callback_data="sure_stop_drop")
    builder.button(text="Нет", callback_data="admin")
    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="Уверен, что хочешь остановить дроп? Убедись что время дропа подошло к концу.",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(lambda c: c.data == "sure_stop_drop")
async def admin_stop_drop(callback: types.CallbackQuery):
    await database.stop_drop()
    products = await database.fetch_products("all")
    await redis_delete_all_products()  # Если вылезет ошибка то проверить эту строку
    await cache_products(products)
    await database.delete_drop_access()
    drop_access = await database.fetch_drop_access()
    await cache_drop_access(drop_access)
    builder = InlineKeyboardBuilder()
    builder.button(text="Ok", callback_data="admin")
    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="Поздравляю, дроп закончен",
        reply_markup=builder.as_markup()
    )



@dp.callback_query(lambda c: c.data == "edit_support")
async def admin_edit_support(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(adminStates.waiting_for_new_support)
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin")
    await bot.edit_message_text(
        chat_id = callback.message.chat.id,
        message_id = callback.message.message_id,
        text = "Отправь новую ссылку на поддержку в виде: http://t.me/nikix_info",
        reply_markup=builder.as_markup()
    )
    await state.update_data(last_message_id=callback.message.message_id)


@dp.message(adminStates.waiting_for_new_support)
async def edit_support_json(message: types.Message, state: FSMContext):
    support_link = message.text.strip()
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    with open("bot_settings.json", "r") as f:
        jdata = json.load(f)
    jdata["support_link"] = support_link
    with open("bot_settings.json", "w") as f:
        json.dump(jdata, f)
    await cache_support_link(support_link)
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    builder = InlineKeyboardBuilder()
    builder.button(text="Ок", callback_data="admin")
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=last_message_id,
        text=f"✅ Ссылка изменёна на {support_link}",
        reply_markup=builder.as_markup()
    )
    await state.clear()


@dp.callback_query(lambda c: c.data == "admin_parse")
async def start_admin_parse(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="Ok", callback_data="admin")
    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="✅ Парсинг начался",
        reply_markup=builder.as_markup()
    )
    await update_cache()


@dp.callback_query(lambda c: c.data == "edit_proxy")
async def admin_edit_proxy(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(adminStates.waiting_for_new_proxy)
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin")
    await bot.edit_message_text(
        chat_id = callback.message.chat.id,
        message_id = callback.message.message_id,
        text = "Отправь новый прокси (только англ. текст) в виде: http://quIFjeCM1N:INDeocNfeO@51.15.15.230:9061",
        reply_markup=builder.as_markup()
    )
    await state.update_data(last_message_id=callback.message.message_id)


@dp.message(adminStates.waiting_for_new_proxy)
async def edit_proxy_json(message: types.Message, state: FSMContext):
    proxy = message.text.strip()
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    with open("bot_settings.json", "r") as f:
        jdata = json.load(f)
    jdata["proxy"] = proxy
    with open("bot_settings.json", "w") as f:
        json.dump(jdata, f)
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    builder = InlineKeyboardBuilder()
    builder.button(text="Ок", callback_data="admin")
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=last_message_id,
        text=f"✅ Прокси изменён на {proxy}",
        reply_markup=builder.as_markup()
    )
    await state.clear()


@dp.callback_query(lambda c: c.data == "get_users_for_admin")
async def get_users_admin(callback: types.CallbackQuery):
    await database.fetch_users(onlyID=0)


@dp.message(adminStates.waiting_for_message)
async def get_message_for_client(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    text_for_client = message.text
    await state.update_data(text_for_client=text_for_client, mes_with_but=0)
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    user_id = data.get("user_id_for_admin")
    username = await database.fetch_username_from_id(user_id)
    text = f"Текст для клиента {username[0]}\n\n{text_for_client}\n\nМожно отправить новый текст"
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💬 Отправить сообщение", callback_data="admin_send:1")
    keyboard.button(text="📦 Добавить кнопку 'Мои заказы'", callback_data="add_orders_but")
    keyboard.button(text="❌ Отмена", callback_data="admin_send:0")
    keyboard.adjust(1)
    await bot.edit_message_text(
        text=text,
        chat_id=message.chat.id,
        message_id=last_message_id,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(lambda c: c.data == "add_orders_but")
async def add_orders_button(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text_for_client = data.get("text_for_client")
    await state.update_data(mes_with_but=1)
    user_id = data.get("user_id_for_admin")
    username = await database.fetch_username_from_id(user_id)
    text = f"✅ Кнопка добавлена\nТекст для клиента {username[0]}\n\n{text_for_client}\n\nМожно отправить новый текст"
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💬 Отправить сообщение", callback_data="admin_send:1")
    keyboard.button(text="❌ Отмена", callback_data="admin_send:0")
    keyboard.adjust(1)
    await bot.edit_message_text(
        text=text,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(lambda c: c.data.startswith("admin_send"))
async def send_message_from_admin(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "1":
        data = await state.get_data()
        user_id = data.get("user_id_for_admin")
        text_for_client = data.get("text_for_client")
        mes_with_but = data.get("mes_with_but")
        try:
            builder = InlineKeyboardBuilder()
            # url="https://t.me/nikix_store_bot?start=-1"
            if mes_with_but == 1:
                builder.button(text="📦 Мои заказы", callback_data="my_orders:sd")
            await bot.send_message(text=text_for_client, chat_id=user_id, reply_markup=builder.as_markup())
        except Exception as e:
            await bot.edit_message_text(
                text=f"Ошибка при отправке: {e}",
                chat_id=ADMIN_ID,
                message_id=callback.message.message_id,
                parse_mode="HTML",
            )
            await state.clear()
            return
        await bot.edit_message_text(
            text="✅ Сообщение успешно отправлено",
            chat_id=ADMIN_ID,
            message_id=callback.message.message_id,
            parse_mode="HTML",
        )
    else:
        await bot.delete_message(chat_id=ADMIN_ID, message_id=callback.message.message_id)
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("client_mes_ok"))
async def delete_client_message(callback: types.CallbackQuery):
    await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)


async def choose_status(message, arg):
    if message.from_user.id == ADMIN_ID:
        order_id = int(arg.split("_")[1])
        text = f"Выбери новый статус для заказа: #{order_id}"
        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Оформлен", callback_data=f"set_order_status:0:{order_id}")
        builder.button(text="🚚 В пути", callback_data=f"set_order_status:1:{order_id}")
        builder.button(text="🕘 Ожидает получения", callback_data=f"set_order_status:2:{order_id}")
        builder.button(text="✅ Получен", callback_data=f"set_order_status:3:{order_id}")
        builder.button(text="❌ Отменён", callback_data=f"set_order_status:4:{order_id}")
        builder.adjust(1)
        await bot.send_message(text=text, chat_id=ADMIN_ID, reply_markup=builder.as_markup())



async def decrypt_status(status):
    statuses = {0: "📝 Оформлен", 1: "🚚 В пути", 2: "🕘 Ожидает получения", 3: "✅ Получен", 4: "❌ Отменён"}
    return statuses[status]



@dp.callback_query(lambda c: c.data.startswith("set_order_status"))
async def go_to_change_status(callback: types.CallbackQuery):
    await change_status(callback.data, callback.message.message_id)

async def change_status(callback_data, message_id):
    callback_data = callback_data.split(":")
    status_num = callback_data[1]
    order_id = int(callback_data[2]) - 2000
    if status_num == '4':
        cancel_text = f"Отменён заказ #{order_id + 2000}"
        await send_admin_message(cancel_text)
        await bot.send_message(text=cancel_text, chat_id=CHAT_ORDERS_ID)
    status = await decrypt_status(int(status_num))
    message_channel_id = await database.fetch_message_channel_id(order_id)
    trying = await database.set_order_status(order_id=order_id, status=status_num)
    if trying != 1:
        await send_admin_message(message=f"Ошибка, статус не установлен:\n{trying}")
        logger.error(f"Ошибка, статус #{order_id} не установлен:\n{trying}")
        return
    order_list = await database.fetch_orders(user_id=message_channel_id, id=order_id)
    order = order_list[0]
    user_info = await bot.get_chat(order["user_id"])
    first_name = user_info.first_name
    username = user_info.username
    text_for_chat = (f"📦 Заказ: #<b>{order_id+2000}</b>\n"
                     f"Статус: {status}\n\n"
                     f"Клиент: @{username}\n"
                     f"Имя: {first_name}\n"
                     f"ID: {order["user_id"]}\n"
                     f"Дата заказа: {order['when_buy']}\n\n")
    text_for_chat += (f"🚚 <b>Способ доставки:</b> {order['delivery_way']}\n"
                      f"🏠 <b>Адрес:</b> {order['address']}\n"
                      f"👟 <b>Примерка:</b> {order['preview']}\n"
                      f"💵 <b>Оплата:</b> {order['pay_way']}\n"
                      f"👤 <b>ФИО:</b> {order['fio']}\n"
                      f"☎️ <b>Номер телефона:</b> {order['phone']}\n"
                      f"💬 <b>Комментарий к заказу:</b> {order['comment']}\n\n")
    i = 1
    total_price = 0
    for product in order["products"]:
        text_for_chat += (f"<b>{i}.</b> <a href='{product['channel_url']}'><b>{product['name']}</b></a>\n"
                          f"<b>Артикул:</b> {product['art']}\n"
                          f"<b>Размер:</b> {product['size']} (EU)\n"
                          f"<b>Стоимость:</b> {product['price']} ₽\n\n")
        i += 1
        total_price += product['price']
    total_price += order['delivery_price']
    text_for_chat += (f"<b>Доставка:</b> {order['delivery_price']} ₽\n"
                      f"<b>Всего:</b> {total_price} ₽")

    keyboard = InlineKeyboardBuilder()
    arg = f"admin_send_{order["user_id"]}"
    keyboard.button(text="🔄 Изменить статус заказа", url=f"https://t.me/nikix_store_bot?start=status_{order_id+2000}")
    keyboard.button(text="💬 Написать клиенту через бота", url=f"https://t.me/nikix_store_bot?start={arg}")
    keyboard.button(text="👤 Написать клиенту в лс", url=f"https://t.me/{username}")
    keyboard.adjust(1)

    try:
        await bot.edit_message_text(
            text=text_for_chat,
            chat_id=CHAT_ORDERS_ID,
            message_id=message_channel_id,
            disable_web_page_preview=True,
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )
    except Exception as e:
        await send_admin_message(f"Не удалось изменить статус:{e}")
        logger.error(f"Не удалось изменить статус:{e}")
    if message_id != 0:
        builder = InlineKeyboardBuilder()
        arg = f"admin_send_{order["user_id"]}"
        builder.button(text="💬 Написать клиенту через бота", url=f"https://t.me/nikix_store_bot?start={arg}")
        await bot.edit_message_text(
            text="✅ Статус изменён",
            chat_id=ADMIN_ID,
            message_id=message_id,
            disable_web_page_preview=True,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Рассылка
@dp.callback_query(lambda c: c.data == "make_mailing")
async def mailing_settings(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Только текст", callback_data="mail_only_text")
    keyboard.button(text="❌ Отмена", callback_data="mailing_cancel")
    keyboard.adjust(1)
    try:
        await bot.edit_message_text(
            text="🖼 Никита, отправь 1 фото с текстом для рассылки",
            chat_id=ADMIN_ID,
            message_id=callback.message.message_id,
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )
    except Exception:
        await bot.send_message(
            text="🖼 Никита, отправь 1 фото с текстом для рассылки",
            chat_id=ADMIN_ID,
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )
    await state.set_state(adminStates.waiting_for_mail_photo)

@dp.callback_query(lambda c: c.data == "mailing_cancel")
async def cancel_mailing(callback: types.CallbackQuery, state: FSMContext):
    await admin_panel(callback)
    await state.clear()

@dp.message(adminStates.waiting_for_mail_photo)
async def get_mail_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    mail_text= message.caption
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да", callback_data="checked_mail:photo")
    keyboard.button(text="🔄 Отправить заново", callback_data="make_mailing")
    keyboard.button(text="❌ Отмена", callback_data="mailing_cancel")
    keyboard.adjust(1)
    await bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=mail_text, parse_mode="HTML", reply_markup=keyboard.as_markup())
    await state.update_data(photo_id=photo_id, mail_text=mail_text)

@dp.callback_query(lambda c: c.data == "mail_only_text")
async def only_text_mail_start(callback: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Рассылка с фото", callback_data="make_mailing")
    keyboard.button(text="❌ Отмена", callback_data="mailing_cancel")
    keyboard.adjust(1)
    await bot.edit_message_text(
        text="📝 Тогда отправь только текст для рассылки",
        chat_id=ADMIN_ID,
        message_id=callback.message.message_id,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )
    await state.set_state(adminStates.waiting_for_mail_text)

@dp.message(adminStates.waiting_for_mail_text)
async def get_mail_text(message: types.Message, state: FSMContext):
    mail_text = message.text
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да", callback_data="checked_mail:text")
    keyboard.button(text="🔄 Отправить заново", callback_data="mail_only_text")
    keyboard.button(text="❌ Отмена", callback_data="mailing_cancel")
    keyboard.adjust(1)
    await bot.send_message(
        text=mail_text,
        chat_id=ADMIN_ID,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )
    await state.update_data(mail_text=mail_text)

@dp.callback_query(lambda c: c.data.startswith("checked_mail:"))
async def add_but_for_mail(callback: types.CallbackQuery, state: FSMContext):
    text = "Нужно ли добавить кнопку, направляющую в каталог?"
    format_mail = callback.data.split(":")[1]
    await state.update_data(format_mail=format_mail)
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="С кнопкой", callback_data="add_but_mail")
    keyboard.button(text="Без кнопки", callback_data="ready_to_mailing:nobut")
    keyboard.button(text="❌ Отмена", callback_data="mailing_cancel")
    keyboard.adjust(1)
    await bot.send_message(
        text=text,
        chat_id=ADMIN_ID,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(lambda c: c.data == ("add_but_mail"))
async def add_but_for_mailing(callback: types.CallbackQuery, state: FSMContext):
    text = "Никита, отправь текст для кнопки (например: 🔥 Новинки):"
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="❌ Отмена", callback_data="mailing_cancel")
    await bot.edit_message_text(
        text=text,
        chat_id=ADMIN_ID,
        message_id=callback.message.message_id,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )
    await state.set_state(adminStates.waiting_for_mail_but_text)

@dp.message(adminStates.waiting_for_mail_but_text)
async def get_but_text_mailing(message: types.Message, state: FSMContext):
    but_text = message.text
    await state.update_data(but_text=but_text)
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=but_text, callback_data="ready_to_mailing:but")
    keyboard.button(text="🔄 Отправить заново", callback_data="add_but_mail")
    keyboard.button(text="❌ Отмена", callback_data="mailing_cancel")
    keyboard.adjust(1)
    await bot.send_message(
        text="Нажми на кнопку если готов перейти дальше",
        chat_id=ADMIN_ID,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(lambda c: c.data.startswith("ready_to_mailing:"))
async def ready_mailing(callback: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    format_mail = state_data.get("format_mail")
    mail_text = state_data.get("mail_text")

    keyboard = InlineKeyboardBuilder()
    is_but = callback.data.split(":")[1]
    if is_but == "but":
        but_text = state_data.get("but_text")
        keyboard.button(text=but_text, callback_data="brand:all:from_mail")
    if format_mail == "photo":
        photo_id = state_data.get("photo_id")
        await bot.send_photo(photo=photo_id, caption=mail_text, chat_id=ADMIN_ID, parse_mode="HTML", reply_markup=keyboard.as_markup())
    else:
        await bot.send_message(text=mail_text, chat_id=ADMIN_ID, parse_mode="HTML", reply_markup=keyboard.as_markup())

    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Начать рассылку", callback_data=f"start_mailing:{is_but}")
    builder.button(text="✉️ Показать сообщение", callback_data=f"ready_to_mailing:{is_but}")
    builder.button(text="✏️ Изменить сообщение", callback_data="make_mailing")
    builder.button(text="❌ Отмена", callback_data="mailing_cancel")
    builder.adjust(1)
    await bot.send_message(text="Выбери действие ниже:", chat_id=ADMIN_ID, parse_mode="HTML", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data.startswith("start_mailing:"))
async def start_mail(callback: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    format_mail = state_data.get("format_mail")
    mail_text = state_data.get("mail_text")
    keyboard = InlineKeyboardBuilder()
    is_but = callback.data.split(":")[1]
    if is_but == "but":
        but_text = state_data.get("but_text")
        keyboard.button(text=but_text, callback_data="brand:all:from_mail")
    if format_mail == "photo":
        photo_id = state_data.get("photo_id")

    users = await database.fetch_users(onlyID=1)
    await bot.edit_message_text(text="Рассылка началась", chat_id=ADMIN_ID, message_id=callback.message.message_id)
    for user_id in users:
        try:
            if format_mail == "photo":
                await bot.send_photo(photo=photo_id, caption=mail_text, chat_id=user_id, parse_mode="HTML", reply_markup=keyboard.as_markup())
            else:
                await bot.send_message(text=mail_text, chat_id=user_id, parse_mode="HTML", reply_markup=keyboard.as_markup())
            await asyncio.sleep(0.1) # Задержка от блокировки
        except Exception as e:
            error_text = f"Ошибка при отправке пользователю {user_id}: {e}"
            await send_admin_message(error_text)
    await send_admin_message("Рассылка закончена")
    await state.clear()



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Получить список пользователей
@dp.callback_query(lambda c: c.data == "admin_get_users")
async def get_bot_users(callback: types.CallbackQuery):
    users = await database.fetch_users(onlyID=0)
    file_content = "Список пользователей:\n\n"
    i = 1
    for user in users:
        file_content += f"{i}. username: {user['user_name']}, имя: {user['first_name']}, id: {user['user_id']}\n"
        i += 1

    with open("users.txt", "w", encoding="utf-8") as file:
        file.write(file_content)

    with open("users.txt", "rb") as file:
        file_data = file.read()
        input_file = BufferedInputFile(file_data, filename="users.txt")
        await bot.send_document(ADMIN_ID, input_file, caption="Список пользователей")

    os.remove("users.txt")



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Удалить все товары
@dp.callback_query(lambda c: c.data == "sure_admin_delete")
async def sure_delete_products(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="Да", callback_data="delete_all_products")
    builder.button(text="Нет", callback_data="admin")
    await bot.edit_message_text(
        text="Уверен что хочешь удалить все товары?",
        chat_id=ADMIN_ID,
        message_id=callback.message.message_id,
        reply_markup=builder.as_markup()
    )

@dp.callback_query(lambda c: c.data == "delete_all_products")
async def admin_delete_products(callback: types.CallbackQuery):
    try:
        await database.delete_all_data()
        await redis_delete_all_products()
        text = "Все товары успешно удалены"
    except Exception as e:
        text = f"Ошибка удаления: {e}"
    builder = InlineKeyboardBuilder()
    builder.button(text="Ок", callback_data="admin")
    await bot.edit_message_text(
        text=text,
        chat_id=ADMIN_ID,
        message_id=callback.message.message_id,
        reply_markup=builder.as_markup()
    )



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Загрузить товары из csv
@dp.callback_query(lambda c: c.data == "add_products")
async def request_file_csv(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена",callback_data="admin")
    await bot.edit_message_text(
        text="Отправь csv файл для загрузки кроссовок. (Макс 50 мб)",
        chat_id=ADMIN_ID,
        message_id=callback.message.message_id,
        reply_markup=builder.as_markup()
    )
    await state.set_state(adminStates.waiting_for_csv_file)

@dp.message(adminStates.waiting_for_csv_file)
async def get_csv_products(message: types.Message, state: FSMContext):
    if message.document.file_name.endswith('.csv'):
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        temp_file_path = f"temp_{file_id}.csv"
        await bot.download_file(file_path, temp_file_path)
        builder = InlineKeyboardBuilder()
        builder.button(text="✔️ Ок", callback_data="admin")
        builder.button(text="🔄 Попробовать ещё раз", callback_data="admin")
        builder.adjust(1)
        try:
            await database.upload_products(temp_file_path)
            products = await database.fetch_products("all")
            await redis_delete_all_products() # Если вылезет ошибка то проверить эту строку
            await cache_products(products)
            await bot.send_message(text="Загрузка закончена", chat_id=ADMIN_ID, reply_markup=builder.as_markup())
        except Exception as e:
            await bot.send_message(text=f"Ошибка загрузки: {e}", chat_id=ADMIN_ID, reply_markup=builder.as_markup())
        os.remove(temp_file_path)
        await state.clear()
    else:
        await message.answer("Пожалуйста отправь файл .csv")



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Поменять цену
@dp.callback_query(lambda c: c.data == "change_price")
async def admin_change_price(callback: types.CallbackQuery, state: FSMContext):
    index = await get_brand_and_index(callback.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    products = await get_products_from_index(watch_mode, brand)
    if products == []:
        await callback.answer(text="Ошибка, список товаров для просмотра пуст. Перезапусти каталог", show_alert=True)
        return
    product = products[current_index]
    old_price = await format_number(product["price"])
    text = f"Отправь новую цену (без пробелов, например: 20000) для {product['name']} вместо {old_price} ₽:"
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_change_price")

    await bot.edit_message_media(
        media=types.InputMediaPhoto(media=product["photo_url"], caption=text, parse_mode="HTML"),
        chat_id=ADMIN_ID,
        message_id=callback.message.message_id,
        reply_markup=builder.as_markup()
    )
    await state.set_state(adminStates.waiting_for_new_price)
    await state.update_data(last_message_id=callback.message.message_id)

@dp.callback_query(lambda c: c.data == "cancel_change_price")
async def back_to_catalog_admin_price(callback: types.CallbackQuery, state: FSMContext):
    index = await get_brand_and_index(callback.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    products = await get_products_from_index(watch_mode, brand)
    back_mode = index["back_mode"]
    total_products = len(products)
    await send_or_update_product(callback.message.chat.id, callback.message.message_id,
                                 products[current_index], current_index, total_products, is_edit=True,
                                 back_mode=back_mode)

@dp.message(adminStates.waiting_for_new_price)
async def get_new_admin_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    index = await get_brand_and_index(message.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    products = await get_products_from_index(watch_mode, brand)
    last_message_id = data.get("last_message_id", -1)
    product = products[current_index]
    if products == []:
        await send_admin_message("Ошибка, список товаров для просмотра пуст. Перезапусти каталог")
        return
    builder = InlineKeyboardBuilder()
    try:
        new_price = int(message.text)
        formated_price = await format_number(new_price)
        caption = f"Новая цена: {formated_price} ₽\nМожешь отправить цену заново:"
        builder.button(text="✅ Поменять цену", callback_data=f"finally_price:{new_price}")
    except Exception:
        caption = "Цена должна быть в виде числа. Пришли ещё раз:"

    builder.button(text="❌ Отмена", callback_data="cancel_change_price")
    builder.adjust(1)
    await bot.delete_message(chat_id=ADMIN_ID, message_id=message.message_id)
    await bot.edit_message_media(
        media=types.InputMediaPhoto(media=product["photo_url"], caption=caption, parse_mode="HTML"),
        chat_id=ADMIN_ID,
        message_id=last_message_id,
        reply_markup=builder.as_markup()
    )

@dp.callback_query(lambda c: c.data.startswith("finally_price:"))
async def finally_change_price(callback: types.CallbackQuery):
    index = await get_brand_and_index(callback.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    back_mode = index["back_mode"]
    products = await get_products_from_index(watch_mode, brand)
    product = products[current_index]
    total_products = len(products)

    new_price = int(callback.data.split(":")[1])

    if products == []:
        await send_admin_message("Ошибка, список товаров для просмотра пуст. Перезапусти каталог")
        return
    await database.change_price(new_price=new_price, art=product["art"])
    if brand != -1:
        products_from_brand = await database.fetch_products(brand)
        products = products_from_brand[::-1]
        await redis_delete_all_products()
        await cache_products(products)
    await send_or_update_product(callback.message.chat.id, callback.message.message_id,
                                 products[current_index], current_index, total_products, is_edit=True,
                                 back_mode=back_mode)



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Удаление товара
@dp.callback_query(lambda c: c.data == "admin_delete_product")
async def sure_delete_admin_product(callback: types.CallbackQuery):
    index = await get_brand_and_index(callback.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    products = await get_products_from_index(watch_mode, brand)
    if products == []:
        await send_admin_message("Ошибка, список товаров для просмотра пуст. Перезапусти каталог")
        return
    product = products[current_index]
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, уверен", callback_data="yes_delete_product")
    builder.button(text="❌ Отмена", callback_data="cancel_change_price")
    builder.adjust(1)
    await bot.edit_message_media(
        media=types.InputMediaPhoto(media=product["photo_url"], caption=f"Уверен, что хочешь удалить <b>{product['name']}</b>?", parse_mode="HTML"),
        chat_id=ADMIN_ID,
        message_id=callback.message.message_id,
        reply_markup=builder.as_markup()
    )

@dp.callback_query(lambda c: c.data == "yes_delete_product")
async def delete_admin_product(callback: types.CallbackQuery):
    index = await get_brand_and_index(callback.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    back_mode = index["back_mode"]
    products = await get_products_from_index(watch_mode, brand)
    total_products = len(products)
    if products == []:
        await send_admin_message("Ошибка, список товаров для просмотра пуст. Перезапусти каталог")
        return
    product = products[current_index]
    await database.delete_product(product["art"])
    products = await database.fetch_products("all")
    await redis_delete_all_products()
    await cache_products(products)
    try:
        await send_or_update_product(callback.message.chat.id, callback.message.message_id,
                                     products[current_index], current_index, total_products, is_edit=True,
                                     back_mode=back_mode)
    except Exception:
        await start_handler(message=callback.message)



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Замена ссылки на пост у конкретного товара
@dp.callback_query(lambda c: c.data == "change_post_link")
async def edit_post_link(callback: types.CallbackQuery, state: FSMContext):
    await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
    new_message = await bot.send_message(text="Отправь новую ссылку на пост в канале или 0 если её пока нет", chat_id=callback.from_user.id)
    await state.update_data(last_message_id=new_message.message_id)
    await state.set_state(adminStates.waiting_for_post_link)

@dp.message(adminStates.waiting_for_post_link)
async def get_new_post_link(message: types.Message, state: FSMContext):
    link = message.text
    index = await get_brand_and_index(ADMIN_ID)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    products = await get_products_from_index(watch_mode, brand)
    if products == []:
        await send_admin_message("Ошибка, список товаров для просмотра пуст. Перезапусти каталог")
        return
    product = products[current_index]
    await database.edit_post_link(art=product["art"], new_link=link)
    await redis_delete_all_products()
    products = await database.fetch_products("all")
    await cache_products(products)

    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    builder = InlineKeyboardBuilder()
    builder.button(text="Ok", callback_data="same")
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    await bot.edit_message_text(text=f"Ссылка изменена на {link}", chat_id=message.chat.id, message_id=last_message_id, reply_markup=builder.as_markup())
    await state.clear()



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Загрузить доп фото из csv
@dp.callback_query(lambda c: c.data == "add_photo_links")
async def request_file_csv(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена",callback_data="admin")
    await bot.edit_message_text(
        text="Отправь csv файл для загрузки фото. (Макс 50 мб)",
        chat_id=ADMIN_ID,
        message_id=callback.message.message_id,
        reply_markup=builder.as_markup()
    )
    await state.set_state(adminStates.waiting_for_photos_csv_file)

@dp.message(adminStates.waiting_for_photos_csv_file)
async def get_csv_products(message: types.Message, state: FSMContext):
    if message.document.file_name.endswith('.csv'):
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        temp_file_path = f"temp_{file_id}.csv"
        await bot.download_file(file_path, temp_file_path)
        builder = InlineKeyboardBuilder()
        builder.button(text="✔️ Ок", callback_data="admin")
        builder.button(text="🔄 Попробовать ещё раз", callback_data="admin")
        builder.adjust(1)
        try:
            await database.upload_photo_links(temp_file_path)
            await bot.send_message(text="Загрузка закончена", chat_id=ADMIN_ID, reply_markup=builder.as_markup())
            await database.fetchall_dop_photos()
        except Exception as e:
            await bot.send_message(text=f"Ошибка загрузки: {e}", chat_id=ADMIN_ID, reply_markup=builder.as_markup())
        os.remove(temp_file_path)
        await state.clear()
    else:
        await message.answer("Пожалуйста отправь файл .csv")



async def show_all_photos(arg, message, state):
    index = await get_brand_and_index(message.from_user.id)
    brand = index["brand"]
    current_index = int(index["current_index"])
    watch_mode = index["watch_mode"]
    products = await get_products_from_index(watch_mode, brand)
    product = products[current_index]
    data_arg = arg.split("photos")
    art = data_arg[0]
    last_message_id = data_arg[1]
    other_links = await database.fetch_photo_links_by_art(art)
    links = []
    links.append(product["photo_url"])
    for link in other_links:
        links.append(link)
    media_group = []
    for url in links:
        media_group.append(types.InputMediaPhoto(media=url))
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="hide_photos")
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    messages = await bot.send_media_group(media=media_group, chat_id=message.chat.id)
    message_ids = [mes.message_id for mes in messages]
    await state.update_data(message_ids=message_ids)
    await bot.send_message(text=f"<b>{product['name']}</b>", chat_id=message.chat.id, parse_mode="HTML", reply_markup=builder.as_markup())


# Убрать 4 фото
@dp.callback_query(lambda c: c.data == "hide_photos")
async def hide_product_photos(callback: types.CallbackQuery, state: FSMContext):
    await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
    data = await state.get_data()
    message_ids = data.get("message_ids")
    for mes_id in message_ids:
        await bot.delete_message(chat_id=callback.from_user.id, message_id=mes_id)



# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Получить текущий список товаров
@dp.callback_query(lambda c: c.data == "get_current_product_list")
async def get_bot_users(callback: types.CallbackQuery):
    db_products = await database.fetch_products("all")
    products = sorted(db_products, key=lambda item: int(item["id"]))
    file_content = ""
    i = 0
    for product in products:
        file_content += f"{product['type']},{product['name']},{product['maker'].replace(",", ":")},{product['material'].replace(", ", ":")},{product['season'].replace(", ", ":")},{product['brand']},{product['price']},{product['art']},{product['photo_url']},{product['channel_url']},{product['anki_url']}\n"
        i += 1

    with open("products.txt", "w", encoding="utf-8") as file:
        file.write(file_content)

    with open("products.txt", "rb") as file:
        file_data = file.read()
        input_file = BufferedInputFile(file_data, filename="products.txt")
        await bot.send_document(ADMIN_ID, input_file, caption="👟 Текущий список товаров")

    os.remove("products.txt")



# Загрузить таблицы размеров txt
@dp.callback_query(lambda c: c.data == "add_sizes_length")
async def ack_txt_sizes_length(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin")
    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="Отправь файл с длинами размеров в .txt (Пока что json полностью перезаписывается, поэтому отправь полный файл)",
        reply_markup=builder.as_markup()
    )
    await state.set_state(adminStates.waiting_for_sizes_length)

@dp.message(adminStates.waiting_for_sizes_length)
async def get_csv_products(message: types.Message, state: FSMContext):
    if message.document.file_name.endswith('.txt'):
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        temp_file_path = f"temp_{file_id}.txt"
        await bot.download_file(file_path, temp_file_path)
        builder = InlineKeyboardBuilder()
        builder.button(text="✔️ Ок", callback_data="admin")
        builder.button(text="🔄 Попробовать ещё раз", callback_data="admin")
        builder.adjust(1)
        with open(temp_file_path) as file:
            all_length = []
            for row in file:
                pices = row.split(";")
                art = pices[0]
                sizes = pices[1]
                sizes = sizes.split(",")
                del sizes[-1]
                sizes_length = {}
                for size in sizes:
                    size_pices = size.split(":")
                    eu = size_pices[0].strip()
                    length = size_pices[1].strip()
                    sizes_length[eu] = length
                length_dict = {"art": art, "sizes": sizes_length}
                all_length.append(length_dict)
        with open('sizes_lengths.json', 'w', encoding='utf-8') as f:
            json.dump(all_length, f, ensure_ascii=False, indent=2)
        await cache_sizes_length()
        await bot.send_message(text="Загрузка закончена", chat_id=ADMIN_ID, reply_markup=builder.as_markup())
        os.remove(temp_file_path)
        await state.clear()
    else:
        await message.answer("Пожалуйста отправь файл .txt")


if __name__ == '__main__':
    dp.run_polling(bot, skip_updates=True)