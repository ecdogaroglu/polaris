#!/usr/bin/env python3
"""
POLARIS Strategic Experimentation Experiment Script (Refactored)

This script runs experiments with POLARIS agents in a strategic experimentation environment
based on the Keller and Rady (2020) framework, where agents allocate resources between
a safe arm with known payoff and a risky arm with unknown state-dependent payoff.

This is a wrapper for the refactored POLARIS implementation.
"""

import os
import torch
import numpy as np
import argparse
from pathlib import Path

from polaris.config.experiment_config import (
    ExperimentConfig, AgentConfig, TrainingConfig, StrategicExpConfig
)
from polaris.environments import StrategicExperimentationEnvironment
from polaris.training.simulation import run_experiment
from polaris.utils.device import get_best_device


def main():
    """Main function to run the Strategic Experimentation experiment."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run Keller-Rady Strategic Experimentation")
    parser.add_argument('--agents', type=int, default=2, help='Number of agents')
    parser.add_argument('--episodes', type=int, default=10, help='Number of episodes')
    parser.add_argument('--horizon', type=int, default=1000, help='Steps per episode')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument('--output', type=str, default='results', help='Output directory')
    parser.add_argument('--eval', action='store_true', default=False, help='Evaluation mode')
    parser.add_argument('--load', type=str, default=None, help='Path to load models')
    parser.add_argument('--use-si', action='store_true', default=True, help='Use Synaptic Intelligence')
    parser.add_argument('--si-importance', type=float, default=10.0, help='SI importance weight')
    parser.add_argument('--plot-allocations', action='store_true', default=True, help='Plot allocations')
    parser.add_argument('--plot-incentives', action='store_true', default=True, help='Plot agent incentives')
    parser.add_argument('--plot-states', action='store_true', default=True, help='Plot internal states')
    parser.add_argument('--plot-accuracy', action='store_true', default=True, help='Plot belief and allocation accuracy')
    parser.add_argument('--plot-cf-diagnostics', action='store_true', default=True, help='Plot catastrophic forgetting diagnostics')
    parser.add_argument('--latex-style', action='store_true', default=True, help='Use LaTeX styling')
    parser.add_argument('--device', type=str, default="cpu", choices=['cpu', 'mps', 'cuda'], 
                       help='Device to use')
    parser.add_argument('--update-interval', type=int, default=1, help='Update interval')
    args = parser.parse_args()
    
    # Set initial random seeds
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # Create configuration
    config = create_strategic_config(args)
    
    print("\n=== Strategic Experimentation (Keller-Rady) ===\n")
    
    # Create environment
    env = StrategicExperimentationEnvironment(
        num_agents=config.environment.num_agents,
        num_states=config.environment.num_states,
        network_type=config.environment.network_type,
        horizon=config.training.horizon,
        seed=config.environment.seed,
        safe_payoff=config.environment.safe_payoff,
        drift_rates=config.environment.drift_rates,
        jump_rates=config.environment.jump_rates,
        jump_sizes=config.environment.jump_sizes,
        diffusion_sigma=config.environment.diffusion_sigma,
        background_informativeness=config.environment.background_informativeness,
        time_step=config.environment.time_step
    )
    
    # Print experiment information
    print(f"Running Strategic Experimentation experiment (Keller-Rady framework)")
    print(f"Network type: {config.environment.network_type}, Number of agents: {config.environment.num_agents}")
    print(f"Safe payoff: {config.environment.safe_payoff}")
    print(f"Drift rates: {config.environment.drift_rates}")
    print(f"Jump rates: {config.environment.jump_rates}")
    print(f"Background informativeness: {config.environment.background_informativeness}")
    
    # Print action space type
    if config.environment.continuous_actions:
        print(f"Using continuous action space for resource allocation")
    else:
        print(f"Using discrete action space (action 1 probability mapped to risky arm allocation)")
    
    # Print learning method
    if config.agent.discount_factor == 0.0:
        print(f"Using average reward criterion (discount factor: 0.0)")
    else:
        print(f"Using discounted reward criterion (discount factor: {config.agent.discount_factor})")
    
    # Print episode information if training
    if not config.eval_only and config.training.num_episodes > 1:
        print(f"\nTraining with {config.training.num_episodes} episodes, {config.training.horizon} steps per episode")
        print(f"True state will be randomly selected at the beginning of each episode with different seeds")
    
    if config.agent.use_si:
        print(f"Using Synaptic Intelligence with importance {config.agent.si_importance}")
    
    # Run experiment
    print(f"\nRunning experiment...")
    print(f"Device: {config.device}")
    
    metrics, processed_metrics = run_experiment(env, config)
    
    print("\nExperiment completed!")
    print(f"Results saved to: {config.output_dir}/{config.exp_name}")


def create_strategic_config(args) -> ExperimentConfig:
    """Create experiment configuration for strategic experimentation."""
    # Agent configuration
    agent_config = AgentConfig(
        learning_rate=1e-4,
        discount_factor=0.0,  # Use average reward for strategic experimentation
        use_si=args.use_si,
        si_importance=args.si_importance,
        si_damping=0.01,
        si_exclude_final_layers=False
    )
    
    # Training configuration
    training_config = TrainingConfig(
        batch_size=8,
        buffer_capacity=50,
        num_episodes=args.episodes,
        horizon=args.horizon
    )
    
    # Strategic experimentation environment configuration
    env_config = StrategicExpConfig(
        environment_type='strategic_experimentation',
        num_agents=args.agents,
        seed=args.seed,
        safe_payoff=0.5,
        drift_rates=[0, 1],  # first values for bad state, second for good state
        jump_rates=[0, 0.1],
        jump_sizes=[1.0, 1.0],
        diffusion_sigma=0.1,
        background_informativeness=0.001,
        time_step=1.0, # For discrete time steps, this is the time step size
        continuous_actions=False
    )
    
    # Experiment name (GNN is always used now, so no need for _gnn suffix)
    exp_name = f"strategic_experimentation_agents_{args.agents}"
    if args.use_si:
        exp_name += "_si"
    
    # Create complete configuration
    config = ExperimentConfig(
        agent=agent_config,
        training=training_config,
        environment=env_config,
        device=args.device,
        output_dir=args.output,
        exp_name=exp_name,
        save_model=not args.eval,
        load_model=args.load,
        eval_only=args.eval,
        plot_internal_states=args.plot_states,
        plot_allocations=args.plot_allocations,
        plot_incentives=args.plot_incentives,
        plot_accuracy=args.plot_accuracy,
        plot_cf_diagnostics=args.plot_cf_diagnostics,
        latex_style=args.latex_style,
        use_tex=False  # Avoid LaTeX rendering issues, use LaTeX-like styling instead
    )
    
    return config


if __name__ == "__main__":
    main() 