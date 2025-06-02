import logging
import os
import pandas as pd
from datetime import datetime

# Library untuk Telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Library untuk Google Sheets
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# --- KONFIGURASI ---
# Ambil dari environment variables untuk keamanan saat hosting
TOKEN = os.getenv('BOT_TOKEN', 'GANTI_DENGAN_TOKEN_BOT_ANDA_JIKA_LOKAL')
NAMA_SHEET = os.getenv('GOOGLE_SHEET_NAME', 'Data Keuangan Bot') # Nama Google Sheet Anda

# Konfigurasi logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- KONEKSI GOOGLE SHEETS ---
# Tentukan scope (izin) yang dibutuhkan
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Path ke file credentials.json
# Saat hosting, file ini akan di-upload sebagai secret file
CREDS_FILE = 'credentials.json'

# Fungsi untuk mendapatkan koneksi ke worksheet
def get_worksheet():
    """Mengautentikasi dan mengembalikan objek worksheet dari Google Sheet."""
    try:
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open(NAMA_SHEET)
        return spreadsheet.sheet1 # Menggunakan sheet pertama
    except FileNotFoundError:
        logger.error(f"Error: File '{CREDS_FILE}' tidak ditemukan.")
        return None
    except Exception as e:
        logger.error(f"Terjadi kesalahan saat koneksi ke Google Sheets: {e}")
        return None

# --- FUNGSI UTAMA BOT ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim pesan sambutan dan bantuan."""
    user = update.effective_user
    help_text = (
        f"Halo {user.mention_html()}! 👋\n\n"
        "Saya adalah bot pencatat keuangan pribadi Anda yang terintegrasi dengan Google Sheets.\n\n"
        "<b>PERINTAH YANG TERSEDIA:</b>\n"
        "📈 <b>/masuk</b> <code>JUMLAH DESKRIPSI #KATEGORI</code>\n"
        "   (Contoh: <code>/masuk 1000000 Gaji bulanan #gaji</code>)\n\n"
        "📉 <b>/keluar</b> <code>JUMLAH DESKRIPSI #KATEGORI</code>\n"
        "   (Contoh: <code>/keluar 50000 Makan siang #makanan</code>)\n\n"
        "📊 <b>/laporan</b> - Ringkasan keuangan bulan ini.\n\n"
        "🗑️ <b>/hapus_terakhir</b> - Menghapus data terakhir yang Anda masukkan.\n"
    )
    await update.message.reply_html(help_text)

def catat_transaksi(jenis: str, args: list) -> str:
    """Fungsi generik untuk mencatat pemasukan atau pengeluaran."""
    if not args or len(args) < 2:
        return "Format salah. Contoh: `/masuk 500000 Gaji Pokok #gaji`"
    
    try:
        jumlah = int(args[0])
        teks = " ".join(args[1:])
        
        deskripsi = teks
        kategori = "Lainnya"

        if '#' in teks:
            parts = teks.split('#')
            deskripsi = parts[0].strip()
            kategori = parts[1].strip().lower() if len(parts) > 1 and parts[1].strip() else "Lainnya"

        tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        worksheet = get_worksheet()
        if worksheet is None:
            return "Gagal terhubung ke Google Sheets. Cek log server."

        # Menambahkan baris baru ke Google Sheet
        worksheet.append_row([tanggal, jenis, jumlah, deskripsi, kategori])
        
        logger.info(f"Mencatat {jenis}: {jumlah} - {deskripsi}")
        return f"✅ Berhasil dicatat!\n\n<b>Jenis:</b> {jenis}\n<b>Jumlah:</b> Rp {jumlah:,.0f}\n<b>Deskripsi:</b> {deskripsi}\n<b>Kategori:</b> {kategori.capitalize()}"

    except ValueError:
        return "Jumlah harus berupa angka."
    except Exception as e:
        logger.error(f"Error saat mencatat transaksi: {e}")
        return f"Terjadi kesalahan: {e}"

