# ============================================================
# SincanPBB Telegram Bot
# Versi  : v1.2
# Update : April 2026
# Changelog:
#   v1.2 - Validasi format ADM, tolak jika bukan angka
#   v1.1 - Tambah divisi MOA, PIM, MOI, MERPUT
#          Tambah command /list
#          Urutkan divisi: BINUS, UNTAR, UBM, BRIO, MOA, PIM, MOI, MERPUT
#   v1.0 - Versi awal
# ============================================================

import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import uuid
from datetime import datetime

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8307314684:AAF_W5rHQAXjc4FMJMtAHAFDEUKVqfQl1F0')
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://szuatjsluscavohdgjuy.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_SCssZgbMItHHpIV2v4H8Zw_i_rwgXXW')

DIVISI_MAP = {
    'BINUS':  'https://smartestbinus.com/mimin/adminarea',
    'UNTAR':  'https://flyhighunstopable.com/mimin/adminarea',
    'UBM':    'https://reuniubm.com/mimin/adminarea',
    'BRIO':   'https://surgabrio.com/mimin/adminarea',
    'MOA':    'https://moasigma.com/mimin/adminarea',
    'PIM':    'https://pimskibidi.com/mimin/adminarea',
    'MOI':    'https://moimewing.com/mimin/adminarea',
    'MERPUT': 'https://cueklatte.com/mimin/adminarea',
}

def supabase_insert(data):
    url = f"{SUPABASE_URL}/rest/v1/antrian"
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    response = requests.post(url, json=data, headers=headers)
    print(f"Supabase insert status: {response.status_code} - {response.text}")
    return response.status_code == 201

def parse_adm(value):
    """
    Parse nilai ADM. Return:
    - (float, None)  → berhasil
    - (None, pesan_error) → gagal
    """
    try:
        cleaned = value.strip().replace('.', '').replace(',', '.')
        # Tolak jika bukan angka sama sekali
        result = float(cleaned)
        if result < 0:
            return None, "ADM tidak boleh negatif"
        return result, None
    except ValueError:
        return None, f"Format ADM salah: '{value}'\nADM harus berupa angka, contoh: 2500"

def parse_message(text):
    try:
        data = {}
        for line in text.strip().split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                data[key.strip().upper()] = val.strip()

        print(f"Parsed data: {data}")

        if not all(k in data for k in ['DIVISI', 'ASAL', 'TUJUAN', 'JML']):
            print(f"Missing keys! Got: {list(data.keys())}")
            return None, None

        # Validasi JML
        try:
            jumlah = float(data['JML'].replace('.', '').replace(',', '.'))
        except ValueError:
            return None, f"Format JML salah: '{data['JML']}'\nJML harus berupa angka, contoh: 5000000"

        # Validasi ADM jika ada
        admin = 0
        if 'ADM' in data:
            admin, adm_error = parse_adm(data['ADM'])
            if adm_error:
                return None, adm_error

        return {
            'divisi': data['DIVISI'].upper(),
            'asal': data['ASAL'],
            'tujuan': data['TUJUAN'],
            'jumlah': jumlah,
            'admin': admin
        }, None

    except Exception as e:
        print(f'Parse error: {e}')
        return None, None

def format_rupiah(num):
    return f"Rp {int(num):,}".replace(',', '.')

async def format_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 FORMAT PENGIRIMAN TRANSFER\n\n"
        "DIVISI: Nama Web\n"
        "ASAL: BNI - 1234567890 - Nama\n"
        "TUJUAN: BCA - 1234567890 - Nama\n"
        "JML: 1000000\n"
        "ADM: 2500\n\n"
        "📌 Catatan:\n"
        "• Divisi: BINUS / UNTAR / UBM / BRIO / MOA / PIM / MOI / MERPUT\n"
        "• Format rekening: BANK - NOMORREK - NAMA\n"
        "• Pakai spasi sebelum dan sesudah tanda -\n"
        "• ADM harus berupa angka (contoh: 2500)\n"
        "• ADM boleh dikosongkan jika tidak ada biaya admin\n\n"
        "Contoh tanpa admin:\n\n"
        "DIVISI: Nama Web\n"
        "ASAL: BNI - 1234567890 - Nama\n"
        "TUJUAN: BCA - 1234567890 - Nama\n"
        "JML: 1000000"
    )

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["🌐 DAFTAR DIVISI AKTIF\n"]
    for i, (kode, url) in enumerate(DIVISI_MAP.items(), 1):
        lines.append(f"{i}. {kode} → {url}")
    lines.append(f"\nTotal: {len(DIVISI_MAP)} divisi aktif")
    await update.message.reply_text('\n'.join(lines))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # Abaikan pesan biasa yang bukan format transaksi
    if 'DIVISI' not in text.upper():
        return

    chat_id = update.message.chat_id
    sender = update.message.from_user.first_name if update.message.from_user else 'Unknown'

    parsed, error_msg = parse_message(text)

    if not parsed:
        # Kalau ada pesan error spesifik (ADM/JML salah format), tampilkan
        if error_msg:
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                f"Ketik /format untuk melihat format yang benar."
            )
        else:
            await update.message.reply_text(
                "❌ Format pesan salah!\n\n"
                "Ketik /format untuk melihat format yang benar."
            )
        return

    if parsed['divisi'] not in DIVISI_MAP:
        divisi_list = ' / '.join(DIVISI_MAP.keys())
        await update.message.reply_text(
            f"❌ Divisi '{parsed['divisi']}' tidak ditemukan!\n\n"
            f"Divisi yang tersedia: {divisi_list}"
        )
        return

    row = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.now().isoformat(),
        'divisi': parsed['divisi'],
        'url': DIVISI_MAP[parsed['divisi']],
        'asal': parsed['asal'],
        'tujuan': parsed['tujuan'],
        'jumlah': parsed['jumlah'],
        'admin': parsed['admin'],
        'status': 'PENDING',
        'chat_id': str(chat_id),
        'pengirim': sender
    }

    try:
        success = supabase_insert(row)
        if success:
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
        print(f'Supabase error: {e}')
        await update.message.reply_text("❌ Error koneksi, coba lagi!")

if __name__ == '__main__':
    print("SincanPBB Bot v1.2 berjalan...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('format', format_command))
    app.add_handler(CommandHandler('list', list_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)
