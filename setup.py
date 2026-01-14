#!/usr/bin/env python3
"""Setup script for On-Premises Automation System."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="onprem-automation",
    version="1.0.0",
    author="Infrastructure Automation Team",
    author_email="infra-automation@example.com",
    description="Comprehensive on-premises infrastructure automation system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/example/onprem-automation",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Systems Administration",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=[
        "pyyaml>=6.0",
        "aiohttp>=3.8.0",
        "pyvmomi>=8.0.0.1",
        "netmiko>=4.1.0",
        "paramiko>=3.0.0",
    ],
    extras_require={
        "full": [
            "napalm>=4.0.0",
            "nornir>=3.3.0",
            "pywinrm>=0.4.3",
            "fabric>=3.0.0",
        ],
        "api": [
            "fastapi>=0.100.0",
            "uvicorn>=0.23.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "onprem-auto=onprem_automation.cli:main",
        ],
    },
)
