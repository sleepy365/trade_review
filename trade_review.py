from datetime import datetime
import pytz
import pandas as pd
import os
from trade_counter import count_trades, get_all_trades
from inputs import exposure_table,currency_table, contract_size_table, EXCLUSION_LIST, EXPORT_FOLDER, MIN_SCALP
import yfinance as yf
import matplotlib.pyplot as plt
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', None)  # Show all columns
pd.set_option('display.width', 1000)  # Increase width to fit your screen
pd.set_option('display.expand_frame_repr', False)  # Prevent wrapping
pd.set_option('display.max_colwidth', None)  # Show full content of each column


# Todo
# in analyse trades, use pd.Dataframe on a list of dictionaries and get rid of the bulk .append usage which is stupid

class PositionKeeper:
    """
    Designed to keep track of unrealised and realised positions for a single ticker on a trade by trade basis.
    Can also mark to market for open positions.
    Pnl includes contract size but exposure and market value is in contract units.
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

    def mark_to_market(self, update_timestamp = False):
        # mark to market for open position otherwise do nth
        market_price = get_last_price(self.ticker)
        # all the error handling is done in get_last_price so it just returns None if error
        if market_price is not None:
            self.last_price = market_price
            self.update_stats()
            # update_timestamp is for PL/Exposure plotting to be more chronological
            if update_timestamp:
                hk_time = datetime.now().replace(microsecond=0)
                self.timestamp = hk_time.astimezone(pytz.timezone("Asia/Hong_Kong"))


    def get_position_info(self):
        # nice script to return output in formatted way
        return {
            "timestamp": self.timestamp,
            "exposure": self.exposure,
            "last_price": self.last_price,
            "avg_price": self.avg_price,
            "market_value": self.market_value,
            "realised_pnl": round(float(self.realised_pnl),2),
            "unrealised_pnl": round(float(self.unrealised_pnl),2),
            "total_pnl": round(float(self.realised_pnl + self.unrealised_pnl),2)
        }
def get_contract_size(contract_spec = None, currency_spec = None, ticker = ""):
    if ticker.split()[0] in contract_spec:
        contract_size = contract_spec[ticker.split()[0]]
    # contract size default for HK stocks
    elif len(ticker) == 4 and ticker.isdigit():
        contract_size = 1 / currency_spec["USDHKD"]
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
        if len(manual_df) == 0:
            return all_trades
        print(f"Found manual_trades.csv with {len(manual_df)} trades, injecting with UID 0")
        # add columns to fit all_trades
        first_trade_date = all_trades["date_long"].iloc[-1]
        manual_df["date_long"] = first_trade_date
        manual_df["UID"] = 0
        manual_df["contract_size"] = manual_df.apply(
            lambda x: get_contract_size(contract_size_table, currency_table, x.ticker), axis=1)

        # concat the manual trades with all trades and dump
        all_trades = pd.concat([all_trades, manual_df], ignore_index=True).sort_values(by="date_long", ascending=False)
        all_trades = all_trades.reset_index(drop=True)

        # redump the new all_trades which includes manual_trades
        all_trades.to_csv(file_location + r"\all_trades.csv", index=False)
        manual_df.to_csv(file_location + r"\backups\manual_trades" + f"{datetime.now().strftime("%Y_%m_%d")}"+ ".csv", index=False)
    return all_trades


# need to add a way for my script to differentiate between closed positions and open positions, in chronological order
def analyse_trades(all_trades = pd.DataFrame(), file_location = r""):
    """
    Takes an all_trades df, and analysis pnl by feeding trades into
    a PositionKeeper class which will keep track of the exposure, unrealised pnl and realised pnl.
    Groups the outputs into all_pnl which can be stored and reviewed further.
    """
    tickers = all_trades.ticker.unique()
    tickers = [ticker for ticker in tickers if ticker not in EXCLUSION_LIST]
    all_tickers, open_pnl, close_pnl, open_quantity, open_price, open_notional, last_price, last_date = [],[],[],[],[],[],[],[]
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
        # for open positions, mark to market
        if ticker_position.exposure != 0:
            ticker_position.mark_to_market(update_timestamp=False)

        # retrieve the output of PositionKeeper
        ticker_output = ticker_position.get_position_info()

        # aggregate the per ticker output of unrealised and realised PL
        all_tickers.append(ticker)
        open_pnl.append(ticker_output["unrealised_pnl"])
        close_pnl.append(ticker_output["realised_pnl"])
        open_quantity.append(ticker_output["exposure"])
        open_price.append(ticker_output["avg_price"])
        open_notional.append(ticker_output["market_value"] * contract_size)
        last_price.append(ticker_output["last_price"])
        last_date.append(ticker_output["timestamp"])

    all_pnl = pd.DataFrame(
        {'ticker' : all_tickers,
         'open_pnl': open_pnl,
         'scalp_pnl': close_pnl,
         'open_quantity' : open_quantity,
         'open_price' : open_price,
         'open_notional' : open_notional,
         'last_price' : last_price,
         'last_trade' : last_date
         })

    # sort by absolute PL
    all_pnl.insert(1, "all_pnl", all_pnl["open_pnl"] + all_pnl["scalp_pnl"])
    all_pnl["abs_all_pnl"] = abs(all_pnl["all_pnl"])
    all_pnl = all_pnl.sort_values(by = "abs_all_pnl", ignore_index = True, ascending = False)
    # remove all trades with < MIN SCALP PNL and no open position
    all_pnl = all_pnl.loc[~((all_pnl["abs_all_pnl"]<MIN_SCALP) & (all_pnl["open_quantity"] == 0))]
    all_pnl = all_pnl.drop(columns=["abs_all_pnl"])
    all_pnl.to_csv(file_location + r"\all_summary.csv", index=False)

    # split into open df and output it
    open_df = all_pnl.loc[all_pnl["open_quantity"] != 0].reset_index(drop = True)
    print(open_df, f"\nTotal Open PL is {round(all_pnl["open_pnl"].sum(), 1)}\n"
                   f"Total Scalp PL is {round(all_pnl["scalp_pnl"].sum(), 1)}")
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
        open_summary["exposure"] = open_summary.apply(lambda x: exposure_table.get(x.ticker.split()[0])[0], axis=1)
        open_summary["beta"] = open_summary.apply(lambda x: exposure_table.get(x.ticker.split()[0])[1], axis=1)
    except TypeError:
        print("Some ticker not in exposure_table, fix to see exposure breakdown")
        return None
    exposure_list = open_summary.exposure.unique()
    exposure_notional = []
    exposure_nominal = []
    components = []
    for exposure in exposure_list:
        temp = open_summary[open_summary["exposure"] == exposure]
        exposure_notional.append(round(sum(temp["open_notional"]*temp["beta"]), 1))
        exposure_nominal.append(round(sum(temp["open_notional"]), 1))
        components.append(temp["ticker"].unique())
    exposure_df = pd.DataFrame(
        {
            "exposure" : exposure_list,
            "notional" : exposure_notional,
            "nominal" : exposure_nominal,
            "components" : components,
        }
    )
    print(exposure_df)

    # compute equity and XAU exposures and make some output prints about allocation
    # allocations assume IBKR account holds minimal cash balances are inefficient. Rather just deploy long/short into SGOV.
    equity_exposure = exposure_df.loc[~exposure_df["exposure"].isin(["MM fund", "XAU", "USDCNH", "DV01"])].notional.sum()
    total_nominal = exposure_df.loc[~exposure_df["exposure"].isin(["USDCNH", "DV01"])].nominal.sum()
    print("-----------------------------------------------------------")
    print(f"Equity beta {round(equity_exposure / total_nominal * 100, 1)}%, ")
    if "XAU" in exposure_df["exposure"].unique():
        xau_exposure = exposure_df.loc[exposure_df["exposure"] == "XAU"].notional.sum()
        print(f"XAU allocation {round(xau_exposure/total_nominal*100, 1)}%")
    if "MM fund" in exposure_df["exposure"].unique():
        cash_exposure = exposure_df.loc[exposure_df["exposure"] == "MM fund"].notional.sum()
        print(f"Cash allocation {round(cash_exposure/total_nominal*100, 1)}%")
    print("-----------------------------------------------------------")
    return exposure_df

def get_last_price(ticker = None):
    """
    Wrapper of yfinance func yf.download to extract the last traded price of a ticker.
    """
    # return the most recent closing price of us stock or future
    ib_yf_mapping = {
        # "ticker" : ["yfinance=F", carry rate, expiry date]
        "UC DEC'25": ["USDCNH=X" , -0.024, "2025/12/15"],
        "ZT": ["ZT=F"],
        "ZF": ["ZF=F"],
        "ZN": ["ZN=F"],
        "TN": ["TN=F"],
        "ZB": ["ZB=F"],
        "UB": ["UB=F"],
        "CL": ["CL=F"],
    }
    # default compound factor is 1 because no need to account for interest
    compound_factor = 1
    if " " in ticker:
        ticker_key =  ticker.split()[0] + " " + ticker.split()[1]
        # if it's a cme future, no need to specify the expiration month due to no efp.
        if ticker.split()[0] in ib_yf_mapping.keys():
            ticker = ib_yf_mapping[ticker.split()[0]][0]
        # if it's a future where interest needs to be accounted for
        elif ticker_key in ib_yf_mapping.keys():
            ticker = ib_yf_mapping[ticker_key][0]
            if len(ib_yf_mapping[ticker_key]) == 3:
                days_to_expiry = (datetime.strptime(ib_yf_mapping[ticker_key][2], "%Y/%m/%d") - datetime.now()).days
                compound_factor = (1+ib_yf_mapping[ticker_key][1]/365)**days_to_expiry
        # no future able to be resolved
        else:
            print(f"Future not resolved for {ticker}, not marking to market")
            return None

    # modify script to work for HK tickers
    if len(ticker) == 4 and ticker.isdigit():
        ticker = ticker + ".HK"

    stock_data = yf.download(ticker, period="5d", auto_adjust=True)
    try:
        return stock_data.tail(1)["Close"].values[0][0]*compound_factor
    except:
        print(f"Something went wrong with finding last price for {ticker}, defaulting to open_price")
        print(stock_data)
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
        contract_size = ticker_trades.loc[0, "contract_size"]
        # initiate PositionKeeper
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
        print(f"\nTotal Open PL is {ticker_output_df["unrealised_pnl"].iloc[-1]}"
              f"\nTotal Scalp PL is {ticker_output_df["realised_pnl"].iloc[-1]}"
              f"\nTotal PL is {ticker_output_df["total_pnl"].iloc[-1]}\n")

        # plot the PL and exposure over time
        # Create the plot
        fig, ax1 = plt.subplots(figsize=(10, 6))

        # Plot total_pnl on the left y-axis (ax1)
        ax1.plot(ticker_output_df['timestamp'], ticker_output_df['total_pnl'], label='Total PNL', color='magenta', linewidth=2)
        ax1.set_xlabel('Timestamp')
        ax1.set_ylabel('PNL (USD)', color='magenta')
        ax1.tick_params(axis='y', labelcolor='magenta')
        ax1.grid(True)

        # Create a second y-axis for exposure on the right
        ax2 = ax1.twinx()
        ax2.plot(ticker_output_df['timestamp'], ticker_output_df['exposure'], label='Exposure', color='green', linewidth=2)
        ax2.set_ylabel('Exposure (units)', color='green')
        ax2.tick_params(axis='y', labelcolor='green')

        # Add title and legend
        plt.title(f'{ticker}')
        fig.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=2)

        # Rotate x-axis labels and adjust layout
        ax1.tick_params(axis='x', rotation=45)
        fig.tight_layout()

        # Show the plot
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


def other_functions(all_trades = None, file_location = None):
    """
    This function runs at the end of the program, giving the user a few extra functions to review their trades.
    """
    # at the end of the routine ask the user for other things that they may want to do
    unique_tickers = all_trades["ticker"].unique()
    unique_tickers = [x for x in unique_tickers if x not in EXCLUSION_LIST]
    print(unique_tickers)

    function_loop = True
    while function_loop:
        ticker_input = input(
            "Type ticker to see trades. e.g NVDA\n"
            "Other functions:\n"
            "\t1 to count trades in the current month\n"
            "\t2 to see trade summary per ticker\n"
            "\t3 to see history of tickers traded\n"
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
            print(all_pnl, f"\nTotal Scalp PL is {round(all_pnl["scalp_pnl"].sum(), 1)}")
        # show ticker history
        elif ticker_input == "3":
            ticker_history(all_trades)
        # show trades associated with the inputed ticker
        else:
            get_ticker_trades(all_trades, ticker_input)
    print("Thanks for taking time to review trades, exiting")
    return


if __name__ in "__main__":
    export_location = EXPORT_FOLDER
    # perform all the analytics
    raw_trades = get_all_trades()
    clean_trades = store_trades(raw_trades, export_location)
    all_trades = manual_trades(clean_trades, export_location)
    open_summary = analyse_trades(all_trades, export_location)
    exposure_df = exposure_breakdown(open_summary, exposure_table)
    other_functions(all_trades, export_location)





