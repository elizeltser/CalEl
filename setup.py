from pathlib import Path

from setuptools import find_packages, setup

setup(
    name="calel",
    version="0.1.0",
    description="Universal passive component calculator: standard E-series values "
    "for dividers, op-amp gain networks and RC filters",
    long_description=Path(__file__).with_name("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=("tests", "tests.*")),
    python_requires=">=3.8",
    install_requires=[],
    entry_points={
        "console_scripts": ["calel = calel.cli.parser:main"],
        "gui_scripts": ["calel-gui = calel.gui.app:main"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Environment :: Console",
        "Environment :: X11 Applications :: Tk",
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
    ],
)
