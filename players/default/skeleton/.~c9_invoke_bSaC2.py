'''
The infrastructure for interacting with the engine.
'''
import argparse
import json
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
            packet = self.socketfile.readline().strip()
            if not packet:
                break
            yield packet

    def send(self, action, seat):
        '''
        Encodes an action and sends it to the engine.
        '''
        self.socketfile.write(json.dumps({
            'type': 'action',
            'action': {'verb': 'U' if isinstance(action, UpAction) else 'D'},
            'player': seat,
        }) + '\n')
        self.socketfile.flush()

    def run(self):
        '''
        Reconstructs the game tree based on the action history received from the engine.
        '''
        game_state = GameState(0, 0., 1)
        round_state = None
        seat = 0
        new_round_ready = True
        for packet in self.receive():
            # okay to accept a single json object
            if packet[0] == '{':
                packet = f'[{packet}]'
            for message in json.loads(packet):
                try:
                    match message['type']:
                        case 'hello':
                            pass
                        case 'time':
                            game_state = GameState(game_state.bankroll, float(message['time']), game_state.round_num)
                        case 'info':
                            info = message['info']
                            seat = int(info['seat'])
                            if 'hands' not in info:
                                info['hands'] = [None, None]
                            if 'pips' not in info:
                                info['pips'] = [ANTE, ANTE]
                            if 'stacks' not in info:
                                info['stacks'] = [STARTING_STACK - ANTE, STARTING_STACK - ANTE]
                            round_state = RoundState(seat, 0, 0, info['pips'], info['stacks'], info['hands'], None, None)
                            if 'new_game' in info and info['new_game']:
                                self.pokerbot.handle_new_round(game_state, round_state, seat)
                        case 'action':
                            match message['action']['verb']:
                                case 'U':
                                    round_state = round_state.proceed(UpAction())
                                case 'D':
                                    round_state = round_state.proceed(DownAction())
                                case _:
                                    print(f'WARN Bad action type: {message}')
                        case 'payoff':
                            delta = message['payoff']
                            deltas = [-delta, -delta]
                            deltas[seat] = delta
                            round_state = TerminalState(deltas, round_state)
                            game_state = GameState(game_state.bankroll + delta, game_state.game_clock, game_state.round_num)
                            self.pokerbot.handle_round_over(game_state, round_state, seat)
                        case 'goodbye':
                            return
                        case _:
                            print(f"WARN Bad message type: {message}")
                except KeyError as e:
                    print(f'WARN Message missing required field "{e}": {message}')
                    continue
            action = self.pokerbot.get_action(game_state, round_state, seat)
            self.send(action, seat)

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