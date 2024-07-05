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
import subprocess
import socket
# import eval7
import sys
import os

sys.path.append(os.getcwd())
from config import *

import random

class KuhnDeck:
    def __init__(self):
        self.cards = [0, 1, 2]
        random.shuffle(self.cards)
        self.index = 0
    
    def deal(self):
        if self.index >= len(self.cards):
            raise ValueError("No more cards to deal")
        card = self.cards[self.index]
        self.index += 1
        return card

UpAction = namedtuple('UpAction', [])
DownAction = namedtuple('DownAction', [])
TerminalState = namedtuple('TerminalState', ['deltas', 'previous_state'])

STREET_NAMES = []
DECODE = {'U': UpAction, 'D': DownAction}
CCARDS = lambda card: '{}'.format(card)
PCARDS = lambda card: '[{}]'.format(card)
PVALUE = lambda name, value: ', {} ({})'.format(name, value)
STATUS = lambda players: ''.join([PVALUE(p.name, p.bankroll) for p in players])

# A socket line may be a MESSAGE or a list of MESSAGEs. You are expected
#  once to every newline.
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
# An ACTION_DICT includes a 'verb' field (STRING). Depending on the game,
#   and possibly the verb, additional fields may be required or optional.
# 
# In the course of a game, you should receive:
# info message with new_game = true
# one or more action messages or info messages
# a final info message
# a payoff message
# The actions report both players' actions (including yours) in order.
#
# A player takes an action by sending a legal action message. This is
#  currently the only legal message for players to send.

def message(type, **kwargs):
    result = {'type': type}
    result.update(kwargs)
    return result

class RoundState(namedtuple('_RoundState', ['turn_number', 'street', 'pips', 'stacks', 'hands', 'deck', 'previous_state'])):
    def showdown(self):
        hands = self.hands
        pips = self.pips
        
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
        active = self.turn_number % 2
        inactive = 1 - active
        
        if isinstance(action, DownAction):
            if self.turn_number == 0:
                # First player checks, continue to second player
                return RoundState(self.turn_number + 1, self.street, self.pips, self.stacks, self.hands, self.deck, self)
            elif self.turn_number == 1:
                if self.pips[0] == self.pips[1]:
                    # Both players checked, go to showdown
                    return self.showdown()
                else:
                    # Second player folds after a bet
                    return TerminalState([self.pips[1], -self.pips[1]], self)
            else:
                # This is check-bet-fold
                assert(self.turn_number == 2)
                return TerminalState([-self.pips[0], self.pips[0]], self)
        
        elif isinstance(action, UpAction):
            new_pips = list(self.pips)
            new_stacks = list(self.stacks)
            if self.pips[0] == self.pips[1]:
                # This is a bet
                new_pips[active] += BET_SIZE
                new_stacks[active] -= BET_SIZE
                return RoundState(self.turn_number + 1, self.street, new_pips, new_stacks, self.hands, self.deck, self)
            else:
                # This is a call
                new_pips[active] = new_pips[inactive]
                new_stacks[active] -= (new_pips[active] - self.pips[active])
                # Always go to showdown after a call
                return RoundState(self.turn_number + 1, self.street, new_pips, new_stacks, self.hands, self.deck, self).showdown()

