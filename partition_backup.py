#!/usr/bin/env python3
#
# Inspired by https://gist.github.com/inhies/5069663
#
# Currently backs up /data, /system, and /boot partitions

import subprocess as sp
import os, sys, datetime, socket, time
from sys import stderr
from progressbar import ProgressBar, Percentage, ETA, FileTransferSpeed, Bar

# check that device is booted into TWRP
kver = sp.check_output(('adb','shell','uname -r')).strip().decode()
if '-twrp-' not in kver:
    print("ERROR: Device reports non-TWRP kernel (%s); please boot into TWRP recovery and retry." % kver, file=stderr)
    sys.exit(1)
else:
    print("Device reports TWRP kernel (%s)." % kver, file=stderr)

# build partition map
partmap = []
d = dict(l.decode().split('=',1) for l in sp.check_output(('adb','shell','cat /sys/block/mmcblk0/uevent')).splitlines())
nparts = int(d['NPARTS'])
print("Reading partition map for mmcblk0 (%d partitions)..." % nparts, file=stderr)
pbar = ProgressBar(maxval=nparts, widgets=['  partition map: ', Percentage(), ' ', ETA()]).start()
for ii in range(1, nparts+1):
    d = dict(l.decode().split('=',1) for l in sp.check_output(('adb','shell','cat /sys/block/mmcblk0/mmcblk0p%d/uevent'%ii)).splitlines())
    size = int(sp.check_output(('adb','shell','cat /sys/block/mmcblk0/mmcblk0p%d/size'%ii)))
    partmap.append((d['PARTNAME'], d['DEVNAME'], int(d['PARTN']), size))
    pbar.update(ii)
else:
    pbar.finish()

# backup partitions
backupdir = "partition-backup-%s" % datetime.datetime.now().strftime('%Y-%m-%d--%H-%M-%S')
os.mkdir(backupdir)
os.chdir(backupdir)
print("Saving partition images in %s/ ..." % backupdir, file=stderr)

for partname, devname, partn, size in partmap:
    if partname in ('boot','system','userdata'):
        print("Saving partition %s (%s), %d MiB uncompressed..." % (partname, devname, size/2048))
        sp.check_call(('adb','shell','umount /dev/block/%s'%devname), stdout=sp.DEVNULL)


        port = 5500+partn
        sp.check_call(('adb','forward','tcp:%d'%port, 'tcp:%d'%port))
        child = sp.Popen(('adb','shell','dd if=/dev/block/%s | gzip | nc -l -p%d -w3'%(devname,port)), stdout=sp.DEVNULL)
        time.sleep(1)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('localhost', port))

        pbwidgets = ['  %s: ' % devname, Percentage(), ' ', ETA(), ' ', FileTransferSpeed()]
        pbar = ProgressBar(maxval=size*512, widgets=pbwidgets).start()

        with open('%s.img.gz' % partname, 'wb') as out:
            for block in iter(lambda: s.recv(65536), b''):
                out.write(block)
                pbar.update(out.tell())
            else:
                s.close()
                pbar.maxval = out.tell() or pbar.maxval # need to adjust for the smaller compressed size
                pbar.finish()

        child.terminate()
        sp.check_call(('adb','forward','--remove','tcp:%d'%port))
