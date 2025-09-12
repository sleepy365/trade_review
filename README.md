# trade_review 
Script that pulls trade confirmations from IBKR, stores them and analyses them. I started this project for better trade
recording for personal wealth management and to resolve the limitations of the IBKR GUI. It achieves the following:
1. Queries trade confirmations from IBKR which get sent to my gmail
2. Stores trade confirmations into a trade database which can be accessed, and backed up.
3. Portfolio analysis for exposure management, position management, open positon PL, scalp PL breakdowns, and trades by ticker
4. Also has functions to read in manual_trades incase trade confirmation was missing

# trade_counter
Script that pulls trade confirmations from IBKR and presents timestamps and trade content. This tool counts the number executed 
orders in the current month, removing multiple fills originating from the same order. Functional as a standalone script 
but now is integrated into trade_review as other functions.

# Set up    
1. Setup IMAP for gmail and change the "Folder Size Limits" in IMAP access to unlimited (default is  1000)
2. pip install poetry
3. create a folder /trade_review and cd to it
4. git clone https://github.com/sleepy365/trade_review.git
5. poetry install
6. create credentials.py in the same format as credentials_template.py
7. run trade_counter.py
8. if all works, try to run review_trades.py
9. if all_trades.csv backups are available, just place it in the export location and the script should recognise it

# Known Issues
1. if you make a trade AFTER the script already found trades for the same day, it will not pull the new trades. Need to 
use function 4 to wipe recent day trades and rerun the script
2. There was a 3-month period of time in 2024 where IBKR was misconfigured to not give trade confirmations, this lead to
a gap in recorded trades which I manually filled using manual_trades() functionality