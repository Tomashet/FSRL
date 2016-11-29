"""PolicyGradient."""

from SafeRLBench import AlgorithmBase
from SafeRLBench.spaces import BoundedSpace

import numpy as np
from numpy import array
from numpy.linalg import solve, norm


class PolicyGradient(AlgorithmBase):
    """Implementing many policy gradient methods."""

    def __init__(self,
                 environment, estimator='reinforce',
                 max_it=1000, eps=0.0001, est_eps=0.001,
                 parameter_space=BoundedSpace(array([0, 0, 0]),
                                              array([1, 1, 1])),
                 rate=1):
        """Initialize PolicyGradient."""
        self.environment = environment
        self.parameter_space = parameter_space

        self.max_it = max_it
        self.eps = eps
        self.rate = rate

        if isinstance(estimator, str):
            estimator = estimators[estimator]
        elif issubclass(estimator, PolicyGradientEstimator):
            pass
        else:
            raise ImportError('Invalid Estimator')

        self.estimator = estimator(environment, max_it, est_eps, rate)

    def _initialize(self, policy):
        while True:
            parameter = self.parameter_space.element()

            policy.setParameter(parameter)
            grad = self.estimator(policy)

            if (norm(grad) >= self.eps):
                return parameter

    def _step(self, policy):
        grad = self.estimator(policy)

        parameter = policy.parameter
        policy.setParameter(parameter + grad)

        self.grad = grad

    def _isFinished(self):
        return (norm(self.grad) < self.eps)


class PolicyGradientEstimator(object):

    name = 'Policy Gradient'

    def __init__(self, environment, max_it=200, eps=0.001, rate=1):
        self.environment = environment
        self.state_dim = environment.state.shape[0]
        self.par_dim = self.state_dim + 1

        self.rate = rate
        self.eps = eps
        self.max_it = max_it

    def __call__(self, policy):
        return self._estimate_gradient(policy)


class ForwardFDEstimator(PolicyGradientEstimator):

    name = 'Forward Finite Differences'

    def __init__(self, environment, max_it=200,
                 eps=0.001, rate=1, var=0.5):
        super().__init__(environment, max_it, eps, rate)
        self.var = var

    def _estimate_gradient(self, policy):
        env = self.environment
        var = self.var
        # store current policy parameter
        parameter = policy.parameter

        # using forward differences
        trace = env.rollout(policy)
        Jref = sum([x[2] for x in trace]) / len(trace)

        dJ = np.zeros((2 * self.par_dim))
        dV = np.append(np.eye(self.par_dim), -np.eye(self.par_dim), axis=0)
        dV *= var

        for n in range(self.par_dim):
            variation = dV[n]

            policy.setParameter(parameter + variation)
            trace_n = env.rollout(policy)

            Jn = sum([x[2] for x in trace]) / len(trace_n)

            dJ[n] = Jref - Jn

        grad = solve(dV.T.dot(dV), dV.T.dot(dJ))

        # reset current policy parameter
        policy.setParameter(parameter)

        return grad


class CentralFDEstimator(PolicyGradientEstimator):

    name = 'Central Finite Differences'

    def __init__(self, environment, max_it=200,
                 eps=0.001, rate=1, var=0.5):
        super().__init__(environment, max_it, eps, rate)
        self.var = var

    def _estimate_gradient(self, policy):
        env = self.environment

        parameter = policy.parameter

        dJ = np.zeros((self.par_dim))
        dV = np.eye(self.par_dim) * self.var / 2

        for n in range(self.par_dim):
            variation = dV[n]

            policy.setParameter(parameter + variation)
            trace_n = env.rollout(policy)

            policy.setParameter(parameter - variation)
            trace_n_ref = env.rollout(policy)

            Jn = sum([x[2] for x in trace_n]) / len(trace_n)
            Jn_ref = sum([x[2] for x in trace_n_ref]) / len(trace_n_ref)

            dJ[n] = Jn - Jn_ref

        grad = solve(dV.T.dot(dV), dV.T.dot(dJ))

        policy.setParameter(parameter)

        return grad


class ReinforceEstimator(PolicyGradientEstimator):

    name = 'Reinforce'

    def __init__(self, environment, max_it=200,
                 eps=0.001, rate=1, lam=0.5):
        super().__init__(environment, max_it, eps, rate)
        self.lam = lam

    def _estimate_gradient(self, policy):
        env = self.environment
        par_shape = policy.parameter.shape
        max_it = self.max_it

        b_div = np.zeros(par_shape)
        b_nom = np.zeros(par_shape)

        grads = np.zeros(par_shape)
        grad = np.zeros(par_shape)

        for n in range(max_it):
            trace = env.rollout(policy)

            lam = self.lam

            actions = [x[0] for x in trace]
            states = [x[1] for x in trace]

            rewards_sum = sum([x[2] * lam**k for k, x in enumerate(trace)])

            log_grad_sum = sum(list(map(policy.log_grad, states, actions)))

            b_div_n = log_grad_sum**2
            b_nom_n = b_div_n * rewards_sum

            b_div += b_div_n
            b_nom += b_nom_n

            b = b_nom / b_div
            grad_n = log_grad_sum * (rewards_sum - b)

            grads += grad_n

            grad_old = grad
            grad = grads / (n + 1)

            if (n > 2 and norm(grad_old - grad) < self.eps):
                return grad, trace

        print("Gradient did not converge!")
        return grad


class GPOMDPEstimator(PolicyGradientEstimator):

    name = 'GPOMDP'

    def __init__(self, environment, max_it=200,
                 eps=0.001, rate=1, lam=0.5):
        super().__init__(environment, max_it, eps, rate)
        self.lam = lam

    def _estimate_gradient(self, policy):
        env = self.environment
        H = env.horizon
        shape = policy.parameter_shape

        b_nom = np.zeros((H, shape))
        b_div = np.zeros((H, shape))
        b = np.zeros((H, shape))
        grad = np.zeros(shape)

        lam = self.lam

        for n in range(self.max_it):
            trace = env.rollout(policy)
            b_n = np.zeros((H, shape))

            for k, state in enumerate(trace):
                update = policy.log_grad(state[1], state[0])
                for j in range(k + 1):
                    b_n[j] += update

            fac = n / (n + 1)

            b_n = b_n**2
            b_div = fac * b_div + b_n / (n + 1)

            for k, state in enumerate(trace):
                b_nom[k] = fac * b_nom[k]
                b_nom[k] += b_n[k] * state[2] * lam**k / (n + 1)

            b = b_nom / b_div

            grad_update = np.zeros(shape)
            update = np.zeros(shape)
            for k, state in enumerate(trace):
                update += policy.log_grad(state[1], state[0])
                grad_update += update * (-b[k] + state[2] * lam**k)

            if (n > 2 and norm(grad_update / (n + 1)) < self.eps):
                grad /= (n + 1)
                return grad, trace
            grad += np.nan_to_num(grad_update)

        print("Gradient did not converge!")

        grad /= n + 1
        return grad


'''
Dictionary for resolving estimator strings
'''
estimators = {
    'forward_fd': ForwardFDEstimator,
    'central_fd': CentralFDEstimator,
    'reinforce': ReinforceEstimator,
    'gpomdp': GPOMDPEstimator
}
