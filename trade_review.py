from datetime import datetime
import pytz
import pandas as pd
import os
from trade_counter import count_trades, get_all_trades
from inputs import exposure_table,currency_table, contract_size_table, watch_list, EXCLUSION_LIST, CASH
import yfinance as yf
import matplotlib.pyplot as plt
from pathlib import Path

pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', None)  # Show all columns
pd.set_option('display.width', 1000)  # Increase width to fit your screen
pd.set_option('display.expand_frame_repr', False)  # Prevent wrapping
pd.set_option('display.max_colwidth', None)  # Show full content of each column

# find export location
SCRIPT_DIR = Path(__file__).parent.resolve()
EXPORT_FOLDER = str(SCRIPT_DIR / "exports")



class PositionKeeper:
    """
    Designed to keep track of unrealised and realised positions for a single ticker on a trade by trade basis.
    Can also mark to market for open positions.
    Pnl accounts for contract size correctly all through
    market_value does not account for contract size, except for when returned by get_position_info()
    """
    def __init__(self, ticker, contract_size):
        self.ticker = ticker # name of symbol
        self.contract_size = contract_size # contract size
        self.exposure = 0 # exposure of the base symbol
        self.last_price = 0  # Last trade price of the symbol_base
        self.avg_price = 0  # Average entry price for current exposure
        self.market_value = 0 # Current market value of position
        self.realised_pnl = 0
        self.unrealised_pnl = 0
        self.timestamp = 0 # time of each trade

    def add_trade(self, time, price, quantity):
        # Update last price and timestamp
        self.timestamp = time
        self.last_price = price

        # dealing with the exposure and adding to PL
        if quantity > 0:  # Buy trade exposure
            if self.exposure == 0:
                self.avg_price = price
                self.exposure += quantity

            elif self.exposure > 0:  # Adding to long or flat exposure
                total_cost = (self.exposure * self.avg_price) + (quantity * price)
                self.exposure += quantity
                self.avg_price = total_cost / self.exposure

            elif self.exposure + quantity <= 0: # Reducing short exposure
                profit = -quantity * (price - self.avg_price)
                self.realised_pnl += profit * self.contract_size
                self.exposure += quantity
                if self.exposure == 0:
                    self.avg_price = 0

            elif self.exposure + quantity > 0: # closing short and go long exposure
                profit = self.exposure * (price -self.avg_price)
                self.realised_pnl += profit * self.contract_size
                self.exposure += quantity
                self.avg_price = price

        elif quantity < 0:  # sell trade exposure
            if self.exposure == 0:
                self.avg_price = price
                self.exposure += quantity

            elif self.exposure < 0:  # add to short
                total_cost = (self.exposure * self.avg_price) + (quantity * price)
                self.exposure += quantity
                self.avg_price = total_cost / self.exposure

            elif self.exposure + quantity >= 0: # Reducing long exposure
                profit = -quantity * (price - self.avg_price)
                self.realised_pnl += profit * self.contract_size
                self.exposure += quantity
                if self.exposure == 0:
                    self.avg_price = 0

            elif self.exposure + quantity < 0: # closing long and go short
                profit = self.exposure * (price -self.avg_price)
                self.realised_pnl += profit * self.contract_size
                self.exposure += quantity
                self.avg_price = price

    def update_stats(self):
        self.market_value = self.exposure * self.last_price
        self.unrealised_pnl = (self.market_value - self.exposure * self.avg_price) * self.contract_size

    def mark_to_market(self, update_timestamp = False, market_data = None):
        # if market_data exists, check it for the market price otherwise try to pull it
        if isinstance(market_data, dict):
            # see if ticker exists in market data
            if self.ticker in market_data.keys():
                market_price = market_data
            else:
                market_price = get_last_price([self.ticker])
        else:
            market_price = get_last_price([self.ticker])
        # market_price will be None if error returned by get_last_price
        if market_price is not None:
            if not pd.isna(market_price.get(self.ticker)):
                self.last_price = market_price.get(self.ticker)
                self.update_stats()
                # update_timestamp is for PL/Exposure plotting to be more chronological
                if update_timestamp:
                    hk_time = datetime.now().replace(microsecond=0)
                    self.timestamp = hk_time.astimezone(pytz.timezone("Asia/Hong_Kong"))


    def get_position_info(self):
        # nice script to return output in formatted way
        return {
            "ticker": self.ticker,
            "pos": round(self.exposure),
            "pnl": round(float(self.realised_pnl + self.unrealised_pnl)),
            "open_pnl": round(float(self.unrealised_pnl)),
            "scalp_pnl": round(float(self.realised_pnl)),
            "last_price": round(self.last_price,4),
            "avg_price": round(self.avg_price,4),
            "market_value": round(self.market_value * self.contract_size),
            "timestamp": self.timestamp,
        }
