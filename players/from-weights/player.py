'''
Simple example pokerbot, written in Python.
'''
from skeleton.actions import UpAction, DownAction
from skeleton.states import GameState, TerminalState, RoundState
from skeleton.states import NUM_ROUNDS, STARTING_STACK, ANTE, BET_SIZE
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

import json
import os
from pathlib import Path
import random

class Player(Bot):
    '''
    A pokerbot.
    '''

    def __init__(self):
        '''
        Called when a new game starts. Called exactly once.

        Arguments:
        Nothing.

        Returns:
        Nothing.
        '''
        with (Path(__file__).parent / 'strategy.json').open('r') as f:
            self.strategy = json.load(f)
            print(f'Loaded strategy: {self.strategy}')

    def handle_new_round(self, game_state, round_state, active):
        '''
        Called when a new round starts. Called NUM_ROUNDS times.

        Arguments:
        game_state: the GameState object.
        round_state: the RoundState object.
        active: your player's index.

        Returns:
        Nothing.
        '''
        #my_bankroll = game_state.bankroll  # the total number of chips you've gained or lost from the beginning of the game to the start of this round
        #game_clock = game_state.game_clock  # the total number of seconds your bot has left to play this game
        #round_num = game_state.round_num  # the round number from 1 to NUM_ROUNDS
        #my_cards = round_state.hands[active]  # your cards
        #big_blind = bool(active)  # True if you are the big blind
        pass

    def handle_round_over(self, game_state, terminal_state, active):
        '''
        Called when a round ends. Called NUM_ROUNDS times.

        Arguments:
        game_state: the GameState object.
        terminal_state: the TerminalState object.
        active: your player's index.

        Returns:
        Nothing.
        '''
        #my_delta = terminal_state.deltas[active]  # your bankroll change from this round
        #previous_state = terminal_state.previous_state  # RoundState before payoffs
        #street = previous_state.street  # 0, 3, 4, or 5 representing when this round ended
        #my_cards = previous_state.hands[active]  # your cards
        #opp_cards = previous_state.hands[1-active]  # opponent's cards or [] if not revealed
        pass

    def get_action(self, game_state, round_state, seat):
        '''
        Where the magic happens - your code should implement this function.
        Called any time the engine needs an action from your bot.

        Arguments:
        game_state: the GameState object.
        round_state: the RoundState object.
        seat: your player's index.

        Returns:
        Your action.
        '''
        legal_actions = round_state.legal_actions() if isinstance(round_state, RoundState) else set()  # the actions you are allowed to take
        #street = round_state.street  # 0, 3, 4, or 5 representing pre-flop, flop, turn, or river respectively
        #my_cards = round_state.hands[active]  # your cards
        #board_cards = round_state.deck[:street]  # the board cards
        #my_pip = round_state.pips[active]  # the number of chips you have contributed to the pot this round of betting
        #opp_pip = round_state.pips[1-active]  # the number of chips your opponent has contributed to the pot this round of betting
        #my_stack = round_state.stacks[active]  # the number of chips you have remaining
        #opp_stack = round_state.stacks[1-active]  # the number of chips your opponent has remaining
        #continue_cost = opp_pip - my_pip  # the number of chips needed to stay in the pot
        #my_contribution = STARTING_STACK - my_stack  # the number of chips you have contributed to the pot
        #opp_contribution = STARTING_STACK - opp_stack  # the number of chips your opponent has contributed to the pot
        #if RaiseAction in legal_actions:
        #    min_raise, max_raise = round_state.raise_bounds()  # the smallest and largest numbers of chips for a legal bet/raise
        #    min_cost = min_raise - my_pip  # the cost of a minimum bet/raise
        #    max_cost = max_raise - my_pip  # the cost of a maximum bet/raise
        
        if round_state and round_state.hands:
            my_hand = round_state.hands[seat]
            
            if round_state.hands[seat] is None:
                print(f'WARN Bad round_state: seat {seat}, hands {round_state.hands}')
            
            up_prob = 0.0
            
            # print(round_state)
            
            match round_state.turn:
                case 0:
                    match my_hand:
                        case 0:
                            # print("Q_")
                            up_prob = self.strategy["Q_"]
                        case 1:
                            # print("K_")
                            up_prob = self.strategy["K_"]
                        case 2:
                            # print("A_")
                            up_prob = self.strategy["A_"]
                        case _:
                            print(f'WARN Bad round_state: unknown card {my_hand}')
                            return DownAction()
                case 1:
                    # print(my_hand)
                    # print(round_state.action_history[0])
                    match my_hand, round_state.action_history[0]:
                        case 0, DownAction():
                            # print("_QD")
                            up_prob = self.strategy["_QD"]
                        case 1, DownAction():
                            # print("_KD")
                            up_prob = self.strategy["_KD"]
                        case 2, DownAction():
                            # print("_AD")
                            up_prob = self.strategy["_AD"]
                        case 0, UpAction():
                            # print("_QU")
                            up_prob = self.strategy["_QU"]
                        case 1, UpAction():
                            # print("_KU")
                            up_prob = self.strategy["_KU"]
                        case 2, UpAction():
                            # print("_AU")
                            up_prob = self.strategy["_AU"]
                        case _:
                            print(f'WARN Bad round_state for second turn: {round_state}')
                            return DownAction()
                case 2:
                    match my_hand:
                        case 0:
                            # print("Q_DU")
                            up_prob = self.strategy["Q_DU"]
                        case 1:
                            # print("K_DU")
                            up_prob = self.strategy["K_DU"]
                        case 2:
                            # print("A_DU")
                            up_prob = self.strategy["A_DU"]
                        case _:
                            print(f'WARN Bad round_state: unknown card {round_state.turn}')
                            return DownAction()
                case _:
                    print(f'WARN Bad round_state: unexpected turn {my_hand}')
                    return DownAction()
            
            # print(up_prob)
            action = UpAction() if (random.random() < up_prob) else DownAction()
            # print(action)
            return action
            
        else:
            print(f'WARN Bad round_state: {round_state}')
        
        return DownAction()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
