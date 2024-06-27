'''
The infrastructure for interacting with the engine.
'''
import argparse
import socket
from .actions import UpAction, DownAction
from .states import GameState, TerminalState, RoundState
from .states import STARTING_STACK, ANTE, BET_SIZE
from .bot import Bot

class Runner():
    '''
    Interacts with the engine.
    '''

    def __init__(self, pokerbot, socketfile):
        self.pokerbot = pokerbot
        self.socketfile = socketfile

    def receive(self):
        '''
        Generator for incoming messages from the engine.
        '''
        while True:
            packet = self.socketfile.readline().strip().split(' ')
            if not packet:
                break
            yield packet

    def send(self, action):
        '''
        Encodes an action and sends it to the engine.
        '''
        code = 'U' if isinstance(action, UpAction) else 'D'
        self.socketfile.write(code + '\n')
        self.socketfile.flush()

    def run(self):
        '''
        Reconstructs the game tree based on the action history received from the engine.
        '''
        game_state = GameState(0, 0., 1)
        round_state = None
        active = 0
        round_flag = True
        for packet in self.receive():
            # print(packet)
            for clause in packet:
                if clause[0] == 'T':
                    game_state = GameState(game_state.bankroll, float(clause[1:]), game_state.round_num)
                elif clause[0] == 'P':
                    active = int(clause[1:])
                elif clause[0] == 'H':
                    hands = [None, None]
                    hands[active] = [] if clause[1:] == '' else [int(x) for x in clause[1:].split(',')]
                    pips = [ANTE, ANTE]
                    stacks = [STARTING_STACK - ANTE, STARTING_STACK - ANTE]
                    round_state = RoundState(0, 0, pips, stacks, hands, None, None)
                    if round_flag:
                        self.pokerbot.handle_new_round(game_state, round_state, active)
                        round_flag = False
                elif clause[0] == 'D':  # Down action
                    round_state = round_state.proceed(DownAction())
                elif clause[0] == 'U':  # Up action
                    round_state = round_state.proceed(UpAction())
                elif clause[0] == 'O':
                    round_state = round_state.previous_state
                    revised_hands = list(round_state.hands)
                    revised_hands[1-active] = int(clause[1:])
                    round_state = RoundState(round_state.button, round_state.street, round_state.pips, round_state.stacks,
                                             revised_hands, round_state.deck, round_state.previous_state)
                    # Don't call showdown here, wait for 'S' clause
                elif clause[0] == 'S':  # Showdown
                    delta = int(clause[1:])
                    deltas = [-delta, -delta]
                    deltas[active] = delta
                    round_state = TerminalState(deltas, round_state)
                    game_state = GameState(game_state.bankroll + delta, game_state.game_clock, game_state.round_num)
                    self.pokerbot.handle_round_over(game_state, round_state, active)
                    game_state = GameState(game_state.bankroll, game_state.game_clock, game_state.round_num + 1)
                    round_flag = True
                elif clause[0] == 'Q':
                    return
                # print(clause)
                # print(round_state)
            if round_flag:  # ack the engine
                self.send(DownAction())
            else:
                # print(f'{active} == {round_state.button % 2}')
                # assert active == round_state.button % 2
                action = self.pokerbot.get_action(game_state, round_state, active)
                self.send(action)

def parse_args():
    '''
    Parses arguments corresponding to socket connection information.
    '''
    parser = argparse.ArgumentParser(prog='python3 player.py')
    parser.add_argument('--host', type=str, default='localhost', help='Host to connect to, defaults to localhost')
    parser.add_argument('port', type=int, help='Port on host to connect to')
    return parser.parse_args()

def run_bot(pokerbot, args):
    '''
    Runs the pokerbot.
    '''
    assert isinstance(pokerbot, Bot)
    try:
        sock = socket.create_connection((args.host, args.port))
    except OSError:
        print('Could not connect to {}:{}'.format(args.host, args.port))
        return
    socketfile = sock.makefile('rw')
    runner = Runner(pokerbot, socketfile)
    runner.run()
    socketfile.close()
    sock.close()