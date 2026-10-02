from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    unit: str
    category: str


PRODUCTS = [
    Product(1, "Tomato", "1 kg", "Vegetables"),
    Product(2, "Potato", "1 kg", "Vegetables"),
    Product(3, "Onion", "1 kg", "Vegetables"),
    Product(4, "Carrot", "500 g", "Vegetables"),
    Product(5, "Capsicum", "500 g", "Vegetables"),
    Product(6, "Cabbage", "1 pc", "Vegetables"),
    Product(7, "Cauliflower", "1 pc", "Vegetables"),
    Product(8, "Ladyfinger", "500 g", "Vegetables"),
    Product(9, "Green Beans", "500 g", "Vegetables"),
    Product(10, "Spinach", "1 bunch", "Leafy Greens"),
    Product(11, "Coriander", "1 bunch", "Leafy Greens"),
    Product(12, "Green Chilli", "250 g", "Vegetables"),
    Product(13, "Ginger", "250 g", "Vegetables"),
    Product(14, "Garlic", "250 g", "Vegetables"),
    Product(15, "Banana", "1 dozen", "Fruits"),
    Product(16, "Apple", "1 kg", "Fruits"),
    Product(17, "Orange", "1 kg", "Fruits"),
    Product(18, "Grapes", "500 g", "Fruits"),
    Product(19, "Pomegranate", "1 kg", "Fruits"),
    Product(20, "Papaya", "1 pc", "Fruits"),
    Product(21, "Amul Taaza Milk", "1 L", "Dairy"),
    Product(22, "Amul Masti Dahi", "400 g", "Dairy"),
    Product(23, "Amul Fresh Malai Paneer", "200 g", "Dairy"),
    Product(24, "Amul Butter", "100 g", "Dairy"),
    Product(25, "Amul Pure Milk Cheese Slices", "200 g", "Dairy"),
    Product(26, "Lay's Cream & Onion Chips", "58 g", "Snacks"),
    Product(27, "Bingo Tedhe Medhe", "75 g", "Snacks"),
    Product(28, "Parle Hide & Seek", "100 g", "Snacks"),
    Product(29, "Britannia Jim Jam", "138 g", "Snacks"),
    Product(30, "Chheda's Banana Chips", "170 g", "Snacks"),
    Product(31, "Aashirvaad Whole Wheat Atta", "5 kg", "Grocery"),
    Product(32, "India Gate Rozana Basmati Rice", "5 kg", "Grocery"),
    Product(33, "Tata Salt Iodised", "1 kg", "Grocery"),
    Product(34, "Sugar", "1 kg", "Grocery"),
    Product(35, "Tata Sampann Toor Dal", "1 kg", "Grocery"),
    Product(36, "Fortune Sunlite Sunflower Oil", "800 g", "Grocery"),
    Product(37, "Maggi Masala Noodles", "280 g", "Instant Food"),
    Product(38, "Tata Tea Gold", "500 g", "Beverages"),
    Product(39, "Harvest Gold Atta Bread", "450 g", "Bakery & Breakfast"),
    Product(40, "Catch Coriander Powder", "100 g", "Masala & Spices"),
    Product(41, "Tata Sampann Thick Poha", "500 g", "Bakery & Breakfast"),
    Product(42, "Tata Sampann Moong Dal", "1 kg", "Grocery"),
    Product(43, "Tata Sampann Turmeric Powder", "100 g", "Masala & Spices"),
    Product(44, "Haldiram's Aloo Bhujia", "200 g", "Snacks"),
]


def product_menu() -> str:
    return "\n".join(f"{p.id}. {p.name} — {p.unit}" for p in PRODUCTS)
