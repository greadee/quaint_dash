def cli_loop():
    print("Portfolio Dashboard")
    print("Type 'help' for commands.\n")

    while True: 
        try:
            cmd = input("> ").strip().lower()
        except EOFError:
            break
        
        if cmd in ("quit", "exit"): 
                break 

        if cmd == "help": 
                print("""
                      Commands:
                      exit / quit
                      """)
                continue

        if cmd == "":
            continue
        
        print("Unknown command. Type 'help'.")   