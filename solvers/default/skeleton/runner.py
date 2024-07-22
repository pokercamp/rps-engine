'''
The infrastructure for bridging a solver to the engine.
'''
import argparse
import json
import random
from .base_solver import BaseSolver
from .engine import RoundState, TerminalState, UpAction

def parse_args():
    parser = argparse.ArgumentParser(prog='python3 solver.py')
    parser.add_argument('--iter', type=int, required=True, help='Number of iterations')
    return parser.parse_args()

def get_ev(solver, state, *, iteration):
    # print(state)
    if isinstance(state, TerminalState):
        active = state.previous_state.turn_number % 2
        # print(f'return terminal {state.deltas[active]:+d} for P{active+1}  :  {state}')
        return -state.deltas[active]
    
    active = state.turn_number % 2
    infoset = solver.determine_infoset(active, state.visible_hands(active), state.action_history)
    sampling_policy = solver.get_sampling_policy(infoset, iteration=iteration)
    
    samples = {action : [] for action in solver.sample_actions(infoset, state.legal_actions())}
    
    if (sampling_policy == 'sample'):
        action_p = solver.get_training_strategy_probabilities(infoset, samples.keys())
        action = random.choices(list(action_p.keys()), weights=list(action_p.values()), k=1)[0]
        ev = get_ev(solver, state.proceed(action), iteration=iteration)
        samples[action].append(ev)
        
    elif (sampling_policy == 'expand_all'):
        # print(f'at infoset {infoset}, traversing {list(samples.keys())}')
        ev = 0
        training_p = solver.get_training_strategy_probabilities(infoset, samples.keys())
        for action in samples.keys():
            next = state.proceed(action)
            action_ev = get_ev(solver, next, iteration=iteration)
            samples[action].append(action_ev)
            ev += training_p[action] * action_ev
        # ev is now the expected value weighted by training probs
        
    else:
        raise NotImplementedError(f'sampling policy = {sampling_policy}')
    
    # print(f'{infoset} : {sampling_policy} : {samples} : {ev}')
    solver.handle_new_samples(infoset, sampling_policy, samples, ev)
    
    # print(f'Intermediate probabilities:\n{"\n".join(sorted([f"{infoset: <22}: {value[UpAction()]}" for infoset, value in solver.get_final_probabilities().items()]))}\n')
    
    # print(f'return intermediate sample {ev:+f} for P{active+1}  :  {state}')
    return -ev

def run_solver(solver, args):
    assert isinstance(solver, BaseSolver)
    
    for iteration in range(args.iter):
        solver.handle_new_iteration(iteration)
        
        root = solver.get_root(iteration)
        
        assert isinstance(root, RoundState)
        
        _ = get_ev(solver, root, iteration=iteration)
        
        solver.handle_iteration_over(iteration)
    
    print(f'Final probabilities:\n{"\n".join(sorted([f"{infoset: <22}: {value[UpAction()]}" for infoset, value in solver.get_final_strategy_probabilities().items()]))}')
    
