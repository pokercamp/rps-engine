'''
Simple example bot, written in Python.
'''
from skeleton.actions import RockAction, PaperAction, ScissorsAction
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

import random

class Player(Bot):
    '''
    A bot for playing Rock-Paper-Scissors.
    '''

    def __init__(self):
        '''
        Called when a new matchup starts. Called exactly once.
        '''
        
        self.my_profit = 0
        self.history = []

    def handle_results(self, *, my_action, their_action, my_payoff, match_clock):
        '''
        Called after a round. Called NUM_ROUNDS times.
        '''
        
        self.history.append((my_action, their_action))
        self.my_profit += my_payoff

    def get_action(self, *, match_clock):
        '''
        Where the magic happens. Called when the engine needs an action from
        your bot. Called NUM_ROUNDS times.

        Returns a RockAction(), PaperAction(), or ScissorsAction().
        '''
        
        return random.choice([RockAction(), PaperAction(), ScissorsAction()])


if __name__ == '__main__':
    run_bot(Player(), parse_args())
