import math
from typing import Dict, Optional
from scipy.stats import norm


class InventoryFormulas:
    """
    Core mathematical formulations for Supply Chain Inventory Optimization:
    1. Z-Score Lookup for Target Cycle Service Level (CSL)
    2. Safety Stock (SS) with Constant and Stochastic Lead Times
    3. Demand During Lead Time (DDLT)
    4. Reorder Point (ROP)
    5. Economic Order Quantity (EOQ - Wilson Formula)
    6. Total Annual Inventory Cost (TIC)
    7. Inventory Cycle Time & Order Frequency
    """

    @staticmethod
    def get_z_score(service_level: float = 0.95) -> float:
        """
        Returns the standard normal inverse Z-score for a given service level (e.g., 0.95 -> 1.6449).
        """
        if not 0.50 <= service_level < 1.0:
            raise ValueError(f"Service level must be between 0.50 and 0.999. Got: {service_level}")
        return float(norm.ppf(service_level))

    @staticmethod
    def calculate_safety_stock(
        daily_demand_std: float,
        lead_time_days: float,
        service_level: float = 0.95,
        lead_time_std: float = 0.0,
        daily_demand_mean: float = 0.0
    ) -> float:
        """
        Calculates Safety Stock (SS).
        - Constant Lead Time Formula: SS = Z * sigma_d * sqrt(L)
        - Stochastic Lead Time Formula: SS = Z * sqrt(L * sigma_d^2 + d_avg^2 * sigma_L^2)
        """
        z = InventoryFormulas.get_z_score(service_level)

        if lead_time_std > 0.0 and daily_demand_mean > 0.0:
            variance = (lead_time_days * (daily_demand_std ** 2)) + ((daily_demand_mean ** 2) * (lead_time_std ** 2))
            ss = z * math.sqrt(variance)
        else:
            ss = z * daily_demand_std * math.sqrt(lead_time_days)

        return max(ss, 0.0)

    @staticmethod
    def calculate_reorder_point(
        daily_demand_mean: float,
        lead_time_days: float,
        safety_stock: float
    ) -> float:
        """
        Reorder Point (ROP) = Demand during Lead Time (DDLT) + Safety Stock (SS)
        ROP = (d_avg * L) + SS
        """
        ddlt = daily_demand_mean * lead_time_days
        return max(ddlt + safety_stock, 0.0)

    @staticmethod
    def calculate_eoq(
        annual_demand: float,
        ordering_cost_s: float,
        unit_cost: float,
        holding_cost_rate_h: float = 0.20
    ) -> Dict[str, float]:
        """
        Calculates Economic Order Quantity (EOQ):
        EOQ = sqrt((2 * D * S) / H)
        where:
        - D = Annual Demand (units)
        - S = Fixed Ordering Cost per purchase order ($)
        - H = Annual Unit Holding Cost ($) = unit_cost * holding_cost_rate
        """
        annual_holding_cost_per_unit = unit_cost * holding_cost_rate_h
        if annual_holding_cost_per_unit <= 0 or annual_demand <= 0 or ordering_cost_s <= 0:
            return {
                "eoq": max(annual_demand / 12.0, 10.0),
                "annual_ordering_cost": 0.0,
                "annual_holding_cost": 0.0,
                "total_annual_inventory_cost": 0.0,
                "orders_per_year": 0.0,
                "cycle_time_days": 0.0
            }

        eoq = math.sqrt((2.0 * annual_demand * ordering_cost_s) / annual_holding_cost_per_unit)
        
        # Financial breakdowns
        orders_per_year = annual_demand / eoq
        annual_ordering_cost = orders_per_year * ordering_cost_s
        annual_holding_cost = (eoq / 2.0) * annual_holding_cost_per_unit
        total_cost = annual_ordering_cost + annual_holding_cost
        cycle_time_days = 365.0 / orders_per_year if orders_per_year > 0 else 0.0

        return {
            "eoq": round(eoq, 2),
            "annual_ordering_cost": round(annual_ordering_cost, 2),
            "annual_holding_cost": round(annual_holding_cost, 2),
            "total_annual_inventory_cost": round(total_cost, 2),
            "orders_per_year": round(orders_per_year, 2),
            "cycle_time_days": round(cycle_time_days, 1)
        }
