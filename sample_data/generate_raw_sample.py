"""
Generates realistic raw retail transaction data resembling public datasets (like UCI Online Retail II / Kaggle).
Includes intentional real-world anomalies:
- Missing descriptions and CustomerIDs
- Returns / negative quantities (cancellations prefixed with 'C')
- Outlier spikes in quantity / price
- Mixed timestamp formats
- Zero price entries
"""

import os
from pathlib import Path
import random
import numpy as np
import pandas as pd

# FMCG / Retail Categories and SKUs
SAMPLE_CATALOG = [
    {"sku": "SKU-BEV-001", "name": "Cold Brew Coffee 250ml", "category": "Beverages", "base_price": 3.99},
    {"sku": "SKU-BEV-002", "name": "Organic Green Tea 500ml", "category": "Beverages", "base_price": 2.49},
    {"sku": "SKU-BEV-003", "name": "Sparkling Mineral Water 1L", "category": "Beverages", "base_price": 1.79},
    {"sku": "SKU-SNK-001", "name": "Artisan Sea Salt Potato Chips 150g", "category": "Snacks", "base_price": 2.99},
    {"sku": "SKU-SNK-002", "name": "Roasted Almonds & Cranberry Mix 200g", "category": "Snacks", "base_price": 5.49},
    {"sku": "SKU-SNK-003", "name": "Dark Chocolate 70% Bar 100g", "category": "Snacks", "base_price": 3.29},
    {"sku": "SKU-DRY-001", "name": "Basmati Long Grain Rice 5kg", "category": "Dry Grocery", "base_price": 12.99},
    {"sku": "SKU-DRY-002", "name": "Extra Virgin Olive Oil 750ml", "category": "Dry Grocery", "base_price": 14.50},
    {"sku": "SKU-DRY-003", "name": "Whole Grain Pasta 500g", "category": "Dry Grocery", "base_price": 2.19},
    {"sku": "SKU-PER-001", "name": "Antibacterial Hand Soap 300ml", "category": "Personal Care", "base_price": 4.25},
    {"sku": "SKU-PER-002", "name": "Moisturizing Face Cleanser 150ml", "category": "Personal Care", "base_price": 9.99},
    {"sku": "SKU-HOU-001", "name": "Eco-Friendly Dishwashing Liquid 1L", "category": "Household", "base_price": 3.89},
    {"sku": "SKU-HOU-002", "name": "Multi-Surface Disinfectant Wipes 80ct", "category": "Household", "base_price": 4.99},
    {"sku": "SKU-HOU-003", "name": "Microfiber Cleaning Towels 4-Pack", "category": "Household", "base_price": 6.50},
    {"sku": "SKU-FRZ-001", "name": "Frozen Organic Mixed Berries 400g", "category": "Frozen Foods", "base_price": 4.79},
]

REGIONS = ["United States", "United Kingdom", "Germany", "Canada", "Australia", "France"]


def generate_raw_retail_csv(output_path: str = "sample_data/raw_retail_sales.csv", num_records: int = 5000, seed: int = 42):
    np.random.seed(seed)
    random.seed(seed)
    
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    date_range = pd.date_range(start="2024-01-01", end="2024-12-31", freq="h")
    
    records = []
    invoice_seq = 100000

    for i in range(num_records):
        item = random.choice(SAMPLE_CATALOG)
        sku = item["sku"]
        name = item["name"]
        base_price = item["base_price"]
        
        # Date with varying string formats
        raw_dt = random.choice(date_range)
        date_format = random.choice([
            "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%d-%m-%Y %H:%M",
            "%Y/%m/%d"
        ])
        invoice_date_str = raw_dt.strftime(date_format)

        # Quantity: Poisson/LogNormal demand with anomalies
        qty = int(np.random.poisson(lam=4) + 1)
        
        # 3% chance of cancellation / return
        is_return = random.random() < 0.03
        invoice_no = f"C{invoice_seq + (i // 3)}" if is_return else str(invoice_seq + (i // 3))
        if is_return:
            qty = -qty
            
        # 0.5% extreme outlier
        if random.random() < 0.005:
            qty = random.choice([500, 1000, -2000, 0])

        # Price variations (discounts, rounding errors, rare zero/outlier price)
        price = round(base_price * random.uniform(0.85, 1.15), 2)
        if random.random() < 0.01:
            price = 0.00  # free sample / system error
        elif random.random() < 0.002:
            price = round(base_price * 100, 2)  # data entry typo

        # Customer ID with 8% missing values
        cust_id = f"CUST-{random.randint(1000, 1500)}" if random.random() > 0.08 else ""

        # Description with 2% missing values
        desc = name if random.random() > 0.02 else ""

        country = random.choice(REGIONS)

        records.append({
            "InvoiceNo": invoice_no,
            "StockCode": sku if random.random() > 0.01 else "  " + sku + "  ",  # dirty whitespace
            "Description": desc,
            "Quantity": qty,
            "InvoiceDate": invoice_date_str,
            "UnitPrice": price,
            "CustomerID": cust_id,
            "Country": country
        })

    df = pd.DataFrame(records)
    df.to_csv(out_file, index=False)
    print(f"Generated {len(df)} raw retail records -> {out_file.resolve()}")
    return out_file


if __name__ == "__main__":
    generate_raw_retail_csv()
