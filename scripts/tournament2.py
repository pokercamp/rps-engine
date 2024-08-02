import subprocess
import csv
import glob
import numpy as np
from itertools import product
import argparse
import hashlib
import os

def get_newest_file_mtime(directory):
    return max(
        (os.path.getmtime(os.path.join(root, file))
         for root, _, files in os.walk(directory)
         for file in files),
        default=0
    )

def get_duplicate_filename(duplicate_dir, x, y, n_rounds):
    return f'{duplicate_dir}/{x}_{y}_{n_rounds}.txt'

def get_file_info_hash(filename):
    full_path = os.path.abspath(filename)
    mtime = os.path.getmtime(full_path)
    return hashlib.sha256(f"{full_path}|{mtime}".encode()).hexdigest()

def get_duplicate_id(duplicate_dir, x, y, n_rounds):
    return f'.D{get_file_info_hash(get_duplicate_filename(duplicate_dir, x, y, n_rounds))[:6]}'

def run_games(players_csv, output_dir, n_rounds, probs):
    # Create the duplicate directory if it doesn't exist
    duplicate_dir = os.path.join(output_dir, "duplicate")
    os.makedirs(duplicate_dir, exist_ok=True)

    # Process the probs argument
    probs = [tuple(map(float, prob.split(','))) for prob in probs]
    for x, y in probs:
        output_file = f"{duplicate_dir}/{x}_{y}_{n_rounds}.txt"
        if not os.path.exists(output_file):
            # print(f"Writing {x},{y} duplicate file")
            current_dir = os.path.dirname(os.path.abspath(__file__))
            cmd = f"{current_dir}/psmr_deals.sh {x} {y} | head -n {n_rounds} > {output_file}"
            subprocess.run(cmd, shell=True, executable='/bin/bash')
        else:
            # print(f"Skipping {x},{y} duplicate file: File already exists.")
            pass

    # Read player names and paths from CSV
    with open(players_csv, 'r') as f:
        reader = csv.reader(f)
        players_with_copies = list(reader)
    players = [
        (name + (f'-{(i+1):02d}' if (int(copies) > 1) else ''), path) for name, path, copies in players_with_copies for i in range(int(copies))]
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    engine_path = os.path.join(os.path.dirname(current_dir), 'engine.py')
    
    # Run games for all pairs of players
    for p1, p2 in product(players, repeat=2):
        p1_name, p1_path = p1
        p2_name, p2_path = p2
        if p1_name == p2_name and p1_path == p2_path:
            continue
        
        for x, y in probs:
            output_file = os.path.join(output_dir, f"scores.{p1_name}.{p2_name}{get_duplicate_id(duplicate_dir, x, y, n_rounds)}.txt")
            
            # Check if output file exists and is newer than player directories
            if os.path.exists(output_file):
                output_mtime = os.path.getmtime(output_file)
                p1_newest = get_newest_file_mtime(p1_path)
                p2_newest = get_newest_file_mtime(p2_path)
                
                if output_mtime > p1_newest and output_mtime > p2_newest:
                    print(f"Skipping {p1_name} vs {p2_name} with ({x},{y}): Matchup file is up to date.")
                    continue
            
            print(f'Match {p1_name} vs {p2_name} with ({x},{y})')
            cmd = f"python {engine_path} -p1 {p1_name} {p1_path} -p2 {p2_name} {p2_path} -o {output_dir} -n {n_rounds} --no-switch-seats --duplicate {get_duplicate_filename(duplicate_dir, x, y, n_rounds)}"
            subprocess.run(cmd, shell=True, executable='/bin/bash')
            print('')

def analyze_scores(output_dir):
    score_files = glob.glob(os.path.join(output_dir, "scores.*.*.*.txt"))
    player_scores = {}

    for file in score_files:
        with open(file, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                player_name, score = row
                if player_name not in player_scores:
                    player_scores[player_name] = []
                player_scores[player_name].append(float(score))

    # Calculate statistics and prepare results
    results = []
    for player, scores in player_scores.items():
        scores_array = np.array(scores)
        mean = np.mean(scores_array)
        stderr = np.std(scores_array, ddof=1) / np.sqrt(len(scores_array))
        results.append((player, mean, stderr))
        print(f"Player: {player}")
        print(f"  Mean score: {mean:.2f}")
        print(f"  Standard error of mean: {stderr:.2f}")
        print()

    # Sort results by mean score (descending) and write to file
    results.sort(key=lambda x: x[1], reverse=True)
    with open(os.path.join(output_dir, 'mean_scores.txt'), 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Name', 'Mean', 'StdErr'])
        for result in results:
            writer.writerow([result[0], f"{result[1]:.2f}", f"{result[2]:.2f}"])

def main():
    parser = argparse.ArgumentParser(description="Run games and analyze scores.")
    parser.add_argument("players_csv", help="Path to the CSV file containing player names and paths")
    parser.add_argument("-o", "--output", required=True, help="Output directory for game results")
    parser.add_argument("-n", "--n_rounds", type=int, default=1000, help="Number of rounds to run per matchup")
    parser.add_argument("--probs", nargs='+', required=True, metavar="FLOAT,FLOAT", help="One or more comma-separated pairs of floats")
    args = parser.parse_args()

    # Ensure the output directory exists
    os.makedirs(args.output, exist_ok=True)

    run_games(args.players_csv, args.output, args.n_rounds, args.probs)
    analyze_scores(args.output)

if __name__ == "__main__":
    main()