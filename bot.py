import logging
import os
import json
import uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler, PrefixHandler

# --- CONFIGURACIÓN ---
TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
DATA_FILE = os.environ.get("DATA_FILE", "database.json")

# --- TABLA DE ZONAS Y PRECIOS DE MENSAJERÍA ---
# Ya aplicamos el tope de 1000 CUP según tu tabla
ZONES_PRICES = {
    "Centro Habana": 720,
    "Vedado (hasta Paseo)": 780,
    "Vedado (después de Paseo)": 840,
    "Habana Vieja": 660,
    "Cerro": 600,
    "Nuevo Vedado": 840,
    "Playa (Puente – Calle 60)": 1000, # Tope aplicado
    "Playa (Calle 60 – Paradero)": 1000, # Tope aplicado
    "Siboney": 1000, # Tope aplicado
    "Jaimanita": 1000, # Tope aplicado
    "Santa Fe": 1000, # Tope aplicado
    "Marianao (ITM)": 960,
    "Marianao (100 y 51)": 1000, # Tope aplicado
    "Boyeros (Aeropuerto)": 600,
    "Arroyo Naranjo (Los Pinos)": 300,
    "Arroyo Naranjo (Mantilla)": 360,
    "Arroyo Naranjo (Calvario)": 480,
    "Arroyo Naranjo (Eléctrico)": 540,
    "Diez de Octubre (Santo Suárez)": 420,
    "Diez de Octubre (Lawton)": 540,
    "San Miguel del Padrón (Virgen del Camino)": 720,
    "Cotorro (Puente)": 900,
    "Habana del Este (Regla)": 780,
    "Habana del Este (Guanabo)": 1000, # Tope aplicado
    "Alamar (Zonas 9–11)": 1000 # Tope aplicado
}

# ESTADOS DE CONVERSACIÓN (ADMIN)
ADD_NAME, ADD_PRICE, ADD_PHOTO = range(3)

# ESTADOS DE CONVERSACIÓN (CLIENTE CHECKOUT)
CHK_NAME, CHK_ADDRESS, CHK_PHONE = range(3)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- BASE DE DATOS ---

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"menu": [], "orders": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"menu": [], "orders": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- UTILIDADES ---

def es_admin(user_id):
    return user_id == ADMIN_ID

def get_cart_summary(cart):
    """Calcula el total del carrito"""
    total = 0
    text = ""
    for item in cart:
        subtotal = item['price'] * item['qty']
        total += subtotal
        text += f"{item['qty']}x {item['name']} - {subtotal} CUP\n"
    return text, total

