from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='drbot',
    version='2.0.0',
    description='DrBot - A modular Reddit bot to cure your moderation woes.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/c0d3rman/DRBOT',
    author='c0d3rman',
    license='CC BY-SA 4.0',
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=["praw", "prawcore", "schedule", "tomlkit"],
)
