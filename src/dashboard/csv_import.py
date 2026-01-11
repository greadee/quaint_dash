import csv 
from dashboard.models import Position 

def normalize_optional(value):
    value = value.strip()
    return value if value else None 

def load_positions_csv(csv_path):
    positions: list[Position] = []

    with open(csv_path, mode='r', newline = "", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            pos = Position(
                ticker = row["ticker"].strip().upper(),
                quantity = float(row["quantity"]),
                asset_type = row["asset_type"].strip().lower(),
                currency = row["currency"].strip().upper(),
                country = normalize_optional(row["country"]),
                sector = normalize_optional(row["sector"]),
            )
            positions.append(pos)
        
        return positions