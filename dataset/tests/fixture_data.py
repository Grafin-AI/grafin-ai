"""A tiny hand-made IBM dataset that exercises every edge case the spec names.

Raw rows are deliberately unsorted. They include:
- same-minute ties (rows 1 and 2; rows 6 and 7);
- a zero-padded bank spelling ("0010", only ever used with account A3, so no node merges);
- an account number under two banks (DUP at 10 and at 20);
- a cross-currency row (5);
- two identical rows (6 and 7);
- every IBM payment format;
- 4 laundering rows: 3 in Patterns.txt and 1 unattributed (row 10).
"""

from pathlib import Path

from grafin_ai_dataset.paths import DatasetPaths, dataset_paths

RAW_HEADER = (
    "Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,"
    "Amount Paid,Payment Currency,Payment Format,Is Laundering"
)
RAW_ROWS = [
    "2022/09/02 10:00,010,A1,020,B1,100.00,US Dollar,100.00,US Dollar,ACH,0",
    "2022/09/01 09:30,020,B1,010,A2,250.50,Euro,250.50,Euro,Wire,0",
    "2022/09/01 09:30,0010,A3,020,DUP,1000.00,Yen,1000.00,Yen,Cheque,0",
    "2022/09/01 08:00,010,DUP,030,C2,0.5,Bitcoin,0.5,Bitcoin,Bitcoin,1",
    "2022/09/01 08:05,010,DUP,020,B1,0.25,Bitcoin,0.25,Bitcoin,Bitcoin,1",
    "2022/09/03 23:59,126,C1,010,A1,75.00,US Dollar,70.00,Euro,Credit Card,0",
    "2022/09/02 12:00,020,DUP,010,A2,500.00,US Dollar,500.00,US Dollar,Cash,0",
    "2022/09/02 12:00,020,DUP,010,A2,500.00,US Dollar,500.00,US Dollar,Cash,0",
    "2022/09/03 01:00,030,C2,030,C2,42.42,US Dollar,42.42,US Dollar,Reinvestment,0",
    "2022/09/02 18:45,010,A2,126,C1,3000.00,US Dollar,3000.00,US Dollar,ACH,1",
    "2022/09/03 02:00,020,B1,030,C2,9999.99,Euro,9999.99,Euro,ACH,1",
    "2022/09/01 00:20,010,A1,010,A1,3697.34,US Dollar,3697.34,US Dollar,Reinvestment,0",
]
# Sorted by (timestamp, raw_row): raw row -> the 1-based transaction_id it must receive.
EXPECTED_TID = {11: 1, 3: 2, 4: 3, 1: 4, 2: 5, 0: 6, 6: 7, 7: 8, 9: 9, 8: 10, 10: 11, 5: 12}

RAW_ACCOUNTS = """Bank Name,Bank ID,Account Number,Entity ID,Entity Name
Bank A #1,10,A1,E1,Corporation #1
Bank A #1,10,A2,E1,Corporation #1
Bank A #1,10,A3,E1,Corporation #1
Bank B #2,20,B1,E2,Individual #1
Bank A #1,10,DUP,E3,Partnership #1
Bank B #2,20,DUP,E4,Sole Proprietorship #1
Crytpo Bank #5,126,C1,E5,Country #1
Bank C #3,30,C2,E6,Direct #1
Bank C #3,30,Z9,E7,Corporation #2
"""

RAW_PATTERNS = (
    "BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 2-degree Fan-Out\n"
    f"{RAW_ROWS[3]}\n{RAW_ROWS[4]}\n"
    "END LAUNDERING ATTEMPT - FAN-OUT\n\n"
    "BEGIN LAUNDERING ATTEMPT - CYCLE:  Max 1 hops\n"
    f"{RAW_ROWS[9]}\n"
    "END LAUNDERING ATTEMPT - CYCLE\n\n"
)

LEGACY_ACCOUNTS = """Bank Name,Bank ID,Account Number,Entity ID,Entity Name,risk_score,risk_category
Old Name,10,A1,E1,Old,1.0,Low
Old Name,20,B1,E2,Old,69.44,High
"""


def write_raw(data_root: Path) -> DatasetPaths:
    paths = dataset_paths(data_root, "small")
    paths.raw_dir.mkdir(parents=True)
    paths.raw_trans.write_text(RAW_HEADER + "\n" + "\n".join(RAW_ROWS) + "\n", encoding="utf-8")
    paths.raw_accounts.write_text(RAW_ACCOUNTS, encoding="utf-8")
    paths.raw_patterns.write_text(RAW_PATTERNS, encoding="utf-8")
    return paths
