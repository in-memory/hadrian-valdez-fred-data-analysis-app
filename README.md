# 📊 FRED Economic Data Explorer

A Streamlit-based web application for exploring and visualizing economic data from the [FRED (Federal Reserve Economic Data)](https://fred.stlouisfed.org/) API. This app allows users to fetch, cache, and analyze various economic time series with interactive charts.

---

## 🚀 Features

- **Bidirectional Category Traversal**: Top-down lazy loading drilldown of FRED category hierarchy combined with bottom-up resolution from any series ID to Root (0)
- **Browser-Style Navigation**: Back and Forward buttons with session history stacks and clickable breadcrumbs (`Root > Parent > Child`)
- **Category Tiles & Series Explorer**: Visual category cards, subcategory exploration, and category-level series search
- **Local Persistence & Flat Adjacency Graph**: Graph caching in `fred_cache.json` and time series datasets in `data/` (`.parquet`, `.csv`, `.json`)
- **API Safeguards & Defensive Caching**: Automatic local cache lookup before remote FRED API calls, with graceful rate-limit (HTTP 429) prevention
- **Interactive Visualizations**: High-performance Plotly charts with custom themes, hover tooltips, and time horizon filtering (1Y, 5Y, 10Y, Max)
- **Economic Metrics & Raw Data Export**: Period delta, percent change, period high/low, raw data inspection, and CSV download

---

## 🛠️ Requirements

- Python 3.8+
- [FRED API Key](https://fred.stlouisfed.org/docs/api/api_key.html) (required)

---

## 📦 Installation

1. **Clone or navigate to the project directory:**
   ```bash
   cd hadrian-valdez-fred-data-analysis-app
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   source .venv/bin/activate  # Linux/Mac
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up your API key:**
   ```bash
   # Create a .env file in the project root with:
   FRED_API_KEY=your_api_key_here
   ```

---

## 🎯 Quick Start

1. **Run the app:**
   ```bash
   streamlit run dashboard.py
   ```

2. **In the browser, you'll see:**
   - Navigation bar with Back, Forward, Root, and clickable breadcrumbs
   - Category explorer with subcategory tiles and series filter
   - Direct series search with bottom-up ancestor resolution in the sidebar
   - Time horizon controls (1Y, 5Y, 10Y, Max) and interactive Plotly charts
   - Raw data expander and CSV download

---

## 📂 Project Structure & Separation of Concerns

```
hadrian-valdez-fred-data-analysis-app/
├── dashboard.py          # Presentation layer & Streamlit orchestration
├── category_manager.py   # Hierarchy traversal engine & fred_cache.json manager
├── data_loader.py        # FRED API client & raw dataset storage (.parquet/.csv/.json)
├── fred_cache.json       # Graph adjacency schema cache
├── requirements.txt      # Python dependencies
├── README.md             # Project documentation
├── plan.md               # Technical specification
├── .env                  # FRED API key credentials
└── data/                 # Saved dataset observations
    ├── CPIAUCSL.json
    ├── GDP.json
    ├── UNRATE.parquet
    └── ...
```

---

## 🔍 Architecture & How It Works

1. **`dashboard.py`**:
   - Manages UI session state (`current_category_id`, navigation history stacks, `active_series_id`).
   - Renders layout: sidebar controls, browser navigation, breadcrumbs, category tiles, series lists, Plotly charts.
   - *Never directly calls the FRED API or reads/writes cache files directly.*

2. **`category_manager.py`**:
   - Dedicated exclusively to category logic and graph state.
   - Manages read/write persistence for `fred_cache.json` using the flat adjacency schema.
   - Implements top-down lazy-loading category exploration.
   - Implements bottom-up resolution from `series_id` up to Root (`0`).
   - Computes lineage breadcrumbs (`Root > Parent > Current`).

3. **`data_loader.py`**:
   - Dedicated exclusively to FRED network calls and raw dataset file management.
   - Wraps FRED API endpoints with authentication and rate-limit safeguards.
   - Manages local `data/` dataset persistence (`.parquet`, `.csv`, `.json`).


---

## 📝 Common Series IDs

| Series ID | Description |
|-----------|-------------|
| `CPIAUCSL` | Consumer Price Index, All Urban Consumers |
| `GDP` | Gross Domestic Product, Quarterly (Annualized) |
| `UNRATE` | Unemployment Rate |
| `FEDFUNDS` | Federal Funds Effective Interest Rate |
| `DGS10` | 10-Year Treasury Constant Maturity Rate |
| `PCECPI` | Personal Consumption Expenditures, Chain-type CPI |

*Visit [FRED's search](https://fred.stlouisfed.org/series/) to find more series.*

---

## ⚠️ Troubleshooting

### "No data available" or API errors
- **Verify your `.env` file exists** with a valid `FRED_API_KEY`
- **Check the key is correct** and not truncated
- **Check internet connection** - FRED API requires network access
- **Review cached files**: Files in `data/` should be valid JSON; re-fetch if corrupted

### Charts appear blank
- The series ID might not exist in FRED
- Try a different series (e.g., `GDP` or `UNRATE`)
- Ensure data was successfully fetched and cached

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

## 🔗 Resources

- [FRED API Documentation](https://fred.stlouisfed.org/docs/api/)
- [Streamlit Guide](https://docs.streamlit.io/)
- [Plotly Graphing Objects](https://plotly.com/python/)
- [Pandas Documentation](https://pandas.pydata.org/docs/)

---

## 🙏 Acknowledgments

- Built with [Streamlit](https://streamlit.io/) for rapid data app development
- Visualization powered by [Plotly](https://plotly.com/)
- Economic data provided by [FRED®](https://fred.stlouisfed.org/) (Federal Reserve Economic Data)

---

**Made using Streamlit and FRED Data**