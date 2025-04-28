import asyncio
import redis.asyncio as redis
import json
redis_client = None

# Подключение к redis
async def redis_connect():
    global redis_client
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        await redis_client.set("test_connection", "ok")
        return "Успешное подключение к redis"
    except Exception as e:
        redis_client = None
        return f"Не удалось подключится к redis: {e}"


# Добавление списка пользователей в redis
async def upload_users(user_ids):
    global redis_client
    await redis_client.sadd("user_ids", *user_ids)


async def delete_redis_users():
    global redis_client
    await redis_client.delete("user_ids")


async def check_and_add_user(user_id):
    if redis_client:
        try:
            is_user_exists = await redis_client.sismember("user_ids", user_id)
            # users = await redis_client.smembers("user_ids")
            # print(users)
        except Exception as e:
            return None
        if is_user_exists:
            return 1
        else:
            await redis_client.sadd("user_ids", user_id)
            return 0
    else:
        return None


# Кэш всего списка товаров
# Кэширование товаров, брендов, сезонов для поиска в redis
async def cache_products(products):
    if products == []:
        return
    unique_brands = set()
    for product in products:
        product_key = f"product:{product['brand']}:{product['art']}"
        seasons = product["season"].split(", ")
        # Сохраняем товар как хэш
        try:
            await redis_client.hset(product_key, mapping=product)
            unique_brands.add(product["brand"]) # Сохраняем бренд в множество брендов
            for season in seasons:
                await redis_client.hset(f"season:{season}:{product['art']}", mapping=product)  # Сохраняем артикул в отдельном множестве с сезоном
        except Exception as e:
            return
            # await send_admin_message(f"Redis не отвечает (кэш products): {e}")
    brands = list(unique_brands)
    brands.sort()
    key = "brands"
    if await redis_client.exists(key):
        await redis_client.delete(key)
    await redis_client.rpush(key, *brands)
    '''
    keys = await redis_client.keys(f"product:*:*")
    brands = set()
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match="product:*")
        for key in keys:
            parts = key.decode('utf-8').split(":")
            if len(parts) >= 2:
                brand = parts[1]
                brands.add(brand)
        if cursor == 0:
            break
    brands = list(brands)
    print(brands)
    '''

# Получение товаров по бренду
async def get_cached_products(brand):
    cached_products = []
    # ищем все ключи, соответствующие бренду
    try:
        if brand == "all":
            brand_key = f"product:*:*"
        else:
            brand_key = f"product:{brand}:*"
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match=brand_key)
            for key in keys:
                product = await redis_client.hgetall(key)
                product = {k.decode('utf-8'): v.decode('utf-8') for k, v in product.items()}
                product["id"] = int(product["id"])
                product["price"] = int(product["price"])
                product["drop_price"] = int(product["drop_price"])
                cached_products.append(product)
            if cursor == 0:
                break
        products = sorted(cached_products, key=lambda item: int(item["id"]), reverse=True)
        return products
    except Exception as e:
        # await send_admin_message(f"Redis не отвечает: {e}")
        return []

async def get_search_products(search_mode, param, sizes_cache=None):
    cached_products = []
    try:
        if search_mode == "season":
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor, match=f"season:{param}:*")
                for key in keys:
                    product = await redis_client.hgetall(key)
                    product = {k.decode('utf-8'): v.decode('utf-8') for k, v in product.items()}
                    product["id"] = int(product["id"])
                    product["price"] = int(product["price"])
                    product["drop_price"] = int(product["drop_price"])
                    cached_products.append(product)
                if cursor == 0:
                    break

        if search_mode == "size":
            size = param
            arts = []
            for art in sizes_cache:
                for cache in sizes_cache[art]:
                    if (size == cache) or ((size+" 2/3") == cache):
                        arts.append(art)
                        break
            cursor = 0
            for art in arts:
                while True:
                    cursor, keys = await redis_client.scan(cursor, match=f"product:*:{art}")
                    for key in keys:
                        product = await redis_client.hgetall(key)
                        product = {k.decode('utf-8'): v.decode('utf-8') for k, v in product.items()}
                        product["id"] = int(product["id"])
                        product["price"] = int(product["price"])
                        product["drop_price"] = int(product["drop_price"])
                        cached_products.append(product)
                    if cursor == 0:
                        break

        if search_mode == "art":
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor, match=f"product:*:{param}")
                for key in keys:
                    product = await redis_client.hgetall(key)
                    product = {k.decode('utf-8'): v.decode('utf-8') for k, v in product.items()}
                    product["id"] = int(product["id"])
                    product["price"] = int(product["price"])
                    product["drop_price"] = int(product["drop_price"])
                    cached_products.append(product)
                if cursor == 0:
                    break

        products = sorted(cached_products, key=lambda item: int(item["id"]), reverse=True)
        return products

    except Exception as e:
        # await send_admin_message(f"Redis не отвечает: {e}")
        return []


