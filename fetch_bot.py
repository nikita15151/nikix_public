from gettext import textdomain
from types import new_class
from urllib.request import build_opener

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from dotenv import load_dotenv
import json
import os

FETCH_BOT_TOKEN = os.getenv("FETCH_BOT_TOKEN")
bot = Bot(token=FETCH_BOT_TOKEN)
dp = Dispatcher()
product = {}

class WaitState(StatesGroup):
    waiting_for_maker = State()
    waiting_for_material = State()
    waiting_for_season = State()
    waiting_for_brand = State()
    waiting_for_price = State()
    waiting_for_photo_url = State()
    waiting_for_anki_url = State()
    waiting_for_message = State()
    waiting_for_channel_url = State()


@dp.message(Command(commands=["send"]))
async def send_handler(message: types.Message, state: FSMContext):
    await bot.send_message(text="Я готов", chat_id=message.chat.id)
    await state.set_state(WaitState.waiting_for_message)


@dp.message(WaitState.waiting_for_message)
async def handle_message(message: types.Message, state: FSMContext):
    global product
    if message.forward_from_chat:
        original_text = message.text or message.caption
        if original_text != None:
            rows = (str(original_text)).split("\n")
            product["name"] = rows[0]
            for row in rows:
                if "Артикул:" in row:
                    art_index = row.find("Артикул:")+len("Артикул:")
                    product["art"] = row[art_index:].strip()
                if "Стоимость:" in row:
                    price_index = row.find("Стоимость:")+len("Стоимость:")
                    product["price"] = row[price_index:row.find("₽")-1].replace(" ", "")
                if "Производитель:" in row:
                    maker_index = row.find("Производитель:")+len("Производитель:")
                    product["maker"] = row[maker_index:].strip()
                if "Материал:" in row:
                    material_index = row.find("Материал:")+len("Материал:")
                    material = row[material_index:].strip()
                    if "," in material:
                        material = material.replace(", ", ":")
                    product["material"] = material
            #channel_url = f"https://t.me/nikix_store/{message.message_id}"
            #text = f"sneaker,{name},{maker},{material},season,brand,{price},{art},photo_url,{channel_url},"

            if "Производитель:" not in original_text:
                await bot.send_message(text="Производитель:", chat_id=message.chat.id)
                await state.set_state(WaitState.waiting_for_maker)
            else:
                await state.set_state(WaitState.waiting_for_season)
                await bot.send_message(text=f"{product['name']}\nСезон(d, s, w):", chat_id=message.chat.id)

@dp.message(WaitState.waiting_for_maker)
async def enter_maker(message: types.Message, state: FSMContext):
    global product
    product["maker"] = str(message.text)
    if product["maker"] != None:
        await bot.send_message(text=f"{product['name']}\nМатериал:", chat_id=message.chat.id)
        await state.set_state(WaitState.waiting_for_material)
    else:
        await bot.send_message(text="Ошибка", chat_id=message.chat.id)

@dp.message(WaitState.waiting_for_material)
async def enter_material(message: types.Message, state: FSMContext):
    global product
    product["material"] = str(message.text)
    if product["material"] != None:
        await bot.send_message(text=f"{product['name']}\nСтоимость:", chat_id=message.chat.id)
        await state.set_state(WaitState.waiting_for_price)
    else:
        await bot.send_message(text="Ошибка", chat_id=message.chat.id)

@dp.message(WaitState.waiting_for_price)
async def enter_price(message: types.Message, state: FSMContext):
    global product
    product["price"] = int(message.text)
    if product["price"] != None:
        await bot.send_message(text=f"{product['name']}\nСезон:", chat_id=message.chat.id)
        await state.set_state(WaitState.waiting_for_season)
    else:
        await bot.send_message(text="Ошибка", chat_id=message.chat.id)

