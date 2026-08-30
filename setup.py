from setuptools import setup, find_packages

setup(
    name="shield-bypass",
    version="0.2.0",
    packages=find_packages(),
    package_data={"bypass": ["ext/*"]},
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "shield-bypass = bypass.cli:main",
            "bypass = bypass.cli:main",
            "cf-turnstile = bypass.cli:main",
        ],
    },
)
