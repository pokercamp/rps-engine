'''
Poker Camp Game Engine
(c) 2024 poker.camp; all rights reserved.

Derived from: 6.176 MIT Pokerbots Game Engine at mitpokerbots/engine
'''
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

# Socket encoding scheme:
#
# T#.### the player's game clock
# P# the player's index
# H**,** the player's hand in common format
# U a up action in the round history
# D a down action in the round history
# B**,**,**,**,** the board cards in common format
# O**,** the opponent's hand in common format
# X### the player's bankroll delta from the round
# Q game over
#
# Clauses are separated by spaces
# Messages end with '\n'
# The engine expects a response of K at the end of the round as an ack,
# otherwise a response which encodes the player's action
# Action history is sent once, including the player's actions


class RoundState(namedtuple('_RoundState', ['button', 'street', 'pips', 'stacks', 'hands', 'deck', 'previous_state'])):
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
        active = self.button % 2
        inactive = 1 - active
        
        if isinstance(action, DownAction):
            if self.button == 0:
                # First player checks, continue to second player
                return RoundState(self.button + 1, self.street, self.pips, self.stacks, self.hands, self.deck, self)
            elif self.button == 1:
                if self.pips[0] == self.pips[1]:
                    # Both players checked, go to showdown
                    return self.showdown()
                else:
                    # Second player folds after a bet
                    return TerminalState([self.pips[1], -self.pips[1]], self)
            else:
                # This is check-bet-fold
                assert(self.button == 2)
                return TerminalState([-self.pips[0], self.pips[0]], self)
        
        elif isinstance(action, UpAction):
            new_pips = list(self.pips)
            new_stacks = list(self.stacks)
            if self.pips[0] == self.pips[1]:
                # This is a bet
                new_pips[active] += BET_SIZE
                new_stacks[active] -= BET_SIZE
                return RoundState(self.button + 1, self.street, new_pips, new_stacks, self.hands, self.deck, self)
            else:
                # This is a call
                new_pips[active] = new_pips[inactive]
                new_stacks[active] -= (new_pips[active] - self.pips[active])
                # Always go to showdown after a call
                return RoundState(self.button + 1, self.street, new_pips, new_stacks, self.hands, self.deck, self).showdown()

class Player():
    '''
    Handles subprocess and socket interactions with one player's pokerbot.
    '''

    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.game_clock = STARTING_GAME_CLOCK
        self.bankroll = 0
        self.commands = None
        self.bot_subprocess = None
        self.socketfile = None
        self.bytes_queue = Queue()

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
                        print(self.name, 'connected successfully')
            except (TypeError, ValueError):
                print(self.name, 'run command misformatted')
            except OSError:
                print(self.name, 'run failed - check "run" in commands.json')
            except socket.timeout:
                print('Timed out waiting for', self.name, 'to connect')

    def stop(self):
        '''
        Closes the socket connection and stops the pokerbot.
        '''
        if self.socketfile is not None:
            try:
                self.socketfile.write('Q\n')
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
        with open(self.name + '.txt', 'wb') as log_file:
            bytes_written = 0
            for output in self.bytes_queue.queue:
                try:
                    bytes_written += log_file.write(output)
                    if bytes_written >= PLAYER_LOG_SIZE_LIMIT:
                        break
                except TypeError:
                    pass

    def query(self, round_state, player_message, game_log, message_log):
        legal_actions = round_state.legal_actions() if isinstance(round_state, RoundState) else set()
        if self.socketfile is not None and self.game_clock > 0.:
            clause = ''
            try:
                player_message[0] = 'T{:.3f}'.format(self.game_clock)
                message = ' '.join(player_message) + '\n'
                del player_message[1:]  # do not send redundant action history
                message_log['server'].append(message.strip())
                start_time = time.perf_counter()
                self.socketfile.write(message)
                self.socketfile.flush()
                clause = self.socketfile.readline().strip()
                end_time = time.perf_counter()
                message_log['player'].append(clause)
                if ENFORCE_GAME_CLOCK:
                    self.game_clock -= end_time - start_time
                if self.game_clock <= 0.:
                    raise socket.timeout
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

