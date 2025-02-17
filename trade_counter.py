import imaplib
import email
from datetime import datetime
import calendar
from credentials import imap_host, imap_user, imap_pass

def connect_imap():
    # connect to host using SSL
    imap = imaplib.IMAP4_SSL(imap_host)
    ## login to server
    imap.login(imap_user, imap_pass)
    return imap

if __name__ in "__main__":
    # look for trades After current month
    current_month = datetime.now().month
    current_year = datetime.now().year

    imap = connect_imap()
    imap.select('Inbox')
    result, data = imap.search(None, 'FROM "IB Trading Assistant"' )

    # fetch trades for the current month
    id_list = data[0].split()
    id_list.reverse()
    num_trades,unique_trades = 0, 0
    last_price, last_ticker, last_date = 0, 0, 0
    for id in id_list:
        result, data = imap.fetch(id, '(RFC822)')
        raw_email = data[0][1]                                 # Returns a byte
        msg = email.message_from_string(data[0][1].decode('utf-8'))
        date_tuple = email.utils.parsedate_tz(msg['Date'])
        date_short = f'{date_tuple[1]}/{date_tuple[2]}/{date_tuple[0]}'
        subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))
        if (date_tuple[1] < current_month) | (date_tuple[0] <current_year) :
            trade = "trade" if (num_trades - unique_trades) == 1 else "trades"
            print(f"There are {unique_trades} unique trades found in {calendar.month_name[current_month]} {current_year}."
                  f"\n{num_trades - unique_trades} {trade} have been filtered out.")
            break
        print(date_short, subject)
        subject_split = subject.split()
        # append to trade counter if trade not at the same price (assuming placed by the same order)
        if not(float(subject_split[subject_split.index("@") + 1]) == last_price and subject_split[2] == last_ticker and date_short == last_date):
            unique_trades+=1
        last_price,last_ticker, last_date = float(subject_split[subject_split.index("@") + 1]), subject_split[2], date_short
        num_trades+=1