def get_contract_size(contract_spec = None, currency_spec = None, ticker = ""):
    if ticker.split()[0] in contract_spec:
        contract_size = contract_spec[ticker.split()[0]]
    # hk stocks
    elif len(ticker) <= 4 and ticker.isdigit():
        contract_size = 1 / currency_spec["USDHKD"]
    # ch stocks
    elif len(ticker) == 6 and ticker.isdigit():
        contract_size = 1 / currency_spec["USDCNH"]
    # JP stocks
    elif ticker.endswith("TSEJ"):
        contract_size = 1 / currency_spec["USDJPY"]
    else:
        contract_size = 1
    return contract_size

def store_trades(raw_trades = pd.DataFrame(), file_location = None):
    """
    Designed to convert a dataframe of raw trades generated by get_all_trades
    to a standard format that can be analysed.
    Outputs a set of new_trades, by comparison with the existing all_trades.csv
    """
    if file_location is None:
        print("No file location, please add to credentials.py")
        exit()

    # initialise all_trades
    all_trades = pd.DataFrame()
    for index, row in raw_trades.iterrows():
        uid = row.loc["UID"]
        date_long = row.loc["Date"]
        subject = row.loc["Subject"]

        subject_split = subject.split()
        first_at_index = next(i for i, item in enumerate(subject_split) if '@' in item)
        quantity = round((1 if subject_split[0] == "BOUGHT" else -1) * float(subject_split[1].replace(",","")),0)
        ticker = ''
        for x in range(2, first_at_index):
            ticker += subject_split[x] + " "
        ticker = ticker[:-1].upper()
        contract_size = get_contract_size(contract_size_table, currency_table, ticker)
        trade = pd.DataFrame({
            "UID": [uid],
            "date_long": [date_long],
            "ticker": [ticker],
            "quantity": [quantity],
            "price": [float(subject_split[subject_split.index("@") + 1])],
            "contract_size" : [contract_size],
        })

        if len(all_trades) == 0:
            all_trades = trade
        else:
            all_trades = pd.concat([all_trades,trade], ignore_index = True)

    # compare with existing all_trades.csv to find new_trades
    if os.path.isfile(file_location + r"\all_trades.csv"):
        existing_trades = pd.read_csv(file_location + r"\all_trades.csv")
        existing_trades["UID"] = existing_trades["UID"].astype(str)
        new_trades = all_trades.loc[~all_trades["UID"].isin(existing_trades["UID"])]
        print(f"Found {len(new_trades)} new trades")
        if len(new_trades) != 0:
            print(new_trades)

    # all_trades generated from get_all_trades is already sorted from the first trade being the latest
    all_trades.to_csv(file_location + r"\all_trades.csv", index = False)
    all_trades.to_csv(file_location + r"\backups\all_trades"+f"{datetime.now().strftime("%Y_%m_%d")}"+ ".csv", index=False)
    print(f"Found {len(all_trades)} trade confirmations up to {all_trades["date_long"][0]}")
    return all_trades

def manual_trades(all_trades = pd.DataFrame(), file_location = r""):
    """
    Takes manual trades from manual_trades.csv and injects into all_trades df
    """
    if os.path.isfile(file_location + r"\manual_trades.csv"):
        manual_df = pd.read_csv(file_location + r"\manual_trades.csv")
        # save a backup of manual_trades
        manual_df.to_csv(file_location + r"\backups\manual_trades" + f"{datetime.now().strftime("%Y_%m_%d")}" + ".csv",
                         index=False)
        if len(manual_df) == 0:
            return all_trades
        print(f"Found manual_trades.csv with {len(manual_df)} trades, injecting with UID 0")
        # add columns to fit all_trades

        # parse "date" column (e.g. "2026-05-25") into date_long (HKT midnight)
        hk_tz = pytz.timezone("Asia/Hong_Kong")
        manual_df["date_long"] = pd.to_datetime(manual_df["date"]).dt.tz_localize(hk_tz)
        manual_df = manual_df.drop(columns=["date"])

        manual_df["UID"] = 0
        manual_df["contract_size"] = manual_df.apply(
            lambda x: get_contract_size(contract_size_table, currency_table, x.ticker), axis=1)

        # concat the manual trades with all trades and dump
        all_trades = pd.concat([all_trades, manual_df], ignore_index=True).sort_values(by="date_long", ascending=False)
        all_trades = all_trades.reset_index(drop=True)

        # redump the new all_trades which includes manual_trades
        all_trades.to_csv(file_location + r"\all_trades.csv", index=False)
    return all_trades


