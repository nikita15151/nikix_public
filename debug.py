import asyncio
import asyncio
from database import init_db
asyncio.run(init_db())

'''
from database import delete_all_data
asyncio.run(delete_all_data())

from database import upload_products
asyncio.run(upload_products('sneakers2.csv'))
'''

from database import delete_all_users
asyncio.run(delete_all_users())

'''
import requests
import asyncio
from database import fetch_all_products
async def main():
    products = await fetch_all_products()

    if products:
        for product in products:
            print(product)
            response = requests.head(product[9])
            if response.status_code != 200:
                print("Ссылка недоступна", product[9])
            else:
                print("Ссылка работает")
    else:
        print('Таблица product пуста')

if __name__ == "__main__":
    asyncio.run(main())


import csv
with open('sneakers2.csv', 'r', encoding='utf-8') as csv_file:
    reader = csv.DictReader(csv_file)
    print(reader.fieldnames)  # Покажет список заголовков
    for row in reader:
        print(row)
'''