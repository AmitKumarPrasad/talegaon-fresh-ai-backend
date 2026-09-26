from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    unit: str


PRODUCTS = [
    Product(1, "Tomato", "1 kg"), Product(2, "Potato", "1 kg"),
    Product(3, "Onion", "1 kg"), Product(4, "Carrot", "500 g"),
    Product(5, "Capsicum", "500 g"), Product(6, "Cabbage", "1 pc"),
    Product(7, "Cauliflower", "1 pc"), Product(8, "Ladyfinger", "500 g"),
    Product(9, "Green Beans", "500 g"), Product(10, "Spinach", "1 bunch"),
    Product(11, "Coriander", "1 bunch"), Product(12, "Green Chilli", "250 g"),
    Product(13, "Ginger", "250 g"), Product(14, "Garlic", "250 g"),
    Product(15, "Banana", "1 dozen"), Product(16, "Apple", "1 kg"),
    Product(17, "Orange", "1 kg"), Product(18, "Grapes", "500 g"),
    Product(19, "Pomegranate", "1 kg"), Product(20, "Papaya", "1 pc"),
]


def product_menu() -> str:
    return "\n".join(f"{p.id}. {p.name} — {p.unit}" for p in PRODUCTS)
