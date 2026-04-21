# ============================================================
# SincanPBB Telegram Bot
# Versi  : v1.9
# Update : April 2026
# Filosofi: Cepat + Stabil + Tidak Berantakan
#
# Changelog v1.9:
# - Fix batch insert gagal (tambah jeda 200ms antar insert)
# - Anti spam 1-1-1: bot "marah" kalau user kirim 3+ transaksi <60 detik
# - Notif gabungan batch menampilkan semua transaksi
#
# Changelog v1.8:
# - Auto-timeout transaksi PENDING > 10 menit jadi FAILED
# - Notif peringatan dengan panduan troubleshooting
# - Normalize em dash (—) jadi strip biasa (---) di parser
#
# Changelog v1.7:
# - Keyword: DIVISI (seperti teman)
# - Silent ignore untuk divisi bukan milik bot
# - Simpan message_id untuk reply-to notif
# - Mention link user di notif
# - Notif DONE & FAILED
# - Retry button (tombol "Kirim Ulang") di notif FAILED
# - Command /history & /stats
# - Auto-cleanup DONE/FAILED > 7 hari
# - Batch transaksi (pisah dengan ---)
# - Connection pooling via requests.Session()
# - Validasi ADM ketat
# ============================================================

import os
import requests
import uuid
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ─── KREDENSIAL ──────────────────────────────────────────────
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8307314684:AAF_W5rHQAXjc4FMJMtAHAFDEUKVqfQl1F0')
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://szuatjsluscavohdgjuy.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_SCssZgbMItHHpIV2v4H8Zw_i_rwgXXW')

# ─── DIVISI MAP (7 web aktif) ────────────────────────────────
DIVISI_MAP = {
    'BINUS':  'https://smartestbinus.com/mimin/adminarea',
    'UNTAR':  'https://flyhighunstopable.com/mimin/adminarea',
    'UBM':    'https://reuniubm.com/mimin/adminarea',
    'MOA':    'https://moasigma.com/mimin/adminarea',
    'PIM':    'https://pimskibidi.com/mimin/adminarea',
    'MOI':    'https://moimewing.com/mimin/adminarea',
    'MERPUT': 'https://cueklatte.com/mimin/adminarea',
}

# ─── CONNECTION POOLING ──────────────────────────────────────
# Satu Session dipakai seumur hidup bot → reuse koneksi TCP ke Supabase
# Efek: request 30-40% lebih cepat, memory lebih hemat
SESSION = requests.Session()
SESSION.headers.update({
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
})

# ─── SUPABASE HELPERS ────────────────────────────────────────
def supabase_insert(data):
    url = f"{SUPABASE_URL}/rest/v1/antrian"
    try:
        r = SESSION.post(url, json=data, headers={'Prefer': 'return=minimal'}, timeout=10)
        print(f"[Supabase INSERT] {r.status_code}")
        return r.status_code == 201
    except Exception as e:
        print(f"[Supabase INSERT error] {e}")
        return False

def supabase_mark_notified(row_id):
    url = f"{SUPABASE_URL}/rest/v1/antrian"
    try:
        SESSION.patch(url, params={'id': f'eq.{row_id}'},
                      json={'notified': True}, timeout=10)
    except Exception as e:
        print(f"[mark_notified error] {e}")

def supabase_get(params):
    url = f"{SUPABASE_URL}/rest/v1/antrian"
    try:
        r = SESSION.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[Supabase GET error] {e}")
    return []

def supabase_delete(params):
    url = f"{SUPABASE_URL}/rest/v1/antrian"
    try:
        r = SESSION.delete(url, params=params, timeout=10)
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[Supabase DELETE error] {e}")
        return False

# ─── PARSER ──────────────────────────────────────────────────
def parse_adm(value):
    try:
        cleaned = value.strip().replace('.', '').replace(',', '.')
        result = float(cleaned)
        if result < 0:
            return None, "ADM tidak boleh negatif"
        return result, None
    except ValueError:
        return None, f"Format ADM salah: '{value}'\nADM harus angka, contoh: 2500"

def parse_single_transaction(text):
    """Parse 1 blok transaksi."""
    try:
        # Normalize em dash (—) jadi strip biasa (autofix Telegram Desktop)
        text = text.replace('——', '---').replace('—', '---')
        data = {}
        for line in text.strip().split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                data[key.strip().upper()] = val.strip()

        if not all(k in data for k in ['DIVISI', 'ASAL', 'TUJUAN', 'JML']):
            return None, None

        try:
            jumlah = float(data['JML'].replace('.', '').replace(',', '.'))
            if jumlah <= 0:
                return None, "JML harus lebih dari 0"
        except ValueError:
            return None, f"Format JML salah: '{data['JML']}'\nJML harus angka, contoh: 5000000"

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
        print(f'[Parser error] {e}')
        return None, None

