from setuptools import setup, find_packages
setup(
    name="cleanshot-local",
    version="3.0.6",
    packages=find_packages(include=["display*","core*","claude*","platforms*"]),
)
