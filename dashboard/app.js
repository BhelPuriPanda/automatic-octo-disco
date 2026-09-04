/**
 * SupplyChainIQ — Frontend Dashboard Controller
 */

let monthlyChart = null;
let abcChart = null;
let forecastChart = null;
let allProducts = [];

document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initEventListeners();
    loadDashboardData();
});

function initNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanes = document.querySelectorAll(".tab-pane");

    const pageMeta = {
        overview: { title: "Executive Supply Chain Overview", desc: "Real-time demand, multi-echelon stock health & vendor reliability KPIs" },
        forecasting: { title: "Time-Series Demand Forecasting", desc: "Benchmark moving averages against single/double exponential smoothing models" },
        inventory: { title: "Multi-Echelon Inventory Policies & EOQ", desc: "Safety stock math, dynamic service level simulator & order frequency breakdown" },
        replenishment: { title: "Automated Replenishment Recommendations", desc: "Purchase order suggestions with MOQ constraints for SKUs at/below Reorder Point" },
        suppliers: { title: "Supplier Performance Scorecards", desc: "4-Pillar composite vendor ranking: 40% OTIF, 30% Lead Time, 20% Quality, 10% Cost" }
    };

    navItems.forEach(btn => {
        btn.addEventListener("click", () => {
            const target = btn.dataset.tab;
            navItems.forEach(b => b.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));

            btn.classList.add("active");
            document.getElementById(`tab-${target}`).classList.add("active");

            if (pageMeta[target]) {
                document.getElementById("page-title").textContent = pageMeta[target].title;
                document.getElementById("page-desc").textContent = pageMeta[target].desc;
            }

            // Resize charts upon tab switch
            if (target === "overview" && monthlyChart && abcChart) {
                monthlyChart.resize();
                abcChart.resize();
            } else if (target === "forecasting" && forecastChart) {
                forecastChart.resize();
            }
        });
    });
}

