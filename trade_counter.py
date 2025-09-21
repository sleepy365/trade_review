import imaplib
import email
from email.header import decode_header
from datetime import datetime
import pytz
import calendar
from credentials import imap_host, imap_user, imap_pass
from inputs import EXCLUSION_LIST

import pandas as pd
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', None)  # Show all columns
pd.set_option('display.width', 1000)  # Increase width to fit your screen
pd.set_option('display.expand_frame_repr', False)  # Prevent wrapping
pd.set_option('display.max_colwidth', None)  # Show full content of each column

def connect_imap():
    # connect to host using SSL
    imap = imaplib.IMAP4_SSL(imap_host)
    ## login to server
    imap.login(imap_user, imap_pass)
    return imap

def get_all_trades():
    imap = connect_imap()
    imap.select('Inbox')
    result, email_bytes = imap.search(None, 'FROM "IB Trading Assistant"')
    email_ids = [item.decode('utf-8') for item in email_bytes]
    fetch_ids = ','.join(email_ids[0].split())


    result, data = imap.fetch(fetch_ids, '(RFC822.HEADER)')
    header_data = []
    for item in data:
        # Check for the expected tuple format with header data
        if isinstance(item, tuple) and len(item) == 2 and b'(RFC822.HEADER' in item[0]:
            # Extract message ID and header bytes
            msg_id_part, header_bytes = item
            # Message ID is the part before ' (RFC822.HEADER'
            msg_id = msg_id_part.decode().split(' (')[0]

            # Parse the header bytes
            msg = email.message_from_bytes(header_bytes)

            # Extract Date
            date_value = " ".join(msg['Date'].split(" ")[:-1])
            date_long = datetime.strptime(date_value, "%a, %d %b %Y %H:%M:%S %z")
            date_long = date_long.astimezone(pytz.timezone("Asia/Hong_Kong"))

            # extract subject
            subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))

            # Dictionary for Date and Subject and add to the header data
            email_headers = {
                'UID': msg_id,
                'Date': date_long,
                'Subject': subject}
            header_data.append(email_headers)
        # Skip closing parentheses or unexpected items
        elif item == b')':
            continue
        else:
            print(f"Skipping unexpected item: {item}")
    # Create a DataFrame
    raw_trades = pd.DataFrame(header_data, columns=['UID', 'Date', 'Subject'])
    raw_trades = raw_trades.sort_values(by="Date", ascending=False)
    raw_trades = raw_trades.reset_index(drop=True)
    return raw_trades

# counts trades and assumes sorted ids from most recent trade to oldest trade
def count_trades(raw_trades = pd.DataFrame(), exclusion_list = []):
    # look for trades After current month
    current_month = datetime.now().month
    current_year = datetime.now().year

    num_trades,unique_trades = 0, 0
    last_price, last_ticker, last_date = 0, 0, 0
    for index, row in raw_trades.iterrows():
        date_long = row.loc["Date"]
        subject = row.loc["Subject"]

        # get this month's trades
        if (date_long.month < current_month) or (date_long.year <current_year) :
            trade = "trade" if (num_trades - unique_trades) == 1 else "trades"
            print(f"There are {unique_trades} unique trades found in {calendar.month_name[current_month]} {current_year}."
                  f"\n{num_trades - unique_trades} {trade} have been filtered out.")
            break
        print(date_long, subject)
        subject_split = subject.split()
        # append to trade counter if trade not at the same price (assuming placed by the same order)
        if not(float(subject_split[subject_split.index("@") + 1]) == last_price and subject_split[2] == last_ticker and date_long.date() == last_date):
            # also exclude trades if it is in exclusion_list, use case is spot FX trades which should not be counted
            if subject_split[2] not in exclusion_list:
                unique_trades+=1
        last_price,last_ticker, last_date = float(subject_split[subject_split.index("@") + 1]), subject_split[2], date_long.date()
        num_trades+=1

if __name__ in "__main__":
    raw_trades = get_all_trades()
    count_trades(raw_trades, EXCLUSION_LIST)