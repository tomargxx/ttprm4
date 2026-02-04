import os
import logging
import secrets
import string
from pymongo import MongoClient
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variables de entorno
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

# Conexión a MongoDB (se inicializa cuando se necesita)
users_collection = None
config_collection = None

def init_db():
    """Inicializa la conexión a MongoDB"""
    global users_collection, config_collection
    
    if not MONGO_URI:
        logger.error("MONGO_URI no está configurado.")
        return False
    
    try:
        client = MongoClient(MONGO_URI)
        db = client.get_database("RecapMaker")
        users_collection = db.users
        config_collection = db.system_config
        logger.info("✅ Conectado a MongoDB")
        return True
    except Exception as e:
        logger.error(f"❌ Error conectando a MongoDB: {e}")
        return False

# Inicializar DB al importar el módulo
if __name__ == '__main__':
    if not BOT_TOKEN:
        logger.error("TELEGRAM_TOKEN no está configurado. El bot no se iniciará.")
        exit(1)
    if not init_db():
        exit(1)
else:
    # Si se importa como módulo, inicializar DB sin salir
    init_db()

def generate_password(length=12):
    """Genera una contraseña aleatoria segura"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_username(telegram_id, first_name):
    """Genera un nombre de usuario único basado en el nombre y ID de Telegram"""
    base_username = (first_name.lower().replace(' ', '') if first_name else 'user')[:8]
    return f"{base_username}_{str(telegram_id)[-6:]}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start"""
    if users_collection is None:
        await update.message.reply_text("❌ Error: Base de datos no disponible.")
        return
    
    user = update.effective_user
    telegram_id = str(user.id)
    
    # Verificar si el usuario ya existe
    existing_user = users_collection.find_one({"telegram_id": telegram_id})
    
    if existing_user:
        username = existing_user.get('login_username', 'N/A')
        coins = existing_user.get('coins', 0)
        is_verified = existing_user.get('is_verified', False)
        
        message = f"👋 ¡Hola {user.first_name}!\n\n"
        message += f"📋 Tu cuenta:\n"
        message += f"• Usuario: `{username}`\n"
        message += f"• Coins: {coins}\n"
        message += f"• Estado: {'✅ Verificado' if is_verified else '⏳ Pendiente'}\n\n"
        message += f"🌐 Accede al dashboard: http://localhost:7860\n\n"
        message += f"Usa /help para ver todos los comandos disponibles."
        
        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        message = f"👋 ¡Bienvenido {user.first_name}!\n\n"
        message += "Parece que aún no tienes una cuenta.\n"
        message += "Usa /register para crear una cuenta nueva."
        await update.message.reply_text(message)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /register"""
    if users_collection is None:
        await update.message.reply_text("❌ Error: Base de datos no disponible.")
        return
    
    user = update.effective_user
    telegram_id = str(user.id)
    
    # Verificar si el usuario ya existe
    existing_user = users_collection.find_one({"telegram_id": telegram_id})
    
    if existing_user:
        await update.message.reply_text(
            "⚠️ Ya tienes una cuenta registrada.\n"
            "Usa /start para ver tu información."
        )
        return
    
    # Generar credenciales
    username = generate_username(telegram_id, user.first_name)
    password = generate_password()
    
    # Crear usuario en la base de datos
    try:
        new_user = {
            "login_username": username,
            "password": password,
            "telegram_id": telegram_id,
            "coins": 0,
            "is_verified": True,  # Auto-verificar usuarios que se registran por bot
            "is_banned": False,
            "daily_usage_count": 0,
            "last_usage_date": ""
        }
        
        users_collection.insert_one(new_user)
        
        message = "✅ ¡Registro exitoso!\n\n"
        message += "📋 Tus credenciales:\n"
        message += f"• Usuario: `{username}`\n"
        message += f"• Contraseña: `{password}`\n\n"
        message += "⚠️ **Guarda estas credenciales de forma segura.**\n\n"
        message += "🌐 Accede al dashboard: http://localhost:7860\n\n"
        message += "Usa /balance para ver tus coins."
        
        await update.message.reply_text(message, parse_mode='Markdown')
        logger.info(f"✅ Nuevo usuario registrado: {username} (Telegram ID: {telegram_id})")
        
    except Exception as e:
        logger.error(f"❌ Error registrando usuario: {e}")
        await update.message.reply_text(
            "❌ Hubo un error al crear tu cuenta. Por favor, intenta más tarde."
        )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /balance"""
    if users_collection is None or config_collection is None:
        await update.message.reply_text("❌ Error: Base de datos no disponible.")
        return
    
    user = update.effective_user
    telegram_id = str(user.id)
    
    existing_user = users_collection.find_one({"telegram_id": telegram_id})
    
    if not existing_user:
        await update.message.reply_text(
            "⚠️ No tienes una cuenta registrada.\n"
            "Usa /register para crear una cuenta."
        )
        return
    
    coins = existing_user.get('coins', 0)
    daily_usage = existing_user.get('daily_usage_count', 0)
    
    # Obtener límite diario gratuito
    config = config_collection.find_one({"setting_name": "global_config"}) or {}
    daily_limit = config.get('daily_free_limit', 0)
    remaining_free = max(0, daily_limit - daily_usage)
    
    message = f"💰 Tu balance:\n\n"
    message += f"• Coins: {coins}\n"
    if daily_limit > 0:
        message += f"• Usos gratuitos restantes hoy: {remaining_free}/{daily_limit}\n"
    message += f"\n🌐 Accede al dashboard: http://localhost:7860"
    
    await update.message.reply_text(message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /help"""
    message = "📚 Comandos disponibles:\n\n"
    message += "/start - Ver información de tu cuenta\n"
    message += "/register - Crear una nueva cuenta\n"
    message += "/balance - Ver tu balance de coins\n"
    message += "/help - Mostrar esta ayuda\n\n"
    message += "🌐 Accede al dashboard web: http://localhost:7860"
    
    await update.message.reply_text(message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes de texto que no son comandos"""
    await update.message.reply_text(
        "👋 Hola! Usa /help para ver los comandos disponibles.\n"
        "O usa /register para crear una cuenta nueva."
    )

def create_bot_application():
    """Crea y configura la aplicación del bot"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_TOKEN no configurado.")
        return None
    
    if users_collection is None:
        logger.error("Base de datos no inicializada.")
        return None
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Registrar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return application

def main():
    """Inicia el bot (para ejecución independiente)"""
    application = create_bot_application()
    if not application:
        return
    
    logger.info("🚀 Iniciando bot de Telegram...")
    logger.info("✅ Bot iniciado correctamente. Esperando mensajes...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

