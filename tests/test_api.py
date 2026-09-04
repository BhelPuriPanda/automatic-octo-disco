import unittest
from fastapi.testclient import TestClient
from api.main import app


class TestFastAPIDashboard(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_get_overview(self):
        response = self.client.get("/api/overview")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("kpi", data)
        self.assertIn("total_revenue", data["kpi"])
        self.assertIn("monthly_trend", data)

    def test_get_products(self):
        response = self.client.get("/api/products")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("sku", data[0])
        self.assertIn("current_stock", data[0])

    def test_get_inventory_matrix(self):
        response = self.client.get("/api/inventory-matrix")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("abc_distribution", data)
        self.assertIn("status_distribution", data)

    def test_get_replenishment(self):
        response = self.client.get("/api/replenishment")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_replenishment_capital_required", data)
        self.assertIn("orders", data)

    def test_get_suppliers(self):
        response = self.client.get("/api/suppliers")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("composite_score", data[0])

    def test_post_optimize_service_level(self):
        response = self.client.post("/api/optimize", json={"service_level": 0.98})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["service_level"], 0.98)
        self.assertIn("z_score", data)

    def test_serve_dashboard_html(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SupplyChainIQ", response.text)


if __name__ == "__main__":
    unittest.main()
