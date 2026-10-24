import os
import re
import io
import base64
import binascii
import ipaddress
import socket
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiohttp

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_URL_BYTES = 3 * 1024 * 1024

if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN environment variable before running the bot.")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

def main_keyboard():
    b = InlineKeyboardBuilder()
    labels = [
        ("🔒 Basic", "basic"), ("🔒 Pro", "pro"),
        ("⚡ Max", "max"), ("💎 Ultra", "ultra"),
        ("🧩 Decode", "decode"), ("🌐 URL→HTML", "url"),
        ("📸 Img→URL", "img"), ("📋 Formats", "formats"),
        ("ℹ️ Help", "help"), ("📊 Stats", "stats"),
        ("❌ Cancel", "cancel"),
    ]
    for label, data in labels:
        b.button(text=label, callback_data=data)
    b.adjust(2, 2, 2, 2, 2, 1)
    return b.as_markup()

def safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "decoded.html")
    return name[:100] or "decoded.html"

def try_base64_candidates(text: str):
    """Conservative Base64 decoder: returns readable candidates without executing code."""
    candidates = []
    # Base64 data URLs
    for m in re.finditer(r"data:[^;,]+;base64,([A-Za-z0-9+/=\s]+)", text, re.I):
        candidates.append(m.group(1))
    # Long standalone Base64-like strings
    for m in re.finditer(r"(?<![A-Za-z0-9+/=])([A-Za-z0-9+/]{120,}={0,2})(?![A-Za-z0-9+/=])", text):
        candidates.append(m.group(1))
    results = []
    seen = set()
    for c in candidates:
        compact = re.sub(r"\s+", "", c)
        if compact in seen:
            continue
        seen.add(compact)
        try:
            raw = base64.b64decode(compact + "=" * ((4 - len(compact) % 4) % 4), validate=False)
            decoded = raw.decode("utf-8", errors="strict")
            if any(x in decoded.lower() for x in ("<html", "<!doctype", "<script", "function", "var ", "const ", "let ")):
                results.append(decoded)
        except (binascii.Error, UnicodeDecodeError, ValueError):
            pass
    return results

def decode_text(data: bytes):
    text = data.decode("utf-8", errors="replace")
    candidates = try_base64_candidates(text)
    if candidates:
        # Return the largest readable decoded payload.
        return max(candidates, key=len), "Embedded Base64 candidate extracted"
    return text, "No common embedded Base64 payload found; returned readable source"

async def fetch_public_url(url: str):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("শুধু বৈধ http:// বা https:// URL দিন।")
    if p.username or p.password:
        raise ValueError("Login credentials থাকা URL গ্রহণ করা হয় না।")
    try:
        infos = await aiohttp.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except Exception:
        infos = None
    # Resolve and block private/local addresses to reduce SSRF risk.
    try:
        addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global:
                raise ValueError("Private/local network URL নিরাপত্তার কারণে ব্লক করা হয়েছে।")
    except socket.gaierror:
        raise ValueError("URL host resolve করা যায়নি।")
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "HTMLHelperBot/1.0"}) as session:
        async with session.get(url, allow_redirects=False) as resp:
            if resp.status < 200 or resp.status >= 300:
                raise ValueError(f"URL থেকে সফল response আসেনি (HTTP {resp.status})।")
            ctype = resp.headers.get("Content-Type", "").lower()
            if "text/html" not in ctype and "text/plain" not in ctype and "application/xhtml" not in ctype:
                raise ValueError("এই URL HTML/text কনটেন্ট দিচ্ছে না।")
            body = await resp.content.read(MAX_URL_BYTES + 1)
            if len(body) > MAX_URL_BYTES:
                raise ValueError("URL content 3 MB-এর বেশি; ছোট ফাইল দিন।")
            return body

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 HTML TOOL BOT\n\n"
        "HTML/JS ফাইল পাঠিয়ে 🧩 Decode করুন, অথবা 🌐 URL→HTML বেছে URL দিন।\n"
        "এটি সাধারণ Base64 payload শনাক্ত করতে পারে; সব encryption/obfuscation decode করার নিশ্চয়তা নেই।",
        reply_markup=main_keyboard()
    )

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "ব্যবহার:\n"
        "• .html/.htm/.js/.txt ফাইল পাঠান — বট readable source এবং সাধারণ embedded Base64 পরীক্ষা করবে।\n"
        "• URL→HTML চাপুন, তারপর public webpage URL দিন।\n"
        "• বট কোনো HTML/JavaScript execute করে না।\n\n"
        "সীমাবদ্ধতা: proprietary encryption, packed code, server-side protected content বা key-ভিত্তিক encryption-এর জন্য আলাদা decoder/key প্রয়োজন হতে পারে।",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data.in_({"basic","pro","max","ultra"}))
