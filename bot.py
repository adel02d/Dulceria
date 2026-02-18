import logging
import os
import json
import uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# --- CONFIGURACIÓN ---
TOKEN = os.environ.get("TOKEN")

# --- CONFIGURACIÓN DE MULTIPLES ADMINS ---
# Leemos la variable de entorno (ej: "123,456"), la separamos por comas y convertimos a enteros
admins_str = os.environ.get("ADMIN_IDS")
ADMIN_IDS = []
if admins_str:
    ADMIN_IDS = [int(id.strip()) for id in admins_str.split(",")]

DATA_FILE = os.environ.get("DATA_FILE", "database.json") 

# --- TABLA DE ZONAS Y PRECIOS DE MENSAJERÍA ---
ZONES_PRICES = {
    "Centro Habana": 720,
    "Vedado (hasta Paseo)": 780,
    "Vedado (después de Paseo)": 840,
    "Habana Vieja": 660,
    "Cerro": 600,
    "Nuevo Vedado": 840,
    "Playa (Puente – Calle 60)": 1000, 
    "Playa (Calle 60 – Paradero)": 1000, 
    "Siboney": 1000, 
    "Jaimanita": 1000, 
    "Santa Fe": 1000, 
    "Marianao (ITM)": 960,
    "Marianao (100 y 51)": 1000, 
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
    "Habana del Este (Guanabo)": 1000, 
    "Alamar (Zonas 9–11)": 1000 
}

# ESTADOS DE CONVERSACIÓN
ADD_NAME, ADD_PRICE, ADD_PHOTO = range(3)
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

def get_balance():
    data = load_data()
    total_sales = 0
    delivered_count = 0
    for order in data["orders"]:
        if order["status"] == "REALIZADO":
            total_sales += order["total"]
            delivered_count += 1
    return total_sales, delivered_count

def es_admin(user_id):
    return user_id in ADMIN_IDS

def get_cart_summary(cart):
    total = 0
    text = ""
    for item in cart:
        subtotal = item['price'] * item['qty']
        total += subtotal
        text += f"{item['qty']}x {item['name']} - {subtotal} CUP\n"
    return text, total

