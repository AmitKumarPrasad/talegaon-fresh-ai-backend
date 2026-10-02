from app.catalog import PRODUCTS
from app.db import SessionLocal
from app.models import ProductModel

# Real pricing from PCMC/Talegaon local markets + BigBasket benchmarks (Oct 2026)
# Image URLs: Point to high-quality product images from BigBasket CDN
SEED_DATA = {
    # VEGETABLES (Matched to catalog.py product names)
    "Tomato": {"price": 40, "image_url": "https://images.bigbasket.com/p/produce/40043-2_3-tomato-local-loose/260x260-c0bab6ba.jpg"},
    "Potato": {"price": 60, "image_url": "https://images.bigbasket.com/p/produce/40042-2_3-potato-white-loose/260x260-c0bab6ba.jpg"},
    "Onion": {"price": 40, "image_url": "https://images.bigbasket.com/p/produce/40044-2_3-onion-red-loose/260x260-c0bab6ba.jpg"},
    "Carrot": {"price": 50, "image_url": "https://images.bigbasket.com/p/produce/40045-2_3-carrot-orange-loose/260x260-c0bab6ba.jpg"},
    "Capsicum": {"price": 70, "image_url": "https://images.bigbasket.com/p/produce/40046-2_3-capsicum-red-loose/260x260-c0bab6ba.jpg"},
    "Cabbage": {"price": 30, "image_url": "https://images.bigbasket.com/p/produce/40047-2_3-cabbage-green-whole/260x260-c0bab6ba.jpg"},
    "Cauliflower": {"price": 40, "image_url": "https://images.bigbasket.com/p/produce/40048-2_3-cauliflower-whole/260x260-c0bab6ba.jpg"},
    "Ladyfinger": {"price": 60, "image_url": "https://images.bigbasket.com/p/produce/40049-2_3-ladyfinger-loose/260x260-c0bab6ba.jpg"},
    "Green Beans": {"price": 80, "image_url": "https://images.bigbasket.com/p/produce/40050-2_3-green-beans-loose/260x260-c0bab6ba.jpg"},
    "Spinach": {"price": 30, "image_url": "https://images.bigbasket.com/p/produce/40051-2_3-spinach-bunch/260x260-c0bab6ba.jpg"},
    "Coriander": {"price": 20, "image_url": "https://images.bigbasket.com/p/produce/40052-2_3-coriander-bunch/260x260-c0bab6ba.jpg"},
    "Green Chilli": {"price": 30, "image_url": "https://images.bigbasket.com/p/produce/40053-2_3-green-chilli-loose/260x260-c0bab6ba.jpg"},
    "Ginger": {"price": 40, "image_url": "https://images.bigbasket.com/p/produce/40054-2_3-ginger-loose/260x260-c0bab6ba.jpg"},
    "Garlic": {"price": 50, "image_url": "https://images.bigbasket.com/p/produce/40055-2_3-garlic-loose/260x260-c0bab6ba.jpg"},
    
    # FRUITS
    "Banana": {"price": 90, "image_url": "https://images.bigbasket.com/p/produce/40021-2_3-banana-yelakki-loose/260x260-c0bab6ba.jpg"},
    "Apple": {"price": 220, "image_url": "https://images.bigbasket.com/p/produce/40022-2_3-apple-red-loose/260x260-c0bab6ba.jpg"},
    "Orange": {"price": 90, "image_url": "https://images.bigbasket.com/p/produce/40023-2_3-orange-loose/260x260-c0bab6ba.jpg"},
    "Grapes": {"price": 100, "image_url": "https://images.bigbasket.com/p/produce/40024-2_3-grapes-green-loose/260x260-c0bab6ba.jpg"},
    "Pomegranate": {"price": 140, "image_url": "https://images.bigbasket.com/p/produce/40025-2_3-pomegranate-loose/260x260-c0bab6ba.jpg"},
    "Papaya": {"price": 60, "image_url": "https://images.bigbasket.com/p/produce/40026-2_3-papaya-loose/260x260-c0bab6ba.jpg"},
    
    # DAIRY
    "Amul Taaza Milk": {"price": 59, "image_url": "https://images.bigbasket.com/p/dairy/40101-2_3-milk-cow-loose/260x260-c0bab6ba.jpg"},
    "Amul Masti Dahi": {"price": 50, "image_url": "https://images.bigbasket.com/p/dairy/40102-2_3-yogurt-fresh-loose/260x260-c0bab6ba.jpg"},
    "Amul Fresh Malai Paneer": {"price": 95, "image_url": "https://images.bigbasket.com/p/dairy/40104-2_3-paneer-fresh/260x260-c0bab6ba.jpg"},
    "Amul Butter": {"price": 63, "image_url": "https://images.bigbasket.com/p/dairy/40103-2_3-butter-premium/260x260-c0bab6ba.jpg"},
    "Amul Pure Milk Cheese Slices": {"price": 137, "image_url": "https://images.bigbasket.com/p/dairy/40105-2_3-cheese-processed/260x260-c0bab6ba.jpg"},
    
    # SNACKS  
    "Lay's Cream & Onion Chips": {"price": 20, "image_url": "https://images.bigbasket.com/p/snacks/40301-2_3-lays-chips/260x260-c0bab6ba.jpg"},
    "Bingo Tedhe Medhe": {"price": 14, "image_url": "https://images.bigbasket.com/p/snacks/40302-2_3-bingo-snacks/260x260-c0bab6ba.jpg"},
    "Parle Hide & Seek": {"price": 26, "image_url": "https://images.bigbasket.com/p/snacks/40303-2_3-parle-biscuit/260x260-c0bab6ba.jpg"},
    "Britannia Jim Jam": {"price": 35, "image_url": "https://images.bigbasket.com/p/snacks/40304-2_3-britannia-biscuit/260x260-c0bab6ba.jpg"},
    "Chheda's Banana Chips": {"price": 70, "image_url": "https://images.bigbasket.com/p/snacks/40305-2_3-chheda-chips/260x260-c0bab6ba.jpg"},
    
    # GROCERY
    "Aashirvaad Whole Wheat Atta": {"price": 264, "image_url": "https://images.bigbasket.com/p/grocery/40201-2_3-atta-wheat/260x260-c0bab6ba.jpg"},
    "India Gate Rozana Basmati Rice": {"price": 454, "image_url": "https://images.bigbasket.com/p/grocery/40202-2_3-rice-basmati/260x260-c0bab6ba.jpg"},
    "Tata Salt Iodised": {"price": 29, "image_url": "https://images.bigbasket.com/p/grocery/40203-2_3-salt-refined/260x260-c0bab6ba.jpg"},
    "Sugar": {"price": 69, "image_url": "https://images.bigbasket.com/p/grocery/40204-2_3-sugar-white/260x260-c0bab6ba.jpg"},
    "Tata Sampann Toor Dal": {"price": 174, "image_url": "https://images.bigbasket.com/p/grocery/40205-2_3-dal-toor/260x260-c0bab6ba.jpg"},
    "Fortune Sunlite Sunflower Oil": {"price": 177, "image_url": "https://images.bigbasket.com/p/grocery/40206-2_3-oil-sunflower/260x260-c0bab6ba.jpg"},
    
    # INSTANT FOOD & BEVERAGES
    "Maggi Masala Noodles": {"price": 60, "image_url": "https://images.bigbasket.com/p/instant/40301-2_3-maggi-noodles/260x260-c0bab6ba.jpg"},
    "Tata Tea Gold": {"price": 264, "image_url": "https://images.bigbasket.com/p/beverages/40302-2_3-tata-tea/260x260-c0bab6ba.jpg"},
    
    # BAKERY & BREAKFAST
    "Harvest Gold Atta Bread": {"price": 65, "image_url": "https://images.bigbasket.com/p/bakery/40304-2_3-bread-white/260x260-c0bab6ba.jpg"},
    
    # MASALA & SPICES
    "Catch Coriander Powder": {"price": 32, "image_url": "https://images.bigbasket.com/p/spices/40303-2_3-coriander-powder/260x260-c0bab6ba.jpg"},
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
