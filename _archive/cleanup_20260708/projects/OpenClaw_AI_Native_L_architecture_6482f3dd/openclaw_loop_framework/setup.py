from setuptools import find_packages, setup


setup(
    name="openclaw-loop-framework",
    version="0.1.0",
    description="Three-layer autonomous execution framework for LLM agents",
    python_requires=">=3.10",
    packages=find_packages(),
    package_dir={"": "."},
)
