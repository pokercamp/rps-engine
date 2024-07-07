#!/bin/bash

python scripts/tournament.py ../tournaments/kuhn0/players.csv -o ../tournaments/kuhn0/logs && python scripts/leaderboard.py ../tournaments/kuhn0/logs/mean_scores.txt