class Player():
    '''
    Handles subprocess and socket interactions with one player's pokerbot.
    '''

    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.stdout_path = f'{PLAYER_LOGS_PATH}/{name}.stdout.txt'
        self.game_clock = STARTING_GAME_CLOCK
        self.bankroll = 0
        self.commands = None
        self.bot_subprocess = None
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
            print(self.name, 'commands.json not found - check PLAYER_PATH')
        except json.decoder.JSONDecodeError:
            print(self.name, 'commands.json misformatted')
        if self.commands is not None and len(self.commands['build']) > 0:
            try:
                proc = subprocess.run(self.commands['build'],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      cwd=self.path, timeout=BUILD_TIMEOUT, check=False)
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
                    proc = subprocess.Popen(self.commands['run'] + [str(port)],
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            cwd=self.path)
                    self.bot_subprocess = proc
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
                        packet = json.dumps([message('hello')])+'\n'
                        self.message_log.append(packet)
                        self.socketfile.write(packet)
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
                packet = json.dumps(player_messages[as_player] + [message('goodbye')])+'\n'
                self.message_log.append(packet)
                self.socketfile.write(packet)
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

    def query(self, round_state, player_message, game_log):
        legal_actions = round_state.legal_actions() if isinstance(round_state, RoundState) else set()
        if self.socketfile is not None and self.game_clock > 0.:
            clause = ''
            try:
                player_message[0] = message(
                    'time',
                    time = round(self.game_clock, 3),
                )
                packet = json.dumps(player_message)
                del player_message[1:]  # do not duplicate messages
                self.message_log.append(packet)
                start_time = time.perf_counter()
                self.socketfile.write(packet + '\n')
                self.socketfile.flush()
                response = self.socketfile.readline().strip()
                end_time = time.perf_counter()
                self.response_log.append(packet)
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
                                            print(f'WARN Bad action verb: {response}')
                                case _:
                                    print(f"WARN Bad message type: {response}")
                        except KeyError as e:
                            print(f'WARN Message missing required field "{e}": {response}')
                            continue
                else:
                    action = DECODE[clause[0]]
                
                if action in legal_actions:
                    return action()
                game_log.append(self.name + ' attempted illegal ' + action.__name__)
            except socket.timeout:
                error_message = self.name + ' ran out of time'
                game_log.append(error_message)
                print(error_message)
                self.game_clock = 0.
            except OSError:
                error_message = self.name + ' disconnected'
                game_log.append(error_message)
                print(error_message)
                self.game_clock = 0.
            except (IndexError, KeyError, ValueError):
                game_log.append(self.name + ' response misformatted: ' + str(clause))
        return DownAction() if DownAction in legal_actions else UpAction()

player_messages = [[None], [None]]

