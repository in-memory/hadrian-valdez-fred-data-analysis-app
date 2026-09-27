# 📊 FRED Economic Data Explorer

A Streamlit-based web application for exploring and visualizing economic data from the [FRED (Federal Reserve Economic Data)](https://fred.stlouisfed.org/) API. This app allows users to fetch, cache, and analyze various economic time series with interactive charts.

---

## 🚀 Features

- **Fetch from FRED API**: Access thousands of economic indicators directly through the official FRED API
- **Local Caching**: Automatically caches downloaded data in the `data/` directory for faster loading
- **Interactive Visualizations**: Beautiful line charts using Plotly to track economic trends over time
- **Flexible Time Horizons**: Choose between 1Y, 5Y, 10Y, or All Available Data views
- **Raw Data Inspection**: Access underlying data tables with expandable sections
- **Session Persistence**: Maintains state across app refreshes using Streamlit session management

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

5. **Get your FRED API Key:**
   - Visit [FRED's API page](https://fred.stlouisfed.org/docs/api/api_key.html)
   - Sign up and generate a free API key
   - Copy it into your `.env` file

---

## 🎯 Quick Start

1. **Run the app:**
   ```bash
   streamlit run dashboard.py
   ```

2. **In the browser, you'll see:**
   - A sidebar to select or fetch new series IDs (e.g., `GDP`, `UNRATE`, `CPIAUCSL`)
   - Time horizon controls (1Y, 5Y, 10Y, Max)
   - Interactive Plotly charts
   - Raw data view expander

3. **Try these popular series:**
   - `CPIAUCSL` - Consumer Price Index, All Urban Consumers
   - `GDP` - Gross Domestic Product
   - `UNRATE` - Unemployment Rate
   - `FEDFUNDS` - Federal Funds Effective Rate

---

## 📂 Project Structure

```
hadrian-valdez-fred-data-analysis-app/
├── dashboard.py          # Main Streamlit app entry point
├── data_loader.py        # API interaction and caching logic
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── .env                  # Your FRED API key (create this)
└── data/                 # Cached JSON files (created automatically)
    ├── GDP.json
    ├── UNRATE.json
    └── ...
```

---

## 🔍 How It Works

1. **Input**: User enters a series ID in the sidebar or selects from cached data
2. **Fetch/Cached Load**: The app checks `data/` for cached JSON files first, then fetches from FRED API if needed
3. **Process**: Data is parsed, converted to datetime/numeric types, and cleaned
4. **Visualize**: Plotly creates an interactive line chart with date/time on X-axis and values on Y-axis
5. **Filter**: Default 10-year view (or user-selected time horizon)

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