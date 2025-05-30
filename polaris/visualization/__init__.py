"""
POLARIS Visualization System

A modular plotting framework for analyzing POLARIS experiments.
"""

from .plots.allocations import AllocationPlotter
from .plots.beliefs import BeliefPlotter
from .plots.incentives import IncentivePlotter
from .plots.learning_curves import LearningCurvePlotter


class POLARISPlotter:
    """
    Main plotting coordinator for POLARIS experiments.

    This class orchestrates different plotting modules to generate
    comprehensive visualizations from experiment results.
    """

    def __init__(self, use_latex: bool = False, use_tex: bool = False):
        """
        Initialize the POLARIS plotter.

        Args:
            use_latex: Whether to use LaTeX styling for publication-quality plots
            use_tex: Whether to use actual LaTeX rendering (requires LaTeX installation)
        """
        self.use_latex = use_latex
        self.use_tex = use_tex
        if use_latex:
            from .styles.latex import set_latex_style

            set_latex_style(use_tex=use_tex)

        # Initialize specialized plotters
        self.learning_curves = LearningCurvePlotter(use_latex=use_latex)
        self.beliefs = BeliefPlotter(use_latex=use_latex)
        self.allocations = AllocationPlotter(use_latex=use_latex)
        self.incentives = IncentivePlotter(use_latex=use_latex)

    def generate_all_plots(
        self, metrics, env, args, output_dir, training=True, episodic_metrics=None
    ):
        """
        Generate all relevant plots for the experiment.

        Args:
            metrics: Combined metrics dictionary
            env: Environment object
            args: Command-line arguments
            output_dir: Directory to save plots
            training: Whether this is training or evaluation
            episodic_metrics: Optional dictionary of metrics for each episode
        """
        # Check if metrics are available
        if not metrics:
            print("No metrics available for plotting")
            return

        print("🎨 Generating visualization plots...")

        # Add environment information to metrics
        metrics["num_states"] = env.num_states
        metrics["num_agents"] = env.num_agents
        metrics["environment_type"] = env.__class__.__name__

        # Generate learning curves
        self.learning_curves.plot(metrics, env, args, output_dir, episodic_metrics)

        # Generate belief visualizations if requested
        if hasattr(args, "plot_internal_states") and args.plot_internal_states:
            self.beliefs.plot(metrics, env, args, output_dir)

        # Generate allocation plots for strategic experimentation
        if (
            hasattr(args, "plot_allocations")
            and args.plot_allocations
            and hasattr(env, "safe_payoff")
        ):
            self.allocations.plot(metrics, env, args, output_dir)

        # Generate incentive plots for strategic experimentation
        if (
            hasattr(args, "plot_incentives")
            and args.plot_incentives
            and hasattr(env, "safe_payoff")
        ):
            print(f"DEBUG: Calling incentive plotter...")
            print(f"DEBUG: args.plot_incentives = {args.plot_incentives}")
            print(f"DEBUG: hasattr(env, 'safe_payoff') = {hasattr(env, 'safe_payoff')}")
            print(f"DEBUG: 'agent_incentives' in metrics = {'agent_incentives' in metrics}")
            self.incentives.plot(metrics, env, args, output_dir)
        else:
            print(f"DEBUG: Incentive plotting conditions not met:")
            print(f"DEBUG: hasattr(args, 'plot_incentives') = {hasattr(args, 'plot_incentives')}")
            if hasattr(args, "plot_incentives"):
                print(f"DEBUG: args.plot_incentives = {args.plot_incentives}")
            print(f"DEBUG: hasattr(env, 'safe_payoff') = {hasattr(env, 'safe_payoff')}")

        print("✅ Visualization plots generated successfully!")

