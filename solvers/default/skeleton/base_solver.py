'''
This file contains the base class that you can implement to use the native
solver hooks in the handout engine.
'''

class BaseSolver():
    def handle_new_iteration(self, iteration_num):
        raise NotImplementedError('handle_new_iteration')
    
    def handle_iteration_over(self, iteration_num):
        raise NotImplementedError('handle_iteration_over')
    
    def get_root(self, iteration_num):
        raise NotImplementedError('get_root')
    
    def determine_infoset(self, info):
        raise NotImplementedError('determine_infoset')
    
    def sample_actions(self, infoset, legal_actions):
        raise NotImplementedError('sample_actions')
    
    def get_sampling_policy(self, infoset):
        raise NotImplementedError('get_sampling_policy')
    
    def handle_new_samples(self, infoset, sampling_policy, samples, use_ev):
        raise NotImplementedError('handle_samples')
    
    def get_training_strategy_probabilities(self, infoset, legal_actions):
        raise NotImplementedError('get_training_probabilites')
    
    def get_final_strategy_probabilities(self, infoset, legal_actions):
        raise NotImplementedError('get_final_probabilites')
