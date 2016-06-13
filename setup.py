#!/usr/bin/env python

import sys
from distutils.core import setup

if not sys.version_info[0] == 3:
    sys.exit("Python 2.x is not supported; Python 3.x is required.")

setup(name="tetherback",
      version="0.1.0",
      description=("Create backups of an Android device over USB (requires adb and TWRP recovery)"),
      long_description=open('README.md').read(),
      author="Daniel Lenski",
      author_email="dlenski@gmail.com",
      install_requires=[ 'progressbar2>=3.6', 'tabulate' ],
      license='GPL v3 or later',
      url="https://github.com/dlenski/tetherback",
      packages=["tetherback"],
      entry_points={ 'console_scripts': [ 'tetherback=tetherback.__main__:main' ] }
      )
