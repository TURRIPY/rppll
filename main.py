import asyncio
import os
import re
import time
import sqlite3
import urllib.request
import sys
import platform
import psutil
import aiohttp
import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from pathlib import Path

BOT_START_TIME = time.time()

current_dir = Path(__file__).parent
load_dotenv(current_dir / "config.env", override=True)

def get_e(k): 
    val = os.getenv(k)
    if not val:
        return ""
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return val.replace('\\n', '\n')

TOK = get_e("BOT_TOKEN")
ADM = int(get_e("ADM_ID"))

PAY_INF = get_e("PAY_INF")
PAY_INF_TON = get_e("PAY_INF_TON")

bot = Bot(token=TOK, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Временные хранилища для отзывов
pending_reviews = {}
temp_case_info = {}

# Функция отправки логов
async def send_log(text: str):
    ch = get_e("LOG_CHANNEL_ID")
    if ch:
        try: await bot.send_message(ch, text)
        except Exception: pass

# бд
db = sqlite3.connect("bot_database.db", check_same_thread=False)
db.row_factory = sqlite3.Row
c = db.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, s INTEGER, r INTEGER, st INTEGER, tn INTEGER)""")
c.execute("""INSERT OR IGNORE INTO stats (id, s, r, st, tn) VALUES (1, 0, 0, 0, 0)""")
c.execute("""CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, uses INTEGER, exp REAL, disc INTEGER)""")
c.execute("""CREATE TABLE IF NOT EXISTS active_promos (uid INTEGER PRIMARY KEY, code TEXT)""")
c.execute("""CREATE TABLE IF NOT EXISTS cases (c_id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, username TEXT)""")
c.execute("""CREATE TABLE IF NOT EXISTS user_cases (uid INTEGER PRIMARY KEY, c_id INTEGER)""")
c.execute("""CREATE TABLE IF NOT EXISTS pending (uid INTEGER PRIMARY KEY, username TEXT, price REAL, pay_type TEXT, c_id INTEGER)""")
c.execute("""CREATE TABLE IF NOT EXISTS users (uid INTEGER PRIMARY KEY, purchases INTEGER DEFAULT 0)""")

# таблицы товаров
c.execute("""CREATE TABLE IF NOT EXISTS products_std (code TEXT PRIMARY KEY, name TEXT, p_rub REAL, p_str REAL, p_ton REAL, p_usdt REAL DEFAULT 0)""")
c.execute("""CREATE TABLE IF NOT EXISTS products_aged (year TEXT PRIMARY KEY, p_rub REAL, p_str REAL, p_ton REAL, p_usdt REAL DEFAULT 0)""")
c.execute("""CREATE TABLE IF NOT EXISTS products_num (code TEXT PRIMARY KEY, name TEXT, p_rub REAL, p_str REAL, p_ton REAL, p_usdt REAL DEFAULT 0)""")

# таблица инвойс для КБ
c.execute("""CREATE TABLE IF NOT EXISTS cp_invoices (inv_id INTEGER PRIMARY KEY, uid INTEGER)""")

# миграция структуры 
try: c.execute("ALTER TABLE pending ADD COLUMN product TEXT DEFAULT 'Неизвестно'")
except sqlite3.OperationalError: pass
try: c.execute("ALTER TABLE cases ADD COLUMN product TEXT DEFAULT 'Неизвестно'")
except sqlite3.OperationalError: pass
try: c.execute("ALTER TABLE cases ADD COLUMN status TEXT DEFAULT 'Ожидает подтверждения'")
except sqlite3.OperationalError: pass
try: c.execute("ALTER TABLE products_std ADD COLUMN p_usdt REAL DEFAULT 0")
except sqlite3.OperationalError: pass
try: c.execute("ALTER TABLE products_aged ADD COLUMN p_usdt REAL DEFAULT 0")
except sqlite3.OperationalError: pass
try: c.execute("ALTER TABLE products_num ADD COLUMN p_usdt REAL DEFAULT 0")
except sqlite3.OperationalError: pass

db.commit()

# функция работы с КБ АПИ
async def create_crypto_invoice(asset: str, amount: float, payload: str = ""):
    token = get_e("CRYPTO_PAY_TOKEN")
    if not token: return None
    url = get_e("CRYPTO_PAY_API_URL") or "https://pay.send.tg/api/"
    if not url.endswith("/"): url += "/"
    
    headers = {"Crypto-Pay-API-Token": token}
    data = {"asset": asset, "amount": str(amount), "payload": payload}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url + "createInvoice", json=data, headers=headers) as resp:
                res = await resp.json()
                if res.get("ok"): return res["result"]
    except Exception as e: pass
    return None

async def check_crypto_invoice(invoice_id: int):
    token = get_e("CRYPTO_PAY_TOKEN")
    if not token: return False
    url = get_e("CRYPTO_PAY_API_URL") or "https://pay.send.tg/api/"
    if not url.endswith("/"): url += "/"
    
    headers = {"Crypto-Pay-API-Token": token}
    params = {"invoice_ids": str(invoice_id)}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url + "getInvoices", params=params, headers=headers) as resp:
                res = await resp.json()
                if res.get("ok"):
                    items = res.get("result", {}).get("items", [])
                    if items and items[0]["status"] == "paid":
                        return True
    except Exception as e: pass
    return False

# работа с бд
def get_stats():
    c.execute("SELECT * FROM stats WHERE id = 1")
    return dict(c.fetchone())
    
def add_stats(s=0, r=0, st=0, tn=0):
    c.execute("UPDATE stats SET s = s + ?, r = r + ?, st = st + ?, tn = tn + ? WHERE id = 1", (s, r, st, tn))
    db.commit()

def add_purchase(uid: int):
    c.execute("INSERT OR IGNORE INTO users (uid, purchases) VALUES (?, 0)", (uid,))
    c.execute("UPDATE users SET purchases = purchases + 1 WHERE uid = ?", (uid,))
    db.commit()

def get_promocode(code):
    c.execute("SELECT * FROM promocodes WHERE code = ?", (code,))
    res = c.fetchone()
    return dict(res) if res else None

def get_active_promo(uid):
    c.execute("SELECT code FROM active_promos WHERE uid = ?", (uid,))
    res = c.fetchone()
    return res["code"] if res else None

def remove_active_promo(uid):
    c.execute("DELETE FROM active_promos WHERE uid = ?", (uid,))
    db.commit()

def get_discounted_price(uid: int, base_price: float) -> float:
    code = get_active_promo(uid)
    if not code: return base_price
    promo = get_promocode(code)
    if not promo or promo["uses"] <= 0 or (promo["exp"] > 0 and time.time() > promo["exp"]):
        remove_active_promo(uid)
        return base_price
    discounted = base_price * (1 - promo["disc"] / 100.0)
    return max(0.0, discounted)

# кнопки
def kb_start():
    b = InlineKeyboardBuilder()
    b.button(text=get_e("T_B_START_STD"), callback_data="menu_std")
    b.button(text=get_e("T_B_START_AGED"), callback_data="menu_aged")
    b.button(text=get_e("T_B_START_NUM"), callback_data="menu_num")
    b.adjust(1)
    return b.as_markup()

def kb_country_std():
    b = InlineKeyboardBuilder()
    c.execute("SELECT code, name FROM products_std")
    for row in c.fetchall():
        b.button(text=row["name"], callback_data=f"c_std_{row['code']}")
    b.button(text=get_e("T_B_CANCEL"), callback_data="cancel")
    b.adjust(3)
    return b.as_markup()

def kb_year_aged():
    b = InlineKeyboardBuilder()
    c.execute("SELECT year FROM products_aged")
    for row in c.fetchall():
        b.button(text=str(row["year"]), callback_data=f"y_aged_{row['year']}")
    b.button(text=get_e("T_B_CANCEL"), callback_data="cancel")
    b.adjust(2)
    return b.as_markup()

def kb_country_num():
    b = InlineKeyboardBuilder()
    c.execute("SELECT code, name FROM products_num")
    for row in c.fetchall():
        b.button(text=row["name"], callback_data=f"c_num_{row['code']}")
    b.button(text=get_e("T_B_CANCEL"), callback_data="cancel")
    b.adjust(3)
    return b.as_markup()

def kb_pay(acc_type, subtype):
    b = InlineKeyboardBuilder()
    b.button(text=get_e("T_B_STR"), callback_data=f"p_str_{acc_type}_{subtype}")
    b.button(text=get_e("T_B_RUB"), callback_data=f"p_rub_{acc_type}_{subtype}")
    b.button(text=get_e("T_B_TON"), callback_data=f"p_mton_{acc_type}_{subtype}")
    b.button(text="Crypto Pay (USDT)", callback_data=f"p_cp_USDT_{acc_type}_{subtype}")
    b.button(text="Crypto Pay (TON)", callback_data=f"p_cp_TON_{acc_type}_{subtype}")
    
    if acc_type == "std": b.button(text=get_e("T_B_BACK"), callback_data="menu_std")
    elif acc_type == "aged": b.button(text=get_e("T_B_BACK"), callback_data="menu_aged")
    elif acc_type == "num": b.button(text=get_e("T_B_BACK"), callback_data="menu_num")
    
    b.button(text=get_e("T_B_CANCEL"), callback_data="cancel")
    b.adjust(1, 2, 2, 1, 1) 
    return b.as_markup()

def kb_rub_conf(acc_type, subtype):
    b = InlineKeyboardBuilder()
    b.button(text=get_e("T_B_PAID"), callback_data=f"c_rub_{acc_type}_{subtype}")
    b.button(text=get_e("T_B_CANCEL"), callback_data="cancel")
    b.adjust(1)
    return b.as_markup()

def kb_mton_conf(acc_type, subtype):
    b = InlineKeyboardBuilder()
    b.button(text=get_e("T_B_PAID"), callback_data=f"c_mton_{acc_type}_{subtype}")
    b.button(text=get_e("T_B_CANCEL"), callback_data="cancel")
    b.adjust(1)
    return b.as_markup()

def kb_adm_chk(uid: int, pay_type="rub"):
    b = InlineKeyboardBuilder()
    b.button(text=get_e("T_B_APPR"), callback_data=f"ok_{pay_type}_{uid}")
    b.button(text=get_e("T_B_REJ"), callback_data=f"no_{pay_type}_{uid}")
    b.adjust(2)
    return b.as_markup()

# навигация 
@dp.message(CommandStart(), F.chat.type == "private")
async def c_start(m: types.Message):
    # Добавляем юзера в бд для рассылок
    c.execute("INSERT OR IGNORE INTO users (uid, purchases) VALUES (?, 0)", (m.from_user.id,))
    db.commit()

    if m.from_user.id == ADM:
        await m.answer(text=get_e("T_ADM_START"), disable_web_page_preview=True)
    else:
        await m.answer(text=get_e("T_START"), reply_markup=kb_start(), disable_web_page_preview=False)

@dp.callback_query(F.data == "cancel", F.message.chat.type == "private")
async def nav_cancel(c_q: types.CallbackQuery):
    await c_q.message.edit_text(text=get_e("T_START"), reply_markup=kb_start(), disable_web_page_preview=False)

@dp.callback_query(F.data == "menu_std", F.message.chat.type == "private")
async def nav_menu_std(c_q: types.CallbackQuery):
    await c_q.message.edit_text(text=get_e("T_MENU_COUNTRY"), reply_markup=kb_country_std())

@dp.callback_query(F.data.startswith("c_std_"), F.message.chat.type == "private")
async def nav_std_pay(c_q: types.CallbackQuery):
    country_code = c_q.data.split("_")[2]
    prod, _ = get_product_info("std", country_code)
    await c_q.message.edit_text(text=get_e("T_MENU_PAY").format(prod=prod), reply_markup=kb_pay("std", country_code))

@dp.callback_query(F.data == "menu_aged", F.message.chat.type == "private")
async def nav_menu_aged(c_q: types.CallbackQuery):
    await c_q.message.edit_text(text=get_e("T_MENU_AGED"), reply_markup=kb_year_aged())

@dp.callback_query(F.data.startswith("y_aged_"), F.message.chat.type == "private")
async def nav_aged_pay(c_q: types.CallbackQuery):
    year = c_q.data.split("_")[2]
    prod, _ = get_product_info("aged", year)
    await c_q.message.edit_text(text=get_e("T_MENU_PAY").format(prod=prod), reply_markup=kb_pay("aged", year))

@dp.callback_query(F.data == "menu_num", F.message.chat.type == "private")
async def nav_menu_num(c_q: types.CallbackQuery):
    await c_q.message.edit_text(text=get_e("T_MENU_NUM"), reply_markup=kb_country_num())

@dp.callback_query(F.data.startswith("c_num_"), F.message.chat.type == "private")
async def nav_num_pay(c_q: types.CallbackQuery):
    code = c_q.data.split("_")[2]
    prod, _ = get_product_info("num", code)
    await c_q.message.edit_text(text=get_e("T_MENU_PAY").format(prod=prod), reply_markup=kb_pay("num", code))

def get_product_info(acc_type, subtype):
    if acc_type == "std":
        c.execute("SELECT * FROM products_std WHERE code = ?", (subtype,))
        row = c.fetchone()
        if row: return f"Стандартный ({row['name']})", {"rub": row["p_rub"], "str": row["p_str"], "ton": row["p_ton"], "usdt": row["p_usdt"]}
    elif acc_type == "aged":
        c.execute("SELECT * FROM products_aged WHERE year = ?", (subtype,))
        row = c.fetchone()
        if row: return f"С отлегой ({row['year']} год)", {"rub": row["p_rub"], "str": row["p_str"], "ton": row["p_ton"], "usdt": row["p_usdt"]}
    elif acc_type == "num":
        c.execute("SELECT * FROM products_num WHERE code = ?", (subtype,))
        row = c.fetchone()
        if row: return f"Номер для смены ({row['name']})", {"rub": row["p_rub"], "str": row["p_str"], "ton": row["p_ton"], "usdt": row["p_usdt"]}
    return "Неизвестно", {"rub": 0, "str": 0, "ton": 0, "usdt": 0}

async def handle_free_bypass(c_q: types.CallbackQuery, uid: int, prod: str):
    code = get_active_promo(uid)
    if code:
        c.execute("UPDATE promocodes SET uses = uses - 1 WHERE code = ?", (code,))
        c.execute("DELETE FROM promocodes WHERE code = ? AND uses <= 0", (code,))
        remove_active_promo(uid)
        db.commit()
        
    username = c_q.from_user.username or c_q.from_user.first_name or str(uid)
    
    # cтрока add_purchase(uid) удалена, теперь покупка не засчитываетс..
    
    c.execute("INSERT INTO cases (uid, username, product, status) VALUES (?, ?, ?, 'Подтвержден')", (uid, username, prod))
    c_id = c.lastrowid
    c.execute("REPLACE INTO user_cases (uid, c_id) VALUES (?, ?)", (uid, c_id))
    db.commit()
    
    await c_q.message.edit_text(get_e("T_FREE_BYPASS").format(prod=prod))
    await bot.send_message(uid, get_e("T_SUCC"))
    await bot.send_message(ADM, get_e("T_ADM_FREE").format(u=username, i=uid, c=c_id, prod=prod))
    await send_log(get_e("T_LOG_APPROVED").format(c=c_id, u=username, i=uid, prod=prod))

# зв
@dp.callback_query(F.data.startswith("p_str_"), F.message.chat.type == "private")
async def pay_str(c_q: types.CallbackQuery):
    uid = c_q.from_user.id
    c.execute("SELECT c_id FROM user_cases WHERE uid = ?", (uid,))
    if c.fetchone(): return await c_q.answer(get_e("T_ERR_ALREADY_HAS_CASE"), show_alert=True)

    _, _, acc_type, subtype = c_q.data.split("_")
    prod, prices = get_product_info(acc_type, subtype)
    base_price = prices["str"]
    final_price = int(get_discounted_price(uid, base_price))
    
    if final_price <= 0: return await handle_free_bypass(c_q, uid, prod)
    
    await c_q.message.delete()
    await bot.send_invoice(
        uid, 
        title=get_e("T_INV_T"), 
        description=get_e("T_INV_D").format(prod=prod),
        payload=f"acc_str_{acc_type}_{subtype}", 
        provider_token="", 
        currency="XTR",
        prices=[LabeledPrice(label=get_e("T_INV_L"), amount=final_price)]
    )

@dp.pre_checkout_query(lambda q: True)
async def pre_chk(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def succ_pay(m: types.Message):
    if m.chat.type != "private": return
    uid = m.from_user.id
    payload = m.successful_payment.invoice_payload
    parts = payload.split("_")
    
    if len(parts) >= 4:
        acc_type, subtype = parts[2], parts[3]
        prod, _ = get_product_info(acc_type, subtype)
    else: prod = "Неизвестно"
    
    code = get_active_promo(uid)
    if code:
        c.execute("UPDATE promocodes SET uses = uses - 1 WHERE code = ?", (code,))
        c.execute("DELETE FROM promocodes WHERE code = ? AND uses <= 0", (code,))
        remove_active_promo(uid)
        db.commit()

    add_stats(s=1, st=m.successful_payment.total_amount)
    add_purchase(uid) 
    
    username = m.from_user.username or m.from_user.first_name or str(uid)
    
    await m.answer(get_e("T_SUCC"))
    
    c.execute("INSERT INTO cases (uid, username, product, status) VALUES (?, ?, ?, 'Подтвержден')", (uid, username, prod))
    c_id = c.lastrowid
    c.execute("REPLACE INTO user_cases (uid, c_id) VALUES (?, ?)", (uid, c_id))
    db.commit()
    
    await bot.send_message(ADM, get_e("T_ADM_STR").format(u=username, i=uid, c=c_id, prod=prod))
    await send_log(get_e("T_LOG_APPROVED").format(c=c_id, u=username, i=uid, prod=prod))

# рубли
@dp.callback_query(F.data.startswith("p_rub_"), F.message.chat.type == "private")
async def pay_rub(c_q: types.CallbackQuery):
    uid = c_q.from_user.id
    _, _, acc_type, subtype = c_q.data.split("_")
    prod, prices = get_product_info(acc_type, subtype)
    base_price = prices["rub"]
    final_price = int(get_discounted_price(uid, base_price))
    
    if final_price <= 0: return await handle_free_bypass(c_q, uid, prod)
        
    await c_q.message.edit_text(get_e("T_RUB_REQ").format(prod=prod, p=final_price, inf=PAY_INF), reply_markup=kb_rub_conf(acc_type, subtype))

@dp.callback_query(F.data.startswith("c_rub_"), F.message.chat.type == "private")
async def chk_rub(c_q: types.CallbackQuery):
    uid = c_q.from_user.id
    c.execute("SELECT * FROM pending WHERE uid = ?", (uid,))
    if c.fetchone(): return await c_q.answer("Ожидайте подтверждения!", show_alert=True)

    c.execute("SELECT c_id FROM user_cases WHERE uid = ?", (uid,))
    if c.fetchone(): return await c_q.answer(get_e("T_ERR_ALREADY_HAS_CASE"), show_alert=True)

    _, _, acc_type, subtype = c_q.data.split("_")
    prod, prices = get_product_info(acc_type, subtype)
    base_price = prices["rub"]
    
    username = c_q.from_user.username or c_q.from_user.first_name or str(uid)
    final_price = int(get_discounted_price(uid, base_price))
    
    c.execute("INSERT INTO cases (uid, username, product, status) VALUES (?, ?, ?, 'Ожидает подтверждения')", (uid, username, prod))
    c_id = c.lastrowid
    c.execute("REPLACE INTO pending (uid, username, price, pay_type, c_id, product) VALUES (?, ?, ?, ?, ?, ?)", (uid, username, final_price, "rub", c_id, prod))
    db.commit()
    
    await c_q.message.edit_text(get_e("T_RUB_WAIT"))
    await bot.send_message(ADM, get_e("T_ADM_RUB_REQ").format(u=username, i=uid, p=final_price, c=c_id, prod=prod), reply_markup=kb_adm_chk(uid, "rub"))
    await send_log(get_e("T_LOG_NEW_CASE").format(c=c_id, u=username, i=uid, prod=prod))

# тон
@dp.callback_query(F.data.startswith("p_mton_"), F.message.chat.type == "private")
async def pay_mton(c_q: types.CallbackQuery):
    uid = c_q.from_user.id
    _, _, acc_type, subtype = c_q.data.split("_")
    prod, prices = get_product_info(acc_type, subtype)
    base_price = prices["ton"]
    final_price = round(get_discounted_price(uid, base_price), 2)
    
    if final_price <= 0: return await handle_free_bypass(c_q, uid, prod)
        
    await c_q.message.edit_text(get_e("T_TON_REQ").format(prod=prod, p=final_price, inf=PAY_INF_TON), reply_markup=kb_mton_conf(acc_type, subtype))

@dp.callback_query(F.data.startswith("c_mton_"), F.message.chat.type == "private")
async def chk_mton(c_q: types.CallbackQuery):
    uid = c_q.from_user.id
    c.execute("SELECT * FROM pending WHERE uid = ?", (uid,))
    if c.fetchone(): return await c_q.answer("Ожидайте подтверждения!", show_alert=True)

    c.execute("SELECT c_id FROM user_cases WHERE uid = ?", (uid,))
    if c.fetchone(): return await c_q.answer(get_e("T_ERR_ALREADY_HAS_CASE"), show_alert=True)

    _, _, acc_type, subtype = c_q.data.split("_")
    prod, prices = get_product_info(acc_type, subtype)
    base_price = prices["ton"]
    
    username = c_q.from_user.username or c_q.from_user.first_name or str(uid)
    final_price = round(get_discounted_price(uid, base_price), 2)
    
    c.execute("INSERT INTO cases (uid, username, product, status) VALUES (?, ?, ?, 'Ожидает подтверждения')", (uid, username, prod))
    c_id = c.lastrowid
    c.execute("REPLACE INTO pending (uid, username, price, pay_type, c_id, product) VALUES (?, ?, ?, ?, ?, ?)", (uid, username, final_price, "ton", c_id, prod))
    db.commit()
    
    await c_q.message.edit_text(get_e("T_TON_WAIT"))
    await bot.send_message(ADM, get_e("T_ADM_TON_REQ").format(u=username, i=uid, p=final_price, c=c_id, prod=prod), reply_markup=kb_adm_chk(uid, "ton"))
    await send_log(get_e("T_LOG_NEW_CASE").format(c=c_id, u=username, i=uid, prod=prod))


# CRYPTO PAY
@dp.callback_query(F.data.startswith("p_cp_"), F.message.chat.type == "private")
async def pay_cp(c_q: types.CallbackQuery):
    uid = c_q.from_user.id
    parts = c_q.data.split("_")
    asset = parts[2]
    acc_type = parts[3]
    subtype = parts[4]
    
    c.execute("SELECT c_id FROM user_cases WHERE uid = ?", (uid,))
    if c.fetchone(): return await c_q.answer(get_e("T_ERR_ALREADY_HAS_CASE"), show_alert=True)

    prod, prices = get_product_info(acc_type, subtype)
    
    if asset == "TON": base_price = prices["ton"]
    else: base_price = prices["usdt"]
        
    final_price = round(get_discounted_price(uid, base_price), 2)
    if final_price <= 0: return await handle_free_bypass(c_q, uid, prod)
        
    token = get_e("CRYPTO_PAY_TOKEN")
    if not token: return await c_q.answer("Оплата Crypto Pay сейчас недоступна. Админ еще не настроил токен.", show_alert=True)
        
    await c_q.message.edit_text("Генерирую счет для оплаты через Crypto Pay...")
    
    inv = await create_crypto_invoice(asset, final_price, f"order_{uid}_{acc_type}_{subtype}")
    if not inv:
        return await c_q.message.edit_text("Произошла ошибка при создании счета. Попробуйте другой способ оплаты.")
        
    inv_id = inv["invoice_id"]
    pay_url = inv["pay_url"]
    
    b = InlineKeyboardBuilder()
    b.button(text="Оплатить", url=pay_url)
    b.button(text="Проверить оплату", callback_data=f"chk_cp_{inv_id}_{acc_type}_{subtype}_{asset}_{final_price}")
    b.button(text=get_e("T_B_CANCEL"), callback_data="cancel")
    b.adjust(1)
    
    await c_q.message.edit_text(
        f"<b>Автоматическая оплата Crypto Pay</b>\n\nТовар: <b>{prod}</b>\nК оплате: <b>{final_price} {asset}</b>\n\n<i>1. Нажмите «Оплатить» и завершите перевод.\n2. Вернитесь в бота и нажмите «Проверить оплату».</i>",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data.startswith("chk_cp_"), F.message.chat.type == "private")
async def chk_cp(c_q: types.CallbackQuery):
    parts = c_q.data.split("_")
    inv_id = int(parts[2])
    acc_type = parts[3]
    subtype = parts[4]
    asset = parts[5]
    price = float(parts[6])
    uid = c_q.from_user.id
    
    c.execute("SELECT * FROM cp_invoices WHERE inv_id = ?", (inv_id,))
    if c.fetchone(): return await c_q.answer("Счет уже оплачен и товар выдан!", show_alert=True)
        
    is_paid = await check_crypto_invoice(inv_id)
    if is_paid:
        c.execute("INSERT INTO cp_invoices (inv_id, uid) VALUES (?, ?)", (inv_id, uid))
        prod, _ = get_product_info(acc_type, subtype)
        
        code = get_active_promo(uid)
        if code:
            c.execute("UPDATE promocodes SET uses = uses - 1 WHERE code = ?", (code,))
            c.execute("DELETE FROM promocodes WHERE code = ? AND uses <= 0", (code,))
            remove_active_promo(uid)

        if asset == "TON": add_stats(s=1, tn=price)
        else: add_stats(s=1)
        
        username = c_q.from_user.username or c_q.from_user.first_name or str(uid)
        add_purchase(uid)

        c.execute("INSERT INTO cases (uid, username, product, status) VALUES (?, ?, ?, 'Подтвержден')", (uid, username, prod))
        c_id = c.lastrowid
        c.execute("REPLACE INTO user_cases (uid, c_id) VALUES (?, ?)", (uid, c_id))
        db.commit()

        await c_q.message.edit_text(f"Оплата {price} {asset} успешно найдена!\n\nТовар: <b>{prod}</b>\nБот выдаст товар автоматически через 1-10 минут.")
        await bot.send_message(ADM, f"<b>[ Авто-покупка Crypto Pay ]</b>\nПользователь: @{username} (ID: {uid})\nОплачено: {price} {asset}\nТовар: {prod}\nКейс #{c_id}")
        await send_log(get_e("T_LOG_APPROVED").format(c=c_id, u=username, i=uid, prod=prod))
    else:
        await c_q.answer("Оплата еще не поступила. Завершите перевод по ссылке и попробуйте снова через 10 секунд.", show_alert=True)


# АДМ
@dp.callback_query(F.data.startswith("ok_") | F.data.startswith("no_"), F.message.chat.type == "private")
async def adm_ver(c_q: types.CallbackQuery):
    if c_q.from_user.id != ADM: return
    parts = c_q.data.split("_")
    act, pay_type, uid = parts[0], parts[1], int(parts[2])
    
    c.execute("SELECT * FROM pending WHERE uid = ? AND pay_type = ?", (uid, pay_type))
    pend_data = c.fetchone()
    if not pend_data: return await c_q.message.edit_text("Заявка уже обработана или отменена.")
        
    c_id, username, price, prod = pend_data["c_id"], pend_data["username"], pend_data["price"], pend_data["product"]
    c.execute("DELETE FROM pending WHERE uid = ? AND pay_type = ?", (uid, pay_type))
    db.commit()
    
    if act == "ok":
        code = get_active_promo(uid)
        if code:
            c.execute("UPDATE promocodes SET uses = uses - 1 WHERE code = ?", (code,))
            c.execute("DELETE FROM promocodes WHERE code = ? AND uses <= 0", (code,))
            remove_active_promo(uid)
            db.commit()

        if pay_type == "rub":
            add_stats(s=1, r=price)
            msg_template = get_e("T_ADM_RUB_APPR")
        elif pay_type == "ton":
            add_stats(s=1, tn=price)
            msg_template = get_e("T_ADM_TON_APPR")

        c.execute("UPDATE cases SET status = 'Подтвержден' WHERE c_id = ?", (c_id,))
        c.execute("REPLACE INTO user_cases (uid, c_id) VALUES (?, ?)", (uid, c_id))
        db.commit()
        
        await c_q.message.edit_text(msg_template.format(u=username, i=uid, c=c_id, p=price, prod=prod))
        await bot.send_message(uid, get_e("T_SUCC"))
        await send_log(get_e("T_LOG_APPROVED").format(c=c_id, u=username, i=uid, prod=prod))
    else:
        c.execute("DELETE FROM cases WHERE c_id = ?", (c_id,))
        db.commit()

        if pay_type == "rub":
            msg_template = get_e("T_ADM_RUB_REJ")
        elif pay_type == "ton":
            msg_template = get_e("T_ADM_TON_REJ")
            
        await c_q.message.edit_text(msg_template.format(u=username, i=uid, c=c_id))
        await bot.send_message(uid, get_e("T_USR_REJ"))

# profile и promo (Единственная команда доступная в группах)
@dp.message(Command("profile"))
async def c_profile(m: types.Message):
    args = m.text.split()
    target_uid = m.from_user.id
    if len(args) > 1 and m.from_user.id in [ADM, 610519378]:
        try:
            target_uid = int(args[1])
        except ValueError:
            return await m.answer("Неверный формат ID. Используйте: /profile [ID]")
            
    # Получаем данные пользователя
    if target_uid == m.from_user.id:
        first_name = m.from_user.first_name or "Без имени"
        username = f"@{m.from_user.username}" if m.from_user.username else "Скрыт"
    else:
        try:
            chat_info = await bot.get_chat(target_uid)
            first_name = chat_info.first_name or "Без имени"
            username = f"@{chat_info.username}" if chat_info.username else "Скрыт"
        except Exception:
            first_name = "Неизвестно"
            username = "Скрыт"

    c.execute("SELECT purchases FROM users WHERE uid = ?", (target_uid,))
    row = c.fetchone()
    purchases = row["purchases"] if row else 0
    
    text = (f"<tg-emoji emoji-id='5902335789798265487'>👤</tg-emoji> | <b>Профиль</b>\n\n"
        f"<b>Никнейм:</b> {first_name}\n"
        f"<b>Юзернейм:</b> {username}\n"
        f"<b>Айди:</b> <code>{target_uid}</code>\n\n"
        f"<b><tg-emoji emoji-id='5895514131896733546'>✅</tg-emoji> | Покупок:</b> {purchases}")
    
    try:
        photos = await bot.get_user_profile_photos(target_uid)
        if photos.total_count > 0: 
            await m.answer_photo(photo=photos.photos[0][-1].file_id, caption=text)
        else: 
            await m.answer(text)
    except Exception:
        await m.answer(text)

@dp.message(Command("promo"), F.chat.type == "private")
async def c_use_promo(m: types.Message):
    if m.from_user.id == ADM: return await m.answer("Админам нельзя использовать промокоды.")
    if get_active_promo(m.from_user.id): return await m.answer(f"У вас уже активен промокод! Используйте его.")

    args = m.text.split()
    if len(args) < 2: return await m.answer("Использование: /promo [КОД]")
    code = args[1].upper()
    promo = get_promocode(code)
    
    if not promo or promo["uses"] <= 0 or (promo["exp"] > 0 and time.time() > promo["exp"]):
        return await m.answer(get_e("T_PROMO_ERR"))
        
    c.execute("REPLACE INTO active_promos (uid, code) VALUES (?, ?)", (m.from_user.id, code))
    db.commit()
    await m.answer(get_e("T_PROMO_OK").format(d=promo["disc"]))

@dp.message(Command("create_promocode"), F.chat.type == "private")
async def c_create_promo(m: types.Message):
    if m.from_user.id != ADM: return
    args = m.text.split()
    if len(args) < 5: return await m.answer("Формат: /create_promocode код колво-использования часы скидка \n\n(Часы = 0 для бессрочного)")
        
    code, uses, hours, disc = args[1].upper(), int(args[2]), float(args[3]), int(args[4])
    if disc > 100: return await m.answer("Ошибка: Скидка не может быть > 100%.")
        
    exp_time = time.time() + (hours * 3600) if hours > 0 else 0
    c.execute("REPLACE INTO promocodes (code, uses, exp, disc) VALUES (?, ?, ?, ?)", (code, uses, exp_time, disc))
    db.commit()
    await m.answer(f"Промокод <b>{code}</b> создан!\nСкидка: {disc}%\nИспользований: {uses}")

@dp.message(Command("delete_promocode"), F.chat.type == "private")
async def c_delete_promo(m: types.Message):
    if m.from_user.id != ADM: return
    args = m.text.split()
    if len(args) < 2: return await m.answer("Формат: /delete_promocode [КОД]")
    code = args[1].upper()
    if get_promocode(code):
        c.execute("DELETE FROM promocodes WHERE code = ?", (code,))
        c.execute("DELETE FROM active_promos WHERE code = ?", (code,))
        db.commit()
        await m.answer(f"Промокод <b>{code}</b> успешно удален.")
    else: await m.answer("Такого промокода не существует.")

@dp.message(Command("promocodes"), F.chat.type == "private")
async def c_list_promos(m: types.Message):
    if m.from_user.id != ADM: return
    c.execute("SELECT * FROM promocodes")
    promos = c.fetchall()
    if not promos: return await m.answer("Список пуст.")
    res = "<b>Все промокоды:</b>\n\n"
    for p in promos:
        exp_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(p['exp'])) if p['exp'] > 0 else "Бессрочно"
        res += f"<b>{p['code']}</b>: {p['disc']}% скидка | Осталось: {p['uses']} | До: {exp_str}\n"
    await m.answer(res)

@dp.message(Command("active_promocodes"), F.chat.type == "private")
async def c_active_promos(m: types.Message):
    if m.from_user.id != ADM: return
    c.execute("SELECT * FROM promocodes WHERE uses > 0 AND (exp = 0 OR exp > ?)", (time.time(),))
    active = c.fetchall()
    if not active: return await m.answer("Активных нет.")
    res = "<b>Активные промокоды:</b>\n\n"
    for p in active: res += f"<b>{p['code']}</b> скидка {p['disc']}% (Осталось: {p['uses']})\n"
    await m.answer(res)

# ДОБАВЛЕНИЕ И УДАЛЕНИЕ ТОВАРОВ
@dp.message(Command("add"), F.chat.type == "private")
async def c_add_item(m: types.Message):
    if m.from_user.id != ADM: return
    args = m.text.split()
    if len(args) < 3: return await m.answer("Формат:\n/add reg [код] [название_слитно] [руб] [звезды] [ton] [usdt]\n/add old [год] [руб] [звезды] [ton] [usdt]\n/add num [код] [название_слитно] [руб] [звезды] [ton] [usdt]")
    
    type_ = args[1].lower()
    try:
        if type_ == "reg":
            if len(args) < 8: return await m.answer("Недостаточно аргументов для reg. Нужно 6 параметров.")
            code, name, rub, str_p, ton, usdt = args[2], args[3], float(args[4]), float(args[5]), float(args[6]), float(args[7])
            name = name.replace("_", " ") 
            c.execute("REPLACE INTO products_std (code, name, p_rub, p_str, p_ton, p_usdt) VALUES (?, ?, ?, ?, ?, ?)", (code, name, rub, str_p, ton, usdt))
            db.commit()
            await m.answer(get_e("T_ADM_ADD_REG").format(name=name, code=code))
        elif type_ == "old":
            if len(args) < 7: return await m.answer("Недостаточно аргументов для old. Нужно 5 параметров.")
            year, rub, str_p, ton, usdt = args[2], float(args[3]), float(args[4]), float(args[5]), float(args[6])
            c.execute("REPLACE INTO products_aged (year, p_rub, p_str, p_ton, p_usdt) VALUES (?, ?, ?, ?, ?)", (year, rub, str_p, ton, usdt))
            db.commit()
            await m.answer(get_e("T_ADM_ADD_OLD").format(year=year))
        elif type_ == "num":
            if len(args) < 8: return await m.answer("Недостаточно аргументов для num. Нужно 6 параметров.")
            code, name, rub, str_p, ton, usdt = args[2], args[3], float(args[4]), float(args[5]), float(args[6]), float(args[7])
            name = name.replace("_", " ") 
            c.execute("REPLACE INTO products_num (code, name, p_rub, p_str, p_ton, p_usdt) VALUES (?, ?, ?, ?, ?, ?)", (code, name, rub, str_p, ton, usdt))
            db.commit()
            await m.answer(get_e("T_ADM_ADD_NUM").format(name=name, code=code))
    except ValueError:
        await m.answer("Ошибка: цены должны быть числами.")

@dp.message(Command("del"), F.chat.type == "private")
async def c_del_item(m: types.Message):
    if m.from_user.id != ADM: return
    args = m.text.split()
    if len(args) < 3: return await m.answer("Формат:\n/del reg [код]\n/del old [год]\n/del num [код]")
        
    type_, val = args[1].lower(), args[2]
    if type_ == "reg":
        c.execute("DELETE FROM products_std WHERE code = ?", (val,))
        db.commit()
        await m.answer(get_e("T_ADM_DEL_REG").format(code=val))
    elif type_ == "old":
        c.execute("DELETE FROM products_aged WHERE year = ?", (val,))
        db.commit()
        await m.answer(get_e("T_ADM_DEL_OLD").format(year=val))
    elif type_ == "num":
        c.execute("DELETE FROM products_num WHERE code = ?", (val,))
        db.commit()
        await m.answer(get_e("T_ADM_DEL_NUM").format(code=val))

@dp.message(Command("broadcast"), F.chat.type == "private")
async def c_broadcast(m: types.Message):
    if m.from_user.id != ADM: return
    
    c.execute("SELECT uid FROM users")
    users = c.fetchall()
    if not users: return await m.answer("Нет пользователей для рассылки.")
    
    text_to_send = None
    if m.text and len(m.text.split()) > 1:
        cmd_len = len(m.text.split()[0])
        text_to_send = m.html_text[cmd_len:].strip()
    

    if not m.reply_to_message and not text_to_send:
        return await m.answer("Используйте: /broadcast &lt;текст&gt; или сделайте Reply на сообщение (с текстом или медиа).")
        
    await m.answer(get_e("T_BROADCAST_START"))
    
    success_count = 0
    fail_count = 0
    error_details = {} # словарь для группировки одинаковых ошибок
    
    for u in users:
        uid = u["uid"]
        try:
            if m.reply_to_message:
                await m.reply_to_message.copy_to(uid)
            else:
                await bot.send_message(uid, text_to_send)
            
            success_count += 1
            await asyncio.sleep(0.05) # лимит Telegram: ~30 сообщений в секунду
            
        except Exception as e:
            fail_count += 1
            error_msg = str(e)
            

            if error_msg not in error_details:
                error_details[error_msg] = 1
            else:
                error_details[error_msg] += 1
            
            if "Too Many Requests" in error_msg or "retry after" in error_msg.lower():
                await asyncio.sleep(3) 

    # формируем итоговый текст с отчетом
    final_text = get_e("T_BROADCAST_DONE").format(count=success_count)
    
    if fail_count > 0:
        final_text += f"\n\n<b>Не удалось отправить:</b> {fail_count} пользователям."
        final_text += "\n<b>Причины ошибок:</b>"
        for err, cnt in error_details.items():
            final_text += f"\n— <code>{err}</code> ({cnt} раз)"
            
    await m.answer(final_text, parse_mode="HTML")

# oбработчик текста для отзывов ДО chat_h
@dp.message(F.chat.type == "private", ~F.text.startswith('/'), lambda m: m.from_user.id in pending_reviews)
async def catch_review_comment(m: types.Message):
    uid = m.from_user.id
    rev_data = pending_reviews.pop(uid)
    c_id = rev_data["c_id"]
    stars = rev_data["stars"]
    date_str = rev_data["time"]
    comment = m.text or "[Без текста]"
    
    prod = temp_case_info.pop(str(c_id), "Неизвестный товар")
    
    rev_text = get_e("T_REVIEW_PUBLISHED").format(prod=prod, date=date_str, stars=stars, comment=comment)
    
    REV_CH = get_e("REVIEW_CHANNEL_ID")
    if REV_CH:
        try: await bot.send_message(REV_CH, rev_text)
        except Exception: pass
    else:
        # если канал отзывов не указан, шлем в канал логов
        await send_log(rev_text)
        
    await m.answer(get_e("T_REVIEW_THANKS"))

# чат с админом
@dp.message(
    F.chat.type == "private", 
    ~F.sticker, 
    ~F.text.startswith('/'), 
    ~F.caption.startswith('/')
)
async def chat_h(m: types.Message):
    if m.from_user.id == ADM:
        rep = m.reply_to_message
        if rep:
            rep_text = rep.text or rep.caption or ""
            match = re.search(r"#(\d+)", rep_text)
            
            if match:
                c_id = int(match.group(1))
                c.execute("SELECT uid FROM cases WHERE c_id = ?", (c_id,))
                case_row = c.fetchone()
                
                if case_row:
                    uid = case_row["uid"]
                    if m.text:
                        await bot.send_message(uid, get_e("T_MGR_M").format(t=m.text))
                    else:
                        mgr_text = get_e("T_MGR_M").format(t=m.caption or "").strip()
                        if len(mgr_text) <= 1024:
                            await bot.copy_message(chat_id=uid, from_chat_id=m.chat.id, message_id=m.message_id, caption=mgr_text)
                        else:
                            await bot.send_message(uid, get_e("T_MGR_M").format(t="[Медиа]"))
                            await m.send_copy(chat_id=uid)
                else: 
                    await m.answer("Кейс закрыт или не найден.")
            else: 
                await m.answer("Сделайте <b>Reply</b> на сообщение с #ID.")
    else:
        c.execute("SELECT c_id FROM user_cases WHERE uid = ?", (m.from_user.id,))
        case_row = c.fetchone()
        
        if case_row:
            c_id = case_row["c_id"]
            c.execute("SELECT username FROM cases WHERE c_id = ?", (c_id,))
            u_name = c.fetchone()["username"]
            
            if m.text:
                await bot.send_message(ADM, get_e("T_USR_M").format(c=c_id, u=u_name, t=m.text))
            else:
                usr_text = get_e("T_USR_M").format(c=c_id, u=u_name, t=m.caption or "").strip()
                if len(usr_text) <= 1024:
                    await bot.copy_message(chat_id=ADM, from_chat_id=m.chat.id, message_id=m.message_id, caption=usr_text)
                else:
                    await bot.send_message(ADM, get_e("T_USR_M").format(c=c_id, u=u_name, t="[Медиа вложение]"))
                    await m.send_copy(chat_id=ADM)

# адм команды
@dp.message(Command("end"), F.chat.type == "private")
async def c_end(m: types.Message):
    if m.from_user.id != ADM: return
    args = m.text.split()
    
    if len(args) == 3 and args[1].isdigit() and args[2].lower() in ['tr', 'f']:
        c_id = int(args[1])
        status = args[2].lower()
        
        c.execute("SELECT uid, product FROM cases WHERE c_id = ?", (c_id,))
        case_row = c.fetchone()
        
        if case_row:
            target_uid = case_row["uid"]
            prod_name = case_row["product"]
            c.execute("DELETE FROM cases WHERE c_id = ?", (c_id,))
            c.execute("DELETE FROM user_cases WHERE uid = ?", (target_uid,))
            db.commit()
            
            if status == "tr":
                add_purchase(target_uid) 
                temp_case_info[str(c_id)] = prod_name
                await m.answer(get_e("T_C_END_A").format(c=c_id) + " (Успешно закрыт, покупка засчитана)")
                await bot.send_message(target_uid, get_e("T_C_END_U"))
                await send_log(get_e("T_LOG_CASE_CLOSED").format(c=c_id, status="Успешно (Выдан)"))
                
                # Запрашиваем отзыв
                kb = InlineKeyboardBuilder()
                kb.button(text=get_e("T_B_YES"), callback_data=f"rev_yes_{c_id}")
                kb.button(text=get_e("T_B_NO"), callback_data="rev_no")
                kb.adjust(2)
                await bot.send_message(target_uid, get_e("T_REVIEW_ASK").format(prod=prod_name), reply_markup=kb.as_markup())
                
            elif status == "f":
                await m.answer(get_e("T_C_END_A").format(c=c_id) + " (Отменено, без зачисления покупки)")
                await bot.send_message(target_uid, get_e("T_USR_REJ"))
                await send_log(get_e("T_LOG_CASE_CLOSED").format(c=c_id, status="Отменено (Отказ)"))
        else: await m.answer("Кейс не найден.")
    else: await m.answer("Формат команды:\n/end [ID] tr — Успешно завершить (покупка зачислится)\n/end [ID] f — Отменить заказ (без зачисления покупки)")

# коллбеки для отзывов
@dp.callback_query(F.data.startswith("rev_yes_"), F.message.chat.type == "private")
async def h_rev_yes(c_q: types.CallbackQuery):
    c_id = c_q.data.split("_")[2]
    b = InlineKeyboardBuilder()
    for i in range(1, 6):
        b.button(text=f"{i}⭐", callback_data=f"rev_star_{c_id}_{i}")
    b.adjust(5)
    await c_q.message.edit_text(get_e("T_REVIEW_STARS"), reply_markup=b.as_markup())

@dp.callback_query(F.data == "rev_no", F.message.chat.type == "private")
async def h_rev_no(c_q: types.CallbackQuery):
    await c_q.message.edit_text(get_e("T_REVIEW_THANKS"))

@dp.callback_query(F.data.startswith("rev_star_"), F.message.chat.type == "private")
async def h_rev_star(c_q: types.CallbackQuery):
    _, _, c_id, star = c_q.data.split("_")
    pending_reviews[c_q.from_user.id] = {
        "c_id": c_id, 
        "stars": "⭐" * int(star), 
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    await c_q.message.edit_text(get_e("T_REVIEW_COMMENT"))

@dp.message(Command("help"), F.chat.type == "private")
async def c_help(m: types.Message):
    if m.from_user.id == ADM: await m.answer(get_e("T_HELP"))

@dp.message(Command("stats"), F.chat.type == "private")
async def c_stats(m: types.Message):
    if m.from_user.id == ADM: 
        s = get_stats()
        stats_msg = get_e("T_STATS").format(s=s["s"], r=s["r"], st=s["st"], tn=s["tn"])
        
        c.execute("SELECT name, p_rub, p_str, p_ton, p_usdt FROM products_std")
        std_prods = c.fetchall()
        std_list = "\n".join([f"- {p['name']} ({p['p_rub']}₽ | {p['p_str']}ЗВ | {p['p_ton']} TON | {p['p_usdt']} USDT)" for p in std_prods]) if std_prods else "Нет товаров"
        
        c.execute("SELECT year, p_rub, p_str, p_ton, p_usdt FROM products_aged")
        aged_prods = c.fetchall()
        aged_list = "\n".join([f"- {p['year']} год ({p['p_rub']}₽ | {p['p_str']}ЗВ | {p['p_ton']} TON | {p['p_usdt']} USDT)" for p in aged_prods]) if aged_prods else "Нет товаров"
        
        c.execute("SELECT code, name, p_rub, p_str, p_ton, p_usdt FROM products_num")
        num_prods = c.fetchall()
        num_list = "\n".join([f"- {p['name']} ({p['code']}) ({p['p_rub']}₽ | {p['p_str']}ЗВ | {p['p_ton']} TON | {p['p_usdt']} USDT)" for p in num_prods]) if num_prods else "Нет товаров"
        
        prod_msg = f"\n\n<b>[ Активные товары ]</b>\n<b>Региональные(СТАНДАРТНЫЕ):</b>\n{std_list}\n\n<b>С отлегой:</b>\n{aged_list}\n\n<b>Номера для смены:</b>\n{num_list}"
        
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        os_info = f"{platform.system()} {platform.release()}"
        host_msg = get_e("T_STATS_HOST").format(
            os=os_info, cpu=cpu, ram_u=ram.used//1048576, ram_t=ram.total//1048576, 
            ram_p=ram.percent, ver=get_e("BOT_VERSION")
        )
        
        await m.answer(stats_msg + prod_msg + "\n\n" + host_msg)

@dp.message(Command("ping"), F.chat.type == "private")
async def c_ping(m: types.Message):
    if m.from_user.id not in [ADM, 610519378]: return
    start_time = time.time()
    msg = await m.answer("<i>Замеряю отклик...</i>")
    ping_ms = round((time.time() - start_time) * 1000)
    await msg.edit_text(f"<b>{get_e('T_PING')}</b>\nВремя отклика: <code>{ping_ms} мс</code>")

@dp.message(Command("cases"), F.chat.type == "private")
async def c_admin_cases(m: types.Message):
    if m.from_user.id != ADM: return
    await send_cases_page(m, 1)

@dp.callback_query(F.data.startswith("cases_page_"), F.message.chat.type == "private")
async def c_cases_nav(c_q: types.CallbackQuery):
    if c_q.from_user.id != ADM: return
    page = int(c_q.data.split("_")[2])
    await send_cases_page(c_q.message, page, edit=True)

async def send_cases_page(message: types.Message, page: int, edit: bool = False):
    limit = 5
    offset = (page - 1) * limit
    
    c.execute("SELECT COUNT(*) FROM cases")
    total_count = c.fetchone()[0]
    total_pages = (total_count + limit - 1) // limit or 1
    
    if total_count == 0:
        text = get_e("T_ADM_CASES_EMPTY")
        return await (message.edit_text(text) if edit else message.answer(text))

    c.execute("SELECT * FROM cases LIMIT ? OFFSET ?", (limit, offset))
    rows = c.fetchall()
    
    items_text = ""
    for r in rows:
        r_dict = dict(r)
        items_text += get_e("T_ADM_CASES_ITEM").format(
            c_id=r_dict['c_id'], 
            u=r_dict['username'], 
            prod=r_dict.get('product', 'Неизвестно'), 
            status=r_dict.get('status', 'Неизвестно')
        ) + "\n"

    text = get_e("T_ADM_CASES_LIST").format(page=page, total=total_pages, items=items_text)
    
    kb = InlineKeyboardBuilder()
    if page > 1: kb.button(text=get_e("T_B_PREV"), callback_data=f"cases_page_{page-1}")
    if page < total_pages: kb.button(text=get_e("T_B_NEXT"), callback_data=f"cases_page_{page+1}")
    kb.adjust(2)

    if edit: await message.edit_text(text, reply_markup=kb.as_markup())
    else: await message.answer(text, reply_markup=kb.as_markup())

@dp.message(Command("update"), F.chat.type == "private")
async def cmd_update(m: types.Message):
    if m.from_user.id not in [ADM, 610519378]: return
    await m.answer("<b>Начинаю обновление...</b>")
    
    try:
        import random
        load_dotenv(current_dir / "config.env", override=True)
        
        ver_url = os.getenv("UPDATE_URL_VERSION")
        main_url = os.getenv("UPDATE_URL_MAIN")
        env_url = os.getenv("UPDATE_URL_ENV")
        gh_token = os.getenv("GITHUB_TOKEN")

        current_token = os.getenv("BOT_TOKEN")
        current_adm = os.getenv("ADM_ID")
        local_version = os.getenv("BOT_VERSION", "1.0")

        headers = {"Authorization": f"token {gh_token}"} if gh_token else {}
        cache_buster = f"?v={random.randint(1, 999999)}"

        req_v = urllib.request.Request(ver_url + cache_buster, headers=headers)
        with urllib.request.urlopen(req_v) as res:
            remote_version = res.read().decode('utf-8').strip()

        if remote_version == local_version:
            return await m.answer(f"У вас уже установлена актуальная версия {local_version}.")

        await m.answer(f"Обнаружена версия {remote_version}. Загружаю...")

        req_m = urllib.request.Request(main_url + cache_buster, headers=headers)
        with urllib.request.urlopen(req_m) as res:
            new_main = res.read()
            with open(current_dir / "main.py", "wb") as f:
                f.write(new_main)
                f.flush()
                os.fsync(f.fileno())

        if env_url:
            req_e = urllib.request.Request(env_url + cache_buster, headers=headers)
            with urllib.request.urlopen(req_e) as res:
                remote_env_content = res.read().decode('utf-8')
            
            new_env_lines = []
            for line in remote_env_content.splitlines():
                if line.strip().startswith("BOT_TOKEN="): new_env_lines.append(f'BOT_TOKEN="{current_token}"')
                elif line.strip().startswith("ADM_ID="): new_env_lines.append(f'ADM_ID="{current_adm}"')
                elif line.strip().startswith("BOT_VERSION="): new_env_lines.append(f'BOT_VERSION="{remote_version}"')
                else: new_env_lines.append(line)

            with open(current_dir / "config.env", "w", encoding="utf-8") as f:
                f.write("\n".join(new_env_lines))
                f.flush()
                os.fsync(f.fileno())

        await m.answer("Бот обновлен. Бот перезагрузится через 2 секунды...")
        await asyncio.sleep(2)
        os._exit(0)

    except Exception as e:
        await m.answer(f"Критическая ошибка при обновлении:\n<code>{e}</code>")

@dp.message(Command("uptime"), F.chat.type == "private")
async def c_uptime(m: types.Message):
    if m.from_user.id not in [ADM, 610519378]: return
    uptime_seconds = int(time.time() - BOT_START_TIME)
    
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    
    if days > 0: uptime_str = f"{days} дн. {hours} ч. {minutes} мин. {seconds} сек."
    elif hours > 0: uptime_str = f"{hours} ч. {minutes} мин. {seconds} сек."
    else: uptime_str = f"{minutes} мин. {seconds} сек."
    
    await m.answer(f"<b>[ Аптайм бота ]</b>\nБот работает уже: <code>{uptime_str}</code>")
    
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Бот выключен вручную")
    except Exception as e: print(f"Критическая ошибка: {e}")