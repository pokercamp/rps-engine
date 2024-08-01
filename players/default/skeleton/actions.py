'''
The actions that the player is allowed to take.
'''
from collections import namedtuple

class RockAction(namedtuple('RockAction', [])):
    def __hash__(self):
        return hash('RockAction')
    def __eq__(self, other):
        return isinstance(other, RockAction)
    def __repr__(self):
        return 'Rock'

class PaperAction(namedtuple('PaperAction', [])):
    def __hash__(self):
        return hash('PaperAction')
    def __eq__(self, other):
        return isinstance(other, PaperAction)
    def __repr__(self):
        return 'Paper'

class ScissorsAction(namedtuple('ScissorsAction', [])):
    def __hash__(self):
        return hash('ScissorsAction')
    def __eq__(self, other):
        return isinstance(other, ScissorsAction)
    def __repr__(self):
        return 'Scissors'
