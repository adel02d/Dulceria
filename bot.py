import logging
import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# CONFIGURACIÓN
TOKEN = os.environ.get("TOKEN")  # Obtenemos el Token de las variables de entorno
ADMIN_ID = int(os.environ.get("ADMIN_ID"))  # Tu ID de Telegram como número entero
DATA_FILE = os.environ.get("DATA_FILE", "database.json") # Ruta del archivo de datos

# Configuración de logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- GESTIÓN DE DATOS (BASE DE DATOS SIMPLE) ---

def load_data():
    if not os.path.exists(DATA_FILE):
        # Estructura inicial si no existe el archivo
        return {"menu": [], "orders": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"menu": [], "orders": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- FUNCIONES AUXILIARES ---

def es_admin(user_id):
    return user_id == ADMIN_ID

# --- MANEJADORES DE COMANDOS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saludo de bienvenida"""
    user = update.effective_user
    if es_admin(user.id):
        await update.message.reply_text(
            f"Hola Admin de Dolezza 👋.\n"
            f"Usa /menu para ver el menú actual.\n"
            f"Usa /agregar <dulce> para añadir productos.\n"
            f"Usa /borrar_menu para limpiar el menú.\n"
            f"Usa /pedidos para ver las solicitudes."
        )
    else:
        await update.message.reply_text(
            f"¡Bienvenido a *Dolezza* 🍬!\n"
            f"Estamos listos para atenderte.\n"
            f"Usa /menu para ver los dulces de hoy.",
            parse_mode="Markdown"
        )

async def ver_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los dulces disponibles"""
    data = load_data()
    if not data["menu"]:
        await update.message.reply_text("Hoy no hay dulces disponibles aún. ☹️")
    else:
        texto = "🍬 *Dulces disponibles hoy:*\n\n"
        for i, dulce in enumerate(data["menu"], 1):
            texto += f"{i}. {dulce}\n"
        texto += "\n¿Cuál quieres? Escríbeme o usa /pedido para iniciar."
        await update.message.reply_text(texto, parse_mode="Markdown")

# --- FUNCIONES DE ADMINISTRADOR ---

async def admin_agregar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin agrega un dulce a la lista"""
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo el admin puede hacer esto.")
        return

    if not context.args:
        await update.message.reply_text("Usa: /agregar <nombre del dulce>")
        return

    nuevo_dulce = " ".join(context.args)
    data = load_data()
    data["menu"].append(nuevo_dulce)
    save_data(data)
    await update.message.reply_text(f"✅ Se agregó: {nuevo_dulce}")

async def admin_borrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin limpia el menú del día anterior"""
    if not es_admin(update.effective_user.id):
        return
    
    data = load_data()
    data["menu"] = []
    save_data(data)
    await update.message.reply_text("🗑️ Menú limpio. Lista para cargar los dulces de hoy.")

# --- FUNCIONES DE PEDIDOS (CLIENTE) ---

async def iniciar_pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pregunta al cliente qué desea"""
    data = load_data()
    if not data["menu"]:
        await update.message.reply_text("Lo siento, no hay menú disponible hoy.")
        return

    await update.message.reply_text(
        "Por favor, escríbeme el nombre del dulce que deseas pedir del menú:"
    )

async def recibir_pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el texto del cliente y lo guarda como pedido"""
    # Verificamos si estamos en medio de una conversación o si el usuario simplemente escribió algo
    # Para simplificar, asumiremos que si no es comando y el menú existe, es un pedido.
    # NOTA: En una app real, usaríamos ConversationHandler para estados más complejos.
    
    texto = update.message.text
    if texto.startswith("/"):
        return # Ignorar comandos

    data = load_data()
    
    # Validar que el dulce exista en el menú (opcional, pero recomendado)
    if texto not in data["menu"]:
        await update.message.reply_text(
            f"Ese dulce no está en el menú de hoy. Por favor verifica con /menu e intenta de nuevo."
        )
        return

    nuevo_pedido = {
        "order_id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "user_id": update.effective_user.id,
        "user_name": update.effective_user.first_name,
        "item": texto,
        "status": "PENDIENTE",
        "date": datetime.now().strftime("%d/%m/%Y %H:%M")
    }
    
    data["orders"].append(nuevo_pedido)
    save_data(data)

    await update.message.reply_text(
        f"✅ ¡Pedido recibido!\n"
        f"Solicitaste: *{texto}*\n"
        f"Espera a que el admin de Dolezza confirme tu pedido.",
        parse_mode="Markdown"
    )
    
    # Notificar al admin (opcional, pero útil)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 Nuevo pedido de {update.effective_user.first_name}: {texto}"
        )
    except:
        pass

# --- GESTIÓN DE PEDIDOS (ADMIN) ---

async def admin_pedidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra lista de pedidos con botones para Aceptar/Rechazar"""
    if not es_admin(update.effective_user.id):
        return

    data = load_data()
    pendientes = [p for p in data["orders"] if p["status"] == "PENDIENTE"]

    if not pendientes:
        await update.message.reply_text("No hay pedidos pendientes.")
        return

    for p in pendientes:
        keyboard = [
            [InlineKeyboardButton("✅ Aceptar", callback_data=f"aceptar_{p['order_id']}"),
             InlineKeyboardButton("❌ Rechazar", callback_data=f"rechazar_{p['order_id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        texto = (f"Pedido #{p['order_id']}\n"
                 f"Cliente: {p['user_name']}\n"
                 f"Pedido: {p['item']}\n"
                 f"Fecha: {p['date']}")
        
        await update.message.reply_text(texto, reply_markup=reply_markup)

async def botones_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el clic en Aceptar/Rechazar"""
    query = update.callback_query
    await query.answer() # Confirma que se recibió el clic

    action, order_id = query.data.split("_")
    data = load_data()
    
    # Buscar el pedido
    pedido_encontrado = False
    for p in data["orders"]:
        if p["order_id"] == order_id:
            if action == "aceptar":
                p["status"] = "ACEPTADO"
                msg = f"✅ Tu pedido de *{p['item']}* ha sido ACEPTADO. ¡Gracias por comprar en Dolezza! 🍬"
                msg_admin = "Pedido aceptado."
            else:
                p["status"] = "RECHAZADO"
                msg = f"❌ Lo sentimos, tu pedido de *{p['item']}* no se pudo procesar en este momento."
                msg_admin = "Pedido rechazado."
            
            pedido_encontrado = True
            save_data(data)
            
            # Notificar al cliente
            try:
                await context.bot.send_message(chat_id=p["user_id"], text=msg, parse_mode="Markdown")
            except:
                pass # Error si el usuario bloqueó al bot
            
            # Actualizar mensaje del admin
            await query.edit_message_text(text=f"{query.message.text}\n\n---> {msg_admin}")
            break
    
    if not pedido_encontrado:
        await query.edit_message_text(text="Error: Pedido no encontrado.")

# --- MAIN ---

def main():
    """Inicia el bot"""
    application = Application.builder().token(TOKEN).build()

    # Comandos básicos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", ver_menu))
    
    # Comandos Admin
    application.add_handler(CommandHandler("agregar", admin_agregar))
    application.add_handler(CommandHandler("borrar_menu", admin_borrar_menu))
    application.add_handler(CommandHandler("pedidos", admin_pedidos))
    
    # Proceso de pedido (Cliente)
    # Nota: Para simplificar, asumimos que cualquier texto que no sea comando es un intento de pedido
    # si el usuario inició la interacción. Aquí lo ponemos como filtro genérico.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_pedido))
    
    # Botones de admin
    application.add_handler(CallbackQueryHandler(botones_admin))

    # Iniciar el bot (Webhook para Render o Polling para local)
    # Render usa Webhooks idealmente, pero Polling funciona si configuras el sleep correctamente.
    # Para mantenerlo simple en Render, usaremos polling con un loop infinito.
    print("Bot de Dolezza iniciado...")
    application.run_polling()

if __name__ == "__main__":
    main()
