import imaplib
import email
from datetime import datetime, timedelta
import calendar, pytz
import pandas as pd
import numpy as np
import os
from trade_counter import connect_imap, count_trades
from credentials import export_folder
import yfinance as yf
pd.options.mode.chained_assignment = None  # default='warn'
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', None)  # Show all columns
pd.set_option('display.width', 1000)  # Increase width to fit your screen
pd.set_option('display.expand_frame_repr', False)  # Prevent wrapping
pd.set_option('display.max_colwidth', None)  # Show full content of each column


# Set Variables

START_DATE = datetime(2023, 1, 1)
MIN_SCALP = 100
EXCLUSION_LIST = ["USD.HKD", "AUD.USD", "EUR.USD", "USD.CNH"]


# Todo
# find a way to clean up future symbols so the identifier is not like UB Sep'25 @CBOT, remove the exc
# in analyse trades, use pd.Dataframe on a list of dictionaries and get rid of the bulk .append usage which is stupid

class PositionKeeper:
    # Designed to keep track of unrealised and realised positions for a single ticker on a trade by trade basis
    # Can also mark to market
    # Can be changed to manage exchange dual listings through adding a self.position dictionary variable
    # pnl includes contract size but exposure and market value is in contract units
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

    def mark_to_market(self):
        # mark to market for open position otherwise do nth
        market_price = get_last_price(self.ticker)
        # all the error handling is done in get_last_price so it just returns None if error
        if market_price is not None:
            self.last_price = market_price
            self.update_stats()

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

def store_trades(start_date = START_DATE, all_trades = None, file_location = None):
    if file_location is None:
        print("No file location")
        return "0"
    currency_table = {
        "EURUSD" : 1.09,
        "USDCNH" : 7.23,
    }
    contract_size_table = {
        "ZT": 2000,
        "ZF": 1000,
        "ZN": 1000,
        "TN": 1000,
        "ZB": 1000,
        "UB": 1000,
        "MES" : 5,
        "M2K" : 5,
        "MNQ" : 2,
        "SOFR3" : 2500,
        "GBS" : 1000*currency_table["EURUSD"],
        "UC" : 100000/currency_table["USDCNH"],
        "CL" : 1000,
    }
    imap = connect_imap()
    imap.select('Inbox')
    result, data = imap.search(None, 'FROM "IB Trading Assistant"' )
    #fetch all trades on the account, store in a csv, and on reruns of the script, just append to the csv instead of recreating the database

    id_list = data[0].split()
    id_list.reverse()
    for id in id_list:
        result, data = imap.fetch(id, '(RFC822)')
        msg = email.message_from_string(data[0][1].decode('utf-8'))


        # remove the english of timezone to input into timezone aware datetime object
        new_msg = " ".join(msg['Date'].split(" ")[:-1])
        date_long = datetime.strptime(new_msg, "%a, %d %b %Y %H:%M:%S %z")
        date_long = date_long.astimezone(pytz.timezone("Asia/Hong_Kong"))

        subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))
        if datetime(date_long.year, date_long.month, date_long.day) < start_date:
            break
        # create the trade item
        print(date_long, subject)
        subject_split = subject.split()
        quantity = round((1 if subject_split[0] == "BOUGHT" else -1) * float(subject_split[1].replace(",","")),0)
        ticker = ''
        for x in range(2, subject_split.index("@")):
            ticker += subject_split[x] + " "
        ticker = ticker[:-1]
        if ticker.split()[0] in contract_size_table:
            contract_size = contract_size_table[ticker.split()[0]]
        else:
            contract_size = 1
        trade = pd.DataFrame({
            "date_short": [date_long.strftime("%Y/%m/%d")],
            "ticker": [ticker],
            "quantity": [quantity],
            "price": [float(subject_split[subject_split.index("@") + 1])],
            "contract_size" : [contract_size],
            "trade_type": "AUTO",
        })

        if all_trades is None:
            all_trades = trade
        else:
            all_trades = pd.concat([trade,all_trades], ignore_index = True)
    all_trades["temp"] = [datetime.strptime(date, "%Y/%m/%d") for date in all_trades.date_short]
    all_trades = all_trades.sort_values(by=["temp"], ascending=False, ignore_index=True)
    all_trades = all_trades.drop(columns = ["temp"])

    all_trades.to_csv(file_location + r"\all_trades.csv", index = False)
    all_trades.to_csv(file_location + r"\backups\all_trades"+f"{datetime.now().strftime("%Y_%m_%d")}"+ ".csv", index=False)
    return all_trades

def find_trades(file_location):
    if os.path.isfile(file_location+r"\all_trades.csv"):
        all_trades = pd.read_csv(file_location+r"\all_trades.csv")
        last_trade_date = datetime.strptime(all_trades.date_short.iloc[0],"%Y/%m/%d")
        num_trades = len(all_trades)
        print(f"trade database found with {num_trades} trades up to {last_trade_date}\n"
              f"Checking for new trades")

        all_trades = store_trades(last_trade_date+timedelta(days=1), all_trades, file_location)
        print(f"found {len(all_trades)-num_trades} new trades")
    else:
        print("no trades found, creating database")
        all_trades = store_trades(all_trades = None,file_location = file_location)
        print(f"{len(all_trades)} new trades have been added to the trade database")
    return all_trades

