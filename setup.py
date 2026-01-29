"""
Setup script for Conversation Toolkit v2
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="conversation-tk",
    version="2.6.0",
    author="Alex Towell",
    author_email="lex@metafunctor.com",
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
        "sqlalchemy>=2.0.0",
        "alembic>=1.13.0",
        "pydantic>=2.0.0",
        "requests>=2.31.0",
        "rich>=13.0.0",
        "mcp>=1.0.0",
        "networkx>=3.0",
        "scikit-learn>=1.3.0",
        "numpy>=1.24.0",
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