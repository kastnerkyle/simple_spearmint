import spearmint.tasks.task_group
import spearmint.choosers.default_chooser
import os
import sys
import numpy as np


class SimpleSpearmint(object):
    """ Thin wrapper around Spearmint's Gaussian Process optimizer.

    Parameters
    ----------
    parameter_space : dict
        Dictionary defining the parameters to optimize over.  The keys should
        be parameter names and the values should be dictionaries which specify
        the parameter; for example, a parameter called "x" which is a float
        between -1 and 1 would be specified as
        ``'x': {'type': 'float', 'min': -1, 'max': 1}``.  Possible parameter
        types are ``'float'``, ``'int'``, and ``'enum'``.  For ``'float'`` and
        ``'int'``, ``'min'`` and ``'max'`` values must be supplied; for
        ``'enum'``, the possible parameter values must be supplied as a list
        with the key ``'options'``.

    noiseless : bool
        Whether the objective function is noiseless or not.  If the objective
        is noisy, set ``noiseless=True``.

    debug : bool
        Whether to allow Spearmint to print debug information to stderr.

    Examples
    --------
    Create a parameter optimizer over three parameters: x, a float between -2
    and 2; y, an int between 0 and 3, and function, which can be either
    ``'sin'`` or ``'cos'``.

    >>> ss = simple_spearmint.SimpleSpearmint(
    ...     {'x': {'type': 'float', 'min': -2, 'max': 2},
    ...      'y': {'type': 'int', 'min': 0, 'max': 3},
    ...      'function': {'type': 'enum', 'options': ['sin', 'cos']}})
    ...
    >>> suggested_parameters = ss.suggest()

    """

    def __init__(self, parameter_space, noiseless=False, debug=False):
        # Add the 'size' key to each entry in the parameter space.
        # We assume all parameters are size 1, which is reasonable.
        for name, spec in parameter_space.items():
            spec['size'] = 1
            parameter_space[name] = spec
        # Convert the "noiseless" bool flag to Spearmint's string semantics
        noiseless = 'NOISELESS' if noiseless else 'GAUSSIAN'
        # Set up task configuration dict
        self.task_config = {'main': {'type': 'objective',
                                     'likelihood': noiseless}}
        # Create a "task group" for this experiment
        self.task_group = spearmint.tasks.task_group.TaskGroup(
            self.task_config, parameter_space)
        # Use Spearmint's default chooser
        self.chooser = spearmint.choosers.default_chooser.init({})
        # Initialize lists of parameter and objective value trials
        self.parameter_values = []
        self.objective_values = []
        # We need to persistently store the model hyperparameters
        self.hypers = None
        self.debug = debug

    def spec_parameter_values(self, parameter_values):
        """ Converts parameter values in the form ``{'parameter_name': value}``
        to a spearmint-friendly format, which includes the key ``'type'`` and
        where ``'enum'`` variables have a list value.

        Parameters
        ----------
        parameter_values : dict
            Dictionary of the form ``{'parameter_name': value}``.

        Returns
        -------
        specd_parameter_values : dict
            Converted dictionary in the format expected by Spearmint's
            ``vectorify`` function.

        """
        specd_parameter_values = {}
        for name, value in parameter_values.items():
            # Retrieve the param type string from the variable spec
            param_type = self.task_group.variables_config[name]['type']
            # If the variable type is an enum, make the value a list
            if param_type == 'enum':
                values = [value]
            else:
                values = value
            # Create an entry in the "specd" parameter values which will make
            # spearmint happy
            specd_parameter_values[name] = {'type': param_type,
                                            'values': values}
        return specd_parameter_values

    def update(self, parameter_values, objective_value):
        """ Update the optimizer with a new result.

        Parameters
        ----------
        parameter_values : dict
            Dictionary mapping each parameter name to its value.

        objective_value : float
            The value of the objective function achieved by using these
            parameters.

        """
        # Add this parameter setting and objective value to our list of trials
        self.parameter_values.append(parameter_values)
        self.objective_values.append(objective_value)
        # Update the task group with these parameter settings
        self.task_group.inputs = np.array(
            [self.task_group.vectorify(self.spec_parameter_values(values))
             for values in self.parameter_values])
        # Update the task group with the objective value
        self.task_group.values = {'main': np.array(self.objective_values)}

    def suggest(self):
        """ Generate a new parameter suggestion.

        Returns
        -------
        suggestion : dict
            Dictionary mapping parameter names to the suggested values.
        """
        # When not debugging, redirect sys.stderr to devnull!
        if not self.debug:
            old_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
        # Update the model hyperparameters given the current trial list
        self.hypers = self.chooser.fit(
            self.task_group, self.hypers, self.task_config)
        # Get a parameter suggestion
        suggestion = self.chooser.suggest()
        if not self.debug:
            sys.stderr.close()
            sys.stderr = old_stderr
        # Convert the vector format returned by chooser.suggest() to a dict
        suggestion = self.task_group.paramify(np.atleast_1d(suggestion))
        # Retrieve the values, and also flatten the 1d arrays that spearmint
        # forces you to use
        suggestion = dict((name, value['values'][0])
                          for name, value in suggestion.items())
        return suggestion

    def get_best_parameters(self):
        """ Retrieve the best parameter values and objective for all trials.

        Returns
        -------
        best_parameters : dict
            Dictionary mapping parameter names to the suggested values
            corresponding to the trial with the lowest objective value.

        objective_value : float
            The lowest objective function value achieved.
        """
        # Retrieve the index of the lowest objective value
        best_objective = np.argmin(self.objective_values)
        return (self.parameter_values[best_objective],
                self.objective_values[best_objective])
