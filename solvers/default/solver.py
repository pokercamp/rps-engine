'''
Example solver.
'''
from skeleton.base_solver import BaseSolver
from skeleton.engine import RoundState
from skeleton.runner import parse_args, run_solver

class Solver(BaseSolver):
    def __init__(self):
        self.regrets = {}
    
    def handle_new_iteration(self, _):
        '''
        Called when iteration is about to begin.
        '''
        pass
    
    def handle_iteration_over(self, _):
        '''
        Called when iteration is over.
        '''
        pass
    
    def get_root(self, _):
        '''
        Returns the RoundState to start a new iteration at.
        '''
        return RoundState.new()
    
    def determine_infoset(self, active, hands, action_history):
        '''
        Called to ask for the canonical name of an infoset.
        
        You might use this to coalesce multiple gamehistories into the same infoset.
        '''
        return f'(P{active+1}){hands}{action_history}'
    
    def sample_actions(self, infoset, legal_actions):
        '''
        legal_actions is a list of types; this function should give one or more
        instances of each type (it might be 'or more' if you need to try
        different bet sizes...)
        '''
        return [action() for action in legal_actions]
    
    def get_sampling_policy(self, infoset, *, iteration):
        '''
        Called to ask for the sampling policy at this infoset.
        
        You can let this vary by iteration #, if you like.
        Currently supported: "expand_all", "sample"
        '''
        return 'expand_all'
    
    def handle_new_samples(self, infoset, sampling_policy, samples, use_ev):
        '''
        Called on each new set of samples produced for a node.
        
        You should use this opportunity to update your strategy probabilites
        (or whatever stored values they are derived from, like cumulative
        regrets)
        '''
        if sampling_policy == 'expand_all':
            for action, sample_list in samples.items():
                regret = sample_list[0] - use_ev
                
                if infoset not in self.regrets:
                    self.regrets[infoset] = {}
                    
                if action not in self.regrets[infoset]:
                    self.regrets[infoset][action] = 0
                
                # if regret > 0:
                #     print(f'add {max(regret, 0)} to {action} at {infoset}; EV {sample_list[0]} > {use_ev}')
                self.regrets[infoset][action] += max(0, regret)
    
    def get_training_strategy_probabilities(self, infoset, legal_actions):
        '''
        Called to ask for the current probabilities that should be used in a training iteration.
        '''
        total_regret = sum(self.regrets[infoset].values()) if infoset in self.regrets else None
        if infoset not in self.regrets or total_regret == 0:
            n_legal_actions = len(legal_actions)
            return {action : 1 / n_legal_actions for action in legal_actions}
        return {action : value / total_regret for action, value in self.regrets[infoset].items()}
    
    def get_final_strategy_probabilities(self):
        '''
        Called to ask for the final probabilities to report.
        
        This might be different from get_training_probabilites if you wanted to average over multiple
        recent iterations.
        '''
        return {infoset : self.get_training_strategy_probabilities(infoset, [None]) for infoset in self.regrets.keys()}

if __name__ == '__main__':
    run_solver(Solver(), parse_args())
