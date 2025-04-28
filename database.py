from email.policy import default
from shutil import which

import aiosqlite
import csv
import asyncio
from main import send_admin_message

DATABASE_PATH = "nikix_bot_database.db"

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Таблица пользователи
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name VARCHAR(32),
                first_name VARCHAR(32),
                when_created DATE DEFAULT CURRENT_DATE
                );
            ''')

        # Таблица товары
        await db.execute('''
            CREATE TABLE IF NOT EXISTS products(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type VARCHAR(15),
                name VARCHAR(100),
                maker VARCHAR(15),
                material VARCHAR(15),
                season VARCHAR(15),
                brand VARCHAR(30),
                price INTEGER,
                art VARCHAR(30) UNIQUE,
                photo_url TEXT,
                channel_url TEXT,
                anki_url TEXT,
                drop INTEGER
                );
            ''')

        # Таблица заказы
        await db.execute('''
            CREATE TABLE IF NOT EXISTS orders(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                fio TEXT,
                phone_number VARCHAR(14),
                address TEXT,
                delivery_way TEXT,
                preview VARCHAR(50),
                pay_way TEXT,
                status INTEGER,
                comment TEXT,
                delivery_price INTEGER,
                message_from_channel INTEGER,
                when_buy DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            ''')

        # Таблица товаров в заказе
        await db.execute('''
            CREATE TABLE IF NOT EXISTS order_items(
                order_id INTEGER,
                name TEXT,
                art VARCHAR(30),
                size VARCHAR(10)
                );
            ''')

        # Таблица корзина
        await db.execute('''
            CREATE TABLE IF NOT EXISTS basket(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                art VARCHAR(30),
                size VARCHAR(10)
                );
            ''')

        # Таблица ссылок на фото
        await db.execute('''
                    CREATE TABLE IF NOT EXISTS photo_links(
                        art VARCHAR(30) UNIQUE,
                        photo2_url TEXT,
                        photo3_url TEXT,
                        photo4_url TEXT
                        );
                    ''')

        # индексы
        await db.execute('CREATE INDEX IF NOT EXISTS idx_basket_user_id ON basket(user_id);')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_basket_art ON basket(art);')

        await db.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_orders_when_buy ON orders(when_buy)')

        await db.execute('CREATE INDEX IF NOT EXISTS idx_order_items_id ON order_items(order_id)')

        await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_products_art ON products(art)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_products_season ON products(season)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_products_type ON products(type)')

        await db.execute('CREATE INDEX IF NOT EXISTS idx_users_name ON users(user_name)')

        await db.commit() # конец init


async def upload_products(csv_file_path):
    flag = 0
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute('BEGIN'):
            with open(csv_file_path, 'r', encoding='utf-8') as csv_file:
                reader = csv.DictReader(csv_file)
                reader.fieldnames = [field.strip() for field in reader.fieldnames]
                for row in reader:
                    try:
                        cleaned_row = {key.strip(): (value.strip() if value else "") for key, value in row.items()}
                        if cleaned_row["drop"] not in ["0", "1"]:
                            cleaned_row["drop"] = "0"
                        await db.execute('''
                        INSERT INTO products (type, name, maker, material, season, brand, price, art, photo_url, channel_url, anki_url, drop)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        ''', (cleaned_row['type'], cleaned_row['name'], cleaned_row['maker'], cleaned_row['material'].replace(":", ", ").lower(), cleaned_row['season'].replace(":", ", "), cleaned_row['brand'], int(cleaned_row['price']), cleaned_row['art'], cleaned_row['photo_url'], cleaned_row['channel_url'], cleaned_row['anki_url'], int(cleaned_row["drop"])))
                    except Exception as e:
                        flag = 1
                        await asyncio.sleep(0.2)
                        await send_admin_message(message=f"Ошибка при загрузке строки {row}: {e}", is_log=True)

        await db.commit()
    if flag == 0:
        await send_admin_message('Загрузка таблицы успешно завершена')
    else:
        await send_admin_message('Загрузка таблицы завершена с ошибками. Посмотри логи!')

async def delete_all_data():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('DELETE FROM products;')
        await db.commit()

async def fetch_products(brand: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if brand == "all":
            cursor = await db.execute('SELECT * FROM products')
        else:
            cursor = await db.execute('SELECT * FROM products WHERE brand = ?', (brand,))
        rows = await cursor.fetchall()
        products = [{"id": row[0], "type": row[1], "name": row[2], "maker": row[3], "material": row[4], "season": row[5], "brand": row[6], "price": row[7], "art": row[8], "photo_url": row[9], "channel_url": row[10], "anki_url": row[11], "drop": row[12]} for row in rows]
        print(products[0])
        return products

#Взять названия брендов из базы
async def fetch_brands():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT brand FROM products;") #Запрос вернёт список всех уникальных брендов таблицы products
        brands = await cursor.fetchall()
        return [row[0] for row in brands if row[0]] #Возвращение списка, исключая None или пустые значения

#Добавить товар в корзину
async def add_to_basket(user_id: int, art: int, size: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('INSERT INTO basket (user_id, art, size) VALUES (?, ?, ?)', (user_id, art, size))
        await db.commit()

#Получение товаров из корзины
async def fetch_basket(user_id: int, count=False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        query = """
        SELECT b.id AS basket_id, p.id AS product_id, p.name, p.price, photo_url, b.size, p.art, p.channel_url
        FROM basket b
        INNER JOIN products p ON b.art = p.art
        WHERE b.user_id = ?
        """
        cursor = await db.execute(query, (user_id,))
        rows = await cursor.fetchall()
        await cursor.close()
        if not count:
            basket = [
                {
                    "basket_id": row[0],
                    "product_id": row[1],
                    "name": row[2],
                    "price": row[3],
                    "photo_url": row[4],
                    "size": row[5],
                    "art": row[6],
                    "channel_url": row[7]
                }
                for row in rows
            ]
            return basket
        else:
            i = 0
            for row in rows:
                i += 1
            return i

async def clear_basket(user_id: int, basket_id: int, is_all: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if is_all == 0:
            await  db.execute("DELETE FROM basket WHERE id = ?", (basket_id,)) #Удаляем один товар из корзины
        else:
            await  db.execute("DELETE FROM basket WHERE user_id = ?", (user_id,)) #Удаляем все товары из корзины
        await db.commit()

# Вернуть все юрл для парсинга размеров
async def fetch_url_sizes():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT art, anki_url FROM products")
        rows = await cursor.fetchall()
        urls = [{"art": row[0], "url": row[1]} for row in rows]
        await cursor.close()
        return urls

async def fetch_users(onlyID=0):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if onlyID == 1:
            cursor = await db.execute("SELECT user_id FROM users")
            rows = await cursor.fetchall()
            users = [row[0] for row in rows]
            await cursor.close()
            return users
        else:
            cursor = await db.execute("SELECT id, user_id, user_name, first_name, when_created FROM users")
            rows = await cursor.fetchall()
            users = [{"id": row[0], "user_id": row[1], "user_name": row[2], "first_name": row[3]} for row in rows]
            await cursor.close()
            return users

async def fetch_username_from_id(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT user_name FROM users WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        return rows[0]


# Добавить пользователя при старте
async def add_user(user_id: int, user_name: str, first_name: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT INTO users (user_id, user_name, first_name) VALUES (?, ?, ?)", (user_id, user_name, first_name))
        await db.commit()

async def delete_all_users():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM users")
        await db.commit()


async def add_order(user_id, basket, fio, phone_number, address, delivery_way, preview, pay_way, status, comment, delivery_price):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            cursor = await db.execute("INSERT INTO orders (user_id, fio, phone_number, address, delivery_way, preview, pay_way, status, comment, delivery_price, message_from_channel) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (user_id, fio, phone_number, address, delivery_way, preview, pay_way, status, comment, delivery_price, 0))
            await db.commit()
            order_id = cursor.lastrowid
            for product in basket:
                await db.execute("INSERT INTO order_items (order_id, name, art, size) VALUES (?, ?, ?, ?)", (order_id, product['name'], product['art'], product['size']))
            await db.commit()
            return 2000 + order_id # Вернуть номер последнего заказа, то есть который добавили только что
        except Exception as e:
            await db.rollback()
            await send_admin_message(f"Ошибка при добавлении заказа: {e}")
            raise

async def change_channel_id_for_order(order_id, message_id):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute("UPDATE orders SET message_from_channel = ? WHERE id = ?", (message_id, order_id))
            await db.commit()
        except Exception as e:
            return e
        return 1

async def fetch_message_channel_id(order_id):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT message_from_channel FROM orders WHERE id = ?", (order_id,))
        rows = await cursor.fetchone()
        return rows[0]

async def set_order_status(order_id, status):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
            await db.commit()
        except Exception as e:
            return e
        return 1

async def fetch_orders(user_id: int, id=0):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        query = "SELECT id, user_id, fio, phone_number, address, delivery_way, preview, pay_way, status, comment, delivery_price, when_buy FROM orders WHERE"
        if id == 0:
            query += " user_id = ?"
            cursor = await db.execute(query, (user_id,))
        else:
            query += " id = ?"
            cursor = await db.execute(query, (id,))
        rows = await cursor.fetchall()
        orders = []
        for row in rows:
            cursor = await db.execute("SELECT p.name, o.art, o.size, p.channel_url, p.price, p.photo_url FROM order_items o INNER JOIN products p ON o.art = p.art WHERE o.order_id = ?", (row[0],))
            items = await cursor.fetchall()
            products = [{"name": item[0], "art": item[1], "size": item[2], "channel_url": item[3], "price": item[4], "photo_url": item[5]} for item in items]
            orders.append({"id": (2000 + row[0]), "user_id": row[1], "fio": row[2], "phone": row[3],
                           "address": row[4], "delivery_way": row[5], "preview": row[6], "pay_way": row[7],
                           "status": row[8], "comment": row[9],"delivery_price": row[10], "when_buy": row[11],
                           "products": products})
        return orders


async def fetch_products_from_search(mode, data): # 0-season, 1-size, 2-art
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if mode == 0:
            cursor = await db.execute('SELECT * FROM products WHERE season LIKE ?', (data,))
            rows = await cursor.fetchall()
        elif mode == 1:
            rows = []
            for art in data:
                cursor = await db.execute('SELECT * FROM products WHERE art = ?', (art,))
                row = await cursor.fetchall()
                if row != []:
                    rows.append(row[0])
        elif mode == 2:
            cursor = await db.execute('SELECT * FROM products WHERE art LIKE ?', (data,))
            rows = await cursor.fetchall()
        else:
            await send_admin_message("Ошибка поиска")
            return
        products = [{"id": row[0], "type": row[1], "name": row[2], "maker": row[3], "material": row[4], "season": row[5],
                     "brand": row[6], "price": row[7], "art": row[8], "photo_url": row[9], "channel_url": row[10],
                     "anki_url": row[11]} for row in rows]
        products = products[::-1]
        return products


async def change_price(new_price: int, art: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute("UPDATE products SET price = ? WHERE art = ?", (new_price, art))
            await db.commit()
        except Exception as e:
            await send_admin_message(f"Не удалось обновить цену: {e}")

async def delete_product(art: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute("DELETE FROM products WHERE art = ?", (art,))
            await db.commit()
        except Exception as e:
            await send_admin_message(f"Не удалось удалить товар: {e}")


# Загрузка ссылок на фото в базу, перед загрузкой происходит автоматическое удаление старых ссылок
async def upload_photo_links(csv_file_path):
    flag = 0
    async with (aiosqlite.connect(DATABASE_PATH) as db):
        await db.execute("DELETE FROM photo_links")
        await db.commit()
        async with db.execute('BEGIN'):
            with open(csv_file_path, 'r', encoding='utf-8') as csv_file:
                reader = csv.DictReader(csv_file)
                reader.fieldnames = [field.strip() for field in reader.fieldnames]
                for row in reader:
                    try:
                        cleaned_row = {key.strip(): (value.strip() if value else "") for key, value in row.items()}
                        await db.execute("INSERT INTO photo_links (art, photo2_url, photo3_url, photo4_url) VALUES (?, ?, ?, ?)", (cleaned_row["art"], cleaned_row["photo2_url"], cleaned_row["photo3_url"], cleaned_row["photo4_url"]))
                    except Exception as e:
                        flag = 1
                        await asyncio.sleep(0.2)
                        await send_admin_message(message=f"Ошибка при загрузке строки {row}: {e}", is_log=True)

        await db.commit()
    if flag == 0:
        await send_admin_message('Загрузка таблицы успешно завершена')
    else:
        await send_admin_message('Загрузка таблицы завершена с ошибками. Посмотри логи!')



# Получить ссылки по артикулу
async def fetch_photo_links_by_art(art):
    photo_links = []
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('SELECT photo_url FROM products WHERE art = ?', (art,))
        row = await cursor.fetchone()
        photo_links.append(row[0])
        cursor = await db.execute("SELECT photo2_url, photo3_url, photo4_url FROM photo_links WHERE art = ?", (art,))
        rows = await cursor.fetchone()
        return rows


async def fetchall_dop_photos():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT p.art, p.photo_url, u.photo2_url, u.photo3_url, u.photo4_url FROM products p INNER JOIN photo_links u ON p.art = u.art")
        rows = await cursor.fetchall()
        print(rows)


#
async def edit_post_link(art, new_link):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute("UPDATE products SET channel_url = ? WHERE art = ?", (new_link, art))
            await db.commit()
        except Exception as e:
            await send_admin_message(f"Не удалось изменить ссылку: {e}")