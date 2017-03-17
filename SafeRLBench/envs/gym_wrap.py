"""Wrapper for OpenAI Gym."""

from SafeRLBench import EnvironmentBase
from SafeRLBench.error import add_dependency

try:
    import gym
except:
    gym = None


@add_dependency(gym, 'Gym')
class GymWrap(EnvironmentBase):
    """Wrapper class for the OpenAI Gym.

    Attributes
    ----------
    env : gym environment
        Environment of the OpenAI Gym created by gym.make().
    horizon : integer
        Horizon for rollout.
    render : boolean
        Default: False. If True simulation will be rendered during rollouts on
        this instance.
    """

    def __init__(self, env, horizon=100, render=False):
        """Initialize attributes.

        Parameters
        ----------
        env : gym environment
            Instance of the gym environment that should be optimized on.
        horizon : integer
            Horizon for rollout.
        render : boolean
            Default: False ; If True simulation will be rendered during
            rollouts on this instance.
        """
        # Do not use super here.
        EnvironmentBase.__init__(self, env.observation_space, env.action_space,
                                 horizon)
        self.environment = env
        self.render = render
        self.done = False

        self._state = env.reset()

    def _update(self, action):
        observation, reward, done, info = self.environment.step(action)
        self._state = observation
        self.done = done
        return action, observation, reward

    def _reset(self):
        self._state = self.environment.reset()
        self.done = False

    def _rollout(self, policy):
        state = self.environment.reset()
        trace = []
        for n in range(self.horizon):
            if self.render:
                self.environment.render()
            trace.append(self.update(policy(state)))
            state = self.state

            if self.done:
                break
        return trace

    @property
    def state(self):
        """Observable system state."""
        return self._state

    @state.setter
    def state(self, s):
        assert self.state_space.contains(s)
        self.environment.state = s
        self._state = s
