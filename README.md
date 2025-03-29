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
2. install python 3.1 for this project
3. create credentials.py in the same format as credentials_template.py
4. run trade_counter.py
5. if all works, try run review_trades.py

# Known Issues
1. if you make a trade AFTER the script already found trades for the same day, it will miss the new trades. 
Solution is to use the Other functions to wipe recent day trades and rerun
2. There was a 3-month period of time in 2024 where IBKR was misconfigured to not give trade confirmations, this lead to
a gap in recorded trades which I manually filled using manual_trades() functionality