def parse_batch(text):
    """Parse multiple transaksi dipisah dengan ---"""
    blocks = [b.strip() for b in text.split('---') if b.strip()]
    results = []
    errors = []
    for i, block in enumerate(blocks, 1):
        parsed, error = parse_single_transaction(block)
        if parsed:
            results.append(parsed)
        elif error:
            errors.append(f"Transaksi #{i}: {error}")
    return results, errors

def format_rupiah(num):
    return f"Rp {int(num):,}".replace(',', '.')

def make_mention(user_id, first_name):
    """Buat mention link yang bisa di-klik."""
    safe_name = (first_name or 'User').replace('<', '').replace('>', '').replace('&', '')
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'

# ─── ANTI SPAM TRACKING ──────────────────────────────────────
# Untuk deteksi user yang kirim transaksi 1-1-1 padahal bisa batch
user_send_times = {}  # {user_id: [timestamp1, timestamp2, ...]}
last_scold_time = {}  # {user_id: last_scold_timestamp}


# ─── COMMAND HANDLERS ────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Halo! Ini SincanPBB Bot.\n\n"
        "Ketik /format untuk lihat format transaksi.\n"
        "Ketik /divisi untuk lihat divisi yang tersedia.\n"
        "Ketik /history untuk lihat 10 transaksi terakhir.\n"
        "Ketik /stats untuk lihat statistik hari ini.\n"
        "Ketik /ping untuk cek bot online."
    )

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 Bot online & siap terima transaksi.")

async def divisi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["🌐 DAFTAR DIVISI AKTIF\n"]
    for i, (kode, url) in enumerate(DIVISI_MAP.items(), 1):
        lines.append(f"{i}. {kode} → {url}")
    lines.append(f"\nTotal: {len(DIVISI_MAP)} divisi aktif")
    await update.message.reply_text('\n'.join(lines))

async def format_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    divisi_list = ' / '.join(DIVISI_MAP.keys())
    await update.message.reply_text(
        "📋 FORMAT PENGIRIMAN TRANSFER\n\n"
        "DIVISI: Nama Divisi\n"
        "ASAL: BNI - 1234567890 - Nama\n"
        "TUJUAN: BCA - 1234567890 - Nama\n"
        "JML: 1000000\n"
        "ADM: 2500\n\n"
        "📌 Catatan:\n"
        f"• Divisi: {divisi_list}\n"
        "• Format rekening: BANK - NOMORREK - NAMA\n"
        "• Pakai spasi sebelum dan sesudah tanda -\n"
        "• ADM harus angka (contoh: 2500)\n"
        "• ADM boleh dikosongkan jika tidak ada biaya admin\n\n"
        "🔢 KIRIM BANYAK SEKALIGUS (pisahkan dengan ---):\n\n"
        "DIVISI: BINUS\n"
        "ASAL: BCA - 123 - Andi\n"
        "TUJUAN: BNI - 456 - Budi\n"
        "JML: 1000000\n"
        "---\n"
        "DIVISI: UBM\n"
        "ASAL: BCA - 789 - Citra\n"
        "TUJUAN: BRI - 012 - Dedi\n"
        "JML: 2000000"
    )

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    rows = supabase_get({
        'chat_id': f'eq.{chat_id}',
        'select': '*',
        'order': 'timestamp.desc',
        'limit': '10'
    })
    if not rows:
        await update.message.reply_text("📜 Belum ada riwayat transaksi.")
        return

    lines = ["📜 10 TRANSAKSI TERAKHIR\n"]
    for row in rows:
        status_icon = {
            'DONE': '✅',
            'FAILED': '❌',
            'PENDING': '⏳',
            'PROCESSING': '⚙️'
        }.get(row['status'], '❔')
        ts = row['timestamp'][:16].replace('T', ' ')
        lines.append(
            f"{status_icon} {row['divisi']} — {format_rupiah(row['jumlah'])} — {ts}"
        )
    await update.message.reply_text('\n'.join(lines))

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime('%Y-%m-%d')
    rows = supabase_get({
        'timestamp': f'gte.{today}',
        'select': '*'
    })

    total = len(rows)
    done = sum(1 for r in rows if r['status'] == 'DONE')
    failed = sum(1 for r in rows if r['status'] == 'FAILED')
    pending = sum(1 for r in rows if r['status'] in ('PENDING', 'PROCESSING'))

    per_divisi = {}
    total_jumlah = 0
    for row in rows:
        per_divisi[row['divisi']] = per_divisi.get(row['divisi'], 0) + 1
        if row['status'] == 'DONE':
            total_jumlah += row.get('jumlah', 0)

    lines = [f"📊 STATISTIK HARI INI ({today})\n"]
    lines.append(f"Total transaksi: {total}")
    lines.append(f"✅ Berhasil: {done}")
    lines.append(f"❌ Gagal: {failed}")
    lines.append(f"⏳ Pending: {pending}")
    lines.append(f"💰 Total dana (DONE): {format_rupiah(total_jumlah)}")
    if per_divisi:
        lines.append("\nPer divisi:")
        for divisi, count in sorted(per_divisi.items(), key=lambda x: -x[1]):
            lines.append(f"• {divisi}: {count}")
    await update.message.reply_text('\n'.join(lines))

