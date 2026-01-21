
from datetime import datetime
from dashboard.services.import_csv import TxnImporterCSV
from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import PortfolioManager

SUPPORTED_CCY = ["CAD", "USD"]


def cli_loop():
    """
    Basic REPL style CLI.
    Commands: 

        command: help 
        def: lists all available commands 

        command: list-portfolios
        def: displays all current portfolio objects name and id.

        command: open-portfolio <portfolio_name>
        def: returns and displays a Portfolio object pertaining to the name parameter given
        param: <portfolio_name> - name of the portfolio to open

        command: import-transaction-batch <csv_path>
        def: user can choose to add a transactio batch to the ledger via csv import
        param: <csv_path> - file path to the transaction batch csv

        command: add-transaction 
        def: user can choose to add a transaction to the ledger via manual entry

        command: exit / quit
        def: exits the program
    """
    print("Portfolio Dashboard")
    print("Type 'help' for commands.\n")

    db = DB("tests/data/test_db.db")
    manager = PortfolioManager(db)
    init_db(db)
    importer = TxnImporterCSV(manager)


    while True: 
        try:
            cmd = input("> ").strip().lower()
        except EOFError:
            break

        if cmd == "":
            print("Unknown command. Type 'help'.") 
            continue
        
        if cmd in ("quit", "exit"): 
            print("Goodbye.")
            break 

        if cmd == "help": 
            print("""
                    Commands: 

                    command: help 
                    def: lists all available commands 

                    command: list-portfolios
                    def: displays all current portfolio objects name and id.

                    command: open-portfolio <portfolio_name>
                    def: returns and displays a Portfolio object pertaining to the name parameter given
                    param: <portfolio_name> - name of the portfolio to open

                    command: import-transaction-batch <csv_path>
                    def: user can choose to add a transactio batch to the ledger via csv import
                    param: <csv_path> - file path to the transaction batch csv

                    command: add-transaction 
                    def: user can choose to add a transaction to the ledger via manual entry

                    command: exit / quit
                    def: exits the program
                """)
            continue

        if cmd == "list-portfolios":
            return manager.list_portfolios()

        args = cmd.split(" ")

        if args[0] == "open-portfolio":
            try: 
                portfolio_name = args[1]
            except IndexError:
                print("Missing required number of arguments (2) for command open-portfolio.")
            except: 
                print("Unknown error.")

            portfolio_store = manager.open_portfolio_by_name(portfolio_name)
            portfolio_obj = portfolio_store.load_portfolio()
            print(portfolio_obj)

        if args[0] == "import-transaction-batch":
            try: 
                csv_path = args[1]
            except IndexError:
                print("Missing required number of arguments (2) for command import-transaction-batch.")
            except: 
                print("Unknown error.")
            import_data = importer.import_csv(csv_path)
            
            print(f"""Batch Import Succesful.
                    Transactions appended: {import_data.inserted_rows}
                    """)
            
            print(f"Batch ID: {import_data.portfolios_affected[0][3]}")
            for (p_id, p_name, created, _) in import_data.portfolios_affected:
                if created: 
                    print(f"Portfolio created -> {p_id}: {p_name}")
                else: 
                    print(f"Portoflio updated -> {p_id}: {p_name}")
                store = manager.open_portfolio_by_name(p_name)
                print(store.list_txns())
            

        if args[0] == "add-transaction":
            conn = manager.conn
            # Txn.portfolio_id
            id_or_name = input("Portfolio ID or name: ")
            if not id_or_name.isdigit():
               portfolio_id = conn.execute("SELECT portfolio_id FROM portfolio where name = ?", [id_or_name.strip()],)
           
            # Txn.time_stamp
            time_stamp = datetime.now()
            
            # Txn.txn_type
            valid_txn_type = False
            while not valid_txn_type:
                print("Transaction types:\nBuy\nSell\nContribution\nWithdrawal\nDividend\nInterest")
                txn_subtype = input("Transaction type: ").strip().lower()
                if txn_subtype in ["buy", "sell", "divdend"]: 
                    txn_type = "asset"
                    valid_txn_type = True
                elif txn_subtype in ["contribution, withdrawal, interest"]:
                    txn_type = "cash"
                    valid_txn_type = True
                else:
                    print("Transaction type invalid. Please try again.")
                    continue

            # Txn.asset_id, Txn.qty, Txn.price
            if txn_type == "asset":
                if txn_subtype == "buy":
                    pass 
                elif txn_subtype == "sell":
                    pass 
                elif txn_subtype == "dividend":
                    pass

            elif txn_type == "cash":
                asset_id, qty, price = "", "", "" 
            
            # Txn.ccy
            valid_ccy = False 
            while not valid_ccy:
                txn_ccy = input("Transaction currency (default = CAD): ").strip().lower()
                if txn_ccy and txn_ccy not in SUPPORTED_CCY:
                    print("Invalid or unsupported currency. Please try again.")
                    continue
                elif not txn_ccy:
                    txn_ccy = "CAD"
                    valid_ccy = True
                elif txn_ccy in SUPPORTED_CCY:
                    valid_ccy = True

            # Txn.cash_amt
            cash_amt = input("Cash value of transaction: $")

            # Txn.fee_amt
            fee_amt = input("Transaction fees incurred (default = 0): $")
            if not fee_amt: 
                fee_amt = 0

            # Txn.batch_id
            batch_id = importer.get_next_batch_id(portfolio_id, "manual-entry")
            
            return manager.add_txn(portfolio_id, 
                                time_stamp, 
                                txn_type, 
                                asset_id, 
                                qty, 
                                price, 
                                txn_ccy, 
                                cash_amt, 
                                fee_amt, 
                                batch_id)        