async def tier(callback: CallbackQuery):
    await callback.answer()
    tier_name = callback.data.upper()
    await callback.message.answer(
        f"{tier_name} mode নির্বাচিত।\n"
        "এই starter version-এ paid/locked tiers কেবল UI placeholder। "
        "নিজের অনুমোদিত API/decoder যুক্ত করলে এই mode-এ আলাদা processing বসানো যাবে.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "decode")
async def decode_help(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("এখন HTML/HTM/JS/TXT ফাইলটি এখানে upload করুন।")

@dp.callback_query(F.data == "url")
async def url_help(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("একটি public webpage-এর https:// বা http:// URL পাঠান।")

@dp.callback_query(F.data == "img")
async def img_help(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Img→URL-এর জন্য image-hosting provider-এর API key প্রয়োজন। "
        "এই starter-এ ছবি স্বয়ংক্রিয়ভাবে public URL-এ upload করা হয় না। "
        "নিজের অনুমোদিত hosting API যুক্ত করা যাবে।"
    )

@dp.callback_query(F.data == "formats")
async def formats(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("সমর্থিত input: .html, .htm, .js, .txt এবং public webpage URL।")

@dp.callback_query(F.data == "help")
async def help_button(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("ফাইল পাঠান অথবা /help লিখুন।", reply_markup=main_keyboard())

@dp.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("📊 এই starter build-এ persistent user statistics চালু নেই।")

@dp.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery):
    await callback.answer("Cancelled")
    await callback.message.answer("কাজ বাতিল হয়েছে।", reply_markup=main_keyboard())

@dp.message(F.document)
async def handle_document(message: Message):
    doc = message.document
    filename = doc.file_name or "upload.html"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".html", ".htm", ".js", ".txt"}:
        await message.answer("এই ফাইল টাইপ সমর্থিত নয়। .html, .htm, .js বা .txt দিন।")
        return
    if doc.file_size and doc.file_size > MAX_FILE_BYTES:
        await message.answer("ফাইলটি 8 MB-এর বেশি। ছোট ফাইল দিন।")
        return
    try:
        tg_file = await bot.get_file(doc.file_id)
        stream = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=stream)
        raw = stream.getvalue()
        if len(raw) > MAX_FILE_BYTES:
            await message.answer("ফাইলটি 8 MB-এর বেশি।")
            return
        output, note = decode_text(raw)
        outname = "decoded_" + safe_name(filename)
        payload = output.encode("utf-8")
        await message.answer(f"✅ ফাইল পরীক্ষা শেষ\nℹ️ {note}\n📄 Output: {outname}")
        await message.answer_document(BufferedInputFile(payload, filename=outname))
    except Exception as e:
        await message.answer(f"ফাইল প্রসেস করা যায়নি: {str(e)[:250]}")

@dp.message(F.text)
async def handle_text(message: Message):
    text = (message.text or "").strip()
    if text.startswith(("http://", "https://")):
        try:
            raw = await fetch_public_url(text)
            output, note = decode_text(raw)
            await message.answer(f"✅ URL content পাওয়া গেছে\nℹ️ {note}")
            await message.answer_document(
                BufferedInputFile(output.encode("utf-8"), filename="url_page.html")
            )
        except Exception as e:
            await message.answer(f"URL প্রসেস করা যায়নি: {str(e)[:250]}")
    else:
        await message.answer("HTML ফাইল upload করুন, অথবা public URL দিন।", reply_markup=main_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
