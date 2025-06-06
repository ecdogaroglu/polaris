"""
Core simulation logic for POLARIS experiments.
"""

import os
import time

import numpy as np
import torch
from tqdm import tqdm
from pathlib import Path

from ..agents.memory.replay_buffer import ReplayBuffer
from ..agents.polaris_agent import POLARISAgent
from ..utils.encoding import calculate_observation_dimension, encode_observation
from ..utils.io import (
    create_output_directory,
    flatten_episodic_metrics,
    load_agent_models,
    reset_agent_internal_states,
    save_final_models,
    select_agent_actions,
    set_metrics,
    setup_random_seeds,
    store_transition_in_buffer,
    update_progress_display,
    update_total_rewards,
    write_config_file,
)
from ..utils.metrics import MetricsTracker
from ..visualization import POLARISPlotter


class InvalidBeliefDistributionError(ValueError):
    """Raised when belief distributions contain invalid values that cannot be processed."""
    pass


class ObservationProcessingError(RuntimeError):
    """Raised when observation processing fails due to missing required fields."""
    pass


class Trainer:
    """
    POLARIS training and evaluation class.

    This class encapsulates all the logic for running POLARIS agents in social learning
    environments, including training, evaluation, and model management.
    
    The trainer now uses the MetricsTracker class for efficient metrics collection and 
    processing, providing better organization and easier extensibility.
    """

    def __init__(self, env, args):
        """
        Initialize the trainer.

        Args:
            env: The social learning environment
            args: Command-line arguments/configuration
        """
        self.env = env
        self.args = args
        self.agents = None
        self.replay_buffers = None
        self.metrics_tracker = None
        self.output_dir = None
        self.plotter = POLARISPlotter(
            use_latex=self.args.latex_style if hasattr(self.args, "latex_style") else False,
            use_tex=self.args.use_tex if hasattr(self.args, "use_tex") else False
        )

    def run_agents(self, training=True, model_path=None):
        """
        Run POLARIS agents in the social learning environment.

        Args:
            training: Whether to train the agents (True) or just evaluate (False)
            model_path: Path to load models from (optional)

        Returns:
            learning_rates: Dictionary of learning rates for each agent
            serializable_metrics: Dictionary of metrics for JSON serialization
        """
        # Setup directory
        self.output_dir = create_output_directory(self.args, self.env, training)

        # Initialize agents and components
        obs_dim = calculate_observation_dimension(self.env)
        self.agents = self._initialize_agents(obs_dim)
        load_agent_models(
            self.agents, model_path, self.env.num_agents, training=training
        )

        # Store agents for potential SI visualization
        if hasattr(self.args, "visualize_si") and self.args.visualize_si and training:
            from ..visualization.si_analysis import create_si_visualizations

            create_si_visualizations(self.agents, self.output_dir)

        # Calculate and display theoretical bounds using temporary tracker
        temp_tracker = MetricsTracker(self.env, self.args, training=training)
        theoretical_bounds = temp_tracker.get_theoretical_bounds()

        # Handle training vs evaluation
        if training:
            return self._run_training(theoretical_bounds)
        else:
            return self._run_evaluation(theoretical_bounds)

    def _run_training(self, theoretical_bounds):
        """Run the training process."""
        self.replay_buffers = self._initialize_replay_buffers(
            calculate_observation_dimension(self.env)
        )

        # Write configuration
        write_config_file(self.args, self.env, theoretical_bounds, self.output_dir)

        print(
            f"Running {self.args.num_episodes} training episode(s) with {self.args.horizon} steps per episode"
        )

        # Set agents to training mode
        self._set_agents_train_mode()

        # Initialize episodic metrics to store each episode separately
        episodic_metrics = {"episodes": []}

        # Training episode loop
        for episode in range(self.args.num_episodes):
            # Set a different seed for each episode based on the base seed
            episode_seed = self.args.seed + episode
            setup_random_seeds(episode_seed, self.env)
            print(
                f"\nStarting training episode {episode+1}/{self.args.num_episodes} with seed {episode_seed}"
            )

            # Initialize fresh metrics for this episode
            self.metrics_tracker = MetricsTracker(self.env, self.args, training=True)

            # Run simulation for this episode
            observations, episode_metrics = self._run_simulation(training=True)

            # Store this episode's metrics separately
            episodic_metrics["episodes"].append(episode_metrics)

        # Process training results
        return self._process_training_results(episodic_metrics, theoretical_bounds)

    def _run_evaluation(self, theoretical_bounds):
        """Run the evaluation process."""
        print(
            f"Running evaluation for {self.args.num_episodes} episode(s) with {self.args.horizon} steps per episode"
        )

        # Set agents to evaluation mode
        self._set_agents_eval_mode()

        # Initialize episodic metrics to store each episode separately
        episodic_metrics = {"episodes": []}

        # Evaluation episode loop
        for episode in range(self.args.num_episodes):
            # Set different seed for each episode (offset to avoid training seed overlap)
            episode_seed = self.args.seed + episode + 1000
            setup_random_seeds(episode_seed, self.env)
            print(
                f"\nEvaluating episode {episode+1}/{self.args.num_episodes} with seed {episode_seed}"
            )

            # Initialize fresh metrics for this episode
            self.metrics_tracker = MetricsTracker(self.env, self.args, training=False)

            # Run simulation for this episode
            observations, episode_metrics = self._run_simulation(training=False)

            # Store this episode's metrics separately
            episodic_metrics["episodes"].append(episode_metrics)

        # Process evaluation results
        return self._process_evaluation_results(episodic_metrics, theoretical_bounds)

    def _process_evaluation_results(self, episodic_metrics, theoretical_bounds):
        """Process and save evaluation results."""
        # Aggregate results across episodes
        combined_metrics = self._aggregate_episode_results(episodic_metrics)

        # Use MetricsTracker to calculate learning rates
        temp_tracker = MetricsTracker(self.env, self.args, training=False)
        temp_tracker.metrics = combined_metrics
        learning_rates = temp_tracker.get_learning_rates()

        # Add evaluation summary
        evaluation_summary = self._calculate_evaluation_summary(
            episodic_metrics, learning_rates
        )

        # Use MetricsTracker to prepare serializable metrics
        serializable_metrics = temp_tracker.prepare_for_serialization(
            learning_rates,
            theoretical_bounds,
            self.args.horizon,
        )

        # Save detailed evaluation results
        evaluation_serializable_metrics = {
            "evaluation_summary": evaluation_summary,
            "episodic_data": episodic_metrics,
            "aggregated_metrics": combined_metrics,
            "learning_rates": learning_rates,
            "theoretical_bounds": theoretical_bounds,
            "episode_length": self.args.horizon,
            "num_episodes": self.args.num_episodes,
        }

        # Use MetricsTracker to save metrics files
        temp_tracker.save_to_file(self.output_dir)
        temp_tracker.save_to_file(
            self.output_dir,
            filename="detailed_evaluation_results.json"
        )

        # Generate plots with LaTeX style if requested
        self.plotter.generate_all_plots(
            combined_metrics,
            self.env,
            self.args,
            self.output_dir,
            training=False,
            episodic_metrics=episodic_metrics,
        )

        return episodic_metrics, serializable_metrics

    def _process_training_results(self, episodic_metrics, theoretical_bounds):
        """Process and save training results."""
        # Create a flattened version of metrics
        combined_metrics = flatten_episodic_metrics(
            episodic_metrics, self.env.num_agents
        )

        # Use MetricsTracker to calculate learning rates
        temp_tracker = MetricsTracker(self.env, self.args, training=True)
        temp_tracker.metrics = combined_metrics
        learning_rates = temp_tracker.get_learning_rates()

        # Create SI visualizations after training is complete
        if hasattr(self.args, "visualize_si") and self.args.visualize_si:
            from ..visualization.si_analysis import create_si_visualizations

            print("\n===== FINAL SI STATE (AFTER TRAINING) =====")
            create_si_visualizations(self.agents, self.output_dir)

        # Use MetricsTracker to prepare serializable metrics
        serializable_metrics = temp_tracker.prepare_for_serialization(
            learning_rates,
            theoretical_bounds,
            self.args.horizon,
        )

        # Also save the episodic metrics for more detailed analysis
        episodic_serializable_metrics = {
            "episodic_data": episodic_metrics,
            "learning_rates": learning_rates,
            "theoretical_bounds": theoretical_bounds,
            "episode_length": self.args.horizon,
            "num_episodes": self.args.num_episodes,
        }

        # Use MetricsTracker to save metrics files
        temp_tracker.save_to_file(self.output_dir)
        temp_tracker.save_to_file(
            self.output_dir,
            filename="episodic_metrics.json"
        )

        if self.args.save_model:
            save_final_models(self.agents, self.output_dir)
        
        # Generate plots with LaTeX style if requested (skip if plotting is disabled)
        if not getattr(self.args, 'disable_plotting', False):
            self.plotter.generate_all_plots(
                combined_metrics,
                self.env,
                self.args,
                self.output_dir,
                training=True,
                episodic_metrics=episodic_metrics,
            )

        return episodic_metrics, serializable_metrics

    def _run_simulation(self, training=True):
        """Run the main simulation loop for either training or evaluation."""
        mode_str = "training" if training else "evaluation"
        print(f"Starting {mode_str} for {self.args.horizon} steps...")
        start_time = time.time()

        # Initialize environment and agents
        observations = self.env.initialize()
        total_rewards = np.zeros(self.env.num_agents)

        # Initialize agents and components
        obs_dim = calculate_observation_dimension(self.env)
        self.agents = self._initialize_agents(obs_dim)

        # Print environment state information
        self._print_environment_info()

        # If using SI, set the current true state for all agents (only during training)
        if training:
            self._setup_si_for_training()

        # Set global metrics for access in other functions
        set_metrics(self.metrics_tracker.get_raw_metrics())

        # Reset and initialize agent internal states
        reset_agent_internal_states(self.agents)

        # Extract environment parameters for MPE calculation
        env_params = self._extract_environment_params()

        # Initialize attention weights storage
        attention_weights_history = []

        # Main simulation loop
        steps_iterator = tqdm(range(self.args.horizon), desc=mode_str.capitalize())
        for step in steps_iterator:
            # Get agent actions
            actions, action_probs = select_agent_actions(self.agents, self.metrics_tracker.get_raw_metrics())

            # Collect policy information for continuous actions
            policy_info = self._collect_policy_information(training)

            # Take environment step
            next_observations, rewards, done, info = self.env.step(
                actions, action_probs
            )


            # Add policy distribution parameters to info
            if policy_info:
                info.update(policy_info)
                if training:  # Only add env_params during training
                    info["env_params"] = env_params

            # Update rewards
            if rewards:
                update_total_rewards(total_rewards, rewards)

            # Update agent states and store transitions
            self._update_agent_states(
                observations, next_observations, actions, rewards, step, training
            )

            # Capture attention weights from GNN agents
            step_attention_weights = self._capture_attention_weights()
            if step_attention_weights is not None:
                attention_weights_history.append(step_attention_weights)

            # Update observations for next step
            observations = next_observations

            # For Strategic Experimentation environment, add allocations to info
            if hasattr(self.env, "safe_payoff"):  # Strategic experimentation environment
                if (hasattr(self.args, "continuous_actions") and self.args.continuous_actions):
                    # For continuous actions, use the actions directly (allocation values)
                    # Only set if not already provided by environment
                    if "allocations" not in info:
                        info["allocations"] = actions
                else:
                    # For discrete actions, ALWAYS use action 1 probability as allocation to risky arm
                    # This overwrites the environment's allocation which uses discrete actions
                    allocations = {}
                    for agent_id, probs in action_probs.items():
                        if len(probs) >= 2:  # Ensure we have at least 2 actions (action 0 and action 1)
                            # Use probability of action 1 as allocation to risky arm
                            allocations[agent_id] = float(probs[1])
                        else:
                            # Fallback: use 0.5 if probabilities are malformed
                            allocations[agent_id] = 0.5
                    info["allocations"] = allocations

            # Store and process metrics
            self.metrics_tracker.update(info, actions, action_probs)

            # Update progress display
            update_progress_display(
                steps_iterator, info, total_rewards, step, training=training
            )

            if done:
                if training:
                    self._handle_si_state_changes()
                break

        # Store attention weights in metrics
        if attention_weights_history:
            self.metrics_tracker.get_raw_metrics()["attention_weights"] = attention_weights_history

        # Add episode summary to metrics
        total_time = time.time() - start_time
        raw_metrics = self.metrics_tracker.get_raw_metrics()
        raw_metrics["episode_time"] = total_time
        raw_metrics["total_rewards"] = {
            i: total_rewards[i] for i in range(self.env.num_agents)
        }
        raw_metrics["final_observations"] = observations

        # Display completion time
        print(f"{mode_str.capitalize()} completed in {total_time:.2f} seconds")

        return observations, raw_metrics

    def _set_agents_train_mode(self):
        """Set all agents to training mode."""
        for agent in self.agents.values():
            agent.set_train_mode()
        print(f"Set {len(self.agents)} agents to training mode")

    def _set_agents_eval_mode(self):
        """Set all agents to evaluation mode."""
        for agent in self.agents.values():
            agent.set_eval_mode()
        print(f"Set {len(self.agents)} agents to evaluation mode")

    def _aggregate_episode_results(self, episodic_metrics):
        """Aggregate results across multiple episodes."""
        if not episodic_metrics["episodes"]:
            return {}

        # Get the structure from the first episode
        first_episode = episodic_metrics["episodes"][0]
        aggregated = {}

        # Aggregate different types of metrics
        for key, value in first_episode.items():
            if key == "episode_time":
                # Average episode time
                times = [
                    ep.get("episode_time", 0) for ep in episodic_metrics["episodes"]
                ]
                aggregated[key] = np.mean(times)
            elif key == "total_rewards":
                # Average total rewards per agent
                all_rewards = [
                    ep.get("total_rewards", {}) for ep in episodic_metrics["episodes"]
                ]
                if all_rewards and all_rewards[0]:
                    aggregated[key] = {}
                    for agent_id in all_rewards[0].keys():
                        rewards = [
                            ep_rewards.get(agent_id, 0) for ep_rewards in all_rewards
                        ]
                        aggregated[key][agent_id] = np.mean(rewards)
            elif isinstance(value, dict) and all(
                isinstance(v, list) for v in value.values()
            ):
                # Metrics with agent-specific lists (like belief_distributions)
                aggregated[key] = {}
                for agent_id in value.keys():
                    # Concatenate lists across episodes
                    agent_data = []
                    for ep in episodic_metrics["episodes"]:
                        if key in ep and agent_id in ep[key]:
                            agent_data.extend(ep[key][agent_id])
                    aggregated[key][agent_id] = agent_data
            elif isinstance(value, list):
                # Simple lists - concatenate across episodes
                aggregated_list = []
                for ep in episodic_metrics["episodes"]:
                    if key in ep:
                        aggregated_list.extend(ep[key])
                aggregated[key] = aggregated_list

        return aggregated

    def _calculate_evaluation_summary(self, episodic_metrics, learning_rates):
        """Calculate summary statistics for the evaluation."""
        summary = {
            "num_episodes": len(episodic_metrics["episodes"]),
            "learning_rates": learning_rates,
        }

        # Calculate reward statistics
        if (
            episodic_metrics["episodes"]
            and "total_rewards" in episodic_metrics["episodes"][0]
        ):
            reward_stats = {}
            for agent_id in range(self.env.num_agents):
                rewards = [
                    ep["total_rewards"].get(agent_id, 0)
                    for ep in episodic_metrics["episodes"]
                    if "total_rewards" in ep
                ]
                if rewards:
                    reward_stats[agent_id] = {
                        "mean": np.mean(rewards),
                        "std": np.std(rewards),
                        "min": np.min(rewards),
                        "max": np.max(rewards),
                    }
            summary["reward_statistics"] = reward_stats

        # Calculate action accuracy if we have true states and actions
        if (
            episodic_metrics["episodes"]
            and any("true_states" in ep for ep in episodic_metrics["episodes"])
            and any("agent_actions" in ep for ep in episodic_metrics["episodes"])
        ):

            accuracy_stats = {}
            for agent_id in range(self.env.num_agents):
                correct_actions = 0
                total_actions = 0

                for ep in episodic_metrics["episodes"]:
                    if "true_states" in ep and "agent_actions" in ep:
                        true_states = ep["true_states"]
                        agent_actions = ep["agent_actions"].get(agent_id, [])

                        for i, (true_state, action) in enumerate(
                            zip(true_states, agent_actions)
                        ):
                            if action == true_state:
                                correct_actions += 1
                            total_actions += 1

                if total_actions > 0:
                    accuracy_stats[agent_id] = correct_actions / total_actions

            summary["action_accuracy"] = accuracy_stats

        return summary

    class AttentionWeightCaptureError(RuntimeError):
        """Raised when attention weights cannot be captured from agents."""
        pass

    def _capture_attention_weights(self):
        """
        Capture attention weights from GNN agents for visualization.
        
        Returns:
            Attention matrix if available, None otherwise
            
        Raises:
            AttentionWeightCaptureError: If attention weights cannot be captured from any agent
        """
        # Always capture attention weights since GNN is always used now
        for agent_id, agent in self.agents.items():
            try:
                # Get the inference module
                if hasattr(agent, "inference_module"):
                    # Get attention weights
                    attention_weights = agent.inference_module.get_attention_weights()
                    if attention_weights is not None:
                        # Get the latest edge index if available
                        if hasattr(agent.inference_module, "latest_edge_index"):
                            edge_index = agent.inference_module.latest_edge_index
                            attention_matrix = agent.inference_module.get_attention_matrix(
                                edge_index, attention_weights
                            )
                            if attention_matrix is not None:
                                return attention_matrix
            except Exception as e:
                # Continue to next agent, but collect errors
                continue
        
        # If we get here, no agent could provide attention weights
        # This might be normal in some cases, so we'll return None instead of raising
        return None

    def _print_environment_info(self):
        """Print information about the current environment state."""
        if hasattr(self.env, "safe_payoff"):
            # Strategic Experimentation Environment
            if self.env.true_state == 0:
                print(
                    f"True state is bad. Drift rate: {self.env.drift_rates[self.env.true_state]} "
                    f"Jump rate: {self.env.jump_rates[self.env.true_state]} "
                    f"Jump size: {self.env.jump_sizes[self.env.true_state]}"
                )
            else:
                print(
                    f"True state is good. Drift rate: {self.env.drift_rates[self.env.true_state]} "
                    f"Jump rate: {self.env.jump_rates[self.env.true_state]} "
                    f"Jump size: {self.env.jump_sizes[self.env.true_state]}"
                )
        else:
            # Social Learning Environment
            print(f"True state is {self.env.true_state}")

    def _setup_si_for_training(self):
        """Setup Synaptic Intelligence for training if enabled."""
        if hasattr(self.args, "use_si") and self.args.use_si:
            current_true_state = self.env.true_state
            for agent_id, agent in self.agents.items():
                if hasattr(agent, "use_si") and agent.use_si:
                    agent.current_true_state = current_true_state
                    # Set the current task in the SI trackers
                    if hasattr(agent, "belief_si") and hasattr(agent, "policy_si"):
                        agent.belief_si.set_task(current_true_state)
                        agent.policy_si.set_task(current_true_state)
                        # Mark that this agent has path integrals calculated so the SI loss will be applied
                        agent.path_integrals_calculated = True
                    print(
                        f"Set current true state {current_true_state} for agent {agent_id}"
                    )

    def _extract_environment_params(self):
        """Extract environment parameters for metric calculation."""
        env_params = {}
        if hasattr(self.env, "safe_payoff"):
            env_params = {
                "safe_payoff": self.env.safe_payoff,
                "drift_rates": self.env.drift_rates,
                "jump_rates": self.env.jump_rates,
                "jump_sizes": self.env.jump_sizes,
                "background_informativeness": self.env.background_informativeness,
                "num_agents": self.env.num_agents,
                "true_state": self.env.true_state,
            }
        return env_params

    def _collect_policy_information(self, training=True):
        """Collect policy information during simulation."""
        policy_info = {}
        agent_beliefs = {}

        # Always collect agent beliefs for strategic experimentation environment
        # This is needed for belief accuracy plots regardless of action type
        if hasattr(self.env, "safe_payoff"):  # Strategic experimentation environment
            for agent_id, agent in self.agents.items():
                # Extract agent's belief about the state
                if (
                    hasattr(agent, "current_belief_distribution")
                    and agent.current_belief_distribution is not None
                ):
                    # Check if belief distribution is valid (not NaN)
                    if torch.isnan(agent.current_belief_distribution).any():
                        # Raise error instead of using fallback default value
                        raise InvalidBeliefDistributionError(
                            f"Agent {agent_id} has NaN values in belief distribution. "
                            f"This indicates numerical instability in the belief processor. "
                            f"Check learning rates, network initialization, or input preprocessing."
                        )
                    else:
                        # For continuous signals, the belief is directly used
                        if agent.current_belief_distribution.size(1) == 1:
                            # Continuous case - map the value to [0,1] range
                            raw_value = agent.current_belief_distribution[
                                0, 0
                            ].item()
                            # Clip to ensure it's in [0,1] range
                            agent_beliefs[agent_id] = max(0.0, min(1.0, raw_value))
                        # For binary state (common case), the belief about good state is the probability assigned to state 1
                        elif agent.current_belief_distribution.shape[-1] == 2:
                            agent_beliefs[agent_id] = (
                                agent.current_belief_distribution[0, 1].item()
                            )
                        else:
                            # For multi-state cases, use a weighted average
                            belief_weights = torch.arange(
                                agent.current_belief_distribution.shape[-1],
                                device=agent.current_belief_distribution.device,
                            ).float()
                            belief_weights = belief_weights / (
                                agent.current_belief_distribution.shape[-1] - 1
                            )  # Normalize to [0,1]
                            agent_beliefs[agent_id] = torch.sum(
                                agent.current_belief_distribution * belief_weights,
                                dim=-1,
                            ).item()

        if hasattr(self.args, "continuous_actions") and self.args.continuous_actions:
            policy_means = []
            policy_stds = []

            for agent_id, agent in self.agents.items():
                if hasattr(agent, "continuous_actions") and agent.continuous_actions and hasattr(agent.policy, "forward"):
                    # Get policy parameters directly
                    context_manager = torch.no_grad() if not training else torch.enable_grad()
                    with context_manager:
                        action_logits, allocation = agent.policy(
                            agent.current_belief, agent.current_latent
                        )

                    policy_means.append(allocation.item())
                    policy_stds.append(0.0)  # No std for deterministic policy

            policy_info = {
                "policy_means": policy_means,
                "policy_stds": policy_stds,
                "agent_beliefs": agent_beliefs,
            }
        else:
            # For discrete actions, only include agent beliefs
            policy_info = {
                "agent_beliefs": agent_beliefs,
            }

        return policy_info

    def _handle_si_state_changes(self):
        """Handle Synaptic Intelligence state changes when episodes end."""
        if hasattr(self.args, "use_si") and self.args.use_si:
            current_true_state = self.env.true_state
            print(f"Current true state: {current_true_state}")
            # Check if this is a new true state for any agent
            for agent_id, agent in self.agents.items():
                if (
                    hasattr(agent, "use_si")
                    and agent.use_si
                    and hasattr(agent, "seen_true_states")
                ):
                    if current_true_state not in agent.seen_true_states:
                        # We have a new true state, register the previous task and set the new one
                        if hasattr(agent, "belief_si") and hasattr(agent, "policy_si"):
                            # Register completed task for both networks
                            agent.belief_si.register_task()
                            agent.policy_si.register_task()

                            # Set new task
                            agent.belief_si.set_task(current_true_state)
                            agent.policy_si.set_task(current_true_state)

                            # Store task-specific trackers for visualization
                            if hasattr(agent, "state_belief_si_trackers"):
                                # Create clones of the trackers for visualization
                                agent.state_belief_si_trackers[current_true_state] = (
                                    agent._clone_si_tracker(agent.belief_si)
                                )
                                agent.state_policy_si_trackers[current_true_state] = (
                                    agent._clone_si_tracker(agent.policy_si)
                                )

                            print(
                                f"Registered completed task and set new true state {current_true_state} for agent {agent_id}"
                            )

                    # Add current true state to the set of seen states
                    agent.seen_true_states.add(current_true_state)
                    # Update the current true state
                    agent.current_true_state = current_true_state

    def _update_agent_states(
        self, observations, next_observations, actions, rewards, step, training=True
    ):
        """Update agent states and store transitions in replay buffer during training."""

        # Check if we're using continuous actions
        continuous_actions = (
            hasattr(self.args, "continuous_actions") and self.args.continuous_actions
        )

        for agent_id, agent in self.agents.items():
            # Get current and next observations
            obs_data = observations[agent_id]
            next_obs_data = next_observations[agent_id]

            # Extract signals and neighbor actions based on environment type
            if "signal" in obs_data:
                # Social Learning Environment format
                signal = obs_data["signal"]
                next_signal = next_obs_data["signal"]
                neighbor_actions = obs_data["neighbor_actions"]
                next_neighbor_actions = next_obs_data["neighbor_actions"]
            elif "background_signal" in obs_data:
                # Strategic Experimentation Environment format
                # Get the background signal increment if available, otherwise use the background signal
                if (
                    "background_increment" in obs_data
                    and "background_increment" in next_obs_data
                ):
                    # Use the raw increment values directly
                    signal = obs_data["background_increment"]
                    next_signal = next_obs_data["background_increment"]
                else:
                    # Raise error instead of falling back to background signal
                    raise ObservationProcessingError(
                        "Missing 'background_increment' field in strategic experimentation observations. "
                        "This field is required for proper signal processing. "
                        "Check environment configuration and observation generation."
                    )

                # Get allocations instead of discrete actions
                neighbor_allocations = obs_data.get("neighbor_allocations", {})
                next_neighbor_allocations = next_obs_data.get(
                    "neighbor_allocations", {}
                )
                # Handle None values by using empty dictionaries instead
                # Always use raw allocation values for continuous actions, never convert to binary
                neighbor_actions = (
                    {} if neighbor_allocations is None else neighbor_allocations
                )
                next_neighbor_actions = (
                    {}
                    if next_neighbor_allocations is None
                    else next_neighbor_allocations
                )

            # Encode observations
            # Determine if we're using continuous signals based on the environment type
            continuous_signal = "background_increment" in obs_data

            signal_encoded, actions_encoded = encode_observation(
                signal=signal,
                neighbor_actions=neighbor_actions,
                num_agents=self.env.num_agents,
                num_states=self.env.num_states,
                continuous_actions=continuous_actions,
                continuous_signal=continuous_signal,
            )
            next_signal_encoded, next_actions_encoded = encode_observation(
                signal=next_signal,
                neighbor_actions=next_neighbor_actions,
                num_agents=self.env.num_agents,
                num_states=self.env.num_states,
                continuous_actions=continuous_actions,
                continuous_signal=continuous_signal,
            )

            # Get current belief and latent states (before observation update)
            belief = (
                agent.current_belief.detach().clone()
            )  # Make a copy to ensure we have the pre-update state
            latent = agent.current_latent.detach().clone()

            # Update agent belief state
            if training:
                next_belief, next_dstr = agent.observe(signal_encoded, actions_encoded)
                # Infer latent state for next observation
                next_latent = agent.infer_latent(
                    signal_encoded,
                    actions_encoded,
                    (
                        rewards[agent_id]
                        if isinstance(rewards[agent_id], float)
                        else rewards[agent_id]["total"]
                    ),
                    next_signal_encoded,
                )
            else:
                # During evaluation, use no_grad to prevent gradient computation
                with torch.no_grad():
                    next_belief, next_dstr = agent.observe(signal_encoded, actions_encoded)
                    # Infer latent state for next observation
                    next_latent = agent.infer_latent(
                        signal_encoded,
                        actions_encoded,
                        (
                            rewards[agent_id]
                            if isinstance(rewards[agent_id], float)
                            else rewards[agent_id]["total"]
                        ),
                        signal_encoded,  # Use current signal for latent inference during evaluation
                    )

            # Store belief distribution if available
            belief_distribution = agent.get_belief_distribution()
            self.metrics_tracker.get_raw_metrics()["belief_distributions"][agent_id].append(
                belief_distribution.detach().cpu().numpy()
            )

            # Store transition in replay buffer and update networks (only during training)
            if training and agent_id in self.replay_buffers:

                # Get mean and logvar from inference
                mean, logvar = agent.get_latent_distribution_params()

                # Get reward value (handle both scalar and dictionary cases)
                reward_value = (
                    rewards[agent_id]["total"]
                    if isinstance(rewards[agent_id], dict)
                    else rewards[agent_id]
                )

                # Store transition
                # For continuous actions, store the actual allocation value instead of the action index
                action_to_store = actions[agent_id]
                if continuous_actions and hasattr(agent, "continuous_actions") and agent.continuous_actions:
                    # Get the actual allocation from the policy
                    _, allocation = agent.policy(agent.current_belief, agent.current_latent)
                    action_to_store = allocation.item()
                
                store_transition_in_buffer(
                    self.replay_buffers[agent_id],
                    signal_encoded,
                    actions_encoded,
                    belief,
                    latent,
                    action_to_store,
                    reward_value,
                    next_signal_encoded,
                    next_actions_encoded,
                    next_belief,
                    next_latent,
                    mean,
                    logvar,
                )

                # Update networks if enough samples
                if (
                    len(self.replay_buffers[agent_id]) > self.args.batch_size
                    and step % self.args.update_interval == 0
                ):
                    # Sample a batch from the replay buffer
                    batch = self.replay_buffers[agent_id].sample(self.args.batch_size)
                    # Update network parameters and capture training losses
                    losses = agent.update(batch)
                    
                    # Track training losses for catastrophic forgetting diagnostics
                    if training and hasattr(self.metrics_tracker, 'update_training_losses'):
                        self.metrics_tracker.update_training_losses(agent_id, losses)
                    
                    # Also capture action logits for CF diagnostics during training
                    if training and hasattr(agent, 'action_logits'):
                        if agent.action_logits is not None and hasattr(self.metrics_tracker, 'update_action_logits'):
                            self.metrics_tracker.update_action_logits(agent_id, agent.action_logits)

    def _initialize_agents(self, obs_dim):
        """Initialize POLARIS agents."""
        print(
            f"Initializing {self.env.num_agents} agents{' for evaluation' if self.args.eval_only else ''}..."
        )

        # Log GNN configuration (always used now)
        print(
            f"Using Graph Neural Network with {self.args.gnn_layers} layers, {self.args.attn_heads} attention heads, and temporal window of {self.args.temporal_window}"
        )

        # Log if excluding final layers from SI
        if (
            hasattr(self.args, "si_exclude_final_layers")
            and self.args.si_exclude_final_layers
            and hasattr(self.args, "use_si")
            and self.args.use_si
        ):
            print("Excluding final layers from Synaptic Intelligence protection")

        # Log if using continuous actions
        if hasattr(self.args, "continuous_actions") and self.args.continuous_actions:
            print("Using continuous action space for strategic experimentation")

        agents = {}

        for agent_id in range(self.env.num_agents):
            # Determine action dimension based on environment and action space type
            if (
                hasattr(self.args, "continuous_actions")
                and self.args.continuous_actions
            ):
                # For continuous actions, we use 1 dimension (allocation between 0 and 1)
                action_dim = 1
            else:
                # For discrete actions, we use num_states dimensions
                action_dim = self.env.num_states

            agent = POLARISAgent(
                agent_id=agent_id,
                num_agents=self.env.num_agents,
                num_states=self.env.num_states,
                observation_dim=obs_dim,
                action_dim=action_dim,
                hidden_dim=self.args.hidden_dim,
                belief_dim=self.args.belief_dim,
                latent_dim=self.args.latent_dim,
                learning_rate=self.args.learning_rate,
                discount_factor=self.args.discount_factor,
                entropy_weight=self.args.entropy_weight,
                kl_weight=self.args.kl_weight,
                device=self.args.device,
                buffer_capacity=self.args.buffer_capacity,
                max_trajectory_length=self.args.horizon,
                
                # GNN configuration (always used)
                num_gnn_layers=getattr(self.args, "gnn_layers", 2),
                num_attn_heads=getattr(self.args, "attn_heads", 4),
                temporal_window_size=getattr(self.args, "temporal_window", 5),
                
                # Synaptic Intelligence configuration
                use_si=self.args.use_si if hasattr(self.args, "use_si") else False,
                si_importance=(
                    self.args.si_importance
                    if hasattr(self.args, "si_importance")
                    else 100.0
                ),
                si_damping=(
                    self.args.si_damping if hasattr(self.args, "si_damping") else 0.1
                ),
                si_exclude_final_layers=(
                    self.args.si_exclude_final_layers
                    if hasattr(self.args, "si_exclude_final_layers")
                    else False
                ),
                continuous_actions=(
                    self.args.continuous_actions
                    if hasattr(self.args, "continuous_actions")
                    else False
                ),
            )

            agents[agent_id] = agent

        # Set environment parameters for strategic experimentation
        if hasattr(self.env, "safe_payoff"):  # Strategic experimentation environment
            for agent_id, agent in agents.items():
                agent.set_environment_parameters(
                    drift_rates=self.env.drift_rates,
                    jump_rates=self.env.jump_rates, 
                    jump_sizes=self.env.jump_sizes,
                    background_informativeness=self.env.background_informativeness,
                    time_step=self.env.time_step
                )

        return agents

    def _initialize_replay_buffers(self, obs_dim):
        """Initialize replay buffers for training."""
        replay_buffers = {}

        for agent_id in self.agents:
            replay_buffers[agent_id] = ReplayBuffer(
                capacity=self.args.buffer_capacity,
                observation_dim=obs_dim,
                belief_dim=self.args.belief_dim,
                latent_dim=self.args.latent_dim,
                device=self.args.device,
                sequence_length=8,  # Default sequence length for sampling
            )
        return replay_buffers

    def quick_evaluate(self, num_steps=100):
        """
        Perform a quick evaluation for basic performance metrics.

        Args:
            num_steps: Number of steps for quick evaluation

        Returns:
            Dictionary with basic performance metrics
        """
        # Set agents to eval mode
        self._set_agents_eval_mode()

        # Initialize
        observations = self.env.initialize()
        total_rewards = np.zeros(self.env.num_agents)
        correct_actions = np.zeros(self.env.num_agents)

        print(f"Quick evaluation for {num_steps} steps...")

        for step in range(num_steps):
            # Get actions
            actions, _ = select_agent_actions(self.agents, {})

            # Environment step
            next_observations, rewards, done, info = self.env.step(actions, {})

            # Update rewards
            if rewards:
                for agent_id, reward in rewards.items():
                    if isinstance(reward, dict):
                        total_rewards[agent_id] += reward["total"]
                    else:
                        total_rewards[agent_id] += reward

            # Check action correctness if true state is available
            if hasattr(self.env, "true_state"):
                for agent_id, action in actions.items():
                    if action == self.env.true_state:
                        correct_actions[agent_id] += 1

            observations = next_observations

            if done:
                break

        # Calculate metrics
        results = {
            "average_reward": float(np.mean(total_rewards)),
            "total_rewards": {
                i: float(total_rewards[i]) for i in range(self.env.num_agents)
            },
        }

        if hasattr(self.env, "true_state"):
            results["action_accuracy"] = {
                i: float(correct_actions[i] / num_steps)
                for i in range(self.env.num_agents)
            }
            results["average_accuracy"] = float(np.mean(correct_actions / num_steps))

        return results

    # Public evaluation methods for external use
    def evaluate(self, num_episodes=None, num_steps=None):
        """
        Evaluate the trained agents.

        Args:
            num_episodes: Number of episodes to evaluate (optional)
            num_steps: Number of steps per episode (optional)

        Returns:
            Evaluation results dictionary
        """
        # Use provided values or fall back to args
        eval_episodes = (
            num_episodes
            if num_episodes is not None
            else getattr(self.args, "num_episodes", 1)
        )
        eval_steps = (
            num_steps if num_steps is not None else getattr(self.args, "horizon", 1000)
        )

        # Temporarily store original values
        original_episodes = self.args.num_episodes
        original_horizon = self.args.horizon

        # Set the values for evaluation
        self.args.num_episodes = eval_episodes
        self.args.horizon = eval_steps

        try:
            # Run evaluation using the existing evaluation logic
            episodic_metrics, serializable_metrics = self.run_agents(training=False)
            
            # Return in the format expected by external callers
            return {
                "episodic_metrics": episodic_metrics,
                "aggregated_metrics": serializable_metrics,
                "learning_rates": serializable_metrics.get("learning_rates", {}),
                "evaluation_summary": serializable_metrics.get("evaluation_summary", {}),
                "num_episodes": eval_episodes,
                "steps_per_episode": eval_steps,
            }
        finally:
            # Restore original values
            self.args.num_episodes = original_episodes
            self.args.horizon = original_horizon


