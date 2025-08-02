from setuptools import setup, find_packages
import os


class PackageConfigurationError(RuntimeError):
    """Raised when package configuration cannot be determined."""
    pass


# Read the README file with fallback
def get_long_description():
    readme_path = "README.md"
    if os.path.exists(readme_path):
        try:
            with open(readme_path, "r", encoding="utf-8") as fh:
                return fh.read()
        except (IOError, OSError) as e:
            raise PackageConfigurationError(f"Could not read README.md: {e}")
    else:
        raise PackageConfigurationError(f"README.md not found at {readme_path}")

long_description = get_long_description()

# Read version from __init__.py
def get_version():
    init_file = os.path.join("polaris", "__init__.py")
    if not os.path.exists(init_file):
        raise PackageConfigurationError(f"Version file {init_file} not found")
        
    try:
        with open(init_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    return line.split("=")[1].strip().strip('"').strip("'")
        raise PackageConfigurationError(f"Version string not found in {init_file}")
    except (IOError, OSError) as e:
        raise PackageConfigurationError(f"Could not read version from {init_file}: {e}")

setup(
    name="polaris-marl",
    version=get_version(),
    author="Ege Can Doğaroğlu",
    author_email="ecdogaroglu@gmail.com",  # Update with actual email
    description="POLARIS: Partially Observable Learning with Active Reinforcement In Social Environments",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ecdogaroglu/polaris",
    project_urls={
        "Bug Tracker": "https://github.com/ecdogaroglu/polaris/issues",
        "Documentation": "https://github.com/ecdogaroglu/polaris#documentation",
        "Source Code": "https://github.com/ecdogaroglu/polaris",
    },
    packages=find_packages(exclude=["tests*", "experiments*", "results*", "docs*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Environment :: GPU :: NVIDIA CUDA",
        "Environment :: MacOS X",
    ],
    keywords="multi-agent reinforcement-learning social-learning graph-neural-networks pytorch",
    python_requires=">=3.8",
    install_requires=[
        "torch>=1.8.0",
        "numpy>=1.20.0",
        "matplotlib>=3.4.0",
        "networkx>=2.6.0",
        "scikit-learn>=1.0.0",
        "tqdm>=4.60.0",
        "scipy>=1.7.0",
        "pandas>=1.3.0",
        "seaborn>=0.11.0",
    ],
    extras_require={
        "gnn": [
            "torch-geometric>=2.0.0",
            "torch-scatter>=2.0.9",
            "torch-sparse>=0.6.13",
            "torch-cluster>=1.6.0",
            "torch-spline-conv>=1.2.1",
        ],
        "dev": [
            "pytest>=6.0.0",
            "pytest-cov>=2.12.0",
            "black>=21.0.0",
            "flake8>=3.9.0",
            "isort>=5.9.0",
            "mypy>=0.910",
            "pre-commit>=2.15.0",
        ],
        "docs": [
            "sphinx>=4.0.0",
            "sphinx-rtd-theme>=0.5.0",
            "sphinx-autodoc-typehints>=1.12.0",
        ],
        "all": [
            "torch-geometric>=2.0.0",
            "torch-scatter>=2.0.9",
            "torch-sparse>=0.6.13",
            "torch-cluster>=1.6.0",
            "torch-spline-conv>=1.2.1",
            "pytest>=6.0.0",
            "pytest-cov>=2.12.0",
            "black>=21.0.0",
            "flake8>=3.9.0",
            "isort>=5.9.0",
            "mypy>=0.910",
            "pre-commit>=2.15.0",
            "sphinx>=4.0.0",
            "sphinx-rtd-theme>=0.5.0",
            "sphinx-autodoc-typehints>=1.12.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "polaris-simulate=polaris.simulation:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    test_suite="tests",
)