# ─── CALLBACK: RETRY BUTTON ──────────────────────────────────
async def retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Format callback_data: "retry|old_id"
    try:
        _, old_id = query.data.split('|', 1)
    except ValueError:
        await query.edit_message_text("❌ Data retry tidak valid.")
        return

    # Ambil data transaksi lama
    rows = supabase_get({'id': f'eq.{old_id}', 'select': '*'})
    if not rows:
        await query.edit_message_text("❌ Transaksi tidak ditemukan.")
        return

    old = rows[0]
    new_row = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.now().isoformat(),
        'divisi': old['divisi'],
        'url': old['url'],
        'asal': old['asal'],
        'tujuan': old['tujuan'],
        'jumlah': old['jumlah'],
        'admin': old.get('admin', 0),
        'status': 'PENDING',
        'chat_id': old['chat_id'],
        'message_id': old.get('message_id'),
        'pengirim': old.get('pengirim', 'Unknown'),
        'user_id': old.get('user_id'),
        'notified': False
    }

    if supabase_insert(new_row):
        await query.edit_message_text(
            f"🔄 Transaksi dikirim ulang!\n\n"
            f"Divisi: {old['divisi']}\n"
            f"Jumlah: {format_rupiah(old['jumlah'])}\n\n"
            f"⏳ Sedang diproses..."
        )
    else:
        await query.edit_message_text("❌ Gagal kirim ulang, coba manual.")

# ─── MESSAGE HANDLER ─────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # Cek quick: ada kata DIVISI?
    if 'DIVISI' not in text.upper():
        return

    chat_id = update.message.chat_id
    message_id = update.message.message_id
    user = update.message.from_user
    sender = user.first_name if user else 'Unknown'
    user_id = user.id if user else 0

    # Parse — bisa 1 atau banyak transaksi
    transactions, errors = parse_batch(text)

    # Kalau ada error parsing
    if errors and not transactions:
        await update.message.reply_text(
            "❌ Format pesan salah!\n\n" +
            '\n'.join(errors[:5]) +
            "\n\nKetik /format untuk melihat format yang benar."
        )
        return

    # Filter divisi yang milik kita
    valid_transactions = [t for t in transactions if t['divisi'] in DIVISI_MAP]

    # SILENT IGNORE: kalau tidak ada satupun divisi milik kita, diam saja
    if not valid_transactions:
        print(f"[Handler] Semua divisi bukan milik bot ini, silent ignore.")
        return

    # Anti-spam: cek kalau user kirim 3+ transaksi satu-satu dalam 60 detik
    if len(valid_transactions) == 1 and user_id:
        import time as _time
        now_ts = _time.time()
        if user_id not in user_send_times:
            user_send_times[user_id] = []
        # Buang timestamp yang lebih dari 60 detik
        user_send_times[user_id] = [t for t in user_send_times[user_id] if now_ts - t < 60]
        user_send_times[user_id].append(now_ts)
        # Kalau sudah 3+ dalam 60 detik, bot marah (cooldown 5 menit biar tidak spam)
        if len(user_send_times[user_id]) >= 3:
            last_scold = last_scold_time.get(user_id, 0)
            if now_ts - last_scold > 300:
                await update.message.reply_text(
                    "Eh bos! 😤 Dari tadi kirim 1-1-1 terus. "
                    "Kan bisa pakai --- biar sekaligus 3 transaksi!"
                )
                last_scold_time[user_id] = now_ts
                user_send_times[user_id] = []

    # Proses setiap transaksi valid
    import time as _time_insert
    success_count = 0
    for idx, parsed in enumerate(valid_transactions):
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
            'message_id': message_id,
            'pengirim': sender,
            'user_id': user_id,
            'notified': False
        }
        if supabase_insert(row):
            success_count += 1
        # Jeda 200ms antar insert biar Supabase tidak overwhelm (fix batch bug)
        if idx < len(valid_transactions) - 1:
            _time_insert.sleep(0.2)

    # Kirim 1 notif gabungan
    if success_count == 0:
        await update.message.reply_text("❌ Gagal menyimpan data, coba lagi!")
        return

    if len(valid_transactions) == 1:
        t = valid_transactions[0]
        admin_text = format_rupiah(t['admin']) if t['admin'] > 0 else 'Tidak ada'
        await update.message.reply_text(
            f"✅ Transaksi diterima!\n\n"
            f"📋 Detail:\n"
            f"Divisi: {t['divisi']}\n"
            f"Asal: {t['asal']}\n"
            f"Tujuan: {t['tujuan']}\n"
            f"Jumlah: {format_rupiah(t['jumlah'])}\n"
            f"Admin: {admin_text}\n\n"
            f"⏳ Status: PENDING - Sedang diproses..."
        )
    else:
        lines = [f"✅ {success_count} transaksi diterima!\n"]
        for i, t in enumerate(valid_transactions, 1):
            lines.append(f"{i}. {t['divisi']} — {format_rupiah(t['jumlah'])}")
        lines.append("\n⏳ Semua sedang diproses...")
        await update.message.reply_text('\n'.join(lines))

