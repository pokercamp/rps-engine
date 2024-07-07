from sortedcontainers import SortedList
from dataclasses import dataclass, field
import math
import csv
import json
import os
import sys

CLUSTER_MAX_SIGMA = 0.7

@dataclass
class Player:
    name: str
    mean: float
    stderr: float
    variance: float = field(init=False)

    def __post_init__(self):
        self.variance = self.stderr ** 2

    def __lt__(self, other):
        return self.mean < other.mean

@dataclass
class Group:
    low: float
    high: float
    players: SortedList = field(default_factory=SortedList)

    def __lt__(self, other):
        return self.low < other.low

def significance_distance(player1: Player, player2: Player) -> float:
    return abs(player1.mean - player2.mean) / math.sqrt(player1.variance + player2.variance)

def max_significance_distance(player: Player, group: Group) -> float:
    return max(significance_distance(player, other) for other in group.players) if group.players else float('inf')

def create_groups(players):
    groups = SortedList()

    for player in players:
        temp_group = Group(player.mean, player.mean, SortedList())
        index = groups.bisect_left(temp_group)
        
        below_group = groups[index - 1] if index > 0 else None
        above_group = groups[index] if index < len(groups) else None
        
        # Check if player's mean is within an existing group's interval
        if below_group and player.mean <= below_group.high:
            below_group.players.add(player)
            continue
        
        if above_group and player.mean >= above_group.low:
            above_group.players.add(player)
            continue

        # If we're here, the player is not within any existing group's interval
        # Find maximum significance distances to adjacent groups
        lower_dist = max_significance_distance(player, below_group) if below_group else float('inf')
        upper_dist = max_significance_distance(player, above_group) if above_group else float('inf')

        if lower_dist > CLUSTER_MAX_SIGMA and upper_dist > CLUSTER_MAX_SIGMA:
            # Create a new group
            new_group = Group(player.mean, player.mean, SortedList([player]))
            groups.add(new_group)

            while True:
                moved_player = False

                # Check if highest player from below group should move
                if below_group and below_group.players:
                    highest_below = below_group.players[-1]
                    if max_significance_distance(highest_below, new_group) < max_significance_distance(highest_below, below_group):
                        new_group.players.add(highest_below)
                        below_group.players.remove(highest_below)
                        new_group.low = min(new_group.low, highest_below.mean)
                        assert below_group.players, "Below group should not be empty after removing a player"
                        below_group.high = below_group.players[-1].mean
                        moved_player = True

                # Check if lowest player from above group should move
                if above_group and above_group.players:
                    lowest_above = above_group.players[0]
                    if max_significance_distance(lowest_above, new_group) < max_significance_distance(lowest_above, above_group):
                        new_group.players.add(lowest_above)
                        above_group.players.remove(lowest_above)
                        new_group.high = max(new_group.high, lowest_above.mean)
                        assert above_group.players, "Above group should not be empty after removing a player"
                        above_group.low = above_group.players[0].mean
                        moved_player = True

                if not moved_player:
                    break

        elif lower_dist <= upper_dist:
            # Merge with the below group
            below_group.players.add(player)
            below_group.high = player.mean
        else:
            # Merge with the above group
            above_group.players.add(player)
            above_group.low = player.mean

    return groups

def print_groups(groups):
    n_players_reported = 0
    for group in reversed(groups):
        if len(group.players) == 1:
            print(f"Place {n_players_reported+1}:")
        else:
            print(f"Group {n_players_reported+1}-{n_players_reported+len(group.players)}:")
        print(f"  Interval: [{group.low:+.1f}] - [{group.high:+.1f}]")
        print("  Players:", ', '.join(sorted(f"{player.name} ({player.mean:+.1f}±{player.stderr:.1f})" for player in group.players)))
        print()
        n_players_reported += len(group.players)

def create_json(groups):
    leaderboard = []
    n_players_reported = 0
    for group in reversed(groups):
        group_data = {
            "from_place": n_players_reported + 1,
            "to_place": n_players_reported + len(group.players),
            "from_score": group.high,
            "to_score": group.low,
            "players": [{"name": p.name, "mean": p.mean, "stderr": p.stderr} for p in group.players]
        }
        leaderboard.append(group_data)
        n_players_reported += len(group.players)
    return leaderboard

def read_scores(filename):
    players = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)  # Read and skip the header line
        
        # Determine the indices of the required columns
        try:
            name_index = header.index('Name')
            mean_index = header.index('Mean')
            stderr_index = header.index('StdErr')
        except ValueError as e:
            print(f"Error: Missing required column in CSV. {str(e)}")
            return []

        for row in reader:
            try:
                name = row[name_index]
                mean = float(row[mean_index])
                stderr = float(row[stderr_index])
                players.append(Player(name, mean, stderr))
            except (IndexError, ValueError) as e:
                print(f"Warning: Skipping invalid row: {row}. Error: {str(e)}")

    return sorted(players, key=lambda x: x.mean)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <scores_file>")
        sys.exit(1)

    scores_file = sys.argv[1]
    players = read_scores(scores_file)
    groups = create_groups(players)
    print_groups(groups)
    
    leaderboard = create_json(groups)
    json_file = os.path.join(os.path.dirname(scores_file), "leaderboard.json")
    with open(json_file, 'w') as f:
        json.dump(leaderboard, f, indent=2)
    print(f"Leaderboard JSON written to {json_file}")