# need to add a way for my script to differentiate between closed positions and open positions, in chronological order
def analyse_trades(all_trades = pd.DataFrame(), file_location = r""):
    """
    Takes an all_trades df, and analysis pnl by feeding trades into
    a PositionKeeper class which will keep track of the exposure, unrealised pnl and realised pnl.
    Groups the outputs into all_pnl which can be stored and reviewed further.
    """
    tickers = all_trades.ticker.unique()
    tickers = [ticker for ticker in tickers if ticker not in EXCLUSION_LIST and "-COMB" not in ticker]

    # first get market_data for all open positions to save api calls during mark_to_market
    open_positions = all_trades.groupby("ticker")["quantity"].sum()
    open_tickers = open_positions.loc[open_positions != 0].index.tolist()
    open_tickers_traded = [x for x in open_tickers if x not in EXCLUSION_LIST and "-COMB" not in x]
    market_data = get_last_price(open_tickers_traded)

    ticker_outputs = []
    for ticker in tickers:
        ticker_trades = all_trades.loc[all_trades.ticker == ticker].iloc[::-1].reset_index(drop=True)
        contract_size = ticker_trades.loc[0, "contract_size"]

        # create PositionKeeper class to compute unrealised/realised PL per trade
        ticker_position = PositionKeeper(ticker, contract_size)
        for index, row in ticker_trades.iterrows():
            # input each trade into PositionKeeper line by line
            ticker_position.add_trade(row.date_long, row.price, row.quantity)
            # recompute unrealised and realised pnl based on market value
            ticker_position.update_stats()
        # for open positions, use market_data to mark to market
        if ticker_position.exposure != 0:
            ticker_position.mark_to_market(update_timestamp=False, market_data=market_data)

        # retrieve the output of PositionKeeper and append to a list
        ticker_outputs.append(ticker_position.get_position_info())

    # aggregate the per ticker output into a larger dataframe
    all_pnl = pd.DataFrame(ticker_outputs)

    # sort all tickers by absolute PL
    all_pnl["abs_all_pnl"] = abs(all_pnl["pnl"])
    all_pnl = all_pnl.sort_values(by = "abs_all_pnl", ignore_index = True, ascending = False)
    all_pnl = all_pnl.drop(columns=["abs_all_pnl"])


    total_pnl = int(round(all_pnl["pnl"].sum(), 0))
    open_pnl = int(round(all_pnl["open_pnl"].sum(), 0))
    scalp_pnl = int(round(all_pnl["scalp_pnl"].sum(), 0))

    # pull the backup all_summary if it exists to compute change in pnl
    total_pnl_yest,open_pnl_yest, scalp_pnl_yest = 0, 0, 0
    if os.path.isfile(file_location + r"\all_summary.csv"):
        all_pnl_yest = pd.read_csv(file_location + r"\all_summary.csv")
        total_pnl_yest = int(round(all_pnl_yest["pnl"].sum(),0))
        open_pnl_yest = int(round(all_pnl_yest["open_pnl"].sum(), 0))
        scalp_pnl_yest = int(round(all_pnl_yest["scalp_pnl"].sum(), 0))

    # save the new all_summary
    all_pnl.to_csv(file_location + r"\all_summary.csv", index=False)

    # split into open df, sort by open_pnl and display
    open_df = all_pnl.loc[all_pnl["pos"] != 0].reset_index(drop = True)
    open_df = open_df.sort_values("open_pnl", ascending=False, ignore_index=True)
    print(open_df)
    print("----------------------------------------------------------------------------------------------------------")
    print(f"PL is {total_pnl}, {(total_pnl-total_pnl_yest):+}\n"
          f"Open PL is {open_pnl}, {(open_pnl-open_pnl_yest):+}\n"
          f"Scalp PL is {scalp_pnl}, {(scalp_pnl-scalp_pnl_yest):+}")
    return open_df


