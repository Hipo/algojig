import codecs
import os
from setuptools import find_packages, setup
PACKAGE_NAME = "algojig"
VERSION = "0.0.1"
DESCRIPTION = "A testing jig for the Algorand Virtual Machine."
KEYWORDS = "algorand teal tealish"
LICENSE = "MIT"
URL = "https://github.com/Hipo/algojig"
setup(
    name=PACKAGE_NAME,
    version=VERSION,
    description=DESCRIPTION,
    url=URL,
    keywords=KEYWORDS,
    license=LICENSE,
    packages=["algojig"],
    package_data={"algojig": ["algojig_*"]},
    include_package_data=True,
    install_requires=[
        "py-algorand-sdk @ git+https://github.com/algorand/py-algorand-sdk.git@03050cba94553de9a3ac455cba724a3e19ce10c7",
        "tealish >= 0.0.1"
    ],
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)