# ==========================================
# FUNCIONES PRINCIPALES (ADMIN Y CLIENTE)
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el inicio tanto por comando /start como por botón de volver"""
    user = update.effective_user
    uid = user.id
    is_callback = update.callback_query is not None
    
    # Determinar si es admin
    if es_admin(uid):
        keyboard = [
            [InlineKeyboardButton("➕ Agregar Producto", callback_data="admin_add_start")],
            [InlineKeyboardButton("📦 Gestionar Pedidos", callback_data="admin_orders")],
            [InlineKeyboardButton("📊 Ver Balance", callback_data="admin_balance")],
            [InlineKeyboardButton("🗑️ Borrar Menú", callback_data="admin_clear")]
        ]
        text = "👋 Admin Panel de DolceZZa"
    else:
        # Si es cliente, verificar si ya eligió zona en esta sesión
        if not context.user_data.get('zone'):
            await select_zone_start(update, context)
            return
        # Si ya tiene zona, mostrar menú principal
        return await main_menu(update, context)

    # Enviar el mensaje (Nuevo o Editado)
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        if is_callback:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
    except Exception as e:
        # Si el mensaje no cambió, ignorar error para no crashear
        pass

# ==========================================
# LÓGICA DEL CLIENTE
# ==========================================

async def select_zone_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    zonas_list = list(ZONES_PRICES.keys())
    for i in range(0, len(zonas_list), 2):
        row = []
        row.append(InlineKeyboardButton(zonas_list[i], callback_data=f"zone_{zonas_list[i]}"))
        if i + 1 < len(zonas_list):
            row.append(InlineKeyboardButton(zonas_list[i+1], callback_data=f"zone_{zonas_list[i+1]}"))
        keyboard.append(row)
    
    text = "📍 **Bienvenido a DolceZZa** 🍬\n\nPor favor selecciona tu zona para calcular la mensajería:"
    markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    except:
        pass

async def set_zone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    zone_name = query.data.split("zone_")[1]
    context.user_data['zone'] = zone_name
    await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cart_count = sum(item['qty'] for item in context.user_data.get('cart', []))
    zone_name = context.user_data.get('zone', 'No definida')
    
    keyboard = [
        [InlineKeyboardButton(f"🍬 Ver Menú", callback_data="view_menu")],
        [InlineKeyboardButton(f"🛒 Mi Carrito ({cart_count})", callback_data="view_cart")],
        [InlineKeyboardButton(f"📦 Mis Pedidos", callback_data="my_orders")],
        [InlineKeyboardButton(f"📍 Cambiar Zona", callback_data="change_zone")]
    ]
    
    text = f"🍭 *DolceZZa - Dulcería*\n\nZona actual: {zone_name}"
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except:
        pass

async def view_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = load_data()
    if not data["menu"]:
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="back_main")]]
        await query.edit_message_text("🕒 No hay dulces disponibles hoy.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    keyboard = []
    for item in data["menu"]:
        keyboard.append([InlineKeyboardButton(f"🍩 {item['name']} - {item['price']} CUP", callback_data=f"prod_{item['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data="back_main")])
    
    await query.edit_message_text("📜 *Menú del Día*\nToca un dulce para ver detalles:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

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
    
    caption = f"*{product['name']}*\n💰 Precio: {product['price']} CUP"
    
    if product.get("photo_id"):
        await context.bot.send_photo(chat_id=query.message.chat_id, photo=product["photo_id"], caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
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
    
    if 'cart' not in context.user_data: context.user_data['cart'] = []
    
    found = False
    for item in context.user_data['cart']:
        if item['id'] == prod_id:
            item['qty'] += 1
            found = True
            break
    if not found:
        context.user_data['cart'].append({"id": product['id'], "name": product['name'], "price": product['price'], "qty": 1})
    
    keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="view_menu")]]
    try:
        await query.edit_message_text(f"✅ *{product['name']}* agregado.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except:
        pass

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', [])
    if not cart:
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="back_main")]]
        await query.edit_message_text("🛒 Tu carrito está vacío.", reply_markup=InlineKeyboardMarkup(keyboard))
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

# --- CHECKOUT ---

async def start_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('zone'):
        await select_zone_start(update, context)
        return ConversationHandler.END
    await query.edit_message_text("📝 *Pasos para finalizar*\n\nPaso 1/3: Escribe tu **Nombre**:", parse_mode="Markdown")
    return CHK_NAME

async def checkout_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['order_name'] = update.message.text
    await update.message.reply_text("Paso 2/3: Escribe tu **Dirección**:")
    return CHK_ADDRESS

async def checkout_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['order_address'] = update.message.text
    await update.message.reply_text("Paso 3/3: Escribe tu **Teléfono**:")
    return CHK_PHONE

async def checkout_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['order_phone'] = update.message.text
    
    cart = context.user_data.get('cart', [])
    items_text, subtotal = get_cart_summary(cart)
    zone = context.user_data.get('zone')
    delivery_cost = ZONES_PRICES.get(zone, 0)
    total_final = subtotal + delivery_cost
    
    context.user_data['order_totals'] = {'subtotal': subtotal, 'delivery': delivery_cost, 'total': total_final}
    
    text = (f"🧾 *PRE-TICKET*\n\n👤 {context.user_data['order_name']}\n📍 {zone}\n🏠 {context.user_data['order_address']}\n📞 {context.user_data['order_phone']}\n\n"
             f"{items_text}\n----------------\n🛍️ Subtotal: {subtotal} CUP\n🛵 Mensajería: {delivery_cost} CUP\n💰 *TOTAL: {total_final} CUP*")
    
    keyboard = [
        [InlineKeyboardButton("✅ CONFIRMAR PEDIDO", callback_data="confirm_order_accept")],
        [InlineKeyboardButton("❌ CANCELAR", callback_data="confirm_order_reject")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ConversationHandler.END

async def confirm_order_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', [])
    totals = context.user_data.get('order_totals')
    order_id = datetime.now().strftime("%Y%m%d%H%M%S")
    
    new_order = {
        "order_id": order_id, "user_id": query.from_user.id, "user_name": context.user_data['order_name'],
        "user_phone": context.user_data['order_phone'], "address": context.user_data['order_address'],
        "zone": context.user_data['zone'], "items": cart, "subtotal": totals['subtotal'],
        "delivery_cost": totals['delivery'], "total": totals['total'], "status": "PENDIENTE",
        "date": datetime.now().strftime("%d/%m/%Y %H:%M")
    }
    
    data = load_data()
    data["orders"].append(new_order)
    save_data(data)
    context.user_data['cart'] = []
    
    await query.edit_message_text(f"✅ *Pedido Enviado a DolceZZa*.\nEspera confirmación.", parse_mode="Markdown")
    
    # --- NOTIFICAR A TODOS LOS ADMINS ---
    items_text, _ = get_cart_summary(cart)
    admin_text = (f"🆕 *PEDIDO #{order_id}*\n\n👤 {new_order['user_name']}\n📍 {new_order['zone']}\n🏠 {new_order['address']}\n📞 {new_order['user_phone']}\n\n"
                  f"{items_text}\n----------------\n🛵 Mensajería: {new_order['delivery_cost']} CUP\n💰 *TOTAL: {new_order['total']} CUP*")
    
    admin_keyboard = [
        [InlineKeyboardButton("✅ Aceptar", callback_data=f"adm_accept_{order_id}")],
        [InlineKeyboardButton("❌ Rechazar", callback_data=f"adm_reject_{order_id}")]
    ]
    
    # Enviar a cada ID en la lista ADMIN_IDS
    if not ADMIN_IDS:
        print("ADVERTENCIA: No hay administradores configurados en ADMIN_IDS")
    else:
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    reply_markup=InlineKeyboardMarkup(admin_keyboard),
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Error notificando al admin {admin_id}: {e}")

async def confirm_order_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Pedido cancelado.")
    await main_menu(update, context)

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    my_orders_list = [o for o in data["orders"] if o["user_id"] == query.from_user.id]
    
    if not my_orders_list:
        await query.edit_message_text("No hay pedidos.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="back_main")]]))
        return
    
    text = "📦 *Tus Pedidos:*\n\n"
    for o in reversed(my_orders_list[-3:]):
        text += f"🧾 #{o['order_id']} - {o['date']}\nEstado: *{o['status']}*\nTotal: {o['total']} CUP\n\n"
        
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="back_main")]]), parse_mode="Markdown")

# ==========================================
# LÓGICA DEL ADMINISTRADOR
# ==========================================

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("➕ *Agregar Producto*\n\nEscribe el **nombre**:", parse_mode="Markdown")
    return ADD_NAME

async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['prod_name'] = update.message.text
    await update.message.reply_text("Escribe el **precio** en CUP:")
    return ADD_PRICE

async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Debe ser un número:")
        return ADD_PRICE
    context.user_data['prod_price'] = price
    
    keyboard = [[InlineKeyboardButton("⏭️ Sin foto", callback_data="skip_photo_add")]]
    await update.message.reply_text(f"Envía **foto** o pulsa botón:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_PHOTO

async def admin_add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_id = update.message.photo[-1].file_id
    await save_new_product(context, photo_id, update.message)
    return ConversationHandler.END

async def admin_skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.delete_message()
    class DummyMsg:
        def reply_text(self, text, **kwargs): pass 
    await save_new_product(context, None, DummyMsg())
    return ConversationHandler.END

async def save_new_product(context, photo_id, message_obj):
    data = load_data()
    new_item = {"id": str(uuid.uuid4()), "name": context.user_data['prod_name'], "price": context.user_data['prod_price'], "photo_id": photo_id}
    data["menu"].append(new_item)
    save_data(data)
    
    keyboard = [[InlineKeyboardButton("🔙 Menú Admin", callback_data="start")]]
    await message_obj.reply_text(f"✅ Guardado: {new_item['name']} - {new_item['price']} CUP", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_orders_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = load_data()
    active_orders = [o for o in data["orders"] if o["status"] in ["PENDIENTE", "ACEPTADO"]]
    
    if not active_orders:
        keyboard = [[InlineKeyboardButton("🔙 Menú Admin", callback_data="start")]]
        await query.edit_message_text("No hay pedidos activos.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Mostrar el primero
    o = active_orders[0]
    items_text, _ = get_cart_summary(o['items'])
    status_emoji = "⏳" if o['status'] == "PENDIENTE" else "✅"
    
    text = (f"📦 *Pedido #{o['order_id']}*\nEstado: {status_emoji} {o['status']}\n\n👤 {o['user_name']}\n📍 {o['zone']}\n🏠 {o['address']}\n📞 {o['user_phone']}\n\n"
             f"{items_text}\n----------------\n💰 *TOTAL: {o['total']} CUP*")
    
    keyboard = []
    if o['status'] == "PENDIENTE":
        keyboard.append([InlineKeyboardButton("✅ Aceptar", callback_data=f"adm_accept_{o['order_id']}"), InlineKeyboardButton("❌ Rechazar", callback_data=f"adm_reject_{o['order_id']}")])
    elif o['status'] == "ACEPTADO":
        keyboard.append([InlineKeyboardButton("🏁 Marcar Entregado", callback_data=f"adm_done_{o['order_id']}")])
    
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
    reset_user = False
    
    if action == "accept":
        order["status"] = "ACEPTADO"
        msg_cliente = f"✅ *Pedido #{order_id} ACEPTADO* en DolceZZa."
        admin_msg = "Pedido Aceptado."
    elif action == "reject":
        order["status"] = "RECHAZADO"
        msg_cliente = f"❌ *Pedido #{order_id} RECHAZADO*."
        admin_msg = "Pedido Rechazado."
    elif action == "done":
        order["status"] = "REALIZADO"
        msg_cliente = f"🏁 *Pedido #{order_id} ENTREGADO*.\n¡Gracias por comprar en DolceZZa!"
        admin_msg = "Pedido Entregado."
        reset_user = True
    
    save_data(data)
    
    # Notificar cliente
    try:
        user_keyboard = None
        if reset_user:
            user_keyboard = [[InlineKeyboardButton("🔄 Iniciar Nuevo Pedido", callback_data="start")]] # Usar 'start' para reiniciar
        
        await context.bot.send_message(
            chat_id=order["user_id"], 
            text=msg_cliente, 
            reply_markup=InlineKeyboardMarkup(user_keyboard) if user_keyboard else None,
            parse_mode="Markdown"
        )
    except:
        pass
        
    # Volver al menú admin automáticamente tras la acción
    keyboard = [[InlineKeyboardButton("🔙 Menú Admin", callback_data="start")]]
    await query.edit_message_text(f"{admin_msg}\n\nPresiona 'Menú Admin' para volver.", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_clear_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    data["menu"] = []
    save_data(data)
    
    keyboard = [[InlineKeyboardButton("🔙 Menú Admin", callback_data="start")]]
    await query.edit_message_text("🗑️ Menú eliminado.", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    total, count = get_balance()
    
    text = f"📊 *Balance - DolceZZa*\n\n🏁 Entregados: {count}\n💰 Recaudado: {total} CUP"
    keyboard = [[InlineKeyboardButton("🔙 Menú Admin", callback_data="start")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ==========================================
# MAIN Y HANDLERS (EL CORAZÓN DEL BOT)
# ==========================================

def main():
    application = Application.builder().token(TOKEN).build()

    # --- CLIENTES ---
    # Zonas y Menú
    application.add_handler(CallbackQueryHandler(set_zone, pattern="^zone_"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^back_main$"))
    application.add_handler(CallbackQueryHandler(select_zone_start, pattern="^change_zone$"))
    application.add_handler(CallbackQueryHandler(view_menu, pattern="^view_menu$"))
    application.add_handler(CallbackQueryHandler(view_product, pattern="^prod_"))
    application.add_handler(CallbackQueryHandler(add_to_cart, pattern="^addcart_"))
    application.add_handler(CallbackQueryHandler(view_cart, pattern="^view_cart$"))
    application.add_handler(CallbackQueryHandler(clear_cart, pattern="^clear_cart$"))
    application.add_handler(CallbackQueryHandler(my_orders, pattern="^my_orders$"))
    
    # Checkout
    checkout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_checkout, pattern="^start_checkout$")],
        states={
            CHK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_name)],
            CHK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_address)],
            CHK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_phone)],
        },
        fallbacks=[CommandHandler("cancel", confirm_order_reject)], 
    )
    application.add_handler(checkout_conv)
    application.add_handler(CallbackQueryHandler(confirm_order_accept, pattern="^confirm_order_accept$"))
    application.add_handler(CallbackQueryHandler(confirm_order_reject, pattern="^confirm_order_reject$"))

    # --- ADMINISTRADOR ---
    application.add_handler(CallbackQueryHandler(admin_clear_menu, pattern="^admin_clear$"))
    application.add_handler(CallbackQueryHandler(admin_orders_mgmt, pattern="^admin_orders$"))
    application.add_handler(CallbackQueryHandler(admin_balance, pattern="^admin_balance$"))
    application.add_handler(CallbackQueryHandler(admin_action_order, pattern="^adm_(accept|reject|done)_"))
    
    # Agregar Producto
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_start, pattern="^admin_add_start$")],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_name)],
            ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_price)],
            ADD_PHOTO: [MessageHandler(filters.PHOTO, admin_add_photo), CallbackQueryHandler(admin_skip_photo, pattern="^skip_photo_add$")]
        },
        fallbacks=[CommandHandler("cancel", admin_skip_photo)],
    )
    application.add_handler(add_conv)

    # --- GLOBAL (Vital para botones de Volver) ---
    # Esto permite que los botones con callback_data="start" funcionen
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(start, pattern="^start$"))

    # --- WEBHOOK ---
    port = int(os.environ.get("PORT", 8443))
    webhook_url = os.environ.get("RENDER_EXTERNAL_URL")
    
    if webhook_url:
        webhook_url = f"{webhook_url}/telegram-webhook"
        print(f"🚀 Iniciando WEBHOOK en: {webhook_url}")
        application.run_webhook(listen="0.0.0.0", port=port, url_path="telegram-webhook", webhook_url=webhook_url)
    else:
        print("🖥️ Iniciando POLLING (Local)...")
        application.run_polling()

if __name__ == "__main__":
    main()