def exposure_breakdown(open_pos = pd.DataFrame(), exposure_table = None):
    """
    Takes an open_position dataframe and performs portfolio analysis on custom equity exposures.
    Also provides stats on equity, cash and gold allocations
    """
    # a nice learning point from this line is that direct assignment of dataframes in python does not create a new dataframe,
    # it actually passes the underlying objects of the initial dataframe into the new object
    open_summary = open_pos.copy()
    try:
        open_summary["exposure_grp"] = open_summary.apply(lambda x: exposure_table.get(x.ticker.split()[0])[0], axis=1)
        open_summary["type"] = open_summary.apply(lambda x: exposure_table.get(x.ticker.split()[0])[1], axis=1)
        open_summary["beta"] = open_summary.apply(lambda x: exposure_table.get(x.ticker.split()[0])[2], axis=1)

        # create stock allocations
        allocation_summary = open_summary.loc[open_summary["type"] == "stock"].copy()
        allocation_summary = allocation_summary.sort_values("market_value", ascending=False, ignore_index=True)
        allocation_summary = allocation_summary[["ticker", "market_value"]]
        net_asset_val = sum(allocation_summary["market_value"]) + CASH
        allocation_summary["market_value"] = allocation_summary["market_value"] / net_asset_val * 100
        allocation_summary["market_value"] = allocation_summary["market_value"].round(1)
        allocation_summary.columns = [["Ticker", "Allocation (%)"]]

    except TypeError:
        missing_tickers = [x.split()[0] for x in open_summary.ticker if x.split()[0] not in exposure_table.keys()]
        print(f"{missing_tickers} not in exposure_table, fix to see exposure breakdown")
        return None
    exposure_list = open_summary.exposure_grp.unique()

    exposure_notional = []
    exposure_nominal = []
    components = []
    for exposure in exposure_list:
        temp = open_summary[open_summary["exposure_grp"] == exposure]
        exposure_notional.append(round(sum(temp["market_value"]*temp["beta"])))
        exposure_nominal.append(round(sum(temp["market_value"])))
        components.append(temp["ticker"].unique())
    exposure_df = pd.DataFrame(
        {
            "exposure_grp" : exposure_list,
            "adj risk" : exposure_notional,
            "nominal" : exposure_nominal,
            "components" : components,
        }
    )
    # compute some stats for display
    equity_risk = exposure_df.loc[exposure_df["exposure_grp"].isin(
        ["US", "HK", "CN", "IN", "KR", "JP"]), "adj risk"].sum()
    market_beta = round(equity_risk / net_asset_val, 2)

    # add nominal allocation into output
    exposure_df["allocation"] = round(exposure_df["nominal"] / net_asset_val * 100,1)
    exposure_df["allocation"] = exposure_df["allocation"].astype(str) + "%"
    exposure_df = exposure_df.sort_values("adj risk", ascending=False, ignore_index=True)
    exposure_df = exposure_df[["exposure_grp", "adj risk", "nominal", "allocation", "components"]]

    print("----------------------------------------------------------------------------------------------------------")
    print(f"NAV {net_asset_val}, EQUITY RISK {equity_risk}, SPX BETA {market_beta}")
    print("----------------------------------------------------------------------------------------------------------")
    print(exposure_df)
    print("----------------------------------------------------------------------------------------------------------")
    return allocation_summary

