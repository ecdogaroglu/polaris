"""
POLARIS: Partially Observable Learning with Active Reinforcement In Social Environments

A comprehensive multi-agent reinforcement learning framework for strategic social learning
environments with theoretical foundations and practical implementations.
"""

__version__ = "2.0.3"
__author__ = "Ege Can Doğaroğlu"
__email__ = "ecdogaroglu@gmail.com"
__license__ = "MIT"
__description__ = (
    "POLARIS: Partially Observable Learning with Active Reinforcement In Social Environments"
)

# Import only basic configuration functions that don't depend on complex dependencies
try:
    from polaris.config.args import parse_args
except ImportError:
    parse_args = None

try:
    from polaris.config.defaults import get_default_config
except ImportError:
    get_default_config = None

# Try to import main components, but don't fail if dependencies are missing
try:
    from polaris.agents.polaris_agent import POLARISAgent
except ImportError:
    POLARISAgent = None

try:
    from polaris.environments.social_learning import SocialLearningEnvironment
except ImportError:
    SocialLearningEnvironment = None

try:
    from polaris.environments.strategic_exp import StrategicExperimentationEnvironment
except ImportError:
    StrategicExperimentationEnvironment = None

try:
    from polaris.training.trainer import Trainer
except ImportError:
    Trainer = None

# Version info
__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "__license__",
    "__description__",
    "POLARISAgent",
    "SocialLearningEnvironment",
    "StrategicExperimentationEnvironment",
    "Trainer",
    "parse_args",
    "get_default_config",
]

# Package metadata
__pkg_name__ = "polaris-marl"
__pkg_url__ = "https://github.com/ecdogaroglu/polaris"
__pkg_description__ = __description__
__pkg_long_description__ = """
POLARIS bridges economic social learning theory and multi-agent reinforcement learning 
through a novel theoretical framework: Partially Observable Active Markov Games (POAMGs). 
Unlike traditional approaches that treat multi-agent learning as a technical challenge, 
POLARIS models strategic adaptation and policy evolution as fundamental features of 
social learning environments.
"""


def get_version():
    """Get the current version of POLARIS."""
    return __version__


def get_info():
    """Get package information."""
    return {
        "name": __pkg_name__,
        "version": __version__,
        "author": __author__,
        "email": __email__,
        "license": __license__,
        "url": __pkg_url__,
        "description": __description__,
        "long_description": __pkg_long_description__,
    }
