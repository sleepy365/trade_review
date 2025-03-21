import imaplib
import email
from datetime import datetime, timedelta
import calendar
import pandas as pd
import numpy as np
import os
from trade_counter import connect_imap
from credentials import export_folder
import yfinance as yf
pd.options.mode.chained_assignment = None  # default='warn'
pd.set_option('display.max_rows', 500)


# Set Variables

START_DATE = datetime(2023, 1, 1)
MIN_SCALP = 100


def store_trades(start_date = START_DATE, all_trades = None, file_location = None):
    if file_location is None:
        print("No file location")
        return "0"
    currency_table = {
        "EURUSD" : 1.09,
        "USDCNH" : 7.23,
    }
    contract_size_table = {
        "ZT" : 2000,
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
    }
    imap = connect_imap()
    imap.select('Inbox')
    result, data = imap.search(None, 'FROM "IB Trading Assistant"' )
    #fetch all trades on the account, store in a csv, and on reruns of the script, just append to the csv instead of recreating the database

    id_list = data[0].split()
    id_list.reverse()
    for id in id_list:
        result, data = imap.fetch(id, '(RFC822)')
        raw_email = data[0][1]  # Returns a byte
        msg = email.message_from_string(data[0][1].decode('utf-8'))
        date_tuple = email.utils.parsedate_tz(msg['Date'])
        date_short = f'{date_tuple[0]}/{date_tuple[1]}/{date_tuple[2]}'
        # date_obj has no information about hour and minutes, if want to add the precision might create a bug
        date_obj = datetime.strptime(date_short, "%Y/%m/%d")
        subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))
        if date_obj < start_date:
            break
        # create the trade item
        print(date_short, subject)
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
            "date_short": [date_short],
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
    exclusion_list = ["USD.HKD", "AUD.USD", "EUR.USD", "USD.CNH"]
    tickers = [ticker for ticker in tickers if ticker not in exclusion_list]
    open_tickers, open_quantity, open_price, open_notional, last_price = [],[],[],[],[]
    close_tickers, scalp_pnl, close_date = [],[],[]
    for ticker in tickers:
        temp = all_trades[all_trades.ticker == ticker].reset_index(drop=True)
        temp_labeled = label_trades(temp)
        contract_size = temp_labeled.loc[0,"contract_size"]
        # check if position has been closed
        if 'close' in temp_labeled["flag"].values:
            i = temp_labeled[temp_labeled["flag"] == "close"].index[0]
            close_date.append(temp_labeled.loc[i,"date_short"])

            temp_open = temp_labeled.loc[:i-1,]
            temp_close = temp_labeled.loc[i:,]

            # analyse close trades
            pnl = round(-sum(temp_close["quantity"] * temp_close["price"])*contract_size,2)
            close_tickers.append(ticker)
            scalp_pnl.append(pnl)

            # if i != 0, it means there is some open position
            if i != 0:
                qty = temp_open.quantity.sum()
                px = sum(temp_open["quantity"]*temp_open["price"])/qty
                open_tickers.append(ticker)
                open_quantity.append(qty)
                open_price.append(px)
                open_notional.append(round(abs(px*qty*contract_size),0))
                ticker_px = get_last_price(ticker)
                if ticker_px is not None:
                    last_price.append(round(ticker_px, 2))
                else:
                    last_price.append(temp_labeled.loc[0,"price"])

        # there is only open position
        else:
            # analyse open trades
            qty = temp_labeled.quantity.sum()
            px = round(sum(temp_labeled["quantity"]*temp_labeled["price"])/qty,4)
            open_tickers.append(ticker)
            open_quantity.append(qty)
            open_price.append(px)
            open_notional.append(round(abs(px * qty * contract_size), 0))
            ticker_px = get_last_price(ticker)
            if ticker_px is not None:
                last_price.append(round(ticker_px, 2))
            else:
                last_price.append(temp_labeled.loc[0, "price"])

    open_df = pd.DataFrame(
        {'ticker' : open_tickers,
         'open_quantity' : open_quantity,
         'open_price' : open_price,
         'open_notional' : open_notional,
         'last_price' : last_price,
         }
    )
    close_df = pd.DataFrame(
        {'tickers' : close_tickers,
         'scalp_pnl' : scalp_pnl,
         'date_closed' : close_date,
         }
    )
    # sort open_df by notional traded and closed trades by absolute PL
    open_df = open_df.sort_values(by = "open_notional", ignore_index = True, ascending = False)
    open_df["open_pnl"] = round(np.sign(open_df["open_quantity"]) * open_df["open_notional"] * ((open_df["last_price"] / open_df["open_price"])-1), 2)

    close_df["abs_scalp_pnl"] = abs(close_df["scalp_pnl"])
    close_df = close_df.sort_values(by="abs_scalp_pnl", ignore_index=True, ascending=False)
    close_df = close_df[close_df["abs_scalp_pnl"] >= MIN_SCALP]
    close_df = close_df.drop(columns = ["abs_scalp_pnl"])

    # exposure breakdown of open trades
    exposure_df = exposure_breakdown(open_df)
    open_df = open_df.drop(columns = ["open_notional"])

    open_df.to_csv(file_location + r"\open_summary.csv", index=False)
    close_df.to_csv(file_location + r"\scalp_summary.csv", index=False)

    print(open_df, f"\nTotal Open PL is {round(open_df["open_pnl"].sum(), 1)}\n"
                   f"Total Scalp PL is {round(close_df["scalp_pnl"].sum(), 1)}")
    print(exposure_df)
    if input("type y to see scalp breakdown ?\n").lower() == "y":
        print(close_df, f"\nTotal Scalp PL is {round(close_df["scalp_pnl"].sum(), 1)}")
    return


