# ============================================================
# SincanPBB Telegram Bot
# Versi  : v1.4
# Update : April 2026
# Changelog:
#   v1.4 - Tambah divisi TIMNAS
#   v1.3 - Ganti keyword DIVISI → WEB
#          Bot yang kirim notif Done/Gagal (bukan Tampermonkey)
#          Tambah command /start, /ping, /divisi
#          Hapus BRIO, total 7 divisi aktif
#   v1.2 - Validasi format ADM
#   v1.1 - Tambah divisi MOA, PIM, MOI, MERPUT, command /list
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
    'MOA':    'https://moasigma.com/mimin/adminarea',
    'PIM':    'https://pimskibidi.com/mimin/adminarea',
    'MOI':    'https://moimewing.com/mimin/adminarea',
    'MERPUT': 'https://cueklatte.com/mimin/adminarea',
    'TIMNAS': 'https://terbangtimnas.com/mimin/adminarea',
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
    print(f"[Supabase] {response.status_code} - {response.text}")
    return response.status_code == 201

def supabase_mark_notified(row_id):
    url = f"{SUPABASE_URL}/rest/v1/antrian"
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
    }
    params = {'id': f'eq.{row_id}'}
    try:
        requests.patch(url, headers=headers, params=params, json={'notified': True}, timeout=10)
    except Exception as e:
        print(f"[mark_notified error] {e}")

def parse_adm(value):
    try:
        cleaned = value.strip().replace('.', '').replace(',', '.')
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

        print(f"[Parser] {data}")

        if not all(k in data for k in ['WEB', 'ASAL', 'TUJUAN', 'JML']):
            print(f"[Parser] Missing keys. Got: {list(data.keys())}")
            return None, None

        try:
            jumlah = float(data['JML'].replace('.', '').replace(',', '.'))
        except ValueError:
            return None, f"Format JML salah: '{data['JML']}'\nJML harus berupa angka, contoh: 5000000"

        admin = 0
        if 'ADM' in data:
            admin, adm_error = parse_adm(data['ADM'])
            if adm_error:
                return None, adm_error

        return {
            'divisi': data['WEB'].upper(),
            'asal': data['ASAL'],
            'tujuan': data['TUJUAN'],
            'jumlah': jumlah,
            'admin': admin
        }, None

    except Exception as e:
        print(f'[Parser error] {e}')
        return None, None

def format_rupiah(num):
    return f"Rp {int(num):,}".replace(',', '.')

# ─── Command Handlers ─────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Halo! Ini SincanPBB Bot.\n\n"
        "Ketik /format untuk lihat format transaksi.\n"
        "Ketik /divisi untuk lihat divisi yang tersedia.\n"
        "Ketik /ping untuk cek bot online."
    )

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 Bot online & siap terima transaksi.")

async def divisi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["🌐 DAFTAR WEB AKTIF\n"]
    for i, (kode, url) in enumerate(DIVISI_MAP.items(), 1):
        lines.append(f"{i}. {kode} → {url}")
    lines.append(f"\nTotal: {len(DIVISI_MAP)} web aktif")
    await update.message.reply_text('\n'.join(lines))

async def format_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    divisi_list = ' / '.join(DIVISI_MAP.keys())
    await update.message.reply_text(
        "📋 FORMAT PENGIRIMAN TRANSFER\n\n"
        "WEB: Nama Web\n"
        "ASAL: BNI - 1234567890 - Nama\n"
        "TUJUAN: BCA - 1234567890 - Nama\n"
        "JML: 1000000\n"
        "ADM: 2500\n\n"
        "📌 Catatan:\n"
        f"• Web: {divisi_list}\n"
        "• Format rekening: BANK - NOMORREK - NAMA\n"
        "• Pakai spasi sebelum dan sesudah tanda -\n"
        "• ADM harus berupa angka (contoh: 2500)\n"
        "• ADM boleh dikosongkan jika tidak ada biaya admin\n\n"
        "Contoh tanpa admin:\n\n"
        "WEB: BINUS\n"
        "ASAL: BNI - 1234567890 - Nama\n"
        "TUJUAN: BCA - 1234567890 - Nama\n"
        "JML: 1000000"
    )