class Game():
    '''
    Manages logging and the high-level game procedure.
    '''

    def __init__(self):
        self.log = ['Poker Camp Game Engine - ' + PLAYER_1_NAME + ' vs ' + PLAYER_2_NAME]
        self.player_messages = [[], []]
        self.message_log = [{'server': [], 'player': []} for _ in [0, 1]]

    def log_round_state(self, players, round_state):
        '''
        Incorporates RoundState information into the game log and player messages.
        '''
        if round_state.street == 0 and round_state.button == 0:
            self.log.append('{} posts the ante of {}'.format(players[0].name, ANTE))
            self.log.append('{} posts the ante of {}'.format(players[1].name, ANTE))
            self.log.append('{} dealt {}'.format(players[0].name, PCARDS(round_state.hands[0])))
            self.log.append('{} dealt {}'.format(players[1].name, PCARDS(round_state.hands[1])))
            self.player_messages[0] = ['T0.', 'P0', 'H' + CCARDS(round_state.hands[0])]
            self.player_messages[1] = ['T0.', 'P1', 'H' + CCARDS(round_state.hands[1])]
        elif round_state.street > 0 and round_state.button == 1:
            board = round_state.deck.peek(round_state.street)
            self.log.append(STREET_NAMES[round_state.street - 3] + ' ' + PCARDS(board) +
                            PVALUE(players[0].name, STARTING_STACK-round_state.stacks[0]) +
                            PVALUE(players[1].name, STARTING_STACK-round_state.stacks[1]))
            compressed_board = 'B' + CCARDS(board)
            self.player_messages[0].append(compressed_board)
            self.player_messages[1].append(compressed_board)

    def log_action(self, name, action, bet_override):
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
        self.player_messages[0].append(code)
        self.player_messages[1].append(code)

    def log_terminal_state(self, players, round_state):
        '''
        Incorporates TerminalState information into the game log and player messages.
        '''
        previous_state = round_state.previous_state
        if round_state.previous_state.pips[0] == round_state.previous_state.pips[1]:
            self.log.append('{} shows {}'.format(players[0].name, PCARDS(previous_state.hands[0])))
            self.log.append('{} shows {}'.format(players[1].name, PCARDS(previous_state.hands[1])))
            self.player_messages[0].append('O' + CCARDS(previous_state.hands[1]))
            self.player_messages[1].append('O' + CCARDS(previous_state.hands[0]))
        self.log.append('{} awarded {}'.format(players[0].name, round_state.deltas[0]))
        self.log.append('{} awarded {}'.format(players[1].name, round_state.deltas[1]))
        self.player_messages[0].append('X' + str(round_state.deltas[0]))
        self.player_messages[1].append('X' + str(round_state.deltas[1]))

    def run_round(self, players):
        deck = KuhnDeck()
        hands = [deck.deal(), deck.deal()]
        pips = [ANTE, ANTE]
        stacks = [STARTING_STACK - ANTE, STARTING_STACK - ANTE]
        round_state = RoundState(0, 0, pips, stacks, hands, deck, None)
        while not isinstance(round_state, TerminalState):
            self.log_round_state(players, round_state)
            active = round_state.button % 2
            player = players[active]
            action = player.query(round_state, self.player_messages[active], self.log, self.message_log[active])
            self.log_action(player.name, action, False)
            round_state = round_state.proceed(action)
        self.log_terminal_state(players, round_state)
        for player, player_message, delta in zip(players, self.player_messages, round_state.deltas):
            player.query(round_state, player_message, self.log, self.message_log[active])
            player.bankroll += delta

    def run(self):
        '''
        Runs one game of poker.
        '''
        print('Starting the game engine...')
        players = [
            Player(PLAYER_1_NAME, PLAYER_1_PATH),
            Player(PLAYER_2_NAME, PLAYER_2_PATH)
        ]
        for player in players:
            player.build()
            player.run()
        for round_num in range(1, NUM_ROUNDS + 1):
            self.log.append('')
            self.log.append('Round #' + str(round_num) + STATUS(players))
            self.run_round(players)
            players = players[::-1]
        self.log.append('')
        self.log.append('Final' + STATUS(players))
        for player in players:
            player.stop()
        name = GAME_LOG_FILENAME + '.txt'
        print('Writing', name)
        with open(name, 'w') as log_file:
            log_file.write('\n'.join(self.log))
        for active, server_messages_path, player_messages_path in [(0, PLAYER_1_SERVER_MESSAGES_PATH, PLAYER_1_PLAYER_MESSAGES_PATH), (1, PLAYER_2_SERVER_MESSAGES_PATH, PLAYER_2_PLAYER_MESSAGES_PATH)]:
            with open(server_messages_path + '.txt', 'w') as log_file:
                log_file.write('\n'.join(self.message_log[active]['server']))
            with open(player_messages_path + '.txt', 'w') as log_file:
                log_file.write('\n'.join(self.message_log[active]['player']))


if __name__ == '__main__':
    Game().run()
