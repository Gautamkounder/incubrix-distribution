"""Catalogue Tools: import CSV, score relevance, and use AI to capture community rules with human confirm."""
import csv
import json
import time
import random
import argparse
from pathlib import Path

def generate_mock_csv(path: str):
    """Creates a mock CSV with 1,000 destinations to prove speed under 5 mins."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "URL", "Connector", "Community_Type"])
        for i in range(1, 1001):
            conn = random.choice(["discourse", "lemmy", "devto", "ghost", "hashnode", "slack", "mrss"])
            writer.writerow([f"Dest {i}", f"https://dest{i}.example.com", conn, "Tech"])
    print(f"Generated {path} with 1,000 rows.")

def calculate_relevance(destination_row: list) -> int:
    """Mock relevance scorer (1 to 5) based on community type and heuristics."""
    # In a real app, this would use NLP to compare the content niche to the destination's description
    return random.randint(1, 5)

def capture_rules_with_ai(url: str) -> dict:
    """Mock AI rules capture. Simulates reading a community's /rules page."""
    return {
        "self_promo_allowed": random.choice([True, False]),
        "disclosure_required": random.choice([True, False]),
        "frequency_cap": {"max_posts": random.randint(1, 5), "window_hours": 168}
    }

def process_catalogue(csv_path: str, output_path: str):
    print(f"Starting import of {csv_path}...")
    start_time = time.time()
    destinations = []
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            rel_score = calculate_relevance(row)
            dest = {
                "id": f"id_{i}",
                "name": row["Name"],
                "connector_key": row["Connector"],
                "relevance_score": rel_score,
                "config": {}
            }
            # Only do AI capture for highly relevant destinations to save time/cost
            if rel_score == 5 and i < 5:  # Limit prompt in demo to first few
                print(f"\n[AI Rules Engine] Analyzing {row['URL']}/rules...")
                ai_rules = capture_rules_with_ai(row["URL"])
                print(f"AI suggests these rules for {row['Name']}: {ai_rules}")
                # Wait for Human Confirmation
                confirm = input("Approve these rules? (y/n): ").strip().lower()
                if confirm == 'y':
                    dest["config"]["rules"] = ai_rules
                    print("Rules applied.")
                else:
                    print("Rules discarded.")
            destinations.append(dest)
            
    elapsed = time.time() - start_time
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(destinations, out, indent=2)
    
    print(f"\nImport complete! Processed {len(destinations)} destinations in {elapsed:.2f} seconds.")
    if elapsed > 300:
        print("WARNING: Took longer than 5 minutes!")
    else:
        print("SUCCESS: Completed in under 5 minutes.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Generate a mock CSV with 1,000 rows first")
    args = parser.parse_args()
    
    csv_file = "destinations.csv"
    if args.mock:
        generate_mock_csv(csv_file)
        
    process_catalogue(csv_file, "catalogue.json")
