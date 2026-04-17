import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8307314684:AAF_W5rHQAXjc4FMJMtAHAFDEUKVqfQ11F0')
SHEETDB_URL = os.environ.get('SHEETDB_URL', 'https://sheetdb.io/api/v1/2s0isd6qz46v9')

DIVISI_MAP = {
    'UBM': 'https://reuniubm.com/mimin/adminarea',
    'BINUS': 'https://smartestbinus.com/mimin/adminarea',
    'UNTAR': 'https://flyhighunstopable.com/mimin/adminarea'
}

def parse_message(text):
    try:
        lines = text.strip().split('\n')
        data = {}
        for line in lines:
            if ':' in line:
                key, _, val = line.partition(':')
                data[key.strip().upper()] = val.strip()

        if not all(k in data for k in ['DIVISI', 'ASAL', 'TUJUAN', 'JML']):
            return None

        return {
            'divisi': data['DIVISI'].upper(),
            'asal': data['ASAL'],
            'tujuan': data['TUJUAN'],
            'jumlah': float(data['JML'].replace('.', '').replace(',', '.')),
            'admin': float(data['ADM'].replace('.', '').replace(',', '.')) if 'ADM' in data else 0
        }
    except Exception as e:
        print(f'Parse error: {e}')
        return None

def format_rupiah(num):
    return f"Rp {int(num):,}".replace(',', '.')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.message.chat_id
    sender = update.message.from_user.first_name if update.message.from_user else 'Unknown'

    parsed = parse_message(text)

    if not parsed:
        await update.message.reply_text(
            "❌ Format pesan salah!\n\n"
            "Format yang benar:\n"
            "DIVISI: UBM\n"
            "ASAL: BNI-2014428426-Nama\n"
            "TUJUAN: BCA-7180609452-Nama\n"
            "JML: 9000000\n"
            "ADM: 2500 (opsional)"
        )
        return

    if parsed['divisi'] not in DIVISI_MAP:
        divisi_list = ', '.join(DIVISI_MAP.keys())
        await update.message.reply_text(
            f"❌ Divisi '{parsed['divisi']}' tidak ditemukan!\n\n"
            f"Divisi yang tersedia: {divisi_list}"
        )
        return

    import uuid
    from datetime import datetime

    row = {
        'ID': str(uuid.uuid4()),
        'TIMESTAMP': datetime.now().isoformat(),
        'DIVISI': parsed['divisi'],
        'URL': DIVISI_MAP[parsed['divisi']],
        'ASAL': str(parsed['asal']),
        'TUJUAN': str(parsed['tujuan']),
        'JUMLAH': parsed['jumlah'],
        'ADMIN': parsed['admin'],
        'STATUS': 'PENDING',
        'CHAT_ID': str(chat_id),
        'PENGIRIM': sender
    }

    try:
        response = requests.post(SHEETDB_URL, json={'data': row})
        if response.status_code == 201:
            admin_text = format_rupiah(parsed['admin']) if parsed['admin'] > 0 else 'Tidak ada'
            await update.message.reply_text(
                f"✅ Transaksi diterima!\n\n"
                f"📋 Detail:\n"
                f"Divisi: {parsed['divisi']}\n"
                f"Asal: {parsed['asal']}\n"
                f"Tujuan: {parsed['tujuan']}\n"
                f"Jumlah: {format_rupiah(parsed['jumlah'])}\n"
                f"Admin: {admin_text}\n\n"
                f"⏳ Status: PENDING - Sedang diproses..."
            )
        else:
            await update.message.reply_text("❌ Gagal menyimpan data, coba lagi!")
    except Exception as e:
        print(f'SheetDB error: {e}')
        await update.message.reply_text("❌ Error koneksi, coba lagi!")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print('Bot berjalan...')
    app.run_polling()
