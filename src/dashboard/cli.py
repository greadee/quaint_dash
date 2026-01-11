from dashboard.csv_import import load_positions_csv

def cli_loop():
    positions = []

    print("Portfolio Dashboard")
    print("Type 'help' for commands.\n")

    while True: 
        try:
            cmd = input("> ").strip()
        except EOFError:
            break

        cmd_lower = cmd.lower()
        
        if cmd_lower in ("quit", "exit"): 
            print("Goodbye.")
            break 

        if cmd_lower == "help": 
            print("""
                    Commands:
                    import <csv_path>
                    show
                    exit / quit
                    """)
            continue
        
        if cmd_lower.startswith("import"):
            csv_path = cmd.split(maxsplit=1)[1]
            positions = load_positions_csv(csv_path)
            print(f"Loaded {len(positions)} positions.")
            continue

        if cmd == "show": 
            if not positions: 
                print("No positions loaded.")
            else:
                for pos in positions:
                    country = pos.country if pos.country is not None else "-"
                    sector = pos.sector if pos.sector is not None else "-"
                    print(
                        f"{pos.ticker}  qty: {pos.quantity}  type: {pos.asset_type}  "
                        f"{pos.currency}  country = {country}  sector = {sector}\n"
                    )
            continue

        if cmd == "":
            continue
        
        print("Unknown command. Type 'help'.")   