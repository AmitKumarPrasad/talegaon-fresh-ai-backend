MENU = """🥬 Welcome to Talegaon Fresh! 🍎

Please select an option:

1️⃣ Place New Order
2️⃣ View Today's Products
3️⃣ Check My Order
4️⃣ Delivery Information
5️⃣ Payment Options
6️⃣ Talk to Us

Reply with 1, 2, 3, 4, 5 or 6."""
 
MENU_RESPONSES = {
    "1": "🛒 Let's place your order!\n\nSend your items and quantities. Example:\n2 kg tomato, 1 kg potato, 500 g carrot",
    "2": "🥦 Today's Products\n\n1. Tomato\n2. Potato\n3. Onion\n4. Carrot\n5. Capsicum\n6. Cabbage\n7. Cauliflower\n8. Ladyfinger\n9. Green Beans\n10. Spinach\n\nSend the product name and quantity to order.",
    "3": "🔎 Please send your Talegaon Fresh Order ID to check its status.",
    "4": "🚚 Delivery Information\n\nWe provide home delivery in Talegaon and nearby areas. Delivery details are confirmed during your order.\n\nReply 1 to place an order.",
    "5": "💳 Payment Options\n\n1️⃣ UPI\n2️⃣ Cash on Delivery\n\nYour payment method will be confirmed before the order is completed.",
    "6": "👤 Our team will assist you. Please send your question and we will respond as soon as possible.",
}

def menu_response(message: str) -> str | None:
    value = message.strip()
    if value.lower() in {"hi", "hello", "hey", "start", "menu"}:
        return MENU
    return MENU_RESPONSES.get(value)
