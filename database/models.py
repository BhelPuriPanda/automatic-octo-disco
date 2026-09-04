import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    Numeric
)
from sqlalchemy.orm import relationship
from database.connection import Base


class Product(Base):
    __tablename__ = "products"

    product_id = Column(String(50), primary_key=True, index=True)
    sku = Column(String(50), unique=True, index=True, nullable=False)
    product_name = Column(String(255), nullable=False)
    category = Column(String(100), index=True, nullable=False)
    unit_price = Column(Float, nullable=False)
    unit_cost = Column(Float, nullable=False)
    holding_cost_rate = Column(Float, default=0.20, nullable=False)  # Annual holding cost rate % of unit cost
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    sales = relationship("Sale", back_populates="product", cascade="all, delete-orphan")
    inventory = relationship("Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan")
    supplier_mappings = relationship("SupplierProduct", back_populates="product", cascade="all, delete-orphan")
    purchase_orders = relationship("PurchaseOrder", back_populates="product", cascade="all, delete-orphan")
    forecasts = relationship("Forecast", back_populates="product", cascade="all, delete-orphan")
    inventory_metrics = relationship("InventoryMetric", back_populates="product", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Product(id={self.product_id}, sku={self.sku}, name={self.product_name}, category={self.category})>"


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id = Column(String(50), primary_key=True, index=True)
    supplier_name = Column(String(255), nullable=False)
    contact_email = Column(String(255), nullable=True)
    lead_time_days = Column(Integer, nullable=False, default=7)       # Nominal lead time in days
    reliability_score = Column(Float, nullable=False, default=0.95)   # 0.0 to 1.0 (OTIF performance)
    defect_rate = Column(Float, nullable=False, default=0.01)         # 0.0 to 1.0
    ordering_cost = Column(Float, nullable=False, default=50.0)       # Fixed cost per order ($S for EOQ)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    product_mappings = relationship("SupplierProduct", back_populates="supplier", cascade="all, delete-orphan")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Supplier(id={self.supplier_id}, name={self.supplier_name}, lead_time={self.lead_time_days}d)>"


class SupplierProduct(Base):
    __tablename__ = "supplier_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(String(50), ForeignKey("suppliers.supplier_id"), nullable=False, index=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    lead_time_days = Column(Integer, nullable=False, default=7)
    unit_cost = Column(Float, nullable=False)
    min_order_qty = Column(Integer, nullable=False, default=10)

    # Relationships
    supplier = relationship("Supplier", back_populates="product_mappings")
    product = relationship("Product", back_populates="supplier_mappings")

    __table_args__ = (
        Index("ix_supplier_product", "supplier_id", "product_id", unique=True),
    )


class Sale(Base):
    __tablename__ = "sales"

    sale_id = Column(String(100), primary_key=True, index=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    sale_date = Column(DateTime, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_revenue = Column(Float, nullable=False)
    customer_id = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    channel = Column(String(50), nullable=True, default="Online")

    # Relationships
    product = relationship("Product", back_populates="sales")

    def __repr__(self):
        return f"<Sale(id={self.sale_id}, product={self.product_id}, date={self.sale_date}, qty={self.quantity})>"


class Inventory(Base):
    __tablename__ = "inventory"

    inventory_id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), unique=True, nullable=False, index=True)
    current_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)
    reorder_point = Column(Integer, nullable=True)
    safety_stock = Column(Integer, nullable=True)
    max_stock = Column(Integer, nullable=True)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    product = relationship("Product", back_populates="inventory")

    def __repr__(self):
        return f"<Inventory(product={self.product_id}, current_stock={self.current_stock}, ROP={self.reorder_point})>"


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    po_id = Column(String(50), primary_key=True, index=True)
    supplier_id = Column(String(50), ForeignKey("suppliers.supplier_id"), nullable=False, index=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    order_date = Column(DateTime, nullable=False, index=True)
    expected_delivery_date = Column(DateTime, nullable=False)
    actual_delivery_date = Column(DateTime, nullable=True)
    quantity_ordered = Column(Integer, nullable=False)
    quantity_received = Column(Integer, nullable=True)
    unit_cost = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)
    status = Column(String(50), nullable=False, default="Delivered")  # Delivered, In Transit, Pending, Cancelled
    defect_count = Column(Integer, nullable=False, default=0)
    is_on_time = Column(Boolean, nullable=True)
    is_in_full = Column(Boolean, nullable=True)

    # Relationships
    supplier = relationship("Supplier", back_populates="purchase_orders")
    product = relationship("Product", back_populates="purchase_orders")

    def __repr__(self):
        return f"<PurchaseOrder(po_id={self.po_id}, supplier={self.supplier_id}, product={self.product_id}, status={self.status})>"


class Forecast(Base):
    __tablename__ = "forecasts"

    forecast_id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    forecast_date = Column(DateTime, nullable=False, index=True)
    model_name = Column(String(100), nullable=False)  # 'Moving_Average', 'Exponential_Smoothing', 'Prophet', etc.
    predicted_demand = Column(Float, nullable=False)
    actual_demand = Column(Float, nullable=True)
    mae = Column(Float, nullable=True)
    rmse = Column(Float, nullable=True)
    mape = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    product = relationship("Product", back_populates="forecasts")


class InventoryMetric(Base):
    __tablename__ = "inventory_metrics"

    metric_id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    calculation_date = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    abc_classification = Column(String(1), nullable=True)             # 'A', 'B', 'C'
    annual_demand = Column(Float, nullable=True)                      # Units/year (D)
    daily_avg_demand = Column(Float, nullable=True)                   # Units/day (d_avg)
    demand_std_dev = Column(Float, nullable=True)                     # Standard deviation of daily demand (sigma_d)
    lead_time_days = Column(Float, nullable=True)                     # Effective lead time (L)
    safety_stock = Column(Float, nullable=True)                       # SS = Z * sigma_d * sqrt(L)
    reorder_point = Column(Float, nullable=True)                      # ROP = (d_avg * L) + SS
    economic_order_qty = Column(Float, nullable=True)                 # EOQ = sqrt(2 * D * S / H)
    stockout_risk_score = Column(Float, nullable=True)                # Risk index 0-100
    turnover_ratio = Column(Float, nullable=True)                     # COGS / Avg Inventory
    recommended_reorder_qty = Column(Float, nullable=True)

    # Relationships
    product = relationship("Product", back_populates="inventory_metrics")
