'''
Poker Camp Game Engine
(c) 2024 poker.camp; all rights reserved.

Derived from: 6.176 MIT Pokerbots Game Engine at mitpokerbots/engine
'''
import argparse
from collections import namedtuple
from threading import Thread
from queue import Queue
import time
import json
from pathlib import Path
import subprocess
import socket
# import eval7
import sys
import os
import hashlib

sys.path.append(os.getcwd())
from config import *

import random

random.seed(68127)

class Card(int):
    def __new__(cls, value):
        return super(Card, cls).__new__(cls, value)

    @classmethod
    def from_string(cls, s):
        return cls(int(s))

class KuhnDeck:
    
    duplicate_file = None
    duplicate_id = ''
    duplicate_file_iterator = None
    
    @classmethod
    def get_file_info_hash(cls, filename):
        full_path = os.path.abspath(filename)
        mtime = os.path.getmtime(full_path)
        return hashlib.sha256(f"{full_path}|{mtime}".encode()).hexdigest()
    
    @classmethod
    def ensure_duplicate_file_iterator(cls, duplicate_file):
        # for now, requires that the duplicate file never change
        if cls.duplicate_file_iterator is None:
            if duplicate_file:
                if cls.duplicate_file is None:
                    cls.duplicate_file = duplicate_file
                    cls.duplicate_id = f'.D{cls.get_file_info_hash(duplicate_file)[:6]}'
                else:
                    assert cls.duplicate_file == duplicate_file
                
                try:
                    cls.duplicate_file_iterator = open(duplicate_file, 'r')
                except IOError:
                    print(f"WARN: Could not open file {duplicate_file}. Using default shuffled deck.")
                    cls.duplicate_file_iterator = None

    @classmethod
    def done(cls):
        if cls.duplicate_file_iterator:
            cls.duplicate_file_iterator.close()
            cls.duplicate_file_iterator = None
    
    def __init__(self, duplicate_file):
        KuhnDeck.ensure_duplicate_file_iterator(duplicate_file)
        
        if duplicate_file and KuhnDeck.duplicate_file_iterator:
            line = next(KuhnDeck.duplicate_file_iterator, None)
            if line:
                self.cards = [Card.from_string(card) for card in line.strip().split(',')]
            else:
                print(f"WARN: Ran out of entries (lines) in {duplicate_file}. Using default shuffled deck.")
                self.use_default_deck()
        else:
            self.use_default_deck()
        
        self.index = 0

    def use_default_deck(self):
        self.cards = [Card(0), Card(1), Card(2)]
        random.shuffle(self.cards)
    
    def deal(self):
        if self.index >= len(self.cards):
            raise ValueError("No more cards to deal")
        card = self.cards[self.index]
        self.index += 1
        return card

class DownAction(namedtuple('DownAction', [])):
    def __hash__(self):
        return hash('DownAction')
    def __eq__(self, other):
        return isinstance(other, DownAction)
    def __repr__(self):
        return 'Down'
    
class UpAction(namedtuple('UpAction', [])):
    def __hash__(self):
        return hash('UpAction')
    def __eq__(self, other):
        return isinstance(other, UpAction)
    def __repr__(self):
        return 'Up'
    
TerminalState = namedtuple('TerminalState', ['deltas', 'previous_state'])

STREET_NAMES = []
DECODE = {'U': UpAction, 'D': DownAction}
CCARDS = lambda card: f'{card}'
PCARDS = lambda card: f'[{card}]'
PVALUE = lambda name, value: f', {name} ({value:+d})'
STATUS = lambda players: ''.join([PVALUE(p.name, p.bankroll) for p in players])