# ==========================================
# LÓGICA DEL CLIENTE
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    
    # Si es admin, panel de control
    if es_admin(uid):
        keyboard = [
            [InlineKeyboardButton("➕ Agregar Producto", callback_data="admin_add_start")],
            [InlineKeyboardButton("🗑️ Borrar Menú", callback_data="admin_clear")],
            [InlineKeyboardButton("📦 Gestionar Pedidos", callback_data="admin_orders")]
        ]
        await update.message.reply_text("👋 Admin Panel de Dolezza", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Si es cliente, verificar zona
    if not context.user_data.get('zone'):
        await select_zone_start(update, context)
    else:
        await main_menu(update, context)

async def select_zone_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra las zonas para seleccionar"""
    # Crear botones de zonas en grupos de 2 columnas
    keyboard = []
    zonas_list = list(ZONES_PRICES.keys())
    for i in range(0, len(zonas_list), 2):
        row = []
        row.append(InlineKeyboardButton(zonas_list[i], callback_data=f"zone_{zonas_list[i]}"))
        if i + 1 < len(zonas_list):
            row.append(InlineKeyboardButton(zonas_list[i+1], callback_data=f"zone_{zonas_list[i+1]}"))
        keyboard.append(row)
    
    if update.message:
        await update.message.reply_text("📍 **Bienvenido a Dolezza** 🍬\n\nPara calcular tu mensajería correctamente, por favor selecciona tu zona:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text("📍 **Bienvenido a Dolezza** 🍬\n\nPara calcular tu mensajería correctamente, por favor selecciona tu zona:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def set_zone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    zone_name = query.data.split("zone_")[1]
    context.user_data['zone'] = zone_name
    await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menú principal del cliente"""
    cart_count = sum(item['qty'] for item in context.user_data.get('cart', []))
    zone_name = context.user_data.get('zone', 'No definida')
    
    keyboard = [
        [InlineKeyboardButton(f"🍬 Ver Menú y Agregar", callback_data="view_menu")],
        [InlineKeyboardButton(f"🛒 Mi Carrito ({cart_count})", callback_data="view_cart")],
        [InlineKeyboardButton(f"📦 Mis Pedidos", callback_data="my_orders")],
        [InlineKeyboardButton(f"📍 Zona: {zone_name}", callback_data="change_zone")]
    ]
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(f"🍭 *Dolezza - Dulcería*\n\nZona actual: {zone_name}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.message.reply_text(f"🍭 *Dolezza - Dulcería*\n\nZona actual: {zone_name}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except:
        pass # Evitar error si el mensaje es el mismo

# --- MENÚ Y CARRITO ---

async def view_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = load_data()
    if not data["menu"]:
        await query.edit_message_text("🕒 No hay dulces disponibles hoy.")
        return

    keyboard = []
    for item in data["menu"]:
        keyboard.append([InlineKeyboardButton(f"🍩 {item['name']} - {item['price']} CUP", callback_data=f"prod_{item['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data="back_main")])
    
    await query.edit_message_text("📜 *Menú del Día*\nToca un dulce para ver detalles y agregar al carrito:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = query.data.split("_")[1]
    
    data = load_data()
    product = next((p for p in data["menu"] if p["id"] == prod_id), None)
    
    if not product: return

    keyboard = [
        [InlineKeyboardButton("➕ Agregar al Carrito", callback_data=f"addcart_{prod_id}")],
        [InlineKeyboardButton("🔙 Volver al Menú", callback_data="view_menu")]
    ]
    
    caption = f"*{product['name']}*\n💰 Precio: {product['price']} CUP\n\n¿Deseas agregarlo?"
    
    if product.get("photo_id"):
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=product["photo_id"],
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        await query.delete_message()
    else:
        await query.edit_message_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = query.data.split("_")[1]
    
    data = load_data()
    product = next((p for p in data["menu"] if p["id"] == prod_id), None)
    
    if not product: return
    
    if 'cart' not in context.user_data:
        context.user_data['cart'] = []
    
    # Verificar si ya existe para aumentar cantidad
    found = False
    for item in context.user_data['cart']:
        if item['id'] == prod_id:
            item['qty'] += 1
            found = True
            break
    
    if not found:
        context.user_data['cart'].append({
            "id": product['id'],
            "name": product['name'],
            "price": product['price'],
            "qty": 1
        })
    
    await query.edit_message_text(f"✅ *{product['name']}* agregado al carrito.", parse_mode="Markdown")
    # Volver al menú automáticamente tras 1.5 seg (simulado con mensaje estático)
    keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="view_menu")]]
    await query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', [])
    
    if not cart:
        await query.edit_message_text("🛒 Tu carrito está vacío.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menú", callback_data="view_menu")]]))
        return
    
    text, total = get_cart_summary(cart)
    text += f"\n----------------\n💰 *Total Dulces: {total} CUP*"
    
    keyboard = [
        [InlineKeyboardButton("🚀 Realizar Pedido", callback_data="start_checkout")],
        [InlineKeyboardButton("🗑️ Vaciar Carrito", callback_data="clear_cart")],
        [InlineKeyboardButton("🔙 Volver", callback_data="back_main")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['cart'] = []
    await query.edit_message_text("🗑️ Carrito vaciado.")
    await main_menu(update, context)

# --- CHECKOUT Y PRE-TICKET ---

async def start_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('zone'):
        await select_zone_start(update, context)
        return ConversationHandler.END
        
    await query.edit_message_text("📝 *Pasos para finalizar*\n\nPaso 1/3: Escribe tu **Nombre completo**:", parse_mode="Markdown")
    return CHK_NAME

async def checkout_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['order_name'] = update.message.text
    await update.message.reply_text("Paso 2/3: Escribe tu **Dirección exacta**:")
    return CHK_ADDRESS

async def checkout_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['order_address'] = update.message.text
    await update.message.reply_text("Paso 3/3: Escribe tu **Número de Teléfono**:")
    return CHK_PHONE

async def checkout_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['order_phone'] = update.message.text
    
    # Calcular totales
    cart = context.user_data.get('cart', [])
    items_text, subtotal = get_cart_summary(cart)
    
    zone = context.user_data.get('zone')
    delivery_cost = ZONES_PRICES.get(zone, 0)
    total_final = subtotal + delivery_cost
    
    context.user_data['order_totals'] = {
        'subtotal': subtotal,
        'delivery': delivery_cost,
        'total': total_final
    }
    
    # ENVIAR PRE-TICKET
    text = (
        f"🧾 *PRE-TICKET DE PEDIDO*\n\n"
        f"👤 *Cliente:* {context.user_data['order_name']}\n"
        f"📍 *Zona:* {zone}\n"
        f"🏠 *Dirección:* {context.user_data['order_address']}\n"
        f"📞 *Tel:* {context.user_data['order_phone']}\n\n"
        f"--- *Productos* ---\n{items_text}\n"
        f"----------------\n"
        f"🛍️ Subtotal: {subtotal} CUP\n"
        f"🛵 Mensajería ({zone}): {delivery_cost} CUP\n"
        f"💰 *TOTAL A PAGAR: {total_final} CUP*\n\n"
        f"⚠️ *Por favor revisa los datos.* Si todo está correcto, confirma el pedido."
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ ACEPTAR Y CONFIRMAR PEDIDO", callback_data="confirm_order_accept")],
        [InlineKeyboardButton("❌ RECHAZAR / CANCELAR", callback_data="confirm_order_reject")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ConversationHandler.END

async def confirm_order_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Generar orden final
    cart = context.user_data.get('cart', [])
    totals = context.user_data.get('order_totals')
    order_id = datetime.now().strftime("%Y%m%d%H%M%S")
    
    new_order = {
        "order_id": order_id,
        "user_id": query.from_user.id,
        "user_name": context.user_data['order_name'],
        "user_phone": context.user_data['order_phone'],
        "address": context.user_data['order_address'],
        "zone": context.user_data['zone'],
        "items": cart,
        "subtotal": totals['subtotal'],
        "delivery_cost": totals['delivery'],
        "total": totals['total'],
        "status": "PENDIENTE",
        "date": datetime.now().strftime("%d/%m/%Y %H:%M")
    }
    
    # Guardar en DB
    data = load_data()
    data["orders"].append(new_order)
    save_data(data)
    
    # Limpiar carrito
    context.user_data['cart'] = []
    
    # Avisar al cliente
    await query.edit_message_text(f"✅ *Pedido Confirmado!*\n\nTu pedido #{order_id} ha sido enviado a Dolezza.\nEspera nuestra confirmación.", parse_mode="Markdown")
    
    # Enviar TICKET FINAL AL ADMIN
    items_text, _ = get_cart_summary(cart)
    admin_text = (
        f"🆕 *NUEVO PEDIDO CONFIRMADO* #{order_id}\n\n"
        f"👤 *Cliente:* {new_order['user_name']}\n"
        f"📍 *Zona:* {new_order['zone']}\n"
        f"🏠 *Dirección:* {new_order['address']}\n"
        f"📞 *Tel:* {new_order['user_phone']}\n\n"
        f"--- *Pedido* ---\n{items_text}\n"
        f"----------------\n"
        f"🛵 Mensajería: {new_order['delivery_cost']} CUP\n"
        f"💰 *TOTAL COBRAR: {new_order['total']} CUP*"
    )
    
    # Botones para el admin
    admin_keyboard = [
        [InlineKeyboardButton("✅ Aceptar Pedido", callback_data=f"adm_accept_{order_id}")],
        [InlineKeyboardButton("❌ Rechazar Pedido", callback_data=f"adm_reject_{order_id}")]
    ]
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=InlineKeyboardMarkup(admin_keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error notificando admin: {e}")

async def confirm_order_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Pedido cancelado. Volviendo al menú...")
    # No limpiamos el carrito por si quiere modificar algo, o podríamos limpiarlo.
    # Aquí lo dejamos tal cual.
    await main_menu(update, context)

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = load_data()
    my_orders_list = [o for o in data["orders"] if o["user_id"] == query.from_user.id]
    
    if not my_orders_list:
        await query.edit_message_text("No has realizado pedidos aún.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="back_main")]]))
        return
    
    # Mostrar el último pedido (o los últimos 3)
    text = "📦 *Tus Pedidos Recientes:*\n\n"
    for o in reversed(my_orders_list[-3:]):
        text += f"🧾 *#{o['order_id']}* - {o['date']}\n"
        text += f"Estado: 🔹 *{o['status']}*\n"
        text += f"Total: {o['total']} CUP\n\n"
        
    keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="back_main")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ==========================================
# LÓGICA DEL ADMINISTRADOR
# ==========================================

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("➕ *Agregar Producto*\n\n1️⃣ Escribe el **nombre** del dulce:", parse_mode="Markdown")
    return ADD_NAME

async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['prod_name'] = update.message.text
    await update.message.reply_text("2️⃣ Escribe el **precio** en CUP (ej: 500):")
    return ADD_PRICE

async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ El precio debe ser un número. Inténtalo de nuevo:")
        return ADD_PRICE
        
    context.user_data['prod_price'] = price
    
    keyboard = [[InlineKeyboardButton("⏭️ Sin foto", callback_data="skip_photo_add")]]
    await update.message.reply_text(
        f"Nombre: {context.user_data['prod_name']}\nPrecio: {price} CUP\n\n3️⃣ Envía la **foto** o pulsa el botón para omitir.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADD_PHOTO

async def admin_add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_id = update.message.photo[-1].file_id
    await save_new_product(context, photo_id, update.message)
    return ConversationHandler.END

async def admin_skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.delete_message()
    # Simulamos mensaje para reutilizar función
    class DummyMsg:
        def reply_text(self, text, **kwargs):
            # Hack rápido para enviar mensaje desde callback
            pass 
    await save_new_product(context, None, DummyMsg())
    return ConversationHandler.END

async def save_new_product(context, photo_id, message_obj):
    data = load_data()
    new_item = {
        "id": str(uuid.uuid4()),
        "name": context.user_data['prod_name'],
        "price": context.user_data['prod_price'],
        "photo_id": photo_id
    }
    data["menu"].append(new_item)
    save_data(data)
    await message_obj.reply_text(f"✅ Producto guardado:\n{new_item['name']} - {new_item['price']} CUP")

async def admin_orders_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = load_data()
    # Filtrar pedidos pendientes o aceptados (activos)
    active_orders = [o for o in data["orders"] if o["status"] in ["PENDIENTE", "ACEPTADO"]]
    
    if not active_orders:
        await query.edit_message_text("No hay pedidos activos por gestionar.")
        return
    
    # Mostrar el más antiguo primero
    o = active_orders[0]
    
    items_text, _ = get_cart_summary(o['items'])
    
    status_emoji = "⏳" if o['status'] == "PENDIENTE" else "✅"
    
    text = (
        f"📦 *Pedido #{o['order_id']}*\n"
        f"Estado: {status_emoji} {o['status']}\n\n"
        f"👤 {o['user_name']}\n"
        f"📍 {o['zone']}\n"
        f"🏠 {o['address']}\n"
        f"📞 {o['user_phone']}\n\n"
        f"--- *Detalle* ---\n{items_text}\n"
        f"----------------\n"
        f"💰 *TOTAL: {o['total']} CUP*"
    )
    
    keyboard = []
    if o['status'] == "PENDIENTE":
        keyboard.append([
            InlineKeyboardButton("✅ Aceptar", callback_data=f"adm_accept_{o['order_id']}"),
            InlineKeyboardButton("❌ Rechazar", callback_data=f"adm_reject_{o['order_id']}")
        ])
    elif o['status'] == "ACEPTADO":
        keyboard.append([
            InlineKeyboardButton("🏁 Marcar Realizado/Entregado", callback_data=f"adm_done_{o['order_id']}")
        ])
    
    # Botón para ver siguiente si hay más
    if len(active_orders) > 1:
        keyboard.append([InlineKeyboardButton("⏭️ Siguiente Pedido", callback_data="admin_orders")])
        
    keyboard.append([InlineKeyboardButton("🔙 Menú Admin", callback_data="start")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_action_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action, order_id = query.data.split("_")[1], query.data.split("_")[2]
    
    data = load_data()
    order = next((o for o in data["orders"] if o["order_id"] == order_id), None)
    
    if not order: return
    
    msg_cliente = ""
    
    if action == "accept":
        order["status"] = "ACEPTADO"
        msg_cliente = f"✅ *Tu pedido #{order_id} ha sido ACEPTADO.*\nEstamos preparando tu pedido para enviarlo."
        admin_msg = "Pedido Aceptado."
    elif action == "reject":
        order["status"] = "RECHAZADO"
        msg_cliente = f"❌ *Tu pedido #{order_id} ha sido RECHAZADO.*\nPor favor contáctanos para más información."
        admin_msg = "Pedido Rechazado."
    elif action == "done":
        order["status"] = "REALIZADO"
        msg_cliente = f"🏁 *Tu pedido #{order_id} ha sido ENTREGADO/REALIZADO.*\n¡Gracias por comprar en Dolezza! 🍬"
        admin_msg = "Pedido Marcado como Realizado."
    
    save_data(data)
    
    # Notificar cliente
    try:
        await context.bot.send_message(chat_id=order["user_id"], text=msg_cliente, parse_mode="Markdown")
    except:
        pass
        
    # Actualizar vista admin
    await query.edit_message_text(f"{admin_msg}\n\nPresiona 'Siguiente' o vuelve al menú.")
    # Para simplificar, no recargamos el ticket completo para evitar loops, el admin tocará siguiente.

async def admin_clear_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    data["menu"] = []
    save_data(data)
    await query.edit_message_text("🗑️ Menú eliminado.")

# --- MAIN ---

def main():
    application = Application.builder().token(TOKEN).build()

    # Client Flows
    application.add_handler(CallbackQueryHandler(set_zone, pattern="^zone_"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^back_main$"))
    application.add_handler(CallbackQueryHandler(view_menu, pattern="^view_menu$"))
    application.add_handler(CallbackQueryHandler(view_product, pattern="^prod_"))
    application.add_handler(CallbackQueryHandler(add_to_cart, pattern="^addcart_"))
    application.add_handler(CallbackQueryHandler(view_cart, pattern="^view_cart$"))
    application.add_handler(CallbackQueryHandler(clear_cart, pattern="^clear_cart$"))
    application.add_handler(CallbackQueryHandler(my_orders, pattern="^my_orders$"))
    application.add_handler(CallbackQueryHandler(change_zone_start=select_zone_start, pattern="^change_zone$")) # Shortcut handler needed actually

    # Client Checkout Conversation
    checkout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_checkout, pattern="^start_checkout$")],
        states={
            CHK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_name)],
            CHK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_address)],
            CHK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_phone)],
        },
        fallbacks=[CommandHandler("cancel", confirm_order_reject)], # Usar reject como cancel
    )
    application.add_handler(checkout_conv)
    
    # Confirm Order buttons
    application.add_handler(CallbackQueryHandler(confirm_order_accept, pattern="^confirm_order_accept$"))
    application.add_handler(CallbackQueryHandler(confirm_order_reject, pattern="^confirm_order_reject$"))

    # Admin Flows
    application.add_handler(CallbackQueryHandler(admin_clear_menu, pattern="^admin_clear$"))
    application.add_handler(CallbackQueryHandler(admin_orders_mgmt, pattern="^admin_orders$"))
    application.add_handler(CallbackQueryHandler(admin_action_order, pattern="^adm_(accept|reject|done)_"))

    # Admin Add Product Conversation
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_start, pattern="^admin_add_start$")],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_name)],
            ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_price)],
            ADD_PHOTO: [
                MessageHandler(filters.PHOTO, admin_add_photo),
                CallbackQueryHandler(admin_skip_photo, pattern="^skip_photo_add$")
            ]
        },
        fallbacks=[CommandHandler("cancel", admin_skip_photo)],
    )
    application.add_handler(add_conv)
    
    # Start command
    application.add_handler(CommandHandler("start", start))
    
    # Callback for change zone button fix
    application.add_handler(CallbackQueryHandler(select_zone_start, pattern="^change_zone$"))

    print("Bot Dolezza 3.0 (Zonas & Pagos) iniciado...")
    application.run_polling()

if __name__ == "__main__":
    main()