def get_last_price(tickers = None, precision = None):
    """
    Wrapper of yfinance func yf.download to extract the last traded price of a set of tickers
    get_last_price(["BABA", "9988", "CL Jul'25", "USDCNH"])
    """

    yf_tickers = []
    for ticker in tickers:
        # HK tickers
        if len(ticker) <= 4 and ticker.isdigit():
            yf_tickers.append(ticker.zfill(4) + ".HK")
        # SH tickers
        elif len(ticker) == 6 and ticker.startswith("6"):
            yf_tickers.append(ticker + ".SS")
        # SZ tickers
        elif len(ticker) == 6 and ticker.startswith(("0", "3")):
            yf_tickers.append(ticker + ".SZ")
        # JP tickers
        elif ticker.endswith("TSEJ"):
            yf_tickers.append(ticker.split(" ")[0] + ".T")
        # futs will be resolved to the generic active future
        elif " " in ticker:
            yf_tickers.append(ticker.split()[0] + "=F")
        # spot currency
        elif ticker[:3] == "USD" and len(ticker) == 6:
            yf_tickers.append(ticker + "=X")
        # default US ticker need no .US
        else:
            yf_tickers.append(ticker)
    yf_map = dict(zip(yf_tickers, tickers))

    prices = yf.download(yf_tickers, period="3d", auto_adjust=True, progress=False)
    try:
        # forward fill to get the most recent close price, and return dict, if yfinance pull failed, return None
        close_prices = prices["Close"].ffill().iloc[-1]
        if precision is not None:
            close_prices = close_prices.round(precision)
        # use yf_map to set dict keys as function input and return
        close_prices_dict = close_prices.to_dict()
        close_prices_dict_mapped = dict((yf_map[key], value) for (key, value) in close_prices_dict.items())
        return close_prices_dict_mapped
    except IndexError:
        print(f"\nSomething went wrong with finding last price for {yf_tickers}, defaulting to open_price")
        return None

def get_ticker_trades(all_trades = pd.DataFrame(), ticker = ""):
    """
    Takes an all_trades df and does analysis on a specific ticker, will also present a plot on exposure and pnl
    """
    unique_tickers = all_trades["ticker"].unique()
    # first try to resolve the ticker
    ticker = ticker.upper()
    if ticker in unique_tickers:
        ticker_trades = all_trades.loc[all_trades.ticker == ticker].iloc[::-1].reset_index(drop=True)

        # initiate PositionKeeper
        contract_size = ticker_trades.loc[0, "contract_size"]
        ticker_position = PositionKeeper(ticker, contract_size)
        # feed in trades
        ticker_output = []
        for index, row in ticker_trades.iterrows():
            ticker_position.add_trade(row.date_long, row.price, row.quantity)
            ticker_position.update_stats()
            ticker_output.append(ticker_position.get_position_info())
        # mark to market for open positions
        if ticker_position.exposure != 0:
            print("marking to market for open position")
            ticker_position.mark_to_market(update_timestamp=True)
            ticker_output.append(ticker_position.get_position_info())
        ticker_output_df = pd.DataFrame(ticker_output)
        print(ticker_output_df)
        print(f"\nTotal Open PL is {ticker_output_df["open_pnl"].iloc[-1]}"
              f"\nTotal Scalp PL is {ticker_output_df["scalp_pnl"].iloc[-1]}"
              f"\nTotal PL is {ticker_output_df["pnl"].iloc[-1]}\n")

        if len(ticker_trades) > 10:
            # Create figure with 2 subplots, sharing x-axis
            fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(10, 8), sharex=True,
                                                 gridspec_kw={'height_ratios': [3, 1]})

            # --- Top Subplot: PnL and Exposure ---
            ax1 = ax_top
            ax1.plot(ticker_output_df['timestamp'], ticker_output_df['pnl'], label='Total PNL', color='magenta',
                     linewidth=2)
            ax1.set_ylabel('PNL (USD)', color='magenta')
            ax1.tick_params(axis='y', labelcolor='magenta')
            ax1.grid(True)
            ax1.legend(loc='upper left')
            ax2 = ax1.twinx()
            ax2.plot(ticker_output_df['timestamp'], ticker_output_df['pos'], label='Exposure', color='green',
                     linewidth=2)
            ax2.set_ylabel('Exposure (units)', color='green')
            ax2.tick_params(axis='y', labelcolor='green')
            ax2.legend(loc='upper right')
            # --- Bottom Subplot: Price and Buy/Sell Trades ---
            ax_bot.plot(ticker_trades['date_long'], ticker_trades['price'], color='gray', alpha=0.7, label='Price',
                        zorder=1)

            # Scatter buys/sells (Assuming quantity > 0 is Buy, < 0 is Sell. Flip if your convention is reversed)
            buys = ticker_trades[ticker_trades['quantity'] > 0]
            sells = ticker_trades[ticker_trades['quantity'] < 0]

            ax_bot.scatter(buys['date_long'], buys['price'], color='green', marker='^', s=60, label='Buy', zorder=3)
            ax_bot.scatter(sells['date_long'], sells['price'], color='red', marker='v', s=60, label='Sell', zorder=3)

            ax_bot.set_ylabel('Price')
            ax_bot.set_xlabel('Timestamp')
            ax_bot.grid(True, alpha=0.3)
            ax_bot.legend(loc='upper left')
            # --- Final Formatting ---
            plt.suptitle(f'{ticker} - Trade & PnL Analysis', fontsize=14, fontweight='bold')
            ax_bot.tick_params(axis='x', rotation=45)
            fig.tight_layout()
            plt.show()

    else:
        print("Ticker not in unique tickers")
    return