# need to add a way for my script to differentiate between closed positions and open positions, in chronological order
def analyse_trades(all_trades = None):
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
            ticker_position.add_trade(row.date_short, row.price, row.quantity)
            # recompute unrealised and realised pnl based on market value
            ticker_position.update_stats()
        # for open positions, mark to market
        if ticker_position.exposure != 0:
            ticker_position.mark_to_market()

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
    all_pnl.to_csv(file_location + r"\all_summary.csv", index=False)

    # split into open/close df
    close_df = all_pnl.loc[all_pnl["open_quantity"] == 0].reset_index(drop = True)
    open_df = all_pnl.loc[all_pnl["open_quantity"] != 0].reset_index(drop = True)

    # clean up and sort close/open df
    close_df = close_df.sort_values(by="abs_all_pnl", ignore_index=True, ascending=False)
    close_df = close_df[close_df["abs_all_pnl"] >= MIN_SCALP]
    close_df = close_df.drop(columns = ["open_pnl", "open_quantity", "open_notional", "all_pnl", "abs_all_pnl"])
    open_df = open_df.drop(columns = ["abs_all_pnl"])

    # exposure breakdown of open trades
    exposure_df = exposure_breakdown(open_df)

    # save the csv locally
    open_df.to_csv(file_location + r"\open_summary.csv", index=False)
    close_df.to_csv(file_location + r"\scalp_summary.csv", index=False)

    print(open_df, f"\nTotal Open PL is {round(all_pnl["open_pnl"].sum(), 1)}\n"
                   f"Total Scalp PL is {round(all_pnl["scalp_pnl"].sum(), 1)}")
    print(exposure_df)
    print("-----------------------------------------------------------\n")
    return


def manual_trades(file_location):
    # check for manual trade file, inserting trades into the all_trades csv of trade_type = manual
    if os.path.isfile(file_location + r"\manual_trades.csv") & os.path.isfile(file_location + r"\all_trades.csv"):
        manual_df = pd.read_csv(file_location + r"\manual_trades.csv")
        trade_df = pd.read_csv(file_location + r"\all_trades.csv")
        if len(manual_df) == 0:
            return
        print(f"found manual_trades.csv with {len(manual_df)} trades")
        manual_df["date_short"] = [datetime.strptime(date, "%d/%m/%Y") for date in manual_df["date_short"]]
        trade_df["date_short"] = [datetime.strptime(date, "%Y/%m/%d") for date in trade_df["date_short"]]
        print(manual_df)
        if input("manual trades look like this, type y to confirm:\n").lower() == "y":
            print("inserting into all_trades.csv and removing from manual_trades.csv, rerun program")
            df = pd.concat([manual_df, trade_df], ignore_index=True).sort_values(by="date_short", ascending=False,                                                              ignore_index=True)
            df["date_short"] = [x.strftime("%Y/%m/%d") for x in df["date_short"]]
            df.to_csv(file_location + r"\all_trades.csv", index=False)
            manual_df.to_csv(file_location + r"\backups\manual_trades" + f"{datetime.now().strftime("%Y_%m_%d")}"+ ".csv", index=False)
            manual_df = manual_df[0:0]
            manual_df.to_csv(file_location + r"\manual_trades.csv", index=False)
            exit()
        else:
            print("nothing done")
    return


def exposure_breakdown(df = None):
    # a nice learning point from this line is that direct assignment of dataframes in python does not create a new dataframe,
    # it actually passes the underlying objects of the initial dataframe into the new object
    open_summary = df.copy()
    exposure_table = {
        "AMD" : ["US", 1.5],
        "ARM": ["US", 1.5],
        "INDA": ["IN", 1],
        "BABA": ["CH", 1],
        "SMCI": ["US", 2],
        "TCEHY": ["CH", 1],
        "ASPI": ["US", 3],
        "SOFR3": ["DV01", 1/10000],
        "GBS" : ["DV01", 1.86/10000],
        "NVDA" : ["US", 1.5],
        "SGOV": ["MM fund", 1],
        "SPY" : ["US", 1],
        "VOO": ["US", 1],
        "QQQ": ["US", 1.3],
        "QQQM": ["US", 1.3],
        "UC" : ["USDCNH", 1],
        "ZT": ["DV01", 1.8/10000],
        "ZF": ["DV01", 3.8/10000],
        "ZN": ["DV01", 5.8/10000],
        "TN": ["DV01", 7.7/10000],
        "ZB": ["DV01", 10.8/10000],
        "UB": ["DV01", 16.2/10000],
        "GLD" :["XAU", 1],
        "CL" : ["CL", 1],
    }
    try:
        open_summary["exposure"] = open_summary.apply(lambda x: exposure_table.get(x.ticker.split()[0])[0], axis=1)
        open_summary["beta"] = open_summary.apply(lambda x: exposure_table.get(x.ticker.split()[0])[1], axis=1)
    except TypeError:
        print("Some ticker not in exposure_table, fix to see exposure breakdown")
        return None

    exposure_list = open_summary.exposure.unique()
    exposure_notional = []
    components = []
    for exposure in exposure_list:
        temp = open_summary[open_summary["exposure"] == exposure]
        exposure_notional.append(sum(temp["open_notional"]*temp["beta"]))
        components.append(temp["ticker"].unique())
    exposure_df = pd.DataFrame(
        {
            "exposure" : exposure_list,
            "notional" : exposure_notional,
            "components" : components,
        }
    )
    return exposure_df