# A socket line may be a MESSAGE or a list of MESSAGEs. You are expected
# to respond once to every newline.
#
# A MESSAGE is a json object with a 'type' field (STRING). Depending on
#   the type, zero or more other fields may be required:
# hello -> [no fields]
# time -> time : FLOAT match timer remaining
# info -> info : INFO_DICT information available to you
# action -> action : ACTION_DICT, player : INT
# payoff -> payoff : FLOAT incremental payoff to you
# goodbye -> [no fields]
#
# An INFO_DICT may include game-dependent fields; most games will have:
# seat : INT your player number
# new_game : optional BOOL, set to true if this message starts a new game
# 
# An ACTION_DICT includes a 'verb' field (STRING). Depending on the
#   game, and possibly the verb, additional fields may be required or
#   optional.
# ACTION_DICTs sent by the server always include a 'seat' field (INT)
#   which identifies which player acted. This field is optional for
#   messages you send.
# 
# In the course of a round, you should receive:
# info message with new_game = true
# one or more action messages or info messages
# a payoff message
# The actions report both players' actions (including yours) in order.
#
# A player takes an action by sending a legal action message. This is
#  currently the only legal message for players to send.

def message(type, **kwargs):
    result = {'type': type}
    result.update(kwargs)
    return result

class RoundState(namedtuple('_RoundState', ['turn_number', 'street', 'pips', 'stacks', 'hands', 'deck', 'action_history', 'previous_state'])):
    @staticmethod
    def new(duplicate_file):
        deck = KuhnDeck(duplicate_file = duplicate_file)
        hands = [deck.deal(), deck.deal()]
        pips = [ANTE, ANTE]
        stacks = [STARTING_STACK - ANTE, STARTING_STACK - ANTE]
        return RoundState(
            turn_number=0,
            street=0,
            pips=pips,
            stacks=stacks,
            hands=hands,
            deck=deck,
            action_history=[],
            previous_state=None,
        )
    
    def showdown(self):
        hands = self.hands
        pips = self.pips
        
        winner = 0 if hands[0] > hands[1] else 1
        loser = 1 - winner
        
        deltas = [0, 0]
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
        return {UpAction, DownAction}

    def raise_bounds(self):
        return (BET_SIZE, BET_SIZE)  # Not used in Kuhn poker, but kept for compatibility

    def proceed_street(self):
        return self.showdown()  # Kuhn poker is single street

    def proceed(self, action):
        active = self.turn_number % 2
        inactive = 1 - active
        
        if isinstance(action, DownAction):
            if self.turn_number == 0:
                # First player checks, continue to second player
                return RoundState(
                    turn_number=self.turn_number + 1,
                    street=self.street,
                    pips=self.pips,
                    stacks=self.stacks,
                    hands=self.hands,
                    deck=self.deck,
                    action_history=self.action_history + [action],
                    previous_state=self,
                )
            elif self.turn_number == 1:
                if self.pips[0] == self.pips[1]:
                    # Both players checked, go to showdown
                    return RoundState(
                        turn_number=self.turn_number + 1,
                        street=self.street,
                        pips=self.pips,
                        stacks=self.stacks,
                        hands=self.hands,
                        deck=self.deck,
                        action_history=self.action_history + [action],
                        previous_state=self,
                    ).proceed_street()
                else:
                    # Second player folds after a bet
                    return TerminalState(
                        [self.pips[1], -self.pips[1]],
                        RoundState(
                            turn_number=self.turn_number + 1,
                            street=self.street,
                            pips=self.pips,
                            stacks=self.stacks,
                            hands=self.hands,
                            deck=self.deck,
                            action_history=self.action_history + [action],
                            previous_state=self,
                        ),
                    )
            else:
                # This is check-bet-fold
                assert(self.turn_number == 2)
                return TerminalState(
                    [-self.pips[0], self.pips[0]],
                    RoundState(
                        turn_number=self.turn_number + 1,
                        street=self.street,
                        pips=self.pips,
                        stacks=self.stacks,
                        hands=self.hands,
                        deck=self.deck,
                        action_history=self.action_history + [action],
                        previous_state=self,
                    ),
                )
        
        elif isinstance(action, UpAction):
            new_pips = list(self.pips)
            new_stacks = list(self.stacks)
            if self.pips[0] == self.pips[1]:
                # This is a bet
                new_pips[active] += BET_SIZE
                new_stacks[active] -= BET_SIZE
                return RoundState(
                    turn_number=self.turn_number + 1,
                    street=self.street,
                    pips=new_pips,
                    stacks=new_stacks,
                    hands=self.hands,
                    deck=self.deck,
                    action_history=self.action_history + [action],
                    previous_state=self,
                )
            else:
                # This is a call
                new_pips[active] = new_pips[inactive]
                new_stacks[active] -= (new_pips[active] - self.pips[active])
                # Always go to showdown after a call
                return RoundState(
                    turn_number=self.turn_number + 1,
                    street=self.street,
                    pips=new_pips,
                    stacks=new_stacks,
                    hands=self.hands,
                    deck=self.deck,
                    action_history=self.action_history + [action],
                    previous_state=self,
                ).proceed_street()

