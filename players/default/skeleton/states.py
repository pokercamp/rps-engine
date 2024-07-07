'''
Encapsulates game and round state information for the player.
'''
from collections import namedtuple
from .actions import UpAction, DownAction

GameState = namedtuple('GameState', ['bankroll', 'game_clock', 'round_num'])
TerminalState = namedtuple('TerminalState', ['deltas', 'previous_state'])

NUM_ROUNDS = 1000
STARTING_STACK = 2
ANTE = 1
BET_SIZE = 1


class RoundState(namedtuple('_RoundState', ['turn', 'street', 'pips', 'stacks', 'hands', 'deck', 'previous_state'])):
    def showdown(self):
        hands = self.hands
        pips = self.pips
        
        if hands[0] is None or hands[1] is None:
            return TerminalState([0, 0], self)  # This should not happen in normal gameplay
        
        winner = 0 if hands[0] > hands[1] else 1
        loser = 1 - winner
        
        deltas = [0, 0]
        deltas[winner] = pips[loser]
        deltas[loser] = -pips[loser]
        
        return TerminalState(deltas, self)

    def legal_actions(self):
        return {UpAction, DownAction}

    def raise_bounds(self):
        return (BET_SIZE, BET_SIZE)  # Not used in Kuhn poker, but kept for compatibility

    def proceed_street(self):
        return self.showdown()  # Kuhn poker is single street

    def proceed(self, action):
        active = self.turn % 2
        inactive = 1 - active
        
        if isinstance(action, DownAction):
            if self.turn == 0:
                # First player checks, continue to second player
                return RoundState(self.turn + 1, self.street, self.pips, self.stacks, self.hands, self.deck, self)
            elif self.turn == 1:
                if self.pips[0] == self.pips[1]:
                    # Both players checked, go to showdown
                    return self.showdown()
                else:
                    # Second player folds after a bet
                    return TerminalState([self.pips[1], -self.pips[1]], self)
            else:
                # This is check-bet-fold
                assert(self.turn == 2)
                return TerminalState([-self.pips[0], self.pips[0]], self)
        
        elif isinstance(action, UpAction):
            new_pips = list(self.pips)
            new_stacks = list(self.stacks)
            if self.pips[0] == self.pips[1]:
                # This is a bet
                new_pips[active] += BET_SIZE
                new_stacks[active] -= BET_SIZE
                return RoundState(self.turn + 1, self.street, new_pips, new_stacks, self.hands, self.deck, self)
            else:
                # This is a call
                new_pips[active] = new_pips[inactive]
                new_stacks[active] -= (new_pips[active] - self.pips[active])
                # Always go to showdown after a call
                return RoundState(self.turn + 1, self.street, new_pips, new_stacks, self.hands, self.deck, self).showdown()
                