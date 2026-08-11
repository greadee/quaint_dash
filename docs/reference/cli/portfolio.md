# Portfolio Commands
## List
```
list <item-type> [item-filter] [n]
```
Display a list of items associated with the current portfolio. Results are auto-filtered to those belonging to the current portfolio opened (in Portfolio View).
- argument (Required): item-type - Type of item to display
    - e.g.: "asset", "txn", "position"
- argument (Optional): item-filter - Filter selected items by some attribute belonging to the item
    - Requires calling a flag --item-filter or -item-filter to pass the value of item-filter
- argument (Optional): n - How many items to display, default: all
    - Requires calling a flag --n or -n to pass the value of n
## Add Transaction
```
add-transaction
``` 
Add a single transaction to the Portfolio manually through interactive prompting in the CLI.
## Back
```
back 
```
Returns the user back to Dashboard View.
## Command Help
```
help [command-name]
```
Returns a "usage" string for each command present in Portfolio View.
- argument (Required): command-name - name of the command needing clarification, as it appears in the application
## Quit
```
quit/exit
```
Quits the application. Either "quit" or "exit" accepted.