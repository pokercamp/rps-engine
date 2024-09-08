'''
The infrastructure for interacting with the engine.
'''
import argparse
import json
import socket
from .actions import RockAction, PaperAction, ScissorsAction
from .bot import Bot

class Runner():
    '''
    Interacts with the engine.
    '''

    def __init__(self, bot, socketfile):
        self.bot = bot
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
        match action:
            case RockAction():
                verb = 'R'
            case PaperAction():
                verb = 'P'
            case ScissorsAction():
                verb = 'S'
        self.socketfile.write(json.dumps({
            'type': 'action',
            'action': {'verb': verb},
            'player': seat,
        }) + '\n')
        self.socketfile.flush()

    def run(self):
        '''
        Reconstructs the game tree based on the action history received from the engine.
        '''
        match_clock = None
        results = [None, None]
        seat = 0
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
                            match_clock = float(message['time'])
                        
                        case 'info':
                            info = message['info']
                            seat = int(info['seat'])
                            if 'new_game' in info and info['new_game']:
                                results = [None, None]
                        
                        case 'action':
                            match message['action']['verb']:
                                case 'R':
                                    results[message['seat']] = RockAction()
                                case 'P':
                                    results[message['seat']] = PaperAction()
                                case 'S':
                                    results[message['seat']] = ScissorsAction()
                                case _:
                                    print(f'WARN Bad action type: {message}')
                        
                        case 'payoff':
                            payoff = message['payoff']
                            self.bot.handle_results(
                                my_action = results[seat],
                                their_action = results[1-seat],
                                my_payoff = payoff,
                                match_clock = match_clock,
                            )
                        
                        case 'goodbye':
                            return
                    
                        case _:
                            print(f"WARN Bad message type: {message}")
                        
                except KeyError as e:
                    print(f'WARN Message missing required field "{e}": {message}')
                    continue
            action = self.bot.get_action(match_clock = match_clock)
            self.send(action, seat)

def parse_args():
    '''
    Parses arguments corresponding to socket connection information.
    '''
    parser = argparse.ArgumentParser(prog='python3 player.py')
    parser.add_argument('--host', type=str, default='localhost', help='Host to connect to, defaults to localhost')
    parser.add_argument('port', type=int, help='Port on host to connect to')
    return parser.parse_args()

def run_bot(bot, args):
    '''
    Runs the bot.
    '''
    assert isinstance(bot, Bot)
    try:
        sock = socket.create_connection((args.host, args.port))
    except OSError:
        print('Could not connect to {}:{}'.format(args.host, args.port))
        return
    socketfile = sock.makefile('rw')
    runner = Runner(bot, socketfile)
    runner.run()
    socketfile.close()
    sock.close()