class Player():
    '''
    Handles subprocess and socket interactions with one player's pokerbot.
    '''

    def __init__(self, name, path, output_dir, *, capture):
        self.name = name
        self.path = path
        self.stdout_path = f'{output_dir}/{self.name}.stdout.txt'
        self.capture = capture
        self.game_clock = STARTING_GAME_CLOCK
        self.bankroll = 0
        self.commands = None
        self.bot_subprocess = None
        self.messages = [message('time', time=30.)]
        self.socketfile = None
        self.bytes_queue = Queue()
        self.message_log = []
        self.response_log = []

    def build(self):
        '''
        Loads the commands file and builds the pokerbot.
        '''
        try:
            with open(self.path + '/commands.json', 'r') as json_file:
                commands = json.load(json_file)
            if ('build' in commands and 'run' in commands and
                    isinstance(commands['build'], list) and
                    isinstance(commands['run'], list)):
                self.commands = commands
            else:
                print(self.name, 'commands.json missing command')
        except FileNotFoundError:
            print(self.name, f'commands.json not found - check PLAYER_PATH={self.path}')
        except json.decoder.JSONDecodeError:
            print(self.name, 'commands.json misformatted')
        if self.commands is not None and len(self.commands['build']) > 0:
            try:
                proc = subprocess.run(
                    self.commands['build'],
                    **({
                        'stdout': subprocess.PIPE,
                        'stderr': subprocess.STDOUT,
                    } if self.capture else {}),
                    cwd=self.path,
                    timeout=BUILD_TIMEOUT,
                    check=False,
                )
                self.bytes_queue.put(proc.stdout)
            except subprocess.TimeoutExpired as timeout_expired:
                error_message = 'Timed out waiting for ' + self.name + ' to build'
                print(error_message)
                self.bytes_queue.put(timeout_expired.stdout)
                self.bytes_queue.put(error_message.encode())
            except (TypeError, ValueError):
                print(self.name, 'build command misformatted')
            except OSError:
                print(self.name, 'build failed - check "build" in commands.json')

    def run(self):
        '''
        Runs the pokerbot and establishes the socket connection.
        '''
        if self.commands is not None and len(self.commands['run']) > 0:
            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                with server_socket:
                    server_socket.bind(('', 0))
                    server_socket.settimeout(CONNECT_TIMEOUT)
                    server_socket.listen()
                    port = server_socket.getsockname()[1]
                    proc = subprocess.Popen(
                        self.commands['run'] + [str(port)],
                        **({
                            'stdout': subprocess.PIPE,
                            'stderr': subprocess.STDOUT
                        } if self.capture else {}),
                        cwd=self.path,
                    )
                    self.bot_subprocess = proc
                    
                    if self.capture:
                        # function for bot listening
                        def enqueue_output(out, queue):
                            try:
                                for line in out:
                                    queue.put(line)
                            except ValueError:
                                pass
                        # start a separate bot listening thread which dies with the program
                        Thread(target=enqueue_output, args=(proc.stdout, self.bytes_queue), daemon=True).start()
                    
                    # block until we timeout or the player connects
                    client_socket, _ = server_socket.accept()
                    with client_socket:
                        client_socket.settimeout(CONNECT_TIMEOUT)
                        sock = client_socket.makefile('rw')
                        self.socketfile = sock
                        self.append(message('hello'))
                        print(self.name, 'connected successfully')
            except (TypeError, ValueError):
                print(self.name, 'run command misformatted')
            except OSError:
                print(self.name, 'run failed - check "run" in commands.json')
            except socket.timeout:
                print('Timed out waiting for', self.name, 'to connect')

    def stop(self, as_player):
        '''
        Closes the socket connection and stops the pokerbot.
        '''
        if self.socketfile is not None:
            try:
                self.append(message('goodbye'))
                self.query(None, None, wait=False)
                self.socketfile.close()
            except socket.timeout:
                print('Timed out waiting for', self.name, 'to disconnect')
            except OSError:
                print('Could not close socket connection with', self.name)
        if self.bot_subprocess is not None:
            try:
                outs, _ = self.bot_subprocess.communicate(timeout=CONNECT_TIMEOUT)
                self.bytes_queue.put(outs)
            except subprocess.TimeoutExpired:
                print('Timed out waiting for', self.name, 'to quit')
                self.bot_subprocess.kill()
                outs, _ = self.bot_subprocess.communicate()
                self.bytes_queue.put(outs)
        with open(self.stdout_path, 'wb') as log_file:
            bytes_written = 0
            for output in self.bytes_queue.queue:
                try:
                    bytes_written += log_file.write(output)
                    if bytes_written >= PLAYER_LOG_SIZE_LIMIT:
                        break
                except TypeError:
                    pass

    def append(self, msg):
        self.messages.append(msg)

    def query(self, round_state, game_log, *, wait=True):
        legal_actions = round_state.legal_actions() if isinstance(round_state, RoundState) else set()
        if self.socketfile is not None and (self.game_clock > 0. or not wait):
            clause = ''
            try:
                self.messages[0] = message(
                    'time',
                    time = round(self.game_clock, 3),
                )
                packet = json.dumps(self.messages)
                del self.messages[1:]  # do not duplicate messages
                self.message_log.append(packet)
                start_time = time.perf_counter()
                self.socketfile.write(packet + '\n')
                self.socketfile.flush()
                if not wait:
                    return None
                response = self.socketfile.readline().strip()
                end_time = time.perf_counter()
                self.response_log.append(response)
                if ENFORCE_GAME_CLOCK:
                    self.game_clock -= end_time - start_time
                if self.game_clock <= 0.:
                    raise socket.timeout
                
                action = None
                
                if (len(response) > 0
                    and (response[0] == '[' or response[0] == '{')
                ):
                    # okay to accept a single json object
                    if response[0] == '{':
                        response = f'[{response}]'
                    for response in json.loads(response):
                        try:
                            match response['type']:
                                case 'action':
                                    match response['action']['verb']:
                                        case 'U':
                                            action = UpAction
                                        case 'D':
                                            action = DownAction
                                        case _:
                                            print(f'WARN Bad action verb from {self.name}: {response}')
                                case _:
                                    print(f"WARN Bad message type from {self.name}: {response}")
                        except KeyError as e:
                            print(f'WARN Message from {self.name} missing required field "{e}": {response}')
                            continue
                else:
                    if len(response) == 0:
                        print(f'WARN Bad message from {self.name} (empty)')
                    else:
                        print(f'WARN Bad message format from {self.name} (expected json or list of json): {response}')
                
                if action in legal_actions:
                    return action()
                elif action is None:
                    game_log.append(self.name + ' did not respond')
                else:
                    game_log.append(self.name + ' attempted illegal ' + action.__name__)
            except socket.timeout:
                error_message = self.name + ' ran out of time'
                game_log.append(error_message)
                print(error_message)
                self.game_clock = 0.
            except OSError:
                error_message = self.name + ' disconnected'
                if game_log:
                    game_log.append(error_message)
                print(error_message)
                self.game_clock = 0.
            except (IndexError, KeyError, ValueError):
                game_log.append(f'Response from {self.name} misformatted: ' + str(clause))
        return DownAction() if DownAction in legal_actions else UpAction()