def label_trades(temp = None):
    df = temp.reset_index(drop = True)
    df["flag"] = "open"
    # loop from the first last item
    num_trades = len(df)
    if num_trades == 1:
        return df
    # more than 1 trade
    open_qty = df.loc[num_trades-1,"quantity"]
    for x in range(1, num_trades):
        i = num_trades-x-1
        open_qty += df.loc[i,"quantity"]
        if open_qty == 0:
            df.loc[i, "flag"] = "close"
    return df

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
    }

    open_summary["exposure"] = open_summary.apply(lambda x: exposure_table.get(x.ticker.split()[0])[0], axis=1)
    open_summary["beta"] = open_summary.apply(lambda x: exposure_table.get(x.ticker.split()[0])[1], axis=1)

    exposure_list = open_summary.exposure.unique()
    exposure_notional = []
    components = []
    for exposure in exposure_list:
        temp = open_summary[open_summary["exposure"] == exposure]
        exposure_notional.append(sum(temp["open_notional"]*temp["beta"]*np.sign(temp.open_quantity)))
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
    # pass for futures
    ib_yf_mapping = {
        "GBS" : "FGBS=F",
    }
    if " " in ticker:
        ticker_split = ticker.split()[0]
        if ticker_split in ib_yf_mapping.keys():
            ticker = ib_yf_mapping[ticker_split]
        else:
            print(f"Future not resolved for {ticker}, defaulting to open_price")
            return None
    try:
        stock_data = yf.download(ticker, period = "7d", auto_adjust=True)
        return stock_data.tail(1)["Close"].values[0][0]
    except:
        print(f"Something went wrong with finding last price for {ticker}, defaulting to open_price")
        return None

