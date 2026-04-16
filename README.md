# trade_review 
Script that pulls trade confirmations from IBKR, stores them and analyses them. I started this project for 
personal wealth management and to resolve the limitations of the IBKR GUI. It achieves the following:
1. Queries trade confirmations from IBKR which get sent to my gmail
2. Stores trade confirmations into a trade database which can be accessed, and backed up.
3. Portfolio analysis for exposure management, position management, open position PL, scalp PL breakdowns, and trades by ticker
4. Also has functions to read in exports/manual_trades.csv incase trade confirmations are missing

# trade_counter
Script that pulls trade confirmations from IBKR and presents timestamps and trade content. This tool counts the number executed 
orders in the current month, removing multiple fills originating from the same order. Functional as a standalone script 
but now is integrated into trade_review as other functions.

# Set up    
1. Setup IMAP for gmail and change the "Folder Size Limits" in IMAP access to unlimited (default is  1000)
2. Set up a gmail app password https://myaccount.google.com/apppasswords
3. use python>=3.10 to create a venv and activate it
4. cd to intended code directory and git clone https://github.com/sleepy365/trade_review.git
5. pip install poetry
6. poetry config virtualenvs.in-project true
7. poetry env use \your_venv\python.exe
8. poetry install
9. create credentials.py in the same format as credentials_template.py, using 16 character gmail app password
10. edit inputs.py for your specific settings
11. run trade_counter.py
12. if all works, try to run review_trades.py

# Use case for trade_review.py
1. run script to track exposures across regions, FI, XAU and cash equivalents. Also shows all time pnl.
2. by responding to the get_ticker_trades() prompt, see unrealised, realised PL, exposure on a trade by trade basis.
3. There was a 3-month period of time in 2024 where IBKR was misconfigured to not give trade confirmations, 
I have set a fixed exports/manual_trades.csv which the script always checks for

# Known Issues
1. for futures, trade_review.get_last_price() will return the last price for the active future contract 
e.g CL=F. This means unrealised pnl based on mark-to-market prices may be off, especially for far out futures.
2. despite setting yfinance.download() to include pre-post market data, it often only returns the main session prices.