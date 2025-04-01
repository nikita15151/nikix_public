import asyncio
import redis.asyncio as redis
from main import send_admin_message
from database import fetch_products
redis_client = None

# Подключение к redis
async def redis_connect():
    global redis_client
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        await redis_client.set("test_connection", "ok")
        await send_admin_message("Успешное подключение к redis")
    except Exception as e:
        await send_admin_message(f"Не удалось подключится к redis: {e}")
        redis_client = None


# Добавление списка пользователей в redis
async def upload_users(user_ids):
    global redis_client
    await redis_client.sadd("user_ids", *user_ids)


async def check_and_add_user(user_id):
    if redis_client:
        try:
            is_user_exists = await redis_client.sismember("user_ids", user_id)
            # users = await redis_client.smembers("user_ids")
            # print(users)
        except Exception as e:
            await send_admin_message(f"Redis не отвечает (кэш users): {e}")
            return None
        if is_user_exists:
            return 1
        else:
            await redis_client.sadd("user_ids", user_id)
            print("no")
            return 0
    else:
        return None


# Кэш всего списка товаров
# Кэширование товаров, брендов, сезонов для поиска в redis
async def cache_products():
    products = await fetch_products("all")
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
            await send_admin_message(f"Redis не отвечает (кэш products): {e}")
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
                cached_products.append(product)
            if cursor == 0:
                break
        products = sorted(cached_products, key=lambda item: int(item["id"]), reverse=True)
        return products
    except Exception as e:
        await send_admin_message(f"Redis не отвечает: {e}")
        return []

async def get_search_products(search_mode, param):
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
                    cached_products.append(product)
                if cursor == 0:
                    break
            products = sorted(cached_products, key=lambda item: int(item["id"]), reverse=True)
            return products

        if search_mode == "size":
            cursor = 0
            for art in param:
                while True:
                    cursor, keys = await redis_client.scan(cursor, match=f"product:*:{art}")
                    for key in keys:
                        product = await redis_client.hgetall(key)
                        product = {k.decode('utf-8'): v.decode('utf-8') for k, v in product.items()}
                        product["id"] = int(product["id"])
                        product["price"] = int(product["price"])
                        cached_products.append(product)
                    if cursor == 0:
                        break
            products = sorted(cached_products, key=lambda item: int(item["id"]), reverse=True)
            return products

    except Exception as e:
        await send_admin_message(f"Redis не отвечает: {e}")
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