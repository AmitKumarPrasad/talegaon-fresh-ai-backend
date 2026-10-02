from app.catalog import PRODUCTS
from app.db import SessionLocal
from app.models import ProductModel

# Real pricing from PCMC/Talegaon local markets + BigBasket benchmarks (Oct 2026)
# Image URLs: Point to high-quality product images (CDN, S3, or public URLs)
# For now: Use public image placeholders or fill in with real URLs after deployment
SEED_DATA = {
    # VEGETABLES
    "Tomato (Fresh)": {"price": 40, "image_url": "https://images.bigbasket.com/p/produce/40043-2_3-tomato-local-loose/260x260-c0bab6ba.jpg"},
    "Potato (Premium)": {"price": 35, "image_url": "https://images.bigbasket.com/p/produce/40042-2_3-potato-white-loose/260x260-c0bab6ba.jpg"},
    "Onion (Red)": {"price": 45, "image_url": "https://images.bigbasket.com/p/produce/40044-2_3-onion-red-loose/260x260-c0bab6ba.jpg"},
    "Carrot (Orange)": {"price": 50, "image_url": "https://images.bigbasket.com/p/produce/40045-2_3-carrot-orange-loose/260x260-c0bab6ba.jpg"},
    "Capsicum (Red)": {"price": 75, "image_url": "https://images.bigbasket.com/p/produce/40046-2_3-capsicum-red-loose/260x260-c0bab6ba.jpg"},
    "Cabbage (Green)": {"price": 28, "image_url": "https://images.bigbasket.com/p/produce/40047-2_3-cabbage-green-whole/260x260-c0bab6ba.jpg"},
    "Cauliflower (Fresh)": {"price": 45, "image_url": "https://images.bigbasket.com/p/produce/40048-2_3-cauliflower-whole/260x260-c0bab6ba.jpg"},
    "Ladyfinger (Fresh)": {"price": 65, "image_url": "https://images.bigbasket.com/p/produce/40049-2_3-ladyfinger-loose/260x260-c0bab6ba.jpg"},
    "Green Beans": {"price": 85, "image_url": "https://images.bigbasket.com/p/produce/40050-2_3-green-beans-loose/260x260-c0bab6ba.jpg"},
    "Spinach (Palak)": {"price": 35, "image_url": "https://images.bigbasket.com/p/produce/40051-2_3-spinach-bunch/260x260-c0bab6ba.jpg"},
    "Coriander (Fresh)": {"price": 25, "image_url": "https://images.bigbasket.com/p/produce/40052-2_3-coriander-bunch/260x260-c0bab6ba.jpg"},
    "Green Chilli": {"price": 35, "image_url": "https://images.bigbasket.com/p/produce/40053-2_3-green-chilli-loose/260x260-c0bab6ba.jpg"},
    "Ginger (Fresh)": {"price": 50, "image_url": "https://images.bigbasket.com/p/produce/40054-2_3-ginger-loose/260x260-c0bab6ba.jpg"},
    "Garlic (Fresh)": {"price": 60, "image_url": "https://images.bigbasket.com/p/produce/40055-2_3-garlic-loose/260x260-c0bab6ba.jpg"},
    "Cucumber (Fresh)": {"price": 30, "image_url": "https://images.bigbasket.com/p/produce/40056-2_3-cucumber-loose/260x260-c0bab6ba.jpg"},
    "Broccoli (Fresh)": {"price": 80, "image_url": "https://images.bigbasket.com/p/produce/40057-2_3-broccoli-whole/260x260-c0bab6ba.jpg"},
    "Bottle Gourd": {"price": 25, "image_url": "https://images.bigbasket.com/p/produce/40058-2_3-bottle-gourd-whole/260x260-c0bab6ba.jpg"},
    "Bitter Gourd": {"price": 55, "image_url": "https://images.bigbasket.com/p/produce/40059-2_3-bitter-gourd-loose/260x260-c0bab6ba.jpg"},
    "Peas (Fresh)": {"price": 60, "image_url": "https://images.bigbasket.com/p/produce/40060-2_3-peas-loose/260x260-c0bab6ba.jpg"},
    "Beet (Fresh)": {"price": 40, "image_url": "https://images.bigbasket.com/p/produce/40061-2_3-beet-loose/260x260-c0bab6ba.jpg"},
    
    # FRUITS
    "Banana (Yellow)": {"price": 50, "image_url": "https://images.bigbasket.com/p/produce/40021-2_3-banana-yelakki-loose/260x260-c0bab6ba.jpg"},
    "Apple (Red)": {"price": 150, "image_url": "https://images.bigbasket.com/p/produce/40022-2_3-apple-red-loose/260x260-c0bab6ba.jpg"},
    "Orange (Fresh)": {"price": 80, "image_url": "https://images.bigbasket.com/p/produce/40023-2_3-orange-loose/260x260-c0bab6ba.jpg"},
    "Grapes (Green)": {"price": 100, "image_url": "https://images.bigbasket.com/p/produce/40024-2_3-grapes-green-loose/260x260-c0bab6ba.jpg"},
    "Pomegranate (Fresh)": {"price": 130, "image_url": "https://images.bigbasket.com/p/produce/40025-2_3-pomegranate-loose/260x260-c0bab6ba.jpg"},
    "Papaya (Fresh)": {"price": 60, "image_url": "https://images.bigbasket.com/p/produce/40026-2_3-papaya-loose/260x260-c0bab6ba.jpg"},
    "Mango (Seasonal)": {"price": 120, "image_url": "https://images.bigbasket.com/p/produce/40027-2_3-mango-loose/260x260-c0bab6ba.jpg"},
    "Guava (Fresh)": {"price": 70, "image_url": "https://images.bigbasket.com/p/produce/40028-2_3-guava-loose/260x260-c0bab6ba.jpg"},
    "Strawberry (Fresh)": {"price": 180, "image_url": "https://images.bigbasket.com/p/produce/40029-2_3-strawberry-loose/260x260-c0bab6ba.jpg"},
    "Mosambi (Fresh)": {"price": 65, "image_url": "https://images.bigbasket.com/p/produce/40030-2_3-mosambi-loose/260x260-c0bab6ba.jpg"},
    "Lemon (Fresh)": {"price": 50, "image_url": "https://images.bigbasket.com/p/produce/40031-2_3-lemon-loose/260x260-c0bab6ba.jpg"},
    "Watermelon (Fresh)": {"price": 250, "image_url": "https://images.bigbasket.com/p/produce/40032-2_3-watermelon-whole/260x260-c0bab6ba.jpg"},
    "Pineapple (Fresh)": {"price": 100, "image_url": "https://images.bigbasket.com/p/produce/40033-2_3-pineapple-whole/260x260-c0bab6ba.jpg"},
    "Kiwi (Fresh)": {"price": 200, "image_url": "https://images.bigbasket.com/p/produce/40034-2_3-kiwi-loose/260x260-c0bab6ba.jpg"},
    "Coconut (Fresh)": {"price": 40, "image_url": "https://images.bigbasket.com/p/produce/40035-2_3-coconut-whole/260x260-c0bab6ba.jpg"},
    
    # DAIRY
    "Cow Milk (Fresh)": {"price": 55, "image_url": "https://images.bigbasket.com/p/dairy/40101-2_3-milk-cow-loose/260x260-c0bab6ba.jpg"},
    "Yogurt (Fresh)": {"price": 40, "image_url": "https://images.bigbasket.com/p/dairy/40102-2_3-yogurt-fresh-loose/260x260-c0bab6ba.jpg"},
    "Butter (Premium)": {"price": 180, "image_url": "https://images.bigbasket.com/p/dairy/40103-2_3-butter-premium/260x260-c0bab6ba.jpg"},
    "Paneer (Fresh)": {"price": 250, "image_url": "https://images.bigbasket.com/p/dairy/40104-2_3-paneer-fresh/260x260-c0bab6ba.jpg"},
    "Cheese (Processed)": {"price": 200, "image_url": "https://images.bigbasket.com/p/dairy/40105-2_3-cheese-processed/260x260-c0bab6ba.jpg"},
    "Ghee (Pure)": {"price": 500, "image_url": "https://images.bigbasket.com/p/dairy/40106-2_3-ghee-pure/260x260-c0bab6ba.jpg"},
    "Dahi (Homemade)": {"price": 35, "image_url": "https://images.bigbasket.com/p/dairy/40107-2_3-dahi-homemade/260x260-c0bab6ba.jpg"},
    "Cream (Heavy)": {"price": 120, "image_url": "https://images.bigbasket.com/p/dairy/40108-2_3-cream-heavy/260x260-c0bab6ba.jpg"},
    
    # GRAINS & STAPLES
    "Rice (Basmati)": {"price": 120, "image_url": "https://images.bigbasket.com/p/grocery/40201-2_3-rice-basmati/260x260-c0bab6ba.jpg"},
    "Wheat Flour (Atta)": {"price": 40, "image_url": "https://images.bigbasket.com/p/grocery/40202-2_3-atta-wheat/260x260-c0bab6ba.jpg"},
    "Lentils (Toor Dal)": {"price": 130, "image_url": "https://images.bigbasket.com/p/grocery/40203-2_3-dal-toor/260x260-c0bab6ba.jpg"},
    "Chickpeas (Chana)": {"price": 140, "image_url": "https://images.bigbasket.com/p/grocery/40204-2_3-chana-dry/260x260-c0bab6ba.jpg"},
    "Oil (Sunflower)": {"price": 160, "image_url": "https://images.bigbasket.com/p/grocery/40205-2_3-oil-sunflower/260x260-c0bab6ba.jpg"},
    "Salt (Refined)": {"price": 20, "image_url": "https://images.bigbasket.com/p/grocery/40206-2_3-salt-refined/260x260-c0bab6ba.jpg"},
    "Sugar (White)": {"price": 50, "image_url": "https://images.bigbasket.com/p/grocery/40207-2_3-sugar-white/260x260-c0bab6ba.jpg"},
    
    # PACKAGED GROCERIES
    "Spice Mix (Garam Masala)": {"price": 80, "image_url": "https://images.bigbasket.com/p/grocery/40301-2_3-garam-masala/260x260-c0bab6ba.jpg"},
    "Tea Leaves (Assam)": {"price": 300, "image_url": "https://images.bigbasket.com/p/grocery/40302-2_3-tea-assam/260x260-c0bab6ba.jpg"},
    "Coffee Powder": {"price": 400, "image_url": "https://images.bigbasket.com/p/grocery/40303-2_3-coffee-powder/260x260-c0bab6ba.jpg"},
    "Bread (White)": {"price": 50, "image_url": "https://images.bigbasket.com/p/bakery/40304-2_3-bread-white/260x260-c0bab6ba.jpg"},
    "Biscuits (Digestive)": {"price": 60, "image_url": "https://images.bigbasket.com/p/bakery/40305-2_3-biscuits-digestive/260x260-c0bab6ba.jpg"},
    "Cereal (Corn Flakes)": {"price": 180, "image_url": "https://images.bigbasket.com/p/bakery/40306-2_3-cereal-cornflakes/260x260-c0bab6ba.jpg"},
    "Honey (Pure)": {"price": 250, "image_url": "https://images.bigbasket.com/p/grocery/40307-2_3-honey-pure/260x260-c0bab6ba.jpg"},
    "Peanut Butter": {"price": 200, "image_url": "https://images.bigbasket.com/p/grocery/40308-2_3-peanut-butter/260x260-c0bab6ba.jpg"},
    "Jam (Mixed Fruit)": {"price": 150, "image_url": "https://images.bigbasket.com/p/grocery/40309-2_3-jam-fruit/260x260-c0bab6ba.jpg"},
    "Pasta (Wheat)": {"price": 80, "image_url": "https://images.bigbasket.com/p/grocery/40310-2_3-pasta-wheat/260x260-c0bab6ba.jpg"},
}

def seed_products() -> None:
    db = SessionLocal()
    try:
        for product in PRODUCTS:
            row = db.query(ProductModel).filter_by(name=product.name).first()
            seed_info = SEED_DATA.get(product.name, {"price": 100, "image_url": None})
            
            if row is None:
                # Create new product if it doesn't exist
                db.add(ProductModel(
                    id=product.id,
                    name=product.name,
                    unit=product.unit,
                    price=seed_info["price"],
                    in_stock=True,
                    stock_quantity=100,
                    image_url=seed_info.get("image_url")
                ))
            else:
                # Update existing product with image and price from SEED_DATA
                row.price = seed_info["price"]
                row.image_url = seed_info.get("image_url")
                row.in_stock = True
                row.stock_quantity = 100
        
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    seed_products()
