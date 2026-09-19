**This project enhances personal wealth management by resolving limitations of the IBKR GUI. 
Limitations include per-trade pnl breakdowns, exposure management and portfolio allocations.**



# trade_review 
Script that pulls trade confirmations from IBKR, stores them and analyses them. It achieves the following:
1. Queries trade confirmations from IBKR which get sent to my gmail
2. Stores trade confirmations into a trade database which can be accessed, and backed up
3. Portfolio analysis for exposure management, stock allocations, unrealised and realised pnl per trade per ticker
4. Also has functions to read in exports/manual_trades.csv incase trade confirmations are missing

# trade_counter
Script that pulls trade confirmations from IBKR and presents timestamps and trade content. This tool counts the number executed 
orders in the current month, removing multiple fills originating from the same order. Functional as a standalone script 
but now is integrated into trade_review as other functions.

# Set up    
1. setup IMAP for gmail and change the "Folder Size Limits" in IMAP access to unlimited (default is  1000)
2. set up a gmail app password https://myaccount.google.com/apppasswords
3. use python>=3.10 to create a venv and activate it
4. cd to intended code directory and git clone https://github.com/sleepy365/trade_review.git
5. pip install poetry
6. cd to trade_review 
7. poetry env use \your_venv\Scripts\python.exe and run poetry install
8. create credentials.py in the same format as credentials_template.py, using 16 character gmail app password
9. run trade_counter.py to test IMAP
10. edit inputs.py for your specific settings
11. if all works, try to run review_trades.py

# Known Issues
1. **Roll confirmations are not position-trackable.** IBKR's futures roll email
   lacks enough detail to reconstruct both legs, so rolls must be added to
   `exports/manual_trades.csv` by hand