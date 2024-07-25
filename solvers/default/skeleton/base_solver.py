'''
This file contains the base class that you can implement to use the native
solver hooks in the handout engine.
'''

class BaseSolver():
    def handle_new_iteration(self, iteration_num):
        '''
        Called when iteration is about to begin.
        '''
        
        raise NotImplementedError('handle_new_iteration')
    
    def handle_iteration_over(self, iteration_num):
        '''
        Called when iteration is over.
        '''
        
        raise NotImplementedError('handle_iteration_over')
    
    def get_root(self, iteration_num):
        '''
        Returns the RoundState to start a new iteration at.
        '''
        
        raise NotImplementedError('get_root')
    
    def determine_infoset(self, *, public, hands, history):
        '''
        Called to ask for the canonical name of an infoset.
        
        You might use this to coalesce multiple gamehistories into the same
        infoset.
        '''
        
        raise NotImplementedError('determine_infoset')
    
    def sample_actions(self, infoset, legal_actions):
        '''
        legal_actions is a list of types; this function should give one or more
        instances of each type (it might be 'or more' if you need to try
        different bet sizes...)
        '''
        
        raise NotImplementedError('sample_actions')
    
    def get_sampling_policy(self, infoset):
        '''
        Called to ask for the sampling policy at this infoset.
        
        You can let this vary by iteration #, if you like.
        Currently supported: "expand_all", "sample"
        '''
        
        raise NotImplementedError('get_sampling_policy')
    
    def handle_new_samples(self, infoset, sampling_policy, samples, use_infoset_ev):
        '''
        Called on each new set of samples produced for a node.
        
        You should use this opportunity to update your strategy probabilites
        (or whatever stored values they are derived from, like cumulative
        regrets)
        '''
        
        raise NotImplementedError('handle_samples')
    
    def get_training_strategy_probabilities(self, infoset, legal_actions):
        '''
        Called to ask for the current probabilities that should be used in a
        training iteration.
        '''
        
        raise NotImplementedError('get_training_probabilites')
    
    def get_final_strategy_probabilities(self):
        '''
        Called to ask for the final probabilities to report.
        
        This might be different from get_training_probabilites() if you wanted
        to average over multiple recent iterations.
        '''
        
        return {infoset : self.get_training_strategy_probabilities(infoset, [None]) for infoset in self.regrets.keys()}