def ticker_history(all_trades = pd.DataFrame()):
    df = all_trades.copy()
    df = df[~df["ticker"].isin(EXCLUSION_LIST)]
    df["ticker"] = df.apply(lambda x: x.ticker.split()[0], axis = 1)
    df.set_index("date_long", inplace = True, drop = True)
    grouped_df = df.groupby([df.index.year, df.index.month])
    print(grouped_df["ticker"].unique())


def show_watchlist(used_watchlist = None):
    for custom_list in used_watchlist.keys():
        print(f"{custom_list}", get_last_price(used_watchlist.get(custom_list), 3))
    print("----------------------------------------------------------------------------------------------------------")


def other_functions(all_trades = pd.DataFrame(), allocation = pd.DataFrame(), file_location = None):
    """
    This function runs at the end of the program, giving the user a few extra functions to review their trades.
    """
    # at the end of the routine ask the user for other things that they may want to do
    unique_tickers = all_trades["ticker"].unique()
    unique_tickers = [x for x in unique_tickers if x not in EXCLUSION_LIST and "-COMB" not in x]
    print(unique_tickers)

    function_loop = True
    while function_loop:
        ticker_input = input(
            "Type ticker to see trades. e.g NVDA\n"
            "Other functions:\n"
            "\t1 to count trades in the current month\n"
            "\t2 to see trade summary per ticker\n"
            "\t3 to see history of tickers traded\n"
            "\t4 to see last 30 trades\n"
            "\t5 to see allocations\n"
            "\t6 to refresh the script\n"
        )
        # no command was given so exit
        if ticker_input == "":
            function_loop = False
        # count trades
        elif ticker_input == "1":
            raw_trades = get_all_trades()
            count_trades(raw_trades, EXCLUSION_LIST)
        # show scalp summary
        elif ticker_input == "2":
            all_pnl = pd.read_csv(file_location+r"\all_summary.csv")
            all_pnl_light = all_pnl[["ticker", "pnl", "open_pnl", "scalp_pnl", "timestamp"]]
            all_pnl_light = all_pnl_light.copy()
            all_pnl_light["timestamp"] = pd.to_datetime(all_pnl_light["timestamp"])
            all_pnl_light["underlying"] = all_pnl_light.apply(lambda x: x["ticker"].split(" ")[0], axis=1)
            all_pnl_combined = all_pnl_light.groupby("underlying").agg(
                pnl=('pnl', 'sum'),
                open_pnl=('open_pnl', 'sum'),
                scalp_pnl=('scalp_pnl', 'sum'),
                timestamp=('timestamp', 'max'),
            )
            all_pnl_combined = all_pnl_combined.sort_values('pnl', key=lambda x: x.abs(), ascending=False)

            print(all_pnl_combined, f"\nScalp PL is {int(round(all_pnl_light["scalp_pnl"].sum(), 0))}")
        # show ticker history
        elif ticker_input == "3":
            ticker_history(all_trades)
        # show last 30 trades
        elif ticker_input == "4":
            print(all_trades.head(30))
        # show stock allocations computed in exposure_breakdown()
        elif ticker_input == "5":
            print(allocation)
        # rerun script
        elif ticker_input == "6":
            main()
        # show trades for a specific ticker
        else:
            get_ticker_trades(all_trades, ticker_input)
    print("Thanks for taking time to review trades, exiting")
    return

def main():
    export_location = EXPORT_FOLDER

    # perform all the analytics
    raw_trades = get_all_trades()
    clean_trades = store_trades(raw_trades, export_location)
    all_trades = manual_trades(clean_trades, export_location)
    open_summary = analyse_trades(all_trades, export_location)
    allocation_summary = exposure_breakdown(open_summary, exposure_table)
    show_watchlist(watch_list)
    other_functions(all_trades, allocation_summary, export_location)

if __name__ in "__main__":
    main()