@dp.message(WaitState.waiting_for_season)
async def enter_season(message: types.Message, state: FSMContext):
    global product
    data = str(message.text)
    season = ""
    if data != None:
        if "d" in data.lower():
            season += "демисезон:"
        if "s" in data.lower():
            season += "лето:"
        if "w" in data.lower():
            season += "зима:"
        product["season"] = season[:-1]

        builder = InlineKeyboardBuilder()
        name = product["name"].split(" ")
        but_text = ""
        i = 0
        for word in name:
            if but_text == "":
                but_text += word
            elif i < 4:
                but_text += f" {word}"
            builder.button(text=but_text, callback_data=f"brand:{but_text}")
            i += 1
        builder.adjust(1)
        await bot.send_message(text=f"{product['name']}\nБренд:", chat_id=message.chat.id, reply_markup=builder.as_markup())
        await state.clear()
    else:
        await bot.send_message(text="Ошибка", chat_id=message.chat.id)

@dp.callback_query(lambda c: c.data.startswith("brand:"))
async def enter_brand(callback: types.CallbackQuery, state: FSMContext):
    global product
    product["brand"] = callback.data.split(":")[1]
    if product["brand"] != None:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        await bot.send_message(text=f"{product['name']}\nСсылка на фото:", chat_id=callback.message.chat.id)
        await state.set_state(WaitState.waiting_for_photo_url)
    else:
        await bot.send_message(text="Ошибка", chat_id=callback.message.chat.id)

@dp.message(WaitState.waiting_for_photo_url)
async def enter_photo_url(message: types.Message, state: FSMContext):
    global product
    product["photo_url"] = str(message.text)
    if product["photo_url"] != None:
        await bot.send_message(text=f"{product['name']}\nСсылка на anki:", chat_id=message.chat.id)
        await state.set_state(WaitState.waiting_for_anki_url)
    else:
        await bot.send_message(text="Ошибка", chat_id=message.chat.id)

@dp.message(WaitState.waiting_for_anki_url)
async def enter_anki_url(message: types.Message, state: FSMContext):
    global product
    product["anki_url"] = str(message.text)
    if product["anki_url"] != None:
        with open("channel_url.json", "r") as f:
            number = json.load(f)
            new_nomber = number + 4
        with open("channel_url.json", "w") as f:
            json.dump(new_nomber, f)

        product["channel_url"] = f"https://t.me/nikix_store/{number}"
        builder = InlineKeyboardBuilder()
        builder.button(text="Да", callback_data="link_is:good")
        builder.button(text="Нет, вставлю сам", callback_data="link_is:shit")
        builder.adjust(1)
        await bot.send_message(text=f"{product['name']}\n\n {product['channel_url']}\n\n Норм ссылка?", chat_id=message.chat.id, reply_markup=builder.as_markup())
        await state.clear()
    else:
        await bot.send_message(text="Ошибка", chat_id=message.chat.id)

@dp.callback_query(lambda c: c.data.startswith("link_is:"))
async def enter_channel_url(callback: types.CallbackQuery, state: FSMContext):
    global product
    data = callback.data.split(":")[1]
    if data == "good":
        await save_in_file(chat_id=callback.message.chat.id)
    elif data == "shit":
        await state.set_state(WaitState.waiting_for_channel_url)
    await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)

@dp.message(WaitState.waiting_for_channel_url)
async def enter_channel_url(message: types.Message, state: FSMContext):
    global product
    product["channel_url"] = str(message.text)
    if product["channel_url"] != None:
        await save_in_file(chat_id=message.chat.id)
        await state.clear()
    else:
        await bot.send_message(text="Ошибка", chat_id=message.chat.id)


async def save_in_file(chat_id):
    global product
    new_product = f"sneaker,{product['name']},{product['maker']},{product['material']},{product['season']},{product['brand']},{product['price']},{product['art']},{product['photo_url']},{product['channel_url']},{product['anki_url']}\n"
    try:
        with open("sneakers-nikix.txt", "a", encoding="utf-8") as file:
            file.write(new_product)
        await bot.send_message(text=f"{new_product}\n Записано в файл", chat_id=chat_id)
    except Exception:
        await bot.send_message(text="Ошибка записи в файл", chat_id=chat_id)


if __name__ == '__main__':
    dp.run_polling(bot, skip_updates=True)