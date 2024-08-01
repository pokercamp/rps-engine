'''
Encapsulates game and round state information for the player.
'''
from collections import namedtuple
from .actions import RockAction, PaperAction, ScissorsAction

GameState = namedtuple('GameState', ['bankroll', 'game_clock', 'round_num'])
TerminalState = namedtuple('TerminalState', ['deltas', 'previous_state'])

NUM_ROUNDS = 1000
STARTING_STACK = 1
ANTE = 1


class RoundState(namedtuple('_RoundState', ['turn_number', 'street', 'pips', 'stacks', 'hands', 'deck', 'action_history', 'previous_state'])):
    @staticmethod
    def new():
        pips = [ANTE, ANTE]
        stacks = [STARTING_STACK - ANTE, STARTING_STACK - ANTE]
        return RoundState(
            turn_number=0,
            street=0,
            pips=pips,
            stacks=stacks,
            hands=[None,None],
            deck=None,
            action_history=[],
            previous_state=None,
        )
    
    def showdown(self):
        hands = self.hands
        pips = self.pips
        
        beats = [
            (RockAction(), ScissorsAction()),
            (ScissorsAction(), PaperAction()),
            (PaperAction(), RockAction()),
        ]
        if (self.action_history[0], self.action_history[1]) in beats:
            winner = 0
            loser = 1
        elif (self.action_history[1], self.action_history[0]) in beats:
            winner = 1
            loser = 0
        else:
            winner = None
            loser = None
        
        deltas = [0, 0]
        if winner is not None:
            deltas[winner] = pips[loser]
            deltas[loser] = -pips[loser]
        
        return TerminalState(deltas, self)
    
    def visible_hands(self, seat):
        ret = [None for _ in self.hands]
        ret[seat] = self.hands[seat]
        return ret
    
    def public(self):
        return {}

    def legal_actions(self):
        return {RockAction, PaperAction, ScissorsAction} if self.hands[self.turn_number] == 3 else {PaperAction, ScissorsAction}

    def raise_bounds(self):
        return (0, 0)  # Not used in RPMS, but kept for compatibility

    def proceed_street(self):
        return self.showdown()  # RPMS is single street

    def proceed(self, action):
        state = RoundState(
            turn_number = self.turn_number,
            street = self.street,
            pips = self.pips,
            stacks = self.stacks,
            hands = self.hands,
            deck = self.deck,
            action_history = self.action_history + [action],
            previous_state = self,
        )
        
        if self.turn_number == 1:
            return state.proceed_street()
        else:
            return state