# ─── BACKGROUND JOB: NOTIF DONE/FAILED ───────────────────────
async def check_transactions(context: ContextTypes.DEFAULT_TYPE):
    # Cek transaksi DONE
    done_rows = supabase_get({
        'status': 'eq.DONE',
        'notified': 'eq.false',
        'select': '*'
    })
    for row in done_rows:
        try:
            admin_text = format_rupiah(row['admin']) if row.get('admin', 0) > 0 else 'Tidak ada'
            mention = make_mention(row.get('user_id', 0), row.get('pengirim', 'User'))
            msg = (
                f"✅ Transaksi selesai, {mention}!\n\n"
                f"📋 Detail:\n"
                f"Divisi: {row['divisi']}\n"
                f"Asal: {row['asal']}\n"
                f"Tujuan: {row['tujuan']}\n"
                f"Jumlah: {format_rupiah(row['jumlah'])}\n"
                f"Admin: {admin_text}\n\n"
                f"✅ Status: Done - Silahkan Check Balance"
            )
            send_kwargs = {
                'chat_id': int(row['chat_id']),
                'text': msg,
                'parse_mode': 'HTML',
            }
            if row.get('message_id'):
                send_kwargs['reply_to_message_id'] = int(row['message_id'])
                send_kwargs['allow_sending_without_reply'] = True
            await context.bot.send_message(**send_kwargs)
            supabase_mark_notified(row['id'])
        except Exception as e:
            print(f"[notify done error] {e}")

    # Cek transaksi FAILED
    failed_rows = supabase_get({
        'status': 'eq.FAILED',
        'notified': 'eq.false',
        'select': '*'
    })
    for row in failed_rows:
        try:
            mention = make_mention(row.get('user_id', 0), row.get('pengirim', 'User'))
            msg = (
                f"❌ Transaksi GAGAL, {mention}!\n\n"
                f"Divisi: {row['divisi']}\n"
                f"Jumlah: {format_rupiah(row['jumlah'])}\n\n"
                f"Silakan cek manual atau klik tombol di bawah untuk kirim ulang."
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Kirim Ulang", callback_data=f"retry|{row['id']}")
            ]])
            send_kwargs = {
                'chat_id': int(row['chat_id']),
                'text': msg,
                'parse_mode': 'HTML',
                'reply_markup': keyboard,
            }
            if row.get('message_id'):
                send_kwargs['reply_to_message_id'] = int(row['message_id'])
                send_kwargs['allow_sending_without_reply'] = True
            await context.bot.send_message(**send_kwargs)
            supabase_mark_notified(row['id'])
        except Exception as e:
            print(f"[notify failed error] {e}")

# ─── BACKGROUND JOB: AUTO-CLEANUP DATA LAMA (>7 hari) ────────
async def cleanup_old_data(context: ContextTypes.DEFAULT_TYPE):
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    try:
        # Hapus DONE & FAILED yang sudah >7 hari
        for status in ('DONE', 'FAILED'):
            params = {
                'status': f'eq.{status}',
                'timestamp': f'lt.{cutoff}'
            }
            if supabase_delete(params):
                print(f"[Cleanup] Deleted old {status} rows (>7 days)")
    except Exception as e:
        print(f"[Cleanup error] {e}")

