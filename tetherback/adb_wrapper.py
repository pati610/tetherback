import subprocess as sp
import re

class AdbWrapper(object):
    def __init__(self, adbbin='adb', devsel=()):
        self.adbbin = adbbin
        self.devsel = tuple(devsel)

    def get_version(self):
         try:
             s, output = sp.getstatusoutput(self.adbcmd('version'))
         except FileNotFoundError:
             raise
         except sp.CalledProcessError:
             raise

         m = re.search(r'^Android Debug Bridge version ((?:\d+.)+\d+)', output)
         if not m:
             raise RuntimeError("could not parse 'adb version' output")

         adbversions = m.group(1)
         adbversion = tuple(int(x) for x in adbversions.split('.'))
         return adbversions, adbversion

    def adbcmd(self, adbargs):
        return (self.adbbin,) + self.devsel + tuple(adbargs)

    def check_output(self, adbargs, **kwargs):
        un = kwargs.pop('universal_newlines', True)
        return sp.check_output(self.adbcmd(adbargs), universal_newlines=un, **kwargs)

    def pipe_out(self, adbargs, **kwargs):
        return sp.Popen(self.adbcmd(adbargs), stdout=sp.PIPE, **kwargs)

    def check_call(self, adbargs, **kwargs):
        return sp.check_call(self.adbcmd(adbargs), **kwargs)

    def call(self, adbargs, **kwargs):
        return sp.call(self.adbcmd(adbargs), **kwargs)
