"""
Installable Django package for the CAP-IPAWS Bridge composer UI.

Installed by the README's quick-start:

    cd cap_composer_module
    pip install -e .
    python manage.py runserver

Wagtail is listed as an extra rather than a hard dependency so the bare
composer works on a vanilla Django stack; ``pip install -e .[wagtail]``
pulls Wagtail in for jurisdictions that want the full CMS surface around
the alert authoring views.
"""
from setuptools import find_packages, setup

setup(
    name="cap-composer",
    version="0.1.0",
    description="Web UI for authoring CAP 1.2 alerts; ships with the cap-ipaws-bridge.",
    author="Rohith Kadivendi",
    author_email="kv11@iitbbs.ac.in",
    license="MIT",
    python_requires=">=3.10",
    packages=find_packages(exclude=("tests", "tests.*")),
    include_package_data=True,
    install_requires=[
        "Django>=4.2,<6.0",
        "requests>=2.31",
    ],
    extras_require={
        "wagtail": ["wagtail>=5.2,<7.0"],
        "dev": ["pytest>=7.0", "pytest-django>=4.5"],
    },
    entry_points={
        "console_scripts": [
            "cap-composer = cap_composer_app.cli:main",
        ],
    },
    classifiers=[
        "Framework :: Django",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
