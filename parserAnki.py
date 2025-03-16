import aiohttp
from bs4 import BeautifulSoup
import asyncio
import json

# URL страницы товара
url = "https://anki.team/product/new-balance-480v5-black/3227"
proxy = "http://quIFjeCM1N:INDeocNfeO@51.15.15.230:9061"

# Заголовки для имитации запроса от браузера
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
}

async def get_sizes(session, url, proxy):
    try:
        async with session.get(url, headers=headers, proxy=proxy, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                inputs = soup.find_all('input', {'type': 'radio'})

                available_sizes = []
                for input_tag in inputs:
                    if not input_tag.has_attr('disabled'):
                        label = soup.find('label', {'for': input_tag['id']})
                        if label:
                            size = label.find('span').text.strip()
                            available_sizes.append(size)
                return available_sizes
            else:
                print(f"Ошибка при запросе {url}. Код статуса: {response.status}")
                return -1
    except Exception as e:
        print(f"Ошибка при запросе {url}: {e}")
        return -1

async def test_size(url, proxy):
    async with aiohttp.ClientSession() as session:
        sizes = await get_sizes(session=session, url=url, proxy=proxy)
        if sizes == -1:
            print("Ошибка")
            return
        elif len(sizes) == 0:
            print("Нет доступных размеров")
        else:
            print(sizes)

async def get_all_sizes(urls):
    try:
        with open("size_errors.json", "r") as f:
            size_errors = json.load(f)
    except FileNotFoundError:
        size_errors = []
    all_sizes = {}
    async with aiohttp.ClientSession() as session:
        for sneaker in urls:
            sizes = await get_sizes(session=session, url=sneaker["url"], proxy=proxy)
            all_sizes[sneaker["art"]] = sizes
    return all_sizes # Возвращает словарь, ключ - ид модели, значение - список размеров

if __name__ == '__main__':
    asyncio.run(test_size(url, proxy))