def get_ticker_trades(all_trades = None, ticker = None):
    unique_tickers = all_trades["ticker"].unique()
    # first try to resolve the ticker
    if " " not in ticker:
        # ticker is a stock so make it all upper case
        ticker = ticker.upper()


    if ticker in unique_tickers:
        temp = all_trades[all_trades["ticker"] == ticker]
        temp_labeled = label_trades(temp)
        print(temp_labeled)
        contract_size = temp_labeled.loc[0, "contract_size"]
        # check if position has been closed
        trade_closed = False
        if 'close' in temp_labeled["flag"].values:
            trade_closed = True
            i = temp_labeled[temp_labeled["flag"] == "close"].index[0]

            temp_open = temp_labeled.loc[:i - 1, ]
            temp_close = temp_labeled.loc[i:, ]

            # analyse close trades
            temp_scalp_pnl = round(-sum(temp_close["quantity"] * temp_close["price"]) * contract_size, 2)

            # if i != 0, it means there is some open position
            if i != 0:
                temp_open_quantity = temp_open.quantity.sum()
                temp_open_price = sum(temp_open["quantity"] * temp_open["price"]) / temp_open_quantity
                temp_open_notional = round(abs(temp_open_price * temp_open_quantity * contract_size), 0)
                ticker_px = get_last_price(ticker)
                if ticker_px is not None:
                    temp_last_price = round(ticker_px, 2)
                else:
                    temp_last_price = temp_labeled.loc[0, "price"]
                temp_open_pl = round(np.sign(temp_open_quantity) * temp_open_notional * ((temp_last_price / temp_open_price)-1), 2)
                print(f"\nTotal Open PL is {temp_open_pl}\n"
                    f"Total Scalp PL is {temp_scalp_pnl}")
            if i == 0:
                print(f"Total Scalp PL is {temp_scalp_pnl}")

        # there is only open position
        else:
            # analyse open trades
            temp_open_quantity = temp_labeled.quantity.sum()
            temp_open_price = round(sum(temp_labeled["quantity"] * temp_labeled["price"]) / temp_open_quantity, 4)

            temp_open_notional = round(abs(temp_open_price * temp_open_quantity * contract_size), 0)
            ticker_px = get_last_price(ticker)
            if ticker_px is not None:
                temp_last_price = round(ticker_px, 2)
            else:
                temp_last_price = temp_labeled.loc[0, "price"]
            temp_open_pl = round(
                np.sign(temp_open_quantity) * temp_open_notional * ((temp_last_price / temp_open_price) - 1), 2)
            print(f"\nTotal Open PL is {temp_open_pl}\n")
    else:
        print("Ticker not in unique tickers")
    return

def ticker_history(all_trades = None):
    print("testing counting trades")
    df = all_trades.copy()
    exclusion_list = ["USD.HKD", "AUD.USD", "EUR.USD", "USD.CNH"]
    df = df[~df["ticker"].isin(exclusion_list)]
    df["ticker"] = df.apply(lambda x: x.ticker.split()[0], axis = 1)
    df["date_long"] = df.apply(lambda x: datetime.strptime(x.date_short, "%Y/%m/%d"), axis =1)
    df.set_index("date_long", inplace = True, drop = True)
    print(df.groupby([df.index.year, df.index.month])["ticker"].unique())






def other_functions(all_trades = None, file_location = None):
    # at the end of the routine ask the user for other things that they may want to do
    unique_tickers = all_trades["ticker"].unique()
    print(unique_tickers)

    function_loop = True
    while function_loop:
        ticker_input = input(
            "Type ticker to see trades. e.g NVDA\n"
            "Other functions:\n"
            "\t1 to wipe the most recent day of recorded trades\n"
            "\t2 to see history of tickers traded\n"
        )
        if ticker_input == "":
            function_loop = False
        elif ticker_input == "1":
            last_trade_date = all_trades.date_short.iloc[0]
            all_trades = all_trades[all_trades["date_short"] != last_trade_date].reset_index(drop = True)
            print("new trade database looks like this")
            print(all_trades.head(10))
            all_trades.to_csv(file_location + r"\all_trades.csv", index=False)
            all_trades.to_csv(
                file_location + r"\backups\all_trades" + f"{datetime.now().strftime("%Y_%m_%d")}" + ".csv", index=False)
            function_loop = False
        elif ticker_input == "2":
            ticker_history(all_trades)
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





