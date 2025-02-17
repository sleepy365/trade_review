# trade_review
Script that pulls trade confirmations from IBKR, stores them and analyses them. I made this project to for better trade
recording for personal wealth management. It achieves the following:
1. Queries trade confirmations from IBKR which get sent to my gmail
2. stores trade confirmations into a trade database which can be accessed
3. analyse the trade database for monthly trade counter, exposure management, position management, PL breakdowns, and trades by ticker

# Set up
1. Setup IMAP for gmail and increase the # Msgs to 1000+ (default is  100)
2. install python 3.1 for this project
3. create credentials.py in the same format as credentials_template.py
4. run trade_counter.py
5. if all works, try run review_trades.py