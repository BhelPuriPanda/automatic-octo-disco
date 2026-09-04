import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

# Add root directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import DATABASE_URL
from database.connection import get_engine
from inventory_optimization.formulas import InventoryFormulas
from inventory_optimization.optimizer import InventoryOptimizer
from replenishment_analytics.replenishment import ReplenishmentPlanner
from supplier_scorecard.engine import SupplierScorecardEngine
from data_pipeline.ingest import DataIngestionPipeline
from forecasting.engine import ForecastingEngine

app = FastAPI(
    title="SupplyChainIQ API",
    description="Supply Chain Planning, Demand Forecasting & Multi-Echelon Inventory Optimization Platform",
    version="1.0.0"
)

# Enable CORS for local testing & React frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DASHBOARD_DIR = BASE_DIR / "dashboard"
if not DASHBOARD_DIR.exists():
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)


class ServiceLevelOptimizationRequest(BaseModel):
    service_level: float = 0.95


@app.get("/api/overview")
def get_overview():
    """Returns high-level supply chain executive KPIs."""
    engine = get_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Total revenue & orders
        sales_summary = pd.read_sql("""
            SELECT COUNT(DISTINCT sale_id) as total_orders,
                   COALESCE(SUM(total_revenue), 0) as total_revenue,
                   COALESCE(SUM(quantity), 0) as total_units_sold
            FROM sales;
        """, conn).to_dict(orient="records")[0]

        # Inventory valuation & counts
        inv_summary = pd.read_sql("""
            SELECT COUNT(p.product_id) as total_skus,
                   COALESCE(SUM(i.current_stock * p.unit_cost), 0) as total_inventory_valuation,
                   COALESCE(SUM(CASE WHEN i.current_stock <= COALESCE(i.safety_stock, 0) THEN 1 ELSE 0 END), 0) as critical_stockout_count,
                   COALESCE(SUM(CASE WHEN i.current_stock <= COALESCE(i.reorder_point, 0) THEN 1 ELSE 0 END), 0) as reorder_needed_count
            FROM products p
            LEFT JOIN inventory i ON p.product_id = i.product_id;
        """, conn).to_dict(orient="records")[0]

        # Supplier OTIF average
        supplier_summary = pd.read_sql("""
            SELECT AVG(reliability_score) * 100.0 as avg_supplier_reliability_pct,
                   AVG(defect_rate) * 100.0 as avg_defect_rate_pct,
                   COUNT(supplier_id) as active_suppliers_count
            FROM suppliers;
        """, conn).to_dict(orient="records")[0]

        # Monthly Sales Trend
        monthly_trend = pd.read_sql("""
            SELECT strftime('%Y-%m', sale_date) as month,
                   SUM(total_revenue) as monthly_revenue,
                   SUM(quantity) as monthly_units
            FROM sales
            GROUP BY month
            ORDER BY month ASC;
        """, conn).to_dict(orient="records")

    engine.dispose()

    return {
        "kpi": {
            "total_revenue": round(float(sales_summary["total_revenue"]), 2),
            "total_orders": int(sales_summary["total_orders"]),
            "total_units_sold": int(sales_summary["total_units_sold"]),
            "total_skus": int(inv_summary["total_skus"]),
            "total_inventory_valuation": round(float(inv_summary["total_inventory_valuation"]), 2),
            "critical_stockout_count": int(inv_summary["critical_stockout_count"]),
            "reorder_needed_count": int(inv_summary["reorder_needed_count"]),
            "avg_supplier_reliability_pct": round(float(supplier_summary["avg_supplier_reliability_pct"] or 90.0), 1),
            "avg_defect_rate_pct": round(float(supplier_summary["avg_defect_rate_pct"] or 1.5), 2),
            "active_suppliers_count": int(supplier_summary["active_suppliers_count"])
        },
        "monthly_trend": monthly_trend
    }


@app.get("/api/products")
def get_products():
    """Returns catalog of products with prices, stock levels, ROP, SS, EOQ, ABC and Risk Score."""
    engine = get_engine(DATABASE_URL)
    with engine.connect() as conn:
        df = pd.read_sql("""
            SELECT p.product_id, p.sku, p.product_name, p.category, p.unit_price, p.unit_cost,
                   i.current_stock, i.reserved_stock, i.safety_stock, i.reorder_point, i.max_stock,
                   im.abc_classification, im.stockout_risk_score, im.turnover_ratio,
                   im.annual_demand, im.daily_avg_demand, im.economic_order_qty, im.recommended_reorder_qty,
                   s.supplier_name, s.lead_time_days
            FROM products p
            LEFT JOIN inventory i ON p.product_id = i.product_id
            LEFT JOIN inventory_metrics im ON p.product_id = im.product_id
            LEFT JOIN supplier_products sp ON p.product_id = sp.product_id
            LEFT JOIN suppliers s ON sp.supplier_id = s.supplier_id
            GROUP BY p.product_id
            ORDER BY im.stockout_risk_score DESC, p.product_id ASC;
        """, conn)
    engine.dispose()
    df = df.astype(object).where(pd.notna(df), None)
    return df.to_dict(orient="records")


