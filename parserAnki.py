import aiohttp
from bs4 import BeautifulSoup
import asyncio
import json
import re

# URL страницы товара
url = "https://anki.team/product/hoka-one-one-x-nicole-mclaughlin-mafate-three2-white-neon-yellow/3628"

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

                # Находим все input-элементы с типом radio
                inputs = soup.find_all('input', {'type': 'radio'})

                available_sizes = []
                for input_tag in inputs:
                    if not input_tag.has_attr('disabled'):
                        label = soup.find('label', {'for': input_tag['id']})
                        if label:
                            # Ищем все span внутри label
                            spans = label.find_all('span')
                            if spans:
                                # Собираем текст из всех span и объединяем
                                size_parts = [span.text.strip() for span in spans]
                                full_size = ' '.join(size_parts)

                                # Очищаем от лишних пробелов и символов
                                full_size = re.sub(r'\s+', ' ', full_size).strip()

                                # Добавляем только если есть цифры в размере
                                if re.search(r'\d', full_size):
                                    available_sizes.append(full_size)
                return available_sizes
            else:
                print(f"Ошибка при запросе {url}. Код статуса: {response.status}")
                return -1
    except Exception as e:
        print(f"Ошибка при запросе {url}: {e}")
        return -1


async def test_size(url, proxy):
    async with aiohttp.ClientSession() as session:
        with open("bot_settings.json", "r") as f:
            data = json.load(f)
            proxy = data["proxy"]
        sizes = await get_sizes(session=session, url=url, proxy=proxy)
        if sizes == -1:
            print("Ошибка")
            return
        elif len(sizes) == 0:
            print("Нет доступных размеров")
        else:
            print("Доступные размеры:", sizes)


async def get_all_sizes(urls):
    all_sizes = {}
    async with aiohttp.ClientSession() as session:
        with open("bot_settings.json", "r") as f:
            data = json.load(f)
            proxy = data["proxy"]
        for sneaker in urls:
            sizes = await get_sizes(session=session, url=sneaker["url"], proxy=proxy)
            all_sizes[sneaker["art"]] = sizes
    return all_sizes


if __name__ == '__main__':
    asyncio.run(test_size(url))