def get_last_price(ticker = None):
    # return the most recent closing price of us stock or future
    ib_yf_mapping = {
        # "ticker" : ["yfinance=F", carry rate, expiry date]
        "UC Sep'25": ["USDCNH=X" , -0.028, "2025/9/16"],
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
    stock_data = yf.download(ticker, period="3d", auto_adjust=True)
    try:
        return stock_data.tail(1)["Close"].values[0][0]*compound_factor
    except:
        print(f"Something went wrong with finding last price for {ticker}, defaulting to open_price")
        print(stock_data)
        return None

def get_ticker_trades(all_trades = None, ticker = None):
    unique_tickers = all_trades["ticker"].unique()
    # first try to resolve the ticker
    if " " not in ticker:
        # ticker is a stock so make it all upper case
        ticker = ticker.upper()

    if ticker in unique_tickers:
        ticker_trades = all_trades.loc[all_trades.ticker == ticker].iloc[::-1].reset_index(drop=True)
        contract_size = ticker_trades.loc[0, "contract_size"]
        # initiate PositionKeeper
        ticker_position = PositionKeeper(ticker, contract_size)
        # feed in trades
        ticker_output = []
        for index, row in ticker_trades.iterrows():
            ticker_position.add_trade(row.date_short, row.price, row.quantity)
            ticker_position.update_stats()
            ticker_output.append(ticker_position.get_position_info())
        # mark to market for open positions
        if ticker_position.exposure != 0:
            print("marking to market for open position")
            ticker_position.mark_to_market()
            ticker_output.append(ticker_position.get_position_info())
        ticker_output_df = pd.DataFrame(ticker_output)
        print(ticker_output_df)
        print(f"\nTotal Open PL is {ticker_output_df["unrealised_pnl"].iloc[-1]}"
              f"\nTotal Scalp PL is {ticker_output_df["realised_pnl"].iloc[-1]}"
              f"\nTotal PL is {ticker_output_df["total_pnl"].iloc[-1]}\n")
    else:
        print("Ticker not in unique tickers")
    return

def ticker_history(all_trades = None):
    print("testing counting trades")
    df = all_trades.copy()
    df = df[~df["ticker"].isin(EXCLUSION_LIST)]
    df["ticker"] = df.apply(lambda x: x.ticker.split()[0], axis = 1)
    df["date_long"] = df.apply(lambda x: datetime.strptime(x.date_short, "%Y/%m/%d"), axis =1)
    df.set_index("date_long", inplace = True, drop = True)
    print(df.groupby([df.index.year, df.index.month])["ticker"].unique())


def other_functions(all_trades = None, file_location = None):
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
            "\t2 to see scalp summary\n"
            "\t3 to see history of tickers traded\n"
            "\t4 to wipe the most recent day of recorded trades\n"
        )
        # no command was given so exit
        if ticker_input == "":
            function_loop = False
        # count trades
        elif ticker_input == "1":
            count_trades()
        # show scalp summary
        elif ticker_input == "2":
            close_df = pd.read_csv(file_location+r"\scalp_summary.csv")
            print(close_df, f"\nTotal Scalp PL is {round(close_df["scalp_pnl"].sum(), 1)}")
        # show ticker history
        elif ticker_input == "3":
            ticker_history(all_trades)
        # delete most recent day of recorded trades to repull correct trades on next script launch
        elif ticker_input == "4":
            last_trade_date = all_trades.date_short.iloc[0]
            all_trades = all_trades[all_trades["date_short"] != last_trade_date].reset_index(drop = True)
            print("new trade database looks like this")
            print(all_trades.head(10))
            all_trades.to_csv(file_location + r"\all_trades.csv", index=False)
            all_trades.to_csv(
                file_location + r"\backups\all_trades" + f"{datetime.now().strftime("%Y_%m_%d")}" + ".csv", index=False)
            function_loop = False
        # show trades associated with the inputed ticker
        else:
            get_ticker_trades(all_trades, ticker_input)
    print("trade review finished, exiting.")
    return


if __name__ in "__main__":
    file_location = export_folder

    # perform all the analytics
    all_trades = find_trades(file_location)
    manual_trades(file_location)
    analyse_trades(all_trades)
    other_functions(all_trades, file_location)





