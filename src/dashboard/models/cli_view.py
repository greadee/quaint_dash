"""~/models/
dispatched by cli to handle user commands and communicate with Manager/Importer instances

_NoExitParser: argparse.ArgumentParser object that raises ValueError instead of SystemError
View: abstract base class for CLI Views
DashboardView: abstract parent of PortfolioView
PortfolioView: abstract child of DashboardView
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import argparse
import shlex
from dashboard.models.storage import DashboardManager, PortfolioManager
from dashboard.services.importer import TxnImporterManual, TxnImporterCSV, tTestTxn

class _NoExitParser(argparse.ArgumentParser):
    """
    'argparse.ArgumentParser' normally calls sys.exit() on parse errors (unknown / missing arg)
    _NoExitParser overriders the error method of argparse so the CLI doesn't die.
    """
    def error(self, message):
        """
        Convert argparse error into an exception so the CLI can continue after error.
        """
    
        raise ValueError(message)


def _split(line: str) -> list[str]:
    """
   Split a raw input line into unix style tokens.
   Uses 'shlex.split' so quoted strings behave like a typical terminal.
    - line: str: raw line from input()
    - returns a list of tokens represented in the line.
    """
    return shlex.split(line)


def _print_parse_error(cmd: str, err: Exception) -> None:
    """
    Intended to be used after _NoExitParser raises a ValueError for a bad argument.
    """
    print(f"[{cmd}] {err}")


@dataclass
class View(ABC):
    """
    Abstract base class for CLI Views (a view is an interactive mode / context)

    The CLI loop holds a 'View' instance and loops through the following:
    1. call default_display() to show which view we are in and the available commands.
    2. call prompt_input() to display a string prompting user input.
        * User input is grabbed in cli.py, and passed in as a parameter to handle_input().* 
    3. call handle_input() on the user input to process the command.
    4. performs the necessary command, and if the command involves switching views, opens the next view.
    
    - 'handle_input' should never call 'sys.exit()' directly.
    - A view may print output itself, or delegate the task to the subsequent Manager/Store object.
    """
    @abstractmethod
    def default_display(self) -> None:
        """
        Print the default header/help for the view.
        """
        pass

    @abstractmethod
    def prompt_input(self) -> str:
        """
        Print the default input prompt for the view.
        """
        pass

    @abstractmethod
    def handle_input(self, line: str):
        """
        Performs the necessary command specified by the input line from the user, or handles input errors.
        param:
          - line: str - untokenized input line from the user
        ret:
          - self (stay in same view -> command printed output already)
          - a different View (switch view)

        - Parse/validation errors should be caught and printed rather than crashing the loop.
        """
        pass


@dataclass
class DashboardView(View):
    """
    Central / Root level CLI for portfolio(s) management actions.
    - parses and dispatches "dash-level" commands. 
    - Owns "dash-level" parsers.
    - Create and return a PortofolioView object when 'open <portfolio_name>' command is called.

    Requires access to DashboardManager object for the execution of commands on the database.
    """
    access: DashboardManager
    cmds: dict[str, argparse.ArgumentParser] = field(default_factory=dict)

    def __post_init__(self):
        """
        Runs post-initialization. 
        Ensures the view has parsers configured properly. (For if we want to cast in certain commands for testing)
        """
        if not self.cmds:
            self.cmds = self.build_dash_parsers()

    def default_display(self):
        """
        Print the default header/help for the view.
        """
        print("\n=== Dashboard ===")
        print("""   
            Commands: 
                list <item-type> [item-filter] [n], 
                create <portfolio-name>, 
                open <portfolio-name>, 
                import <csv-path>, 
                help [command-name], 
                quit/exit
              """)

    def prompt_input(self):
        """
        Print the default input prompt for the view.
        """
        return "dashboard> "

    def handle_input(self, line: str):
        """
        Performs the necessary command specified by the input line from the user, or handles input errors.
        Tokenizes input parameters using shlex.
        param:
          - line: str - untokenized input line from the user
        commands: 
            - quit / exit: raise SystemExit to quit the application
            - back: return the root view DashboardView
            - help: calls handle_help() to display a help message detailing usage over all available commands.
            - list [N]: list integer N number of (transactions), or all if N=None.
            - create [portfolio_name]: creates a new portfolio by name, if name is already taken does nothing.
            - open [portfolio_name]: opens an existing portfolio by name, if name is unavailable (not used yet) does nothing.
            - import [csv_path]: imports a transaction CSV file from the filepath param provided by the user. 
        """
        tokens = _split(line)
        if not tokens:
            return self

        cmd, args = tokens[0], tokens[1:]

        if cmd in ("quit", "exit"):
            print("Goodbye.")
            raise SystemExit

        if cmd == "help":
            self._handle_help(args)
            return self

        parser = self.cmds.get(cmd)
        if not parser:
            print(f"Unknown command: {cmd} (try: help)")
            return self

        try:
            ns = parser.parse_args(args)
        except (ValueError, SystemExit) as e:
            _print_parse_error(cmd, e)
            return self

        if cmd == "list":
            item_type = ns.item_type
            if item_type in ["port", "ports", "portfolio", "portfolios"]:
                rows = self.access.list_portfolios(ns.n)

            elif item_type in ["txn", "txns", "transaction", "transactions"]:
                rows = self.access.list_txns(ns.n)
            
            elif item_type in ["pos", "position", "positions"]:
                self.access.update_positions() # refresh position table

                if getattr(ns, "asset_id", None) is not None: 
                    rows = self.access.list_positions_by_asset(ns.asset_id, ns.n)
                elif getattr(ns, "asset_type", None) is not None: 
                    rows = self.access.list_positions_by_type(ns.asset_type, ns.n)
                elif getattr(ns, "asset_subtype", None) is not None: 
                    rows = self.access.list_positions_by_subtype(ns.asset_subtype, ns.n)
                else:
                    rows = self.access.list_positions(ns.n)
            
            
            if rows is not None:
                print(rows)
            return self
            
        if cmd == "create":
            self.access.upsert_portfolio(ns.portfolio_name)
            print(f"Upserted portfolio: {ns.portfolio_name}")
            return self

        if cmd == "open":
            # Concatenate portfolio_name tokens back into a name that can contain whitespace 
            for i in range(len(ns.portfolio_name)): 
                arg = ns.portfolio_name[i] 
                if not i:
                    p_name = arg
                else:
                    p_name += f" {arg}"

            manager: PortfolioManager = self.access.open_portfolio_by_name(p_name)
            # return a View so cli_loop can switch
            return PortfolioView(
                portfolio_access=manager,
                root_access=self.access
            )
        
        if cmd == "import":
            importer = TxnImporterCSV(self.access, ns.csv_path)
            import_data = importer.run()
            if import_data is not None:
                print(import_data)
            return self

        return self # fallback

    def _handle_help(self, args: list[str]):
        """
        Displays a help message detailing usage over all available commands.
        """
        if not args:
            self.default_display()
            return self

        cmd = args[0]
        if cmd in self.cmds:
            self.cmds[cmd].print_help()
        elif cmd in ("quit", "exit"):
            print("quit: exit the program")
        elif cmd == "help":
            print("help [command]: show general help or command help")
        else:
            print(f"No such command: {cmd}")

    @staticmethod
    def build_dash_parsers():
        """
        Create and return the argparse parsers for dashboard commands.
        Each parser is an `_NoExitParser` so parse errors raise exceptions instead of exiting.
        Ret:
          - dict map from command name -> configured ArgumentParser.
        """
        parsers: dict[str, argparse.ArgumentParser] = {}

        # list cmd parser / subparser
        p = _NoExitParser(prog="list", add_help=True, description="List transactions or positions (optionally filtered).")
        subp = p.add_subparsers(dest="item_type", required=True)
        
        subp_txn: argparse.ArgumentParser = subp.add_parser("txn", aliases=["txn", "txns", "transaction", "transcations"], 
                                   help="List transactions.", description="List transactions.", add_help=True)
        subp_txn.add_argument("-n", "--n", dest="n", type=int, default=None,
                              help = "Number of transactions to display (default: all).")
        
        subp_port: argparse.ArgumentParser = subp.add_parser("port", aliases=["port", "ports", "portfolio", "portfolios"], 
                                    help="List active portfolios.", description="List active portfolios.", add_help=True)
        subp_port.add_argument("-n", "--n", dest="n", type=int, default=None,
                              help = "Number of portfolios to display (default: all).")

        subp_pos: argparse.ArgumentParser = subp.add_parser("pos", aliases = ["pos", "position", "positions"],
                                    help="List positions (optionally filtered).", 
                                    description="List positions filtered by asset id/type/subtype or no filter.", add_help=True)
        subp_pos.add_argument("-n", "--n", dest="n", type=int, default=None,
                              help = "Number of positions to display (default: all).")
        pos_arg_group = subp_pos.add_mutually_exclusive_group()
        
        # position filter
        pos_arg_group.add_argument("-asset-id", "--asset-id", dest="asset_id", help="Filter by asset id.")
        pos_arg_group.add_argument("-asset-type", "--asset-type", dest="asset_type", help="Filter by asset type.")
        pos_arg_group.add_argument("-asset-subtype", "--asset-subtype", dest="asset_subtype", help="Filter by asset subtype.")

        parsers["list"] = p

        # create cmd parser
        p = _NoExitParser(prog="create", add_help=True, description="Create or update a portfolio")
        p.add_argument("portfolio_name", help="Name of portfolio")
        parsers["create"] = p

        # open cmd parser
        p = _NoExitParser(prog="open", add_help=True, description="Open a portfolio")
        p.add_argument("portfolio_name", nargs='*', help="Name of portfolio")

        parsers["open"] = p

        # import cmd parser
        p = _NoExitParser(prog="import", add_help=True, description="Import a CSV transaction batch")
        p.add_argument("csv_path", help="Path to CSV file")
        parsers["import"] = p

        return parsers


@dataclass
class PortfolioView(View):
    portfolio_access: PortfolioManager
    root_access: DashboardManager
    cmds: dict[str, argparse.ArgumentParser] = field(default_factory=dict)

    def __post_init__(self):
        """
        Runs post-initialization. 
        Ensures the view has parsers configured properly. (For if we want to cast in certain commands for testing)
        """
        if not self.cmds:
            self.cmds = self.build_port_parsers()

    def default_display(self):
        """
        Print the default header/help for the view.
        """
        print("\n=== Portfolio ===")
        print("""Commands: 
                list <item-type> [item-filter] [n], 
                add-transaction, 
                import <csv_path>, 
                back, 
                help [command-name], 
                quit/exit
              """)

    def prompt_input(self):
        """
        Print the default input prompt for the view.
        """
        name = getattr(self.portfolio_access, "portfolio_name", "portfolio")
        return f"{name}> "

    def handle_input(self, line: str):
        """
        Performs the necessary command specified by the input line from the user, or handles input errors.
        Tokenizes input parameters using shlex.
        param:
          - line: str - untokenized input line from the user
        commands: 
            - quit / exit: raise SystemExit to quit the application
            - back: return the root view DashboardView
            - help: displays a help message detailing usage over all available commands.
            - add-transaction: appends a single manual entry transaction to the database, interactive prompting for field entries.
            - list [N]: list integer N number of (transactions), or all if N=None.
            - 
        """
        tokens = _split(line)
        if not tokens:
            return self

        cmd, args = tokens[0], tokens[1:]

        if cmd in ("quit", "exit"):
            print("Goodbye")
            raise SystemExit

        if cmd == "back":
            return DashboardView(self.root_access)

        if cmd == "help":
            self._handle_help(args)
            return self

        if cmd == "add-transaction":
            txn_fields = self._prompt_txn_fields()
            importer = TxnImporterManual(self.root_access, txn_fields)
            import_data = importer.run()
            if import_data is not None:
                print(import_data)
            return self

        parser = self.cmds.get(cmd)
        if not parser:
            print(f"Unknown command: {cmd} (try: help)")
            return self

        try:
            ns = parser.parse_args(args)
        except (ValueError, SystemExit) as e:
            _print_parse_error(cmd, e)
            return self

        if cmd == "list":
            item_type = ns.item_type
            if item_type in ["txn", "txns", "transaction", "transactions"]:
                rows = self.portfolio_access.list_txns(ns.n)
            
            elif item_type in ["pos", "position", "positions"]:
                self.root_access.update_positions() # refresh position table

                if getattr(ns, "asset_id", None) is not None: 
                    rows = self.portfolio_access.list_positions_by_asset(ns.n)
                elif getattr(ns, "asset_type", None) is not None: 
                    rows = self.portfolio_access.list_positions_by_type(ns.n)
                elif getattr(ns, "asset_subtype", None) is not None: 
                    rows = self.portfolio_access.list_positions_by_subtype(ns.n)
                else:
                    rows = self.portfolio_access.list_positions(ns.n)

            if rows is not None:
                print(rows)
            return self
        
        return self # fall back

    def _handle_help(self, args: list[str]):
        """
        Displays a help message detailing usage over all available commands.
        """
        if not args:
            self.default_display()
            return self

        cmd = args[0]
        if cmd in self.cmds:
            self.cmds[cmd].print_help()
        elif cmd == "add-transaction":
            print("add-transaction: interactively enter a manual transaction")
        elif cmd == "back":
            print("back: return to dashboard")
        elif cmd in ("quit", "exit"):
            print("quit: exit the program")
        elif cmd == "help":
            print("help [command]: show general help or command help")
        else:
            print(f"No such command: {cmd}")

    def _prompt_txn_fields(self):
        """
        Collect fields interactively and return necessary Txn fields in TestTxn object.
        """
        print("Enter transaction fields (blank to cancel).")

        portfolio_name = getattr(self.portfolio_access, "portfolio_name", "")
        time_stamp = input("time_stamp (YYYY-MM-DD HH:MM:SS): ").strip()
        if not time_stamp:
            print("Cancelled.")
            return self

        txn_type = input("txn_type (buy/sell/div/etc): ").strip()
        asset_id = input("asset_id (e.g., AAPL): ").strip()
        qty = input("qty: ").strip()
        price = input("price: ").strip()
        ccy = input("ccy: ").strip()
        cash_amt = input("cash_amt: ").strip()
        fee_amt = input("fee_amt: ").strip()

        return tTestTxn(
            self.portfolio_access.portfolio_id,
            portfolio_name,
            time_stamp,
            txn_type,
            asset_id,
            qty,
            price,
            ccy,
            cash_amt,
            fee_amt)

    @staticmethod
    def build_port_parsers():
        """
        Create and return the argparse parsers for dashboard commands.
        Each parser is an `_NoExitParser` so parse errors raise exceptions instead of exiting.
        Ret:
          - dict map from command name -> configured ArgumentParser.
        """
        parsers: dict[str, argparse.ArgumentParser] = {}

        # list cmd parser / subparser
        p = _NoExitParser(prog="list", add_help=True, description="List transactions in this portfolio")
        p.add_argument("n", nargs="?", type=int, default=None,
                       help="Number of txns to display (default: all)")
        subp = p.add_subparsers(dest="item_type", required=True)

        
        subp_txn: argparse.ArgumentParser = subp.add_parser("txn", aliases=["txn", "txns", "transaction", "transcations"], 
                                   help="List transactions.", description="List transactions.", add_help=True)
        subp_txn.add_argument("-n", "--n", dest="n", type=int, default=None,
                              help = "Number of transactions to display (default: all).")
        
        subp_pos: argparse.ArgumentParser = subp.add_parser("pos", aliases=["pos", "position", "positions"], 
                                    help="List positions (optionally filtered).", 
                                    description="List positions filtered by asset id/type/subtype or no filter.", add_help=True)
        subp_pos.add_argument("-n", "--n", dest="n", type=int, default=None,
                              help = "Number of positions to display (default: all).")
        pos_arg_group = subp_pos.add_mutually_exclusive_group()
        
        # position filter
        pos_arg_group.add_argument("-asset-id", "--asset-id", dest="asset_id", help="Filter by asset id.")
        pos_arg_group.add_argument("-asset-type", "--asset-type", dest="asset_type", help="Filter by asset type.")
        pos_arg_group.add_argument("-asset-subtype", "--asset-subtype", dest="asset_subtype", help="Filter by asset subtype.")

        parsers["list"] = p

        # import cmd parser
        p = _NoExitParser(prog="import", add_help=True, description="Import a CSV transaction batch")
        p.add_argument("csv_path", help="Path to CSV file")
        parsers["import"] = p

        return parsers