class Game():
    '''
    Manages logging and the high-level game procedure.
    '''

    def __init__(self, p1, p2):
        global PLAYER_1_NAME, PLAYER_1_PATH, PLAYER_2_NAME, PLAYER_2_PATH
        if p1 is not None:
            PLAYER_1_NAME = p1[0]
            PLAYER_1_PATH = p1[1]
        if p2 is not None:
            PLAYER_2_NAME = p2[0]
            PLAYER_2_PATH = p2[1]
        
        self.log = ['Poker Camp Game Engine - ' + PLAYER_1_NAME + ' vs ' + PLAYER_2_NAME]

    def log_round_state(self, players, round_state):
        '''
        Incorporates RoundState information into the game log and player messages.
        '''
        if round_state.street == 0 and round_state.turn_number == 0:
            self.log.append('{} posts the ante of {}'.format(players[0].name, ANTE))
            self.log.append('{} posts the ante of {}'.format(players[1].name, ANTE))
            self.log.append('{} dealt {}'.format(players[0].name, PCARDS(round_state.hands[0])))
            self.log.append('{} dealt {}'.format(players[1].name, PCARDS(round_state.hands[1])))
            player_messages[0].append(message('info', info={
                    'seat': 0,
                    'hands': [round_state.hands[0], None],
                    'new_game': True,
            }))
            player_messages[1].append(message('info', info={
                    'seat': 1,
                    'hands': [round_state.hands[1], None],
                    'new_game': True,
            }))
        elif round_state.street > 0 and round_state.turn_number == 1:
            board = round_state.deck.peek(round_state.street)
            self.log.append(STREET_NAMES[round_state.street - 3] + ' ' + PCARDS(board) +
                            PVALUE(players[0].name, STARTING_STACK-round_state.stacks[0]) +
                            PVALUE(players[1].name, STARTING_STACK-round_state.stacks[1]))
            player_messages[0].append(messages('info', info = {
                'seat': 0,
                'hands': [round_state.hands[0], None],
                'board': board,
            }))
            player_messages[1].append(messages('info', info = {
                'seat': 1,
                'hands': [None, round_state.hands[1]],
                'board': board,
            }))

    def log_action(self, name, action, seat, bet_override):
        '''
        Incorporates action information into the game log and player messages.
        '''
        if isinstance(action, UpAction):
            phrasing = ' up'
            code = 'U'
        else:  # isinstance(action, DownAction)
            phrasing = ' down'
            code = 'D'
        self.log.append(name + phrasing)
        player_messages[0].append(message(
            'action',
            action = {'verb': code},
            player = seat,
        ))
        player_messages[1].append(message(
            'action',
            action = {'verb': code},
            player = seat,
        ))

    def log_terminal_state(self, players, round_state):
        '''
        Incorporates TerminalState information into the game log and player messages.
        '''
        previous_state = round_state.previous_state
        if round_state.previous_state.pips[0] == round_state.previous_state.pips[1]:
            self.log.append('{} shows {}'.format(players[0].name, PCARDS(previous_state.hands[0])))
            self.log.append('{} shows {}'.format(players[1].name, PCARDS(previous_state.hands[1])))
            player_messages[0].append(message('info', info = {
                'seat': 0,
                'hands': previous_state.hands,
            }))
            player_messages[1].append(message('info', info = {
                'seat': 1,
                'hands': previous_state.hands,
            }))
        self.log.append('{} awarded {}'.format(players[0].name, round_state.deltas[0]))
        self.log.append('{} awarded {}'.format(players[1].name, round_state.deltas[1]))
        player_messages[0].append(message(
            'payoff',
            payoff = round_state.deltas[0],
        ))
        player_messages[1].append(message(
            'payoff',
            payoff = round_state.deltas[1],
        ))

    def run_round(self, players):
        deck = KuhnDeck()
        hands = [deck.deal(), deck.deal()]
        pips = [ANTE, ANTE]
        stacks = [STARTING_STACK - ANTE, STARTING_STACK - ANTE]
        round_state = RoundState(0, 0, pips, stacks, hands, deck, None)
        while not isinstance(round_state, TerminalState):
            self.log_round_state(players, round_state)
            active = round_state.turn_number % 2
            player = players[active]
            action = player.query(
                round_state,
                player_messages[active],
                self.log,
            )
            self.log_action(player.name, action, active, False)
            round_state = round_state.proceed(action)
        self.log_terminal_state(players, round_state)
        for player, player_message, delta in zip(players, player_messages, round_state.deltas):
            player.bankroll += delta

    def run(self):
        '''
        Runs one game of poker.
        '''
        print('Starting the game engine...')
        players = [
            Player(PLAYER_1_NAME, PLAYER_1_PATH, ),
            Player(PLAYER_2_NAME, PLAYER_2_PATH, ),
        ]
        for player in players:
            player.build()
            player.run()
        for round_num in range(1, NUM_ROUNDS + 1):
            self.log.append('')
            self.log.append('Round #' + str(round_num) + STATUS(players))
            self.run_round(players)
            players = players[::-1]
            global player_messages
            player_messages = player_messages[::-1]
        self.log.append('')
        self.log.append('Final' + STATUS(players))
        for i, player in enumerate(players):
            player.stop(i)
            
        name = GAME_LOG_FILENAME + '.txt'
        print('Writing', name)
        with open(name, 'w') as log_file:
            log_file.write('\n'.join(self.log))
        for active, name in [
            (0, PLAYER_1_NAME),
            (1, PLAYER_2_NAME),
        ]:
            with open(f'{PLAYER_LOGS_PATH}/{name}.msg.server.txt', 'w') as log_file:
                log_file.write('\n'.join(players[active].message_log))
            with open(f'{PLAYER_LOGS_PATH}/{name}.msg.player.txt', 'w') as log_file:
                log_file.write('\n'.join(players[active].response_log))
        
        with open(f'{SCORE_FILENAME}.{PLAYER_1_NAME}.{PLAYER_2_NAME}.txt', 'w') as score_file:
            score_file.write('\n'.join([f'{p.name},{p.bankroll}' for p in players]))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Game engine with optional player arguments")
    parser.add_argument('-p1', nargs=2, metavar=('NAME', 'FILE'), help='Name and executable for player 1')
    parser.add_argument('-p2', nargs=2, metavar=('NAME', 'FILE'), help='Name and executable for player 2')

    args = parser.parse_args()
    
    Game(args.p1, args.p2).run()
