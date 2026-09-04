import unittest
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np

from database.models import Base
from data_pipeline.schema_validation import RawDataValidator
from data_pipeline.cleaner import DataCleaner
from data_pipeline.synthetic_enricher import SyntheticEnricher
from data_pipeline.ingest import DataIngestionPipeline


class TestSupplyChainPipeline(unittest.TestCase):

    def setUp(self):
        self.sample_raw_df = pd.DataFrame({
            "InvoiceNo": ["536365", "536365", "C536366", "536367", "536368"],
            "StockCode": ["85123A", " 71053 ", "84406B", "84029G", "84029E"],
            "Description": ["WHITE HANGING HEART", None, "RED WOOLLY HOTTIE", "KNITTED UNION FLAG", "FELTCRAFT PRINCESS"],
            "Quantity": [6, 10000, -2, 4, 3],  # includes outlier (10000) and cancellation (-2)
            "InvoiceDate": ["12/1/2023 8:26", "2023-12-01 08:30:00", "01-12-2023 09:00", "2023/12/01", "2023-12-01"],
            "UnitPrice": [2.55, 3.39, 2.75, 0.00, 4.25],  # includes zero price
            "CustomerID": ["17850", None, "17850", "13047", "12583"],
            "Country": ["United Kingdom", "United Kingdom", "United Kingdom", "United Kingdom", None]
        })

    def test_schema_validator(self):
        validator = RawDataValidator(self.sample_raw_df)
        is_valid, mapped_df, report = validator.validate()

        self.assertTrue(is_valid)
        self.assertIn("invoice_id", mapped_df.columns)
        self.assertIn("sku", mapped_df.columns)
        self.assertIn("unit_price", mapped_df.columns)
        self.assertIn("quantity", mapped_df.columns)

    def test_data_cleaner(self):
        validator = RawDataValidator(self.sample_raw_df)
        _, mapped_df, _ = validator.validate()

        cleaner = DataCleaner(mapped_df)
        clean_df, stats = cleaner.clean()

        # Returns / cancellations filtered
        self.assertTrue((clean_df["quantity"] > 0).all())
        # Zero / negative prices filtered
        self.assertTrue((clean_df["unit_price"] > 0).all())
        # No null SKU or dates
        self.assertEqual(clean_df["sku"].isna().sum(), 0)
        self.assertEqual(clean_df["sale_date"].isna().sum(), 0)
        # Derived financial columns exist
        self.assertIn("total_revenue", clean_df.columns)
        self.assertIn("sale_id", clean_df.columns)

    def test_synthetic_enrichment(self):
        validator = RawDataValidator(self.sample_raw_df)
        _, mapped_df, _ = validator.validate()
        cleaner = DataCleaner(mapped_df)
        clean_df, _ = cleaner.clean()

        enricher = SyntheticEnricher(seed=42)
        tables = enricher.enrich(clean_df)

        self.assertIn("products", tables)
        self.assertIn("suppliers", tables)
        self.assertIn("supplier_products", tables)
        self.assertIn("sales", tables)
        self.assertIn("inventory", tables)
        self.assertIn("purchase_orders", tables)

        # Check primary and foreign key integrity
        prod_ids = set(tables["products"]["product_id"])
        self.assertTrue(set(tables["sales"]["product_id"]).issubset(prod_ids))
        self.assertTrue(set(tables["inventory"]["product_id"]).issubset(prod_ids))

        sup_ids = set(tables["suppliers"]["supplier_id"])
        self.assertTrue(set(tables["supplier_products"]["supplier_id"]).issubset(sup_ids))
        self.assertTrue(set(tables["purchase_orders"]["supplier_id"]).issubset(sup_ids))

    def test_end_to_end_in_memory_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test_raw.csv"
            self.sample_raw_df.to_csv(csv_file, index=False)

            test_db_url = f"sqlite:///{Path(tmpdir) / 'test_sc_iq.db'}"
            pipeline = DataIngestionPipeline(raw_csv_path=str(csv_file), db_url=test_db_url)
            counts = pipeline.run()

            self.assertGreater(counts["products"], 0)
            self.assertGreater(counts["suppliers"], 0)
            self.assertGreater(counts["sales"], 0)
            self.assertGreater(counts["inventory"], 0)
            self.assertGreater(counts["purchase_orders"], 0)


if __name__ == "__main__":
    unittest.main()
