#!/usr/bin/env python

from distutils.core import setup

setup(name="Android backup via USB",
      version="0.1.0",
      description=("Create backups of an Android device over USB (requires adb and TWRP recovery)"),
      long_description=open('README.md').read(),
      author="Daniel Lenski",
      author_email="dlenski@gmail.com",
      install_requires=[ 'progressbar>=2.3', 'tabulate' ],
      license='GPL v3 or later',
      url="https://github.com/dlenski/tetherback",
      packages=["tetherback"],
      entry_points={ 'console_scripts': [ 'tetherback=tetherback.tetherback' ] }
      )