function initEventListeners() {
    // Pipeline Refresh Button
    const btnRun = document.getElementById("btn-run-pipeline");
    btnRun.addEventListener("click", async () => {
        btnRun.disabled = true;
        btnRun.innerHTML = `<span>Running Pipeline...</span>`;
        showToast("Executing Phases 1–5 End-to-End Pipeline...");

        try {
            const res = await fetch("/api/pipeline/run-all", { method: "POST" });
            const data = await res.json();
            showToast(data.message || "Pipeline execution completed successfully!");
            await loadDashboardData();
        } catch (e) {
            showToast("Pipeline error: " + e.message, true);
        } finally {
            btnRun.disabled = false;
            btnRun.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg><span>Run Full Pipeline</span>`;
        }
    });

    // SKU Forecast Selector
    const skuSelect = document.getElementById("forecast-sku-select");
    skuSelect.addEventListener("change", (e) => {
        loadSkuForecast(e.target.value);
    });

    // Overview Table Search
    const searchInput = document.getElementById("overview-search");
    searchInput.addEventListener("input", (e) => {
        const q = e.target.value.toLowerCase();
        const filtered = allProducts.filter(p =>
            p.sku.toLowerCase().includes(q) ||
            p.product_name.toLowerCase().includes(q) ||
            p.category.toLowerCase().includes(q) ||
            p.product_id.toLowerCase().includes(q)
        );
        renderOverviewTable(filtered);
    });

    // Service Level Simulator Slider
    const cslSlider = document.getElementById("sim-service-level");
    const cslBubble = document.getElementById("sim-csl-value");
    const zPill = document.getElementById("sim-z-value");
    const btnApplyCsl = document.getElementById("btn-apply-csl");

    const zLookup = {
        "0.80": "0.842", "0.85": "1.036", "0.90": "1.282",
        "0.95": "1.645", "0.98": "2.054", "0.99": "2.326"
    };

    cslSlider.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value).toFixed(2);
        cslBubble.textContent = `${(val * 100).toFixed(1)}% CSL`;
        zPill.textContent = zLookup[val] || (val > 0.95 ? "1.960" : "1.280");
    });

    btnApplyCsl.addEventListener("click", async () => {
        const csl = parseFloat(cslSlider.value);
        btnApplyCsl.disabled = true;
        btnApplyCsl.textContent = "Optimizing...";

        try {
            const res = await fetch("/api/optimize", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ service_level: csl })
            });
            const data = await res.json();
            showToast(data.message);
            await loadInventoryPolicies();
            await loadReplenishment();
            await loadOverview();
        } catch (err) {
            showToast("Optimization failed: " + err.message, true);
        } finally {
            btnApplyCsl.disabled = false;
            btnApplyCsl.textContent = "Apply Dynamic Optimization";
        }
    });
}

async function loadDashboardData() {
    await Promise.all([
        loadOverview(),
        loadProducts(),
        loadInventoryMatrix(),
        loadInventoryPolicies(),
        loadReplenishment(),
        loadSuppliers()
    ]);
}

async function loadOverview() {
    try {
        const res = await fetch("/api/overview");
        const data = await res.json();
        const kpi = data.kpi;

        document.getElementById("kpi-revenue").textContent = `$${kpi.total_revenue.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        document.getElementById("kpi-orders").textContent = `${kpi.total_orders.toLocaleString()} orders (${kpi.total_units_sold.toLocaleString()} units)`;

        document.getElementById("kpi-valuation").textContent = `$${kpi.total_inventory_valuation.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        document.getElementById("kpi-skus").textContent = `Across ${kpi.total_skus} active catalog SKUs`;

        document.getElementById("kpi-stockouts").textContent = `${kpi.reorder_needed_count} SKUs`;
        document.getElementById("kpi-reorders-hint").textContent = `${kpi.critical_stockout_count} Critical below Safety Stock`;

        document.getElementById("kpi-otif").textContent = `${kpi.avg_supplier_reliability_pct}%`;
        document.getElementById("kpi-defects-hint").textContent = `Avg Defect Rate: ${kpi.avg_defect_rate_pct}%`;

        renderMonthlyChart(data.monthly_trend);
    } catch (e) {
        console.error("Failed to load overview:", e);
    }
}

async function loadProducts() {
    try {
        const res = await fetch("/api/products");
        allProducts = await res.json();
        renderOverviewTable(allProducts);
        populateSkuDropdown(allProducts);

        if (allProducts.length > 0) {
            loadSkuForecast(allProducts[0].product_id);
        }
    } catch (e) {
        console.error("Failed to load products:", e);
    }
}

function renderOverviewTable(products) {
    const tbody = document.querySelector("#overview-table tbody");
    tbody.innerHTML = "";

    products.forEach(p => {
        const tr = document.createElement("tr");

        let statusClass = "optimal";
        let statusText = "OPTIMAL BUFFER";
        if (p.current_stock <= (p.safety_stock || 0)) {
            statusClass = "critical";
            statusText = "CRITICAL (BELOW SS)";
        } else if (p.current_stock <= (p.reorder_point || 0)) {
            statusClass = "reorder";
            statusText = "REORDER NEEDED";
        }

        const abcClass = p.abc_classification ? p.abc_classification.toLowerCase() : "c";

        tr.innerHTML = `
            <td style="font-family: var(--font-mono); color: var(--text-secondary);">${p.product_id}</td>
            <td style="font-weight: 600;">${p.sku}</td>
            <td>${p.product_name}</td>
            <td><span class="tag-pill">${p.category}</span></td>
            <td style="font-weight: 700;">${p.current_stock || 0}</td>
            <td style="color: var(--accent-rose); font-weight: 600;">${p.safety_stock || '--'}</td>
            <td style="color: var(--accent-amber); font-weight: 600;">${p.reorder_point || '--'}</td>
            <td style="color: var(--accent-blue); font-weight: 600;">${p.economic_order_qty || '--'}</td>
            <td><span class="status-tag abc-${abcClass}">Class ${p.abc_classification || 'C'}</span></td>
            <td style="font-family: var(--font-mono);">${p.stockout_risk_score || 0}</td>
            <td><span class="status-tag ${statusClass}">${statusText}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

function populateSkuDropdown(products) {
    const select = document.getElementById("forecast-sku-select");
    select.innerHTML = "";
    products.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.product_id;
        opt.textContent = `${p.sku} — ${p.product_name} (${p.category})`;
        select.appendChild(opt);
    });
}

async function loadSkuForecast(productId) {
    try {
        const res = await fetch(`/api/forecasts/${productId}`);
        const data = await res.json();
        const m = data.metrics;

        document.getElementById("fc-champ-model").textContent = m.model_name || "SES";
        document.getElementById("fc-mae").textContent = m.mae ? m.mae.toFixed(2) : "--";
        document.getElementById("fc-rmse").textContent = m.rmse ? m.rmse.toFixed(2) : "--";
        document.getElementById("fc-mape").textContent = m.mape ? `${m.mape.toFixed(1)}%` : "--";

        document.getElementById("fc-chart-title").textContent = `Demand Forecast: ${data.product.sku} — ${data.product.product_name}`;

        renderForecastChart(data);
        renderBacktestTable(data.backtest_evaluation);
        renderForwardTable(data.forward_forecast_30d);
    } catch (e) {
        console.error("Failed to load forecast for SKU:", e);
    }
}

function renderForecastChart(data) {
    const ctx = document.getElementById("chart-forecast").getContext("2d");
    if (forecastChart) forecastChart.destroy();

    const history = data.sales_history.slice(-90); // Last 90 days
    const backtest = data.backtest_evaluation;
    const future = data.forward_forecast_30d;

    // Combine distinct dates
    const dateSet = new Set();
    history.forEach(h => dateSet.add(h.date));
    backtest.forEach(b => dateSet.add(b.forecast_date));
    future.forEach(f => dateSet.add(f.forecast_date));

    const allDates = Array.from(dateSet).sort();

    const actualMap = Object.fromEntries(history.map(h => [h.date, h.qty]));
    const backtestMap = Object.fromEntries(backtest.map(b => [b.forecast_date, b.predicted_demand]));
    const futureMap = Object.fromEntries(future.map(f => [f.forecast_date, f.predicted_demand]));

    const actualSeries = allDates.map(d => actualMap[d] !== undefined ? actualMap[d] : null);
    const backtestSeries = allDates.map(d => backtestMap[d] !== undefined ? backtestMap[d] : null);
    const futureSeries = allDates.map(d => futureMap[d] !== undefined ? futureMap[d] : null);

    forecastChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: allDates,
            datasets: [
                {
                    label: "Historical Actual Demand",
                    data: actualSeries,
                    borderColor: "#38BDF8",
                    backgroundColor: "rgba(56, 189, 248, 0.1)",
                    borderWidth: 2,
                    pointRadius: 2,
                    tension: 0.2
                },
                {
                    label: "Holdout Test Predictions",
                    data: backtestSeries,
                    borderColor: "#A855F7",
                    borderWidth: 2.5,
                    borderDash: [4, 4],
                    pointRadius: 3,
                    tension: 0.2
                },
                {
                    label: "Next 30-Day Forward Forecast",
                    data: futureSeries,
                    borderColor: "#10B981",
                    backgroundColor: "rgba(16, 185, 129, 0.15)",
                    borderWidth: 3,
                    pointRadius: 4,
                    tension: 0.2,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: "#94A3B8", font: { family: "Inter", size: 12 } } }
            },
            scales: {
                x: {
                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                    ticks: { color: "#64748B", maxTicksLimit: 12 }
                },
                y: {
                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                    ticks: { color: "#64748B" },
                    title: { display: true, text: "Daily Units Sold", color: "#94A3B8" }
                }
            }
        }
    });
}

