EXPORT_FOLDER = r"<install location>\trade_view\exports"
EXCLUSION_LIST = ["USD.HKD", "AUD.USD", "EUR.USD", "USD.CNH", "CNH.HKD", "USD.JPY", "USD.CHF", "AUD.CNH"]
PLOTTING = True # this decides if get_ticker_trades() does charting

# currency table is applied in contract_size_table as base currency is USD
currency_table = {
    "EURUSD": 1.16,
    "USDCNH": 7.11,
    "USDHKD": 7.80,
}
contract_size_table = {
    "ZT": 2000,
    "ZF": 1000,
    "ZN": 1000,
    "TN": 1000,
    "ZB": 1000,
    "UB": 1000,
    "SOFR3": 2500,
    "UC": 100000 / currency_table["USDCNH"],
    "CL": 1000,
}

# exposure table for exposure breakdown
exposure_table = {
    "AMD": ["US", 1.5],
    "BABA": ["CH", 1],
    "SOFR3": ["DV01", 1 / 10000],
    "NVDA": ["US", 1.5],
    "SGOV": ["MM fund", 1],
    "ZT": ["DV01", 1.8 / 10000],
    "ZF": ["DV01", 3.8 / 10000],
    "ZN": ["DV01", 5.8 / 10000],
    "TN": ["DV01", 7.7 / 10000],
    "ZB": ["DV01", 10.8 / 10000],
    "UB": ["DV01", 16.2 / 10000],
    "CL": ["CL", 1],
}