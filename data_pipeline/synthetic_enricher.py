import datetime
import random
import logging
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Realistic supplier templates
SUPPLIER_PROFILES = [
    {
        "supplier_id": "SUP-001",
        "supplier_name": "Apex Global Ingredients & FMCG",
        "contact_email": "orders@apexsupply.com",
        "lead_time_days": 7,
        "reliability_score": 0.96,
        "defect_rate": 0.012,
        "ordering_cost": 75.0,
        "categories": ["Beverages", "Snacks", "Dry Grocery"]
    },
    {
        "supplier_id": "SUP-002",
        "supplier_name": "Beacon Prime Distribution",
        "contact_email": "logistics@beaconprime.com",
        "lead_time_days": 14,
        "reliability_score": 0.91,
        "defect_rate": 0.025,
        "ordering_cost": 50.0,
        "categories": ["Household", "Personal Care"]
    },
    {
        "supplier_id": "SUP-003",
        "supplier_name": "Cascade Fresh & Cold Chain",
        "contact_email": "fulfillment@cascadegoods.com",
        "lead_time_days": 5,
        "reliability_score": 0.98,
        "defect_rate": 0.008,
        "ordering_cost": 120.0,
        "categories": ["Beverages", "Frozen Foods"]
    },
    {
        "supplier_id": "SUP-004",
        "supplier_name": "Delta Direct Wholesale",
        "contact_email": "sales@deltadirect.com",
        "lead_time_days": 10,
        "reliability_score": 0.89,
        "defect_rate": 0.031,
        "ordering_cost": 60.0,
        "categories": ["Dry Grocery", "Snacks", "General Merchandise"]
    },
    {
        "supplier_id": "SUP-005",
        "supplier_name": "Evergreen Eco Packaged Goods",
        "contact_email": "b2b@evergreeneco.com",
        "lead_time_days": 8,
        "reliability_score": 0.94,
        "defect_rate": 0.015,
        "ordering_cost": 85.0,
        "categories": ["Household", "Personal Care", "Snacks"]
    }
]

CATEGORY_RULES = {
    "BEV": "Beverages",
    "SNK": "Snacks",
    "DRY": "Dry Grocery",
    "PER": "Personal Care",
    "HOU": "Household",
    "FRZ": "Frozen Foods",
}


class SyntheticEnricher:
    """
    Enriches raw sales data with realistic supply chain attributes:
    1. Products master (categories, unit costs, holding cost rate)
    2. Suppliers master (lead times, defect rates, ordering costs, reliability)
    3. Supplier-Product catalog mappings (costs, MOQs)
    4. Inventory snapshots (current stock, reserved stock)
    5. Historical purchase orders (order dates, actual deliveries, defect counts, OTIF flags)
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        np.random.seed(seed)

    def infer_category(self, sku: str, name: str) -> str:
        for prefix, cat in CATEGORY_RULES.items():
            if prefix in sku.upper():
                return cat
        name_lower = name.lower()
        if any(w in name_lower for w in ["coffee", "tea", "water", "juice", "drink"]):
            return "Beverages"
        elif any(w in name_lower for w in ["chip", "nut", "snack", "chocolate", "cookie"]):
            return "Snacks"
        elif any(w in name_lower for w in ["rice", "oil", "pasta", "flour", "sugar"]):
            return "Dry Grocery"
        elif any(w in name_lower for w in ["soap", "cleanser", "shampoo", "cream"]):
            return "Personal Care"
        elif any(w in name_lower for w in ["wipe", "liquid", "clean", "towel", "bag"]):
            return "Household"
        elif any(w in name_lower for w in ["frozen", "ice", "berry"]):
            return "Frozen Foods"
        return "General Merchandise"

    def enrich(self, clean_sales_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        logger.info("Starting supply chain synthetic enrichment...")
        sales_df = clean_sales_df.copy()

        # -----------------------------------------------------------------
        # 1. GENERATE PRODUCTS
        # -----------------------------------------------------------------
        sku_summary = (
            sales_df.groupby("sku")
            .agg(
                product_name=("product_name", lambda s: s.mode().iloc[0] if not s.empty else "Item"),
                median_price=("unit_price", "median"),
                min_price=("unit_price", "min"),
                total_qty=("quantity", "sum")
            )
            .reset_index()
        )

        products = []
        for idx, row in sku_summary.iterrows():
            prod_id = f"PROD-{idx+1:04d}"
            sku = row["sku"]
            name = row["product_name"]
            category = self.infer_category(sku, name)
            price = round(float(row["median_price"]), 2)
            
            # Unit cost roughly 55% to 68% of sales price (realistic gross margin 32% - 45%)
            cost_margin_pct = random.uniform(0.55, 0.68)
            unit_cost = round(max(price * cost_margin_pct, 0.50), 2)
            holding_cost_rate = 0.20  # 20% annual inventory holding cost

            products.append({
                "product_id": prod_id,
                "sku": sku,
                "product_name": name,
                "category": category,
                "unit_price": price,
                "unit_cost": unit_cost,
                "holding_cost_rate": holding_cost_rate,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            })

        products_df = pd.DataFrame(products)
        sku_to_prod_id = dict(zip(products_df["sku"], products_df["product_id"]))
        sku_to_cost = dict(zip(products_df["sku"], products_df["unit_cost"]))

        # Map product_id into sales_df
        sales_df["product_id"] = sales_df["sku"].map(sku_to_prod_id)

        # -----------------------------------------------------------------
        # 2. GENERATE SUPPLIERS
        # -----------------------------------------------------------------
        suppliers_df = pd.DataFrame([
            {
                "supplier_id": s["supplier_id"],
                "supplier_name": s["supplier_name"],
                "contact_email": s["contact_email"],
                "lead_time_days": s["lead_time_days"],
                "reliability_score": s["reliability_score"],
                "defect_rate": s["defect_rate"],
                "ordering_cost": s["ordering_cost"],
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }
            for s in SUPPLIER_PROFILES
        ])

        # -----------------------------------------------------------------
        # 3. GENERATE SUPPLIER_PRODUCTS (Mapping)
        # -----------------------------------------------------------------
        supplier_products = []
        for _, prod in products_df.iterrows():
            # Find eligible suppliers matching product category or fallback to all
            eligible_sups = [
                s for s in SUPPLIER_PROFILES if prod["category"] in s.get("categories", [])
            ]
            if not eligible_sups:
                eligible_sups = SUPPLIER_PROFILES

            # Pick primary supplier (and 50% chance of secondary supplier)
            assigned_sups = random.sample(eligible_sups, min(len(eligible_sups), random.choice([1, 2])))
            for sup in assigned_sups:
                sup_lead_time = int(max(sup["lead_time_days"] + random.randint(-2, 3), 3))
                sup_cost = round(prod["unit_cost"] * random.uniform(0.95, 1.05), 2)
                moq = random.choice([10, 25, 50, 100])
                
                supplier_products.append({
                    "supplier_id": sup["supplier_id"],
                    "product_id": prod["product_id"],
                    "lead_time_days": sup_lead_time,
                    "unit_cost": sup_cost,
                    "min_order_qty": moq
                })

        supplier_products_df = pd.DataFrame(supplier_products)

        # -----------------------------------------------------------------
        # 4. GENERATE PURCHASE ORDERS (Historical PO Ledger)
        # -----------------------------------------------------------------
        purchase_orders = []
        po_counter = 1001

        min_date = sales_df["sale_date"].min()
        max_date = sales_df["sale_date"].max()

        # If dates are single day or span < 30 days, expand window back 180 days for realistic PO history
        if pd.isna(min_date) or pd.isna(max_date) or (max_date - min_date).days < 30:
            end_anchor = max_date if pd.notna(max_date) else datetime.datetime.now(datetime.timezone.utc)
            start_anchor = end_anchor - datetime.timedelta(days=180)
        else:
            start_anchor = min_date
            end_anchor = max_date

        for _, prod in products_df.iterrows():
            prod_id = prod["product_id"]
            sup_links = supplier_products_df[supplier_products_df["product_id"] == prod_id]
            if sup_links.empty:
                continue
            
            primary_link = sup_links.iloc[0]
            sup_id = primary_link["supplier_id"]
            lead_time = int(primary_link["lead_time_days"])
            unit_cost = float(primary_link["unit_cost"])
            
            sup_prof = next(s for s in SUPPLIER_PROFILES if s["supplier_id"] == sup_id)
            reliability = sup_prof["reliability_score"]
            defect_rate = sup_prof["defect_rate"]

            cur_date = start_anchor
            while cur_date < end_anchor:
                order_date = cur_date + datetime.timedelta(days=random.randint(1, 10))
                if order_date > end_anchor:
                    break

                expected_delivery = order_date + datetime.timedelta(days=lead_time)
                qty_ordered = random.choice([50, 100, 150, 200, 300])

                is_on_time = random.random() < reliability
                if is_on_time:
                    actual_delivery = expected_delivery + datetime.timedelta(days=random.choice([-1, 0]))
                else:
                    delay_days = random.randint(1, 6)
                    actual_delivery = expected_delivery + datetime.timedelta(days=delay_days)

                if actual_delivery > end_anchor:
                    status = "In Transit"
                    actual_delivery_date = None
                    qty_received = None
                    defect_count = 0
                    is_on_time_val = None
                    is_in_full_val = None
                else:
                    status = "Delivered"
                    actual_delivery_date = actual_delivery
                    is_in_full = random.random() < 0.95
                    qty_received = qty_ordered if is_in_full else int(qty_ordered * random.uniform(0.8, 0.95))
                    
                    expected_defects = int(np.random.poisson(lam=qty_received * defect_rate))
                    defect_count = min(expected_defects, qty_received)
                    is_on_time_val = bool(actual_delivery <= expected_delivery)
                    is_in_full_val = bool(qty_received >= qty_ordered)

                po_id = f"PO-{po_counter}"
                po_counter += 1

                purchase_orders.append({
                    "po_id": po_id,
                    "supplier_id": sup_id,
                    "product_id": prod_id,
                    "order_date": order_date,
                    "expected_delivery_date": expected_delivery,
                    "actual_delivery_date": actual_delivery_date,
                    "quantity_ordered": qty_ordered,
                    "quantity_received": qty_received,
                    "unit_cost": unit_cost,
                    "total_cost": round(qty_ordered * unit_cost, 2),
                    "status": status,
                    "defect_count": defect_count,
                    "is_on_time": is_on_time_val,
                    "is_in_full": is_in_full_val
                })

                cur_date = cur_date + datetime.timedelta(days=random.randint(14, 25))

        po_columns = [
            "po_id", "supplier_id", "product_id", "order_date", "expected_delivery_date",
            "actual_delivery_date", "quantity_ordered", "quantity_received", "unit_cost",
            "total_cost", "status", "defect_count", "is_on_time", "is_in_full"
        ]
        purchase_orders_df = pd.DataFrame(purchase_orders, columns=po_columns)

        # -----------------------------------------------------------------
        # 5. GENERATE CURRENT INVENTORY SNAPSHOT
        # -----------------------------------------------------------------
        inventory = []
        for idx, prod in products_df.iterrows():
            prod_id = prod["product_id"]
            prod_sales = sales_df[sales_df["product_id"] == prod_id]
            avg_daily_demand = prod_sales["quantity"].sum() / max((max_date - min_date).days, 1)

            sup_link = supplier_products_df[supplier_products_df["product_id"] == prod_id]
            lt = sup_link.iloc[0]["lead_time_days"] if not sup_link.empty else 7
            safety_stock = int(avg_daily_demand * 1.65 * np.sqrt(lt)) + 5
            reorder_point = int((avg_daily_demand * lt) + safety_stock)
            max_stock = reorder_point * 2

            # Realistic operational distribution:
            # - First 2 SKUs: Low stock below Safety Stock (Critical Stockout Alert)
            # - Next 3 SKUs: Stock below ROP (Standard Replenishment Trigger)
            # - Remaining SKUs: Healthy stock buffer
            if idx in (0, 1):
                current_stock = max(int(safety_stock * random.uniform(0.4, 0.8)), 5)
            elif idx in (2, 3, 4):
                current_stock = max(int(safety_stock + (reorder_point - safety_stock) * random.uniform(0.2, 0.7)), safety_stock + 1)
            else:
                current_stock = int(max(reorder_point + avg_daily_demand * random.uniform(10, 25), reorder_point + 15))

            reserved_stock = max(int(current_stock * random.uniform(0.05, 0.15)), 1)

            inventory.append({
                "product_id": prod_id,
                "current_stock": current_stock,
                "reserved_stock": reserved_stock,
                "reorder_point": reorder_point,
                "safety_stock": safety_stock,
                "max_stock": max_stock,
                "last_updated": datetime.datetime.now(datetime.timezone.utc)
            })

        inventory_df = pd.DataFrame(inventory)

        # Select canonical columns for sales_df
        clean_sales_final = sales_df[[
            "sale_id",
            "product_id",
            "sale_date",
            "quantity",
            "unit_price",
            "total_revenue",
            "customer_id",
            "country"
        ]].copy()
        clean_sales_final["channel"] = "Online"

        logger.info(f"Enrichment completed: {len(products_df)} products, {len(suppliers_df)} suppliers, {len(purchase_orders_df)} POs, {len(clean_sales_final)} sales.")

        return {
            "products": products_df,
            "suppliers": suppliers_df,
            "supplier_products": supplier_products_df,
            "sales": clean_sales_final,
            "inventory": inventory_df,
            "purchase_orders": purchase_orders_df
        }
