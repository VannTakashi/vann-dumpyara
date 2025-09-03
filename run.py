import os
import asyncio
import subprocess
from telegram import Update, Chat
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Load token
with open(".tgtoken") as f:
    TOKEN = f.read().strip()

# Admins list
ADMINS = [6227152745]  # ganti ID admin kalian

# Jobs
jobs = {}      # {job_id: job_data}
queue = []     # list of job_data
job_counter = 0
MAX_RUNNING = 3

# Helpers
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def get_mention(user):
    """Mention user dengan HTML-safe link"""
    if user.username:
        return f"@{user.username}"
    return f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"

async def run_job(job_id: int, job: dict, context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"[Job {job_id}] Starting: {job['link']}")
        process = await asyncio.create_subprocess_exec(
            "bash", "dumpyara.sh", job["link"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )

        async for line in process.stdout:
            print(f"[Job {job_id}] {line.decode().strip()}")

        await process.wait()
        print(f"[Job {job_id}] Finished")

        # Notifikasi user (tanpa link ROM)
        done_msg = (
            f"✅ Job #{job_id} selesai!\n"
            f"📌 Request by: {job['mention']}"
        )
        await context.bot.send_message(
            chat_id=job["chat_id"],
            text=done_msg,
            parse_mode=ParseMode.HTML,
        )

    except Exception as e:
        print(f"[Job {job_id}] Error: {e}")
        await context.bot.send_message(
            chat_id=job["chat_id"],
            text=f"❌ Job #{job_id} gagal: {e}",
        )
    finally:
        jobs.pop(job_id, None)
        await start_next_job(context)

async def start_next_job(context: ContextTypes.DEFAULT_TYPE):
    global jobs
    if len(jobs) >= MAX_RUNNING:
        return
    if not queue:
        return
    job = queue.pop(0)
    job_id = job["id"]
    jobs[job_id] = job
    asyncio.create_task(run_job(job_id, job, context))

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == ChatType.PRIVATE and not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bot ini hanya bisa digunakan di grup.")
        return

    text = (
        "👋 Halo! Aku DumpYara Bot.\n\n"
        "Berikut command yang tersedia:\n"
        "• /dump (URL_ROM) → Tambah job dump\n"
        "• /jobs atau /status → Lihat status semua job\n"
        "• /cancel (id) → Batalkan job (punyamu, admin bebas)\n"
        "• /cleanup → Hapus hasil dump (admin only)\n\n"
        "ℹ️ Max 1 job aktif per user, total 3 job aktif sekaligus.\n"
        "Admin tidak memiliki batasan."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global job_counter
    if len(context.args) != 1:
        await update.message.reply_text("⚠️ Gunakan: /dump <URL_ROM>")
        return
    link = context.args[0]
    user = update.effective_user

    # Batas per user
    if not is_admin(user.id):
        if any(j["user_id"] == user.id for j in jobs.values()):
            await update.message.reply_text("⚠️ Kamu sudah punya 1 job aktif. Tunggu selesai dulu.")
            return

    job_counter += 1
    job_id = job_counter
    job = {
        "id": job_id,
        "user_id": user.id,
        "mention": get_mention(user),
        "link": link,
        "chat_id": update.message.chat_id,
    }

    if len(jobs) < MAX_RUNNING or is_admin(user.id):
        jobs[job_id] = job
        asyncio.create_task(run_job(job_id, job, context))
        await update.message.reply_text(f"✅ Job #{job_id} dimulai untuk {job['mention']}")
    else:
        queue.append(job)
        await update.message.reply_text(f"⏱️ Job #{job_id} dimasukkan ke antrean.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not jobs and not queue:
        await update.message.reply_text("✅ Tidak ada job yang berjalan maupun antrean.")
        return

    text = "📊 <b>Status Jobs</b>\n\n"

    if jobs:
        text += "🔄 <b>Running:</b>\n"
        for job_id, job in jobs.items():
            text += (
                f"📦 Job #{job_id} oleh {job['mention']}\n"
                f"⏳ Status: Sedang berjalan\n"
                f"/cancel_{job_id}\n\n"
            )

    if queue:
        text += "⏱️ <b>Queue:</b>\n"
        for job in queue:
            text += (
                f"📦 Job #{job['id']} oleh {job['mention']}\n"
                f"⏱️ Status: Menunggu giliran\n"
                f"/cancel_{job['id']}\n\n"
            )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Gunakan: /cancel <job_id>")
        return
    try:
        job_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Job ID harus berupa angka.")
        return

    user = update.effective_user
    if job_id in jobs:
        job = jobs[job_id]
        if job["user_id"] != user.id and not is_admin(user.id):
            await update.message.reply_text("❌ Kamu tidak bisa membatalkan job ini.")
            return
        jobs.pop(job_id, None)
        await update.message.reply_text(f"❌ Job #{job_id} dibatalkan.")
    else:
        for j in queue:
            if j["id"] == job_id:
                if j["user_id"] != user.id and not is_admin(user.id):
                    await update.message.reply_text("❌ Kamu tidak bisa membatalkan job ini.")
                    return
                queue.remove(j)
                await update.message.reply_text(f"❌ Job #{job_id} dihapus dari antrean.")
                return
        await update.message.reply_text("⚠️ Job tidak ditemukan.")

async def cancel_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.strip()
    if cmd.startswith("/cancel_"):
        job_id = int(cmd.split("_")[1])
        context.args = [str(job_id)]
        await cancel(update, context)

async def cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Hanya admin yang bisa melakukan ini.")
        return
    working_dir = "working"
    if not os.path.exists(working_dir):
        await update.message.reply_text("🧹 Tidak ada folder working untuk dibersihkan.")
        return
    for f in os.listdir(working_dir):
        path = os.path.join(working_dir, f)
        if os.path.isdir(path) or os.path.isfile(path):
            subprocess.call(["rm", "-rf", path])
    await update.message.reply_text("🧹 Semua hasil dump sudah dihapus.")

# Main
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dump", dump))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("jobs", status))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("cleanup", cleanup))
    app.add_handler(MessageHandler(filters.Regex(r"^/cancel_\d+$"), cancel_click))

    app.run_polling()

if __name__ == "__main__":
    main()