async def masuk_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mencatat pemasukan."""
    response = catat_transaksi("Pemasukan", context.args)
    await update.message.reply_html(response)

async def keluar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mencatat pengeluaran."""
    response = catat_transaksi("Pengeluaran", context.args)
    await update.message.reply_html(response)

async def laporan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Memberikan laporan keuangan bulan ini."""
    worksheet = get_worksheet()
    if worksheet is None:
        await update.message.reply_text("Gagal mengambil data dari Google Sheets.")
        return

    try:
        records = worksheet.get_all_records()
        if not records:
            await update.message.reply_text("Belum ada data keuangan yang tercatat.")
            return

        df = pd.DataFrame(records)
        df['Tanggal'] = pd.to_datetime(df['Tanggal'])
        df['Jumlah'] = pd.to_numeric(df['Jumlah'])

        # Filter untuk bulan dan tahun ini
        bulan_ini = datetime.now().month
        tahun_ini = datetime.now().year
        df_bulan_ini = df[(df['Tanggal'].dt.month == bulan_ini) & (df['Tanggal'].dt.year == tahun_ini)]

        if df_bulan_ini.empty:
            await update.message.reply_text(f"Tidak ada transaksi di bulan {datetime.now().strftime('%B %Y')}.")
            return
            
        total_masuk = df_bulan_ini[df_bulan_ini['Jenis'] == 'Pemasukan']['Jumlah'].sum()
        total_keluar = df_bulan_ini[df_bulan_ini['Jenis'] == 'Pengeluaran']['Jumlah'].sum()
        saldo = total_masuk - total_keluar

        pesan = (
            f"📊 <b>Laporan Keuangan - {datetime.now().strftime('%B %Y')}</b> 📊\n\n"
            f"🟢 <b>Total Pemasukan:</b> Rp {total_masuk:,.0f}\n"
            f"🔴 <b>Total Pengeluaran:</b> Rp {total_keluar:,.0f}\n"
            f"----------------------------------\n"
            f"💰 <b>Saldo Bulan Ini:</b> Rp {saldo:,.0f}\n"
        )
        await update.message.reply_html(pesan)

    except Exception as e:
        logger.error(f"Gagal membuat laporan: {e}")
        await update.message.reply_text(f"Gagal membuat laporan: {e}")

async def hapus_terakhir_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menghapus baris terakhir dari Google Sheet."""
    worksheet = get_worksheet()
    if worksheet is None:
        await update.message.reply_text("Gagal terhubung ke Google Sheets.")
        return

    try:
        all_data = worksheet.get_all_values()
        if len(all_data) <= 1: # Hanya ada header
            await update.message.reply_text("Tidak ada data untuk dihapus.")
            return
        
        data_terhapus = all_data[-1]
        worksheet.delete_rows(len(all_data)) # Hapus baris terakhir
        
        pesan = (
            f"🗑️ Data terakhir berhasil dihapus:\n\n"
            f"<b>Jenis:</b> {data_terhapus[1]}\n"
            f"<b>Jumlah:</b> Rp {int(data_terhapus[2]):,.0f}\n"
            f"<b>Deskripsi:</b> {data_terhapus[3]}"
        )
        await update.message.reply_html(pesan)
        logger.info(f"Data terakhir dihapus: {data_terhapus}")
    except Exception as e:
        logger.error(f"Gagal menghapus data terakhir: {e}")
        await update.message.reply_text(f"Gagal menghapus data terakhir: {e}")


def main() -> None:
    """Jalankan bot."""
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command)) # Alias untuk start
    application.add_handler(CommandHandler("masuk", masuk_command))
    application.add_handler(CommandHandler("keluar", keluar_command))
    application.add_handler(CommandHandler("laporan", laporan_command))
    application.add_handler(CommandHandler("hapus_terakhir", hapus_terakhir_command))

    logger.info("Bot mulai berjalan...")
    application.run_polling()

if __name__ == "__main__":
    main()