async def get_redis_brands():
    brands = await redis_client.lrange("brands", 0, -1)
    return brands


async def upload_user_index_brand(user_id, current_index, brand, watch_mode, back_mode="0"):
    index_key = f"index:{user_id}"
    index = {"current_index": current_index, "brand": brand, "watch_mode": watch_mode, "back_mode": back_mode}
    await redis_client.hset(index_key, mapping=index)

async def get_brand_and_index(user_id):
    index = await redis_client.hgetall(f"index:{user_id}")
    index = {k.decode('utf-8'): v.decode('utf-8') for k, v in index.items()}
    return index

async def redis_delete_all_products():
    keys_to_delete = []
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match="product:*:*")
        for key in keys:
            keys_to_delete.append(key)
        if cursor == 0:
            break
    if keys_to_delete:
        await redis_client.delete(*keys_to_delete)
    keys_to_delete = []
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match="season:*:*")
        for key in keys:
            keys_to_delete.append(key)
        if cursor == 0:
            break
    if keys_to_delete:
        await redis_client.delete(*keys_to_delete)
    await redis_client.delete("brands")

async def redis_delete_product(art):
    await redis_client.delete(f"product:*:{art}")


# Кэширование доп фоток
async def cache_photos(photos):
    if photos == []:
        return
    for photo in photos:
        photo_key = f"photo:{photo['art']}"
        # Сохраняем товар как хэш
        try:
            await redis_client.hset(photo_key, mapping=photo)
        except Exception:
            return


# Кэширование длин размеров
async def cache_sizes_length():
    with open("sizes_lengths.json", "r") as f:
        data = json.load(f)
        for dick in data:
            key = f"length:{dick['art']}"
            await redis_client.hset(key, mapping=dick['sizes'])

# Поиск длин размеров по артикулу
async def get_sizes_length(art):
    try:
        length_key = f"length:{art}"
        sizes = await redis_client.hgetall(length_key)
        sizes = {k.decode('utf-8'): v.decode('utf-8') for k, v in sizes.items()}
        return sizes
    except Exception:
        return {}


# Сохранить ссылку на поддержку
async def cache_support_link(support_link):
    await redis_client.set("support_link", support_link)

# Получить ссылку для поддержки
async def get_support_link():
    support = await redis_client.get("support_link")
    return support.decode("utf-8")


# Таблица с доступом к дропу для каждого пользователя (введён ли пароль у пользователя)
async def cache_drop_access(users_access):
    for user_id in users_access:
        await redis_client.set(f"drop_pas:{user_id}", users_access[user_id])

# Получение информации о том введён ли пароль для дропа у отдельного пользователя
async def get_drop_access(user_id):
    access = await redis_client.get(f"drop_pas:{user_id}")
    return access.decode("utf-8")

async def give_redis_drop_access(user_id):
    await redis_client.set(f"drop_pas:{user_id}", 1)


async def cache_drop_info():
    with open("bot_settings.json", "r") as f:
        data = json.load(f)
    drop = {"drop_password": data['drop_password'], "drop_start_date": data['drop_start_date'], "drop_stop_date": data['drop_stop_date']}
    await redis_client.hset("drop_info", mapping=drop)

async def get_drop_info():
    drop_info_enc = await redis_client.hgetall("drop_info")
    drop_info = {k.decode('utf-8'): v.decode('utf-8') for k, v in drop_info_enc.items()}
    return drop_info