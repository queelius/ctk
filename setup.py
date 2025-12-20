"""
Setup script for Conversation Toolkit v2
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="conversation-tk",
    version="2.5.0",
    author="CTK Contributors",
    description="A robust toolkit for managing tree-based conversations from multiple sources",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/queelius/ctk",
    packages=find_packages(exclude=['export', 'tests']),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        # No external dependencies - using only stdlib!
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "flake8>=6.0",
            "mypy>=1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "ctk=ctk.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "ctk": ["integrations/**/*.py"],
    },
)