class Match():
    '''
    Manages logging and the high-level game procedure.
    '''

    def __init__(self, *,
        p1,
        p2,
        output_path,
        n_rounds,
        switch_seats=True,
        duplicate_file=None,
        secrets=None,
        capture=True,
    ):
        global PLAYER_1_NAME, PLAYER_1_PATH, PLAYER_2_NAME, LOGS_PATH, PLAYER_2_PATH, NUM_ROUNDS
        if p1 is not None:
            PLAYER_1_NAME = p1[0]
            PLAYER_1_PATH = p1[1]
        if p2 is not None:
            PLAYER_2_NAME = p2[0]
            PLAYER_2_PATH = p2[1]
        if output_path is not None:
            LOGS_PATH = output_path
        if n_rounds is not None:
            NUM_ROUNDS = int(n_rounds)
        self.switch_seats = switch_seats
        self.duplicate_file = duplicate_file
        self.secrets = None if secrets is None else secrets.strip().split(',')
        assert self.secrets is None or len(self.secrets) == 2
        self.capture = capture
        
        self.log = ['Poker Camp Game Engine - ' + PLAYER_1_NAME + ' vs ' + PLAYER_2_NAME]

    def send_round_state(self, players, round_state):
        '''
        Incorporates RoundState information into the game log and player messages.
        '''
        if round_state.street == 0 and round_state.turn_number == 0:
            for seat, player in enumerate(players):
                self.log.append(f'{player.name} posts the ante of {ANTE}')
            for seat, player in enumerate(players):
                self.log.append(f'{player.name} dealt {PCARDS(round_state.hands[seat])}')
                player.append(message('info', info={
                        'seat': seat,
                        'hands': round_state.visible_hands(seat),
                        **({'secret': self.secrets[seat]} if self.secrets else {}),
                        'new_game': True,
                }))
        elif round_state.street > 0 and round_state.turn_number == 1:
            board = round_state.deck.peek(round_state.street)
            self.log.append(
                STREET_NAMES[round_state.street - 3]
                + ' '
                + PCARDS(board)
                + ''.join(
                    PVALUE(player.name, STARTING_STACK-round_state.stacks[seat])
                    for seat, player in enumerate(players)
                )
            )
            for seat, player in enumerate(players):
                player.append(messages('info', info = {
                    'seat': seat,
                    'hands': [round_state.visible_hands(seat), None],
                    'board': board,
                }))

    def send_action(self, players, seat, action):
        '''
        Incorporates action information into the game log and player messages.
        '''
        if isinstance(action, UpAction):
            phrasing = ' up'
            code = 'U'
        else:  # isinstance(action, DownAction)
            phrasing = ' down'
            code = 'D'
        self.log.append(players[seat].name + phrasing)
        for player in players:
            player.append(message(
                'action',
                action = {'verb': code},
                seat = seat,
            ))

    def send_terminal_state(self, players, round_state):
        '''
        Incorporates TerminalState information into the game log and player messages.
        '''
        previous_state = round_state.previous_state
        if round_state.previous_state.pips[0] == round_state.previous_state.pips[1]:
            for seat, player in enumerate(players):
                self.log.append(f'{player.name} shows {PCARDS(previous_state.hands[seat])}')
                player.append(message('info', info = {
                    'seat': seat,
                    'hands': previous_state.hands,
                }))
        for seat, player in enumerate(players):
            self.log.append(f'{player.name} awarded {round_state.deltas[seat]:+d}')
            player.append(message(
                'payoff',
                payoff = round_state.deltas[seat],
            ))

    def run_round(self, players):
        round_state = RoundState.new(duplicate_file = self.duplicate_file)
        while not isinstance(round_state, TerminalState):
            self.send_round_state(players, round_state)
            active = round_state.turn_number % 2
            player = players[active]
            action = player.query(
                round_state,
                self.log,
            )
            self.send_action(players, active, action)
            round_state = round_state.proceed(action)
        self.send_terminal_state(players, round_state)
        for player, delta in zip(players, round_state.deltas):
            player.bankroll += delta

    def run(self):
        '''
        Runs one matchup.
        '''
        print('Starting the game engine...')
        KuhnDeck.ensure_duplicate_file_iterator(self.duplicate_file)
        MATCH_DIR = f'{LOGS_PATH}/{PLAYER_1_NAME}.{PLAYER_2_NAME}{KuhnDeck.duplicate_id}'
        Path(MATCH_DIR).mkdir(parents=True, exist_ok=True)
        players = [
            Player(PLAYER_1_NAME, PLAYER_1_PATH, MATCH_DIR, capture=self.capture, ),
            Player(PLAYER_2_NAME, PLAYER_2_PATH, MATCH_DIR, capture=self.capture, ),
        ]
        for player in players:
            player.build()
            player.run()
        for round_num in range(1, NUM_ROUNDS + 1):
            self.log.append('')
            self.log.append('Round #' + str(round_num) + STATUS(players))
            self.run_round(players)
            if self.switch_seats:
                players = players[::-1]
        self.log.append('')
        self.log.append('Final' + STATUS(players))
        for i, player in enumerate(players):
            player.stop(i)
            
        print('Writing logs...')
        
        with open(f'{MATCH_DIR}/{GAME_LOG_FILENAME}.txt', 'w') as log_file:
            log_file.write('\n'.join(self.log))
        for active, name in [
            (0, PLAYER_1_NAME),
            (1, PLAYER_2_NAME),
        ]:
            with open(f'{MATCH_DIR}/{name}.msg.server.txt', 'w') as log_file:
                log_file.write('\n'.join(players[active].message_log))
            with open(f'{MATCH_DIR}/{name}.msg.player.txt', 'w') as log_file:
                log_file.write('\n'.join(players[active].response_log))
        
        with open(f'{LOGS_PATH}/{SCORE_FILENAME}.{PLAYER_1_NAME}.{PLAYER_2_NAME}{KuhnDeck.duplicate_id}.txt', 'w') as score_file:
            score_file.write('\n'.join([f'{p.name},{p.bankroll*100.0/NUM_ROUNDS}' for p in players]))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Game engine with optional player arguments")
    parser.add_argument('-p1', nargs=2, metavar=('NAME', 'FILE'), help='Name and executable for player 1')
    parser.add_argument('-p2', nargs=2, metavar=('NAME', 'FILE'), help='Name and executable for player 2')
    parser.add_argument("-o", "--output", required=True, default="logs", metavar='PATH', help="Output directory for game results")
    parser.add_argument("-n", "--n-rounds", default=1000, metavar='INT', help="Number of rounds to run per matchup")
    parser.add_argument("--switch-seats", default=True, action=argparse.BooleanOptionalAction, help='Do players switch seats between rounds')
    parser.add_argument("-d", "--duplicate", metavar='FILE', help='File to read decks from in duplicate mode')
    parser.add_argument("--secrets", metavar=('STR,STR'), help='Secret info given to players at start of round')
    parser.add_argument("--capture", default=True, action=argparse.BooleanOptionalAction, help='Capture player outputs and write them to log files')


    args = parser.parse_args()
    
    Match(
        p1 = args.p1,
        p2 = args.p2,
        output_path = args.output,
        n_rounds = args.n_rounds,
        switch_seats = args.switch_seats,
        duplicate_file = args.duplicate,
        secrets = args.secrets,
        capture = args.capture,
    ).run()
    
    KuhnDeck.done()
