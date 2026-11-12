import re
from typing import Dict, List, Any


class CategoryMapper:
    """
    Maps granular Leafnet POS categories into clean marketing segment buckets
    (gummies, beverages, flower, pre-rolls, concentrates, vapes, edibles, accessories)
    and generates product category recommendations for Goal 5 & Goal 6.
    """

    BUCKET_RULES: List[tuple[str, List[str]]] = [
        ("gummies", ["gumm", "bites", "sucker", "chew"]),
        ("beverages", ["drink", "bev", "seltzer", "soda", "water", "tea", "lemonade", "coffee"]),
        ("pre-rolls", ["pre-roll", "preroll", " pr", "hash hole", "dope cone", "blunt"]),
        ("vapes", ["cart", "dispo", "vape", "1ml", "2ml", "pod", "battery"]),
        ("flower", ["bag", "3.5g", "14g", "28g", "1g", "7g", "flower", "bud", "eighth", "quarter", "ounce"]),
        ("concentrates", ["dab", "concentrate", "rosin", "wax", "shatter", "badder", "resin", "hash"]),
        ("edibles", ["chocolate", "cookie", "treat", "brownie", "bakery", "bistro", "snack", "honey", "syrup"]),
        ("tinctures-topicals", ["tincture", "balm", "topical", "lotion", "salve", "capsule", "oil"]),
        (
            "accessories",
            [
                "torch",
                "lighter",
                "puffco",
                "pipe",
                "glass",
                "grinder",
                "jar",
                "slick",
                "banger",
                "bowl",
                "carb cap",
                "pearl",
                "tray",
                "scale",
                "wrap",
                "blazy",
                "swisher",
                "white owl",
                "backwood",
                "looseleaf",
                "zig zag",
                "apparel",
                "merch",
                "accessory",
                "accessories",
            ],
        ),
    ]

    RECOMMENDATION_MAP: Dict[str, Dict[str, Any]] = {
        "gummies": {
            "recommended_bucket": "beverages",
            "headline": "Love our Gummies? Try our Infused Canned Drinks!",
            "suggested_categories": ["Canned Drinks", "Snapdragon Gummies", "Chocolate Bars"],
        },
        "beverages": {
            "recommended_bucket": "gummies",
            "headline": "Refreshing Sip! Pair it with NANO Fast-Acting Gummies",
            "suggested_categories": ["Snapdragon Gummies", "Canned Drinks", "Drink Additives"],
        },
        "flower": {
            "recommended_bucket": "pre-rolls",
            "headline": "Top-Shelf Flower Fan? Check out our Connoisseur & Hash Hole Pre-Rolls",
            "suggested_categories": ["Connoisseur PR", "Hash Holes PR", "Dragon's Cut Bags - 3.5g"],
        },
        "pre-rolls": {
            "recommended_bucket": "flower",
            "headline": "Ready when you are! Explore our Craft Reserve & Dragon's Cut Flower Bags",
            "suggested_categories": ["Dragon's Cut Bags - 3.5g", "Connoisseur Bags - 3.5g", "Lighters & Torches"],
        },
        "concentrates": {
            "recommended_bucket": "vapes",
            "headline": "Potent & Pure: Explore Live Rosin & THCA Carts for On-The-Go",
            "suggested_categories": ["Rosin", "Live Resin Cartridges", "Puffco"],
        },
        "vapes": {
            "recommended_bucket": "concentrates",
            "headline": "Smooth Draws: Try our House Concentrates & Solventless Rosin",
            "suggested_categories": ["Live Resin Cartridges", "THCA 2ml Dispo", "Rosin"],
        },
        "edibles": {
            "recommended_bucket": "gummies",
            "headline": "Sweet Tooth? Discover our Best-Selling Snapdragon Gummies & Drinks",
            "suggested_categories": ["Snapdragon Gummies", "Canned Drinks", "Chocolate Bars"],
        },
        "tinctures-topicals": {
            "recommended_bucket": "gummies",
            "headline": "Daily Wellness: Explore NANO Gummies & Infused Beverages",
            "suggested_categories": ["TINCTURES", "Snapdragon Gummies", "Canned Drinks"],
        },
        "accessories": {
            "recommended_bucket": "flower",
            "headline": "Gear Up! Pair your new setup with Craft Flower or Concentrates",
            "suggested_categories": ["Dragon's Cut Bags - 3.5g", "House Concentrates", "CR 1g Pre-Rolls"],
        },
        "general": {
            "recommended_bucket": "gummies",
            "headline": "Customer Favorites: Snapdragon Gummies, Infused Drinks & Top-Shelf Flower",
            "suggested_categories": ["Snapdragon Gummies", "Canned Drinks", "Dragon's Cut Bags - 3.5g"],
        },
    }

    @classmethod
    def normalize_bucket(cls, raw_category: str) -> str:
        """Maps a raw Leafnet category name to a high-level segment bucket."""
        if not raw_category:
            return "general"
        low = raw_category.strip().lower()
        for bucket, keywords in cls.BUCKET_RULES:
            for kw in keywords:
                if kw in low:
                    return bucket
        return "general"

    @classmethod
    def slugify_category(cls, raw_category: str) -> str:
        """Creates a clean tag-safe slug from a raw category name."""
        if not raw_category:
            return "general"
        slug = re.sub(r"[^a-z0-9]+", "-", raw_category.strip().lower()).strip("-")
        return slug or "general"

    @classmethod
    def get_recommendations(cls, raw_categories: List[str]) -> Dict[str, Any]:
        """
        Given a list of purchased categories from an order, returns the primary bucket,
        all normalized buckets, and product recommendation metadata for Omnisend emails.
        """
        buckets: List[str] = []
        for cat in raw_categories:
            b = cls.normalize_bucket(cat)
            if b not in buckets:
                buckets.append(b)

        primary_bucket = buckets[0] if buckets else "general"
        rec = cls.RECOMMENDATION_MAP.get(primary_bucket, cls.RECOMMENDATION_MAP["general"])

        return {
            "primary_bucket": primary_bucket,
            "all_buckets": buckets,
            "recommended_bucket": rec["recommended_bucket"],
            "recommendation_headline": rec["headline"],
            "suggested_categories": rec["suggested_categories"],
        }
