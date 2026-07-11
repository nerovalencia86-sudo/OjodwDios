import os
import asyncio
from datetime import datetime, timedelta
import httpx
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from supabase import create_client, Client

# CONFIGURACIÓN DEL BOT
TOKEN = "8664870579:AAFmy5JsZw4RQ-YyGEN9RaEbAZbtkrPFkMY"
API_KEY = "ohhyejin1"
BASE_URL = "https://cuervo-api.vercel.app/nequi"
OWNER_ID = 8116120039

ESPERANDO_NUMERO = 1

# CONFIGURACIÓN DE SUPABASE
SUPABASE_URL = "https://ywjkjiqylapmtkvsacky.supabase.co"
SUPABASE_KEY = "sb_publishable_IBl_qN866dl5ZRmgwUBxlw_Z_87pApK"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Inicializar FastAPI y Bot para Webhook
app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

# --- FUNCIONES DE BASE DE DATOS ---

def es_seller(user_id: int) -> bool:
    try:
        res = supabase.table("sellers").select("seller_id").eq("seller_id", user_id).execute()
        return len(res.data) > 0
    except Exception as e:
        print(f"Error es_seller: {e}")
        return False

def verificar_acceso(user_id: int) -> tuple[bool, str]:
    if user_id == OWNER_ID:
        return True, "owner"
    try:
        res = supabase.table("usuarios").select("tipo", "expira").eq("user_id", user_id).execute()
        if not res.data:
            return False, "no_tiene"
        info = res.data[0]
        if info["tipo"] == "permanente":
            return True, "permanente"
        expira_dt = datetime.strptime(info["expira"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expira_dt:
            return False, "vencido"
        return True, "temporal"
    except Exception as e:
        print(f"Error verificar_acceso: {e}")
        return False, "error"

async def notificar_owner(context: ContextTypes.DEFAULT_TYPE, mensaje: str):
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=mensaje, parse_mode="Markdown")
    except Exception as e:
        print(f"Error notificar owner: {e}")

# --- COMANDOS DEL BOT ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Bot Ojo de Dios Nequi*\n\n"
        "Usa /nequi para comenzar tu consulta.\n\n"
        "By: @El_CuervoX",
        parse_mode="Markdown"
    )

async def iniciar_nequi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    acceso, motivo = verificar_acceso(user_id)
    
    if not acceso:
        if motivo == "vencido":
            await update.message.reply_text("⏰ *Tu licencia ha vencido.* Contacta a @El_CuervoX.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⛔ *No tienes acceso.* Compra tu licencia con @El_CuervoX.", parse_mode="Markdown")
        return ConversationHandler.END

    await update.message.reply_text("📱 *Envía el número de teléfono a consultar:*", parse_mode="Markdown")
    return ESPERANDO_NUMERO

async def procesar_consulta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    numero = update.message.text.strip()
    
    if not numero.isdigit() or len(numero) < 10:
        await update.message.reply_text("❌ Número inválido. Intenta de nuevo con /nequi.")
        return ConversationHandler.END

    mensaje_carga = await update.message.reply_text("⚡ _Consultando base de datos..._", parse_mode="Markdown")
    
    username_log = f"@{user.username}" if user.username else "Sin user"
    await notificar_owner(context, f"🔍 *Consulta*\n👤 {user.first_name} ({username_log})\n🆔 `{user.id}`\n📱 Número: `{numero}`")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/{numero}?key={API_KEY}", timeout=15.0)
        data = r.json()

        if "error" in data:
            await mensaje_carga.edit_text(f"❌ *Error:* {data['error']}", parse_mode="Markdown")
            return ConversationHandler.END

        texto = "╭─────────────────────╮\n📊   *RESULTADO DE CONSULTA* 📊\n╰─────────────────────╯\n\n"
        for campo, valor in data.items():
            texto += f"🔹 *{campo.replace('_', ' ').title()}:* `{valor}`\n"
        texto += "\n─────────────────────\n👤 *By : @El_CuervoX*"
        await mensaje_carga.edit_text(texto, parse_mode="Markdown")

    except Exception as e:
        await mensaje_carga.edit_text(f"❌ *Error:* {e}", parse_mode="Markdown")

    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Consulta cancelada.")
    return ConversationHandler.END

# --- COMANDOS ADMINISTRATIVOS ---

async def addseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) != 1 or not context.args[0].isdigit(): return
    seller_id = int(context.args[0])
    supabase.table("sellers").upsert({"seller_id": seller_id}).execute()
    await update.message.reply_text(f"✅ ID `{seller_id}` añadido como Seller.")

async def delseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) != 1 or not context.args[0].isdigit(): return
    seller_id = int(context.args[0])
    supabase.table("sellers").delete().eq("seller_id", seller_id).execute()
    await update.message.reply_text(f"❌ ID `{seller_id}` removido de Sellers.")

async def allow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    str_id = update.effective_user.id
    if str_id != OWNER_ID and not es_seller(str_id): return
    if len(context.args) < 2 or not context.args[0].isdigit(): return
    
    target_id = int(context.args[0])
    tipo_acceso = context.args[1].lower()
    
    if tipo_acceso in ["perm", "permanente"]:
        tipo, expira, tiempo_txt = "permanente", "Nunca", "Permanente"
    elif tipo_acceso.isdigit():
        tipo = "temporal"
        expira = (datetime.now() + timedelta(days=int(tipo_acceso))).strftime("%Y-%m-%d %H:%M:%S")
        tiempo_txt = f"{tipo_acceso} días"
    else: return

    supabase.table("usuarios").upsert({"user_id": target_id, "tipo": tipo, "expira": expira}).execute()
    await update.message.reply_text(f"✅ Usuario `{target_id}` registrado: *{tiempo_txt}*.", parse_mode="Markdown")

async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE):
    str_id = update.effective_user.id
    if str_id != OWNER_ID and not es_seller(str_id): return
    if len(context.args) != 1 or not context.args[0].isdigit(): return
    target_id = int(context.args[0])
    supabase.table("usuarios").delete().eq("user_id", target_id).execute()
    await update.message.reply_text(f"❌ Acceso revocado para ID `{target_id}`.")

# --- REGISTRO DE MANEJADORES ---
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("nequi", iniciar_nequi)],
    states={ESPERANDO_NUMERO: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_consulta)]},
    fallbacks=[CommandHandler("cancel", cancelar)],
)
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(conv_handler)
bot_app.add_handler(CommandHandler("addseller", addseller))
bot_app.add_handler(CommandHandler("delseller", delseller))
bot_app.add_handler(CommandHandler("allow", allow))
bot_app.add_handler(CommandHandler("deny", deny))

# --- ENDPOINTS VERCEL VÍA FASTAPI ---

@app.on_event("startup")
async def startup_event():
    await bot_app.initialize()

@app.post("/webhook")
async def webhook_endpoint(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return Response(status_code=200)

@app.get("/")
def index():
    return {"status": "Bot conectado a Supabase Cloud DB"}