function renderBacktestTable(backtest) {
    const tbody = document.querySelector("#backtest-table tbody");
    tbody.innerHTML = "";
    backtest.slice(-10).forEach(b => {
        const error = Math.abs(b.actual_demand - b.predicted_demand).toFixed(2);
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${b.forecast_date}</td>
            <td style="font-weight: 700;">${b.actual_demand}</td>
            <td style="color: var(--accent-purple);">${b.predicted_demand}</td>
            <td style="font-family: var(--font-mono); color: var(--text-secondary);">${error}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderForwardTable(future) {
    const tbody = document.querySelector("#forward-table tbody");
    tbody.innerHTML = "";
    future.slice(0, 10).forEach(f => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${f.forecast_date}</td>
            <td style="font-weight: 700; color: var(--accent-emerald);">${f.predicted_demand} units</td>
            <td><span class="tag-pill">±15% Buffer</span></td>
        `;
        tbody.appendChild(tr);
    });
}

async function loadInventoryMatrix() {
    try {
        const res = await fetch("/api/inventory-matrix");
        const data = await res.json();
        renderAbcChart(data.abc_distribution);
    } catch (e) {
        console.error("Failed to load inventory matrix:", e);
    }
}

function renderAbcChart(abcMap) {
    const ctx = document.getElementById("chart-abc-split").getContext("2d");
    if (abcChart) abcChart.destroy();

    abcChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["Class A (High Value)", "Class B (Moderate Value)", "Class C (Bulk / Long-tail)"],
            datasets: [{
                data: [abcMap["A"] || 0, abcMap["B"] || 0, abcMap["C"] || 0],
                backgroundColor: ["#EF4444", "#F59E0B", "#3B82F6"],
                borderColor: "#111827",
                borderWidth: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "bottom", labels: { color: "#94A3B8", font: { family: "Inter", size: 12 } } }
            }
        }
    });
}

function renderMonthlyChart(monthlyTrend) {
    const ctx = document.getElementById("chart-monthly-trend").getContext("2d");
    if (monthlyChart) monthlyChart.destroy();

    const labels = monthlyTrend.map(m => m.month);
    const revenue = monthlyTrend.map(m => m.monthly_revenue);
    const units = monthlyTrend.map(m => m.monthly_units);

    monthlyChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Monthly Revenue ($)",
                    data: revenue,
                    backgroundColor: "rgba(56, 189, 248, 0.75)",
                    borderRadius: 6,
                    yAxisID: "y"
                },
                {
                    label: "Units Sold",
                    data: units,
                    type: "line",
                    borderColor: "#F59E0B",
                    borderWidth: 2.5,
                    pointRadius: 4,
                    yAxisID: "y1"
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: "#94A3B8", font: { family: "Inter" } } }
            },
            scales: {
                x: { grid: { color: "rgba(255, 255, 255, 0.05)" }, ticks: { color: "#64748B" } },
                y: {
                    position: "left",
                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                    ticks: { color: "#64748B", callback: val => `$${val.toLocaleString()}` }
                },
                y1: {
                    position: "right",
                    grid: { drawOnChartArea: false },
                    ticks: { color: "#F59E0B" }
                }
            }
        }
    });
}

async function loadInventoryPolicies() {
    try {
        const res = await fetch("/api/products");
        const products = await res.json();
        const tbody = document.querySelector("#inventory-policy-table tbody");
        tbody.innerHTML = "";

        products.forEach(p => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="font-weight: 600;">${p.sku}</td>
                <td>${p.product_name}</td>
                <td>${p.lead_time_days || 7} days</td>
                <td style="font-weight: 600;">${p.daily_avg_demand ? p.daily_avg_demand.toFixed(2) : '--'}</td>
                <td style="color: var(--text-muted);">${p.demand_std_dev ? p.demand_std_dev.toFixed(2) : '--'}</td>
                <td style="color: var(--accent-rose); font-weight: 700;">${p.safety_stock || '--'}</td>
                <td style="color: var(--accent-amber); font-weight: 700;">${p.reorder_point || '--'}</td>
                <td style="color: var(--accent-blue); font-weight: 700;">${p.economic_order_qty || '--'}</td>
                <td>${p.max_stock || '--'}</td>
                <td style="font-family: var(--font-mono); color: var(--accent-emerald);">$${(p.unit_cost * (p.annual_demand || 1000) * 0.2).toFixed(2)}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to load inventory policies:", e);
    }
}

async function loadReplenishment() {
    try {
        const res = await fetch("/api/replenishment");
        const data = await res.json();

        document.getElementById("total-rep-capital").textContent = `$${data.total_replenishment_capital_required.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;

        const tbody = document.querySelector("#replenish-table tbody");
        tbody.innerHTML = "";

        if (data.orders.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--accent-emerald); padding: 24px;">All SKUs are above Reorder Point. No replenishment orders currently required.</td></tr>`;
            return;
        }

        data.orders.forEach(o => {
            const tr = document.createElement("tr");
            const urgencyClass = o.urgency.includes("CRITICAL") ? "critical" : "reorder";

            tr.innerHTML = `
                <td style="font-weight: 600;">${o.sku}</td>
                <td>${o.product_name}</td>
                <td style="font-weight: 700;">${o.current_stock}</td>
                <td style="color: var(--accent-amber);">${o.reorder_point}</td>
                <td style="color: var(--accent-rose);">${o.safety_stock}</td>
                <td style="color: var(--accent-emerald); font-weight: 800; font-size: 1rem;">${o.recommended_reorder_qty} units</td>
                <td><span class="tag-pill">${o.supplier_name}</span></td>
                <td>${o.lead_time_days} days</td>
                <td style="font-family: var(--font-mono); font-weight: 700;">$${o.estimated_order_cost.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                <td><span class="status-tag ${urgencyClass}">${o.urgency}</span></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to load replenishment:", e);
    }
}

async function loadSuppliers() {
    try {
        const res = await fetch("/api/suppliers");
        const suppliers = await res.json();
        const tbody = document.querySelector("#suppliers-table tbody");
        tbody.innerHTML = "";

        suppliers.forEach(s => {
            const tr = document.createElement("tr");
            let tierClass = "tier-2";
            if (s.tier.includes("Platinum")) tierClass = "tier-1";
            else if (s.tier.includes("Silver")) tierClass = "tier-3";
            else if (s.tier.includes("At Risk")) tierClass = "tier-4";

            tr.innerHTML = `
                <td style="font-family: var(--font-mono); color: var(--text-secondary);">${s.supplier_id}</td>
                <td style="font-weight: 600;">${s.supplier_name}</td>
                <td style="color: var(--accent-emerald); font-weight: 600;">${s["otif_score (40%)"]}%</td>
                <td style="color: var(--accent-blue); font-weight: 600;">${s["lead_time_score (30%)"]}%</td>
                <td style="color: var(--accent-purple); font-weight: 600;">${s["quality_score (20%)"]}%</td>
                <td style="color: var(--text-secondary); font-weight: 600;">${s["cost_score (10%)"]}%</td>
                <td style="font-size: 1.1rem; font-weight: 800; color: #fff;">${s.composite_score}</td>
                <td><span class="status-tag ${tierClass}">${s.tier}</span></td>
                <td><span class="tag-pill">${s.risk_level}</span></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to load suppliers:", e);
    }
}

function showToast(msg, isError = false) {
    const toast = document.getElementById("toast");
    toast.textContent = msg;
    toast.style.borderColor = isError ? "var(--accent-rose)" : "var(--accent-indigo)";
    toast.classList.remove("hidden");
    setTimeout(() => {
        toast.classList.add("hidden");
    }, 3500);
}