# ─── Message Handler ──────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if 'WEB' not in text.upper():
        return

    chat_id = update.message.chat_id
    sender = update.message.from_user.first_name if update.message.from_user else 'Unknown'

    parsed, error_msg = parse_message(text)

    if not parsed:
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
            f"❌ Web '{parsed['divisi']}' tidak ditemukan!\n\n"
            f"Web yang tersedia: {divisi_list}"
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
        'pengirim': sender,
        'notified': False
    }

    try:
        success = supabase_insert(row)
        if success:
            admin_text = format_rupiah(parsed['admin']) if parsed['admin'] > 0 else 'Tidak ada'
            await update.message.reply_text(
                f"✅ Transaksi diterima!\n\n"
                f"📋 Detail:\n"
                f"Web: {parsed['divisi']}\n"
                f"Asal: {parsed['asal']}\n"
                f"Tujuan: {parsed['tujuan']}\n"
                f"Jumlah: {format_rupiah(parsed['jumlah'])}\n"
                f"Admin: {admin_text}\n\n"
                f"⏳ Status: PENDING - Sedang diproses..."
            )
        else:
            await update.message.reply_text("❌ Gagal menyimpan data, coba lagi!")
    except Exception as e:
        print(f'[Handler error] {e}')
        await update.message.reply_text("❌ Error koneksi, coba lagi!")

# ─── Background Job: Notif Done/Gagal ─────────────────────────
async def check_done_transactions(context: ContextTypes.DEFAULT_TYPE):
    url = f"{SUPABASE_URL}/rest/v1/antrian"
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
    }
    try:
        # Cek transaksi DONE
        r = requests.get(url, headers=headers, params={
            'status': 'eq.DONE',
            'notified': 'eq.false',
            'select': '*'
        }, timeout=10)
        if r.status_code == 200:
            for row in r.json():
                try:
                    admin_text = format_rupiah(row['admin']) if row.get('admin', 0) > 0 else 'Tidak ada'
                    await context.bot.send_message(
                        chat_id=int(row['chat_id']),
                        text=(
                            f"✅ Transaksi selesai!\n\n"
                            f"📋 Detail:\n"
                            f"Web: {row['divisi']}\n"
                            f"Asal: {row['asal']}\n"
                            f"Tujuan: {row['tujuan']}\n"
                            f"Jumlah: {format_rupiah(row['jumlah'])}\n"
                            f"Admin: {admin_text}\n\n"
                            f"✅ Status: Done - Silahkan Check Balance"
                        )
                    )
                    supabase_mark_notified(row['id'])
                except Exception as e:
                    print(f"[notify done error] {e}")

        # Cek transaksi FAILED
        r2 = requests.get(url, headers=headers, params={
            'status': 'eq.FAILED',
            'notified': 'eq.false',
            'select': '*'
        }, timeout=10)
        if r2.status_code == 200:
            for row in r2.json():
                try:
                    await context.bot.send_message(
                        chat_id=int(row['chat_id']),
                        text=(
                            f"❌ Transaksi GAGAL!\n\n"
                            f"Web: {row['divisi']}\n"
                            f"Jumlah: {format_rupiah(row['jumlah'])}\n\n"
                            f"Silakan cek manual!"
                        )
                    )
                    supabase_mark_notified(row['id'])
                except Exception as e:
                    print(f"[notify failed error] {e}")

    except Exception as e:
        print(f"[check_done error] {e}")

# ─── Main ──────────────────────────────────────────────────────
if __name__ == '__main__':
    print("SincanPBB Bot v1.4 berjalan... (8 web aktif)")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('ping', ping_command))
    app.add_handler(CommandHandler('format', format_command))
    app.add_handler(CommandHandler('divisi', divisi_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_repeating(check_done_transactions, interval=5, first=10)

    app.run_polling(drop_pending_updates=True)
