# Telegram HTML Decode Bot (starter)

## Features
- Screenshot-style inline menu
- Accepts `.html`, `.htm`, `.js`, `.txt` uploads
- Detects some embedded Base64 payloads and returns readable output
- Downloads HTML from public HTTP(S) pages (redirects disabled; private/local IPs blocked)
- Does not execute uploaded HTML or JavaScript

## Run
1. Install Python 3.10+.
2. Install dependencies:
   `pip install -r requirements.txt`
3. Create a bot with Telegram's official `@BotFather`.
4. Set your token as an environment variable (do not put it in public code):
   - Linux/macOS: `export BOT_TOKEN="YOUR_TOKEN"`
   - Windows PowerShell: `$env:BOT_TOKEN="YOUR_TOKEN"`
5. Run:
   `python bot.py`

## Important limitations
This is a starter, not a universal decoder. Generic obfuscation cannot always be reversed. Some formats need their exact unpacker or a decryption key. The Basic/Pro/Max/Ultra buttons are UI placeholders. Img→URL needs an image-hosting provider API and is intentionally not wired to an arbitrary service. Persistent stats, admin controls, and rate limits should be added before public deployment.
