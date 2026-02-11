"""~/
program entry point
- dispatches commands to DashboardView -> DashboardManager
- handles ValueErrors raised by DashboardView and or DashboardManager
"""
from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager
from dashboard.models.cli_view import View, DashboardView

def cli_loop():
    """
    Read-Eval-Print loop for the command line interface. 

    Init. core infrastructure (db + DashboardManager)
    Init. default CLI 'View' (DashboardView)
    Loop:
        - display current view
        - prompt for user input 
        - pass user input to subsequent View for handling
        - Active View dispatches commands 
        - Switches to sub-views when requested.
    
    Expects:
    - Views to propogate SystemExit in order to kill the program cleanly.
    - 'view' always references a valid instance of View.
    - View.handle_input() returns some instance of a view.    

    This function should not contain any command logic.
        - All parsing and behaviour lives inside of 'View' subclasses.
    View transitions are driven by return values from `handle_input()`, not by direct mutation inside the views.
    """
    db = DB("data/persistent_db.db")
    init_db(db)
    manager = DashboardManager(db)
    view: View = DashboardView(manager)

    while True:
        view.default_display()
        line = input(view.prompt_input())
        if not line: 
            continue 
        try:
            next_view = view.handle_input(line)
        except ValueError as e:
                print(e)
                next_view = view

        if isinstance(next_view, View):
            view = next_view 