# ─── BACKGROUND JOB: AUTO-TIMEOUT PENDING > 10 MENIT ─────────
async def timeout_stuck_transactions(context: ContextTypes.DEFAULT_TYPE):
    """Transaksi PENDING/PROCESSING yang nyangkut >10 menit → jadi FAILED."""
    cutoff = (datetime.now() - timedelta(minutes=10)).isoformat()
    try:
        # Ambil transaksi yang nyangkut
        stuck = supabase_get({
            'status': 'in.(PENDING,PROCESSING)',
            'timestamp': f'lt.{cutoff}',
            'select': '*'
        })

        for row in stuck:
            # Mark sebagai FAILED_TIMEOUT
            url = f"{SUPABASE_URL}/rest/v1/antrian"
            try:
                SESSION.patch(
                    url,
                    params={'id': f'eq.{row["id"]}'},
                    json={
                        'status': 'FAILED',
                        'locked_by': None,
                        'locked_at': None,
                        'notified': False  # biar dikirim notif peringatan
                    },
                    timeout=10
                )

                # Kirim notif peringatan khusus timeout
                mention = make_mention(row.get('user_id', 0), row.get('pengirim', 'User'))
                msg = (
                    f"⚠️ <b>Transaksi timeout</b>, {mention}!\n\n"
                    f"Transaksi ini sudah menunggu lebih dari 10 menit tanpa diproses.\n\n"
                    f"<b>Detail:</b>\n"
                    f"Divisi: {row['divisi']}\n"
                    f"Asal: {row['asal']}\n"
                    f"Tujuan: {row['tujuan']}\n"
                    f"Jumlah: {format_rupiah(row['jumlah'])}\n\n"
                    f"<b>Kemungkinan penyebab:</b>\n"
                    f"• Tab browser tidur (background throttling)\n"
                    f"• Session website expired (perlu login ulang)\n"
                    f"• Koneksi internet bermasalah\n"
                    f"• Bot/Tampermonkey belum aktif\n\n"
                    f"<b>Yang harus dicek:</b>\n"
                    f"• Klik tab {row['divisi']} di browser\n"
                    f"• Pastikan sudah login di panel\n"
                    f"• Refresh tab (Ctrl+F5)\n"
                    f"• Cek apakah Tampermonkey aktif\n\n"
                    f"Silakan cek manual atau klik tombol di bawah untuk kirim ulang."
                )

                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Kirim Ulang", callback_data=f"retry|{row['id']}")
                ]])
                send_kwargs = {
                    'chat_id': int(row['chat_id']),
                    'text': msg,
                    'parse_mode': 'HTML',
                    'reply_markup': keyboard,
                }
                if row.get('message_id'):
                    send_kwargs['reply_to_message_id'] = int(row['message_id'])
                    send_kwargs['allow_sending_without_reply'] = True

                await context.bot.send_message(**send_kwargs)
                supabase_mark_notified(row['id'])
                print(f"[Timeout] {row['id']} → FAILED (>10 min)")

            except Exception as e:
                print(f"[Timeout error] {row['id']}: {e}")

    except Exception as e:
        print(f"[Timeout job error] {e}")

# ─── MAIN ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 50)
    print("SincanPBB Bot v1.9 berjalan")
    print(f"Divisi aktif: {', '.join(DIVISI_MAP.keys())}")
    print(f"Total: {len(DIVISI_MAP)} divisi")
    print("=" * 50)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('ping', ping_command))
    app.add_handler(CommandHandler('format', format_command))
    app.add_handler(CommandHandler('divisi', divisi_command))
    app.add_handler(CommandHandler('history', history_command))
    app.add_handler(CommandHandler('stats', stats_command))
    app.add_handler(CallbackQueryHandler(retry_callback, pattern='^retry\\|'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Notif DONE/FAILED setiap 5 detik
    app.job_queue.run_repeating(check_transactions, interval=5, first=10)

    # Auto-cleanup data >7 hari setiap 6 jam
    app.job_queue.run_repeating(cleanup_old_data, interval=21600, first=60)

    # Auto-timeout transaksi nyangkut >10 menit, cek tiap 1 menit
    app.job_queue.run_repeating(timeout_stuck_transactions, interval=60, first=30)

    app.run_polling(drop_pending_updates=True)
