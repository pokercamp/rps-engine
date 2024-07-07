import subprocess
import csv
import glob
import numpy as np
from itertools import product
import argparse
import os

def run_games(players_csv, output_dir):
    # Read player names and paths from CSV
    with open(players_csv, 'r') as f:
        reader = csv.reader(f)
        players_with_copies = list(reader)
    players = [
        (f'{name}-{(i+1):02d}', path) for name, path, copies in players_with_copies for i in range(int(copies))]
    
    # Activate virtual environment and run games for all pairs of players
    for p1, p2 in product(players, repeat=2):
        p1_name, p1_path = p1
        p2_name, p2_path = p2
        if p1_name == p2_name and p1_path == p2_path:
            continue
        cmd = f"python engine.py -p1 {p1_name} {p1_path} -p2 {p2_name} {p2_path} -o {output_dir}"
        subprocess.run(cmd, shell=True, executable='/bin/bash')

def analyze_scores(output_dir):
    score_files = glob.glob(os.path.join(output_dir, "scores.*.*.txt"))
    player_scores = {}

    for file in score_files:
        p1_name = os.path.basename(file).split('.')[1]
        
        with open(file, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                player_name, score = row
                if player_name == p1_name:
                    if p1_name not in player_scores:
                        player_scores[p1_name] = []
                    player_scores[p1_name].append(float(score))

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
    args = parser.parse_args()

    # Ensure the output directory exists
    os.makedirs(args.output, exist_ok=True)

    run_games(args.players_csv, args.output)
    analyze_scores(args.output)

if __name__ == "__main__":
    main()
