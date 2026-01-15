def cli_loop():
    '''
    Basic REPL style CLI.
    Commands: 

        command: help 
        def: lists all available commands 

        command: exit / quit
        def: exits the program
    '''
    print("Portfolio Dashboard")
    print("Type 'help' for commands.\n")

    while True: 
        try:
            cmd = input("> ").strip().lower()
        except EOFError:
            break
        
        if cmd in ("quit", "exit"): 
            print("Goodbye.")
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