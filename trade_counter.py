import imaplib
import email
from datetime import datetime
import pytz
import calendar
from credentials import imap_host, imap_user, imap_pass,export_folder
import time
import os
import pandas as pd

def connect_imap():
    # connect to host using SSL
    imap = imaplib.IMAP4_SSL(imap_host)
    ## login to server
    imap.login(imap_user, imap_pass)
    return imap

# turns out imap.search does not return a sorted id list based on email arrival time
def sort_imap_id(file_location):
    # check if existing UID - date map exists
    if os.path.isfile(file_location+r"\uid_date_map.csv"):
        uid_date_map = pd.read_csv(file_location+r"\uid_date_map.csv", parse_dates=["date_long"])
        # Convert DataFrame to dictionary for faster lookup
        uid_date_map = dict(zip(uid_date_map['uid'], uid_date_map['date_long']))
    else:
        uid_date_map = {}

    # time the sorting cuz it takes a while if no existing uid map
    start = time.time()
    imap = connect_imap()
    imap.select('Inbox')
    result, data = imap.search(None, 'FROM "IB Trading Assistant"' )

    # for each id, pull the email header for the date of trade
    id_list = data[0].split()
    date_list = []
    for id in id_list:
        # search the existing map for a match
        non_byte_id = str(id)
        if non_byte_id in uid_date_map:
            date_list.append(uid_date_map[non_byte_id])
        else:
            result, data = imap.fetch(id, '(RFC822.HEADER)')
            raw_email = data[0][1]                                 # Returns a byte
            msg = email.message_from_string(raw_email.decode('utf-8'))

            # remove the english of timezone to input into timezone aware datetime object
            new_msg = " ".join(msg['Date'].split(" ")[:-1])
            date_long = datetime.strptime(new_msg, "%a, %d %b %Y %H:%M:%S %z")
            date_long = date_long.astimezone(pytz.timezone("Asia/Hong_Kong"))
            date_list.append(date_long)
    # create a dataframe, sort it based on date long and save as new map
    uid_date_map = pd.DataFrame({
        "uid" : id_list,
        "date_long" : date_list,
    })
    uid_date_map = uid_date_map.sort_values(by="date_long", ascending=False).reset_index(drop=True)
    uid_date_map.to_csv(file_location + r"\uid_date_map.csv", index=False)

    end = time.time()
    print(f"Email sorting took {round(end-start,0)} seconds")
    return uid_date_map["uid"].tolist()

# counts trades and assumes sorted ids from newest trade to oldest trade
def count_trades(sorted_ids):
    # look for trades After current month
    current_month = datetime.now().month
    current_year = datetime.now().year

    # count trades
    imap = connect_imap()
    imap.select('Inbox')
    num_trades,unique_trades = 0, 0
    last_price, last_ticker, last_date = 0, 0, 0
    for id in sorted_ids:
        result, data = imap.fetch(id, '(RFC822.HEADER)')
        raw_email = data[0][1]                                 # Returns a byte
        msg = email.message_from_string(raw_email.decode('utf-8'))

        # remove the english of timezone to input into timezone aware datetime object
        new_msg = " ".join(msg['Date'].split(" ")[:-1])
        date_long = datetime.strptime(new_msg, "%a, %d %b %Y %H:%M:%S %z")
        date_long = date_long.astimezone(pytz.timezone("Asia/Hong_Kong"))

        # get this month's trades
        subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))
        if (date_long.month < current_month) | (date_long.year <current_year) :
            trade = "trade" if (num_trades - unique_trades) == 1 else "trades"
            print(f"There are {unique_trades} unique trades found in {calendar.month_name[current_month]} {current_year}."
                  f"\n{num_trades - unique_trades} {trade} have been filtered out.")
            break
        print(date_long, subject)
        subject_split = subject.split()
        # append to trade counter if trade not at the same price (assuming placed by the same order)
        if not(float(subject_split[subject_split.index("@") + 1]) == last_price and subject_split[2] == last_ticker and date_long.date() == last_date):
            unique_trades+=1
        last_price,last_ticker, last_date = float(subject_split[subject_split.index("@") + 1]), subject_split[2], date_long.date()
        num_trades+=1
if __name__ in "__main__":
    file_location = export_folder
    sorted_ids = sort_imap_id(file_location)
    count_trades(sorted_ids)