@app.get("/api/forecasts/{product_id}")
def get_product_forecast(product_id: str):
    """Returns actual demand vs forecast history and forward 30-day predictions for a product."""
    engine = get_engine(DATABASE_URL)
    with engine.connect() as conn:
        prod = pd.read_sql(f"SELECT product_id, sku, product_name, category FROM products WHERE product_id = '{product_id}';", conn)
        if prod.empty:
            engine.dispose()
            raise HTTPException(status_code=404, detail="Product not found")

        forecasts_df = pd.read_sql(f"""
            SELECT DATE(forecast_date) as forecast_date, model_name,
                   predicted_demand, actual_demand, mae, rmse, mape
            FROM forecasts
            WHERE product_id = '{product_id}'
            ORDER BY forecast_date ASC;
        """, conn)

        # Recent 60 days historical sales
        sales_hist = pd.read_sql(f"""
            SELECT DATE(sale_date) as date, SUM(quantity) as qty
            FROM sales
            WHERE product_id = '{product_id}'
            GROUP BY DATE(sale_date)
            ORDER BY date ASC;
        """, conn)

    engine.dispose()

    # Convert NaN to None for JSON compliance
    forecasts_df = forecasts_df.astype(object).where(pd.notna(forecasts_df), None)
    sales_hist = sales_hist.astype(object).where(pd.notna(sales_hist), None)

    backtest = forecasts_df[forecasts_df["actual_demand"].notna()].to_dict(orient="records")
    future = forecasts_df[forecasts_df["actual_demand"].isna()].to_dict(orient="records")
    metrics = backtest[0] if backtest else {}

    return {
        "product": prod.to_dict(orient="records")[0],
        "metrics": {
            "model_name": metrics.get("model_name", "N/A"),
            "mae": metrics.get("mae", 0.0),
            "rmse": metrics.get("rmse", 0.0),
            "mape": metrics.get("mape", 0.0)
        },
        "sales_history": sales_hist.to_dict(orient="records"),
        "backtest_evaluation": backtest,
        "forward_forecast_30d": future
    }


@app.get("/api/inventory-matrix")
def get_inventory_matrix():
    """Returns ABC-XYZ breakdown and stock health distribution."""
    engine = get_engine(DATABASE_URL)
    with engine.connect() as conn:
        df = pd.read_sql("""
            SELECT p.product_id, p.sku, p.product_name, p.category,
                   im.abc_classification, im.stockout_risk_score,
                   i.current_stock, i.safety_stock, i.reorder_point,
                   CASE
                       WHEN i.current_stock <= 0 THEN 'CRITICAL STOCKOUT'
                       WHEN i.current_stock <= i.safety_stock THEN 'HIGH RISK (BELOW SS)'
                       WHEN i.current_stock <= i.reorder_point THEN 'REORDER NEEDED'
                       ELSE 'OPTIMAL BUFFER'
                   END as stock_status
            FROM products p
            LEFT JOIN inventory i ON p.product_id = i.product_id
            LEFT JOIN inventory_metrics im ON p.product_id = im.product_id;
        """, conn)
    engine.dispose()

    abc_counts = df["abc_classification"].value_counts().to_dict()
    status_counts = df["stock_status"].value_counts().to_dict()

    return {
        "abc_distribution": abc_counts,
        "status_distribution": status_counts,
        "items": df.to_dict(orient="records")
    }


@app.get("/api/replenishment")
def get_replenishment():
    """Returns active replenishment recommendations."""
    planner = ReplenishmentPlanner(DATABASE_URL)
    plan = planner.run_plan()
    recom_df = plan["replenishment_orders"]
    
    total_cost = float(recom_df["estimated_order_cost"].sum()) if not recom_df.empty else 0.0
    return {
        "total_replenishment_capital_required": round(total_cost, 2),
        "orders_count": len(recom_df),
        "orders": recom_df.to_dict(orient="records") if not recom_df.empty else []
    }


@app.get("/api/suppliers")
def get_suppliers():
    """Returns executive 4-pillar supplier performance scorecard and risk ratings."""
    scorer_engine = SupplierScorecardEngine(DATABASE_URL)
    scorecard_df = scorer_engine.generate_scorecard()
    return scorecard_df.to_dict(orient="records")


@app.post("/api/optimize")
def optimize_service_level(req: ServiceLevelOptimizationRequest):
    """Dynamically re-calculates safety stock, ROP, EOQ for a chosen service level (0.80 - 0.999)."""
    if not (0.70 <= req.service_level < 1.0):
        raise HTTPException(status_code=400, detail="Service level must be between 0.70 and 0.999")

    optimizer = InventoryOptimizer(DATABASE_URL, default_service_level=req.service_level)
    results_df = optimizer.optimize_all_products()

    # Also update replenishment plan
    planner = ReplenishmentPlanner(DATABASE_URL)
    planner.run_plan()

    z_val = InventoryFormulas.get_z_score(req.service_level)
    return {
        "message": f"Inventory policies updated successfully for Service Level = {req.service_level*100:.1f}% (Z={z_val:.3f})",
        "service_level": req.service_level,
        "z_score": round(z_val, 3),
        "policies": results_df.to_dict(orient="records")
    }


@app.post("/api/pipeline/run-all")
def run_all_pipeline():
    """Runs Phase 1 through Phase 5 sequentially."""
    try:
        # Phase 1
        ingest_p = DataIngestionPipeline(db_url=DATABASE_URL)
        ingest_p.run()

        # Phase 2
        forecast_p = ForecastingEngine(db_url=DATABASE_URL)
        forecast_p.execute_and_persist()

        # Phase 3
        inv_p = InventoryOptimizer(db_url=DATABASE_URL, default_service_level=0.95)
        inv_p.optimize_all_products()

        # Phase 4
        rep_p = ReplenishmentPlanner(db_url=DATABASE_URL)
        rep_p.run_plan()

        # Phase 5
        sup_p = SupplierScorecardEngine(db_url=DATABASE_URL)
        sup_p.generate_scorecard()

        return {"status": "success", "message": "All 5 supply chain phases executed and database refreshed successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve static frontend files
app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")

@app.get("/")
def serve_dashboard():
    return FileResponse(DASHBOARD_DIR / "index.html")
