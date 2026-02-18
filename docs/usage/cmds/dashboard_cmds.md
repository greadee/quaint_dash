# Dashboard Commands
## Open Portfolio
```
open <portfolio-name>
``` 
Open the Portfolio View for the portfolio specified by portfolio-name. If the search for portfolio-name is unsuccesful, returns a string informing the user of a lack of portfolio exisiting by that name.
- argument (Required): item-type - Case sensitive, name of portfolio to open
## Create Portfolio
```
create <portfolio-name>
``` 
Create a new portfolio and open the Portfolio View for the new portfolio. If a portfolio already exists by this name, then this command does nothing.
- argument (Required): item-type - Case sensitive, name of portfolio to create
## List
```
list <item-type> [item-filter] [n]
```
Display a list of items associated with the current portfolio.
- argument (Required): item-type - Type of item to display
 - e.g.: "asset", "transaction", "portfolio", "position"
- argument (Optional): item-filter - Filter selected items by some attribute belonging to the item
    - Requires calling a flag --item-filter or -item-filter to pass the value of item-filter
- argument (Optional): n - How many items to display, default: all
    - Requires calling a flag --n or -n to pass the value of n
## Import Transaction Batch
```
import <csv-path>
``` 
Add a batch of transactions contained within a csv file. Transactions for existing portfolios are simply appended, while transactions for non-existent portfolios will create a new portfolio by the portfolio-name specified within the CSV file. Displays a summary log of transactions appended, portfolios affected, etc.
- argument (Required): csv-path - File path from project root (if inside project), else use absolute path

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