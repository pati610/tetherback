#!/usr/bin/env python3
#
# Inspired by https://gist.github.com/inhies/5069663
#
# Currently backs up /data, /system, and /boot partitions
# Excludes /data/media*, just as TWRP does

import subprocess as sp
import os, sys, datetime, socket, time, argparse
from sys import stderr
from base64 import standard_b64decode as b64dec
from progressbar import ProgressBar, Percentage, ETA, FileTransferSpeed, Bar
from tabulate import tabulate
from enum import Enum

adbxp = Enum('AdbTransport', 'tcp pipe_b64 pipe_bin')

p = argparse.ArgumentParser()
p.add_argument('-s', dest='specific', default=None, help="Specific device ID (shown by adb devices). Default is sole USB-connected device.")
p.add_argument('-v', '--verbose', action='count', default=0)
p.add_argument('-X', '--transfer-method', dest='transport', choices=[x.name for x in adbxp], default='tcp',
               help='''Data transfer method (default is %(default)s):
                       - tcp: transfer data using ADB TCP forwarding (should not corrupt data, but prone to timing problems)
                       - base64: transfer data using base64 pipe (slow but reliable, should work with any host OS)
                       - pipe: transfer data using 8-bit clean pipe (fast, but will PROBABLY CORRUPT DATA except on Linux host)''')
g = p.add_argument_group('Backup contents')
g.add_argument('-n', '--nandroid', action='store_true', help="Make nandroid backup; raw images rather than tarballs for /system and /data partitions (default is TWRP backup)")
g.add_argument('-x', '--extra', action='append', dest='extra', default=[], help="Include extra partition as raw image (by partition map name)")
args = p.parse_args()
args.transport = adbxp[args.transport]

if args.specific:
    adbcmd = ('adb','-s',args.specific)
else:
    adbcmd = ('adb','-d')

if args.nandroid:
    backup_partitions = dict(
        boot = ('boot.img.gz', None, None),
        userdata = ('userdata.img.gz', None, None),
        system = ('system.img.gz', None, None),
        **{x:('%s.tar.gz'%x, None, None) for x in args.extra}
    )
else:
    backup_partitions = dict(
        boot = ('boot.emmc.win', None, None),
        userdata = ('data.ext4.win', '/data', '-p --exclude="media*"'),
        system = ('system.ext4.win', '/system', '-p'),
        **{x:('%s.img.win'%x, None, None) for x in args.extra}
    )
    backup_partitions.update()

def backup_how(x):
    if x is None:
        return "(skip)"
    else:
        fn, mount, taropts = x
        if mount:
            return "%s (tarball of %s)" % (fn, mount)
        else:
            return "%s (raw image)" % fn

# check that device is booted into TWRP
kver = sp.check_output(adbcmd+('shell','uname -r')).strip().decode()
if '-twrp-' not in kver:
    print("ERROR: Device reports non-TWRP kernel (%s); please boot into TWRP recovery and retry." % kver, file=stderr)
    sys.exit(1)
else:
    print("Device reports TWRP kernel (%s)." % kver, file=stderr)

# build partition map
partmap = []
d = dict(l.decode().split('=',1) for l in sp.check_output(adbcmd+('shell','cat /sys/block/mmcblk0/uevent')).splitlines())
nparts = int(d['NPARTS'])
print("Reading partition map for mmcblk0 (%d partitions)..." % nparts, file=stderr)
pbar = ProgressBar(maxval=nparts, widgets=['  partition map: ', Percentage(), ' ', ETA()]).start()
for ii in range(1, nparts+1):
    d = dict(l.decode().split('=',1) for l in sp.check_output(adbcmd+('shell','cat /sys/block/mmcblk0/mmcblk0p%d/uevent'%ii)).splitlines())
    size = int(sp.check_output(adbcmd+('shell','cat /sys/block/mmcblk0/mmcblk0p%d/size'%ii)))
    partmap.append((d['PARTNAME'], d['DEVNAME'], int(d['PARTN']), size))
    pbar.update(ii)
else:
    pbar.finish()

if args.verbose > 0:
    print(tabulate(  [[ '','NAME','DEVICE','SIZE (KiB)','BACKUP?' ]]
                   + [[ partn, partname, devname, size//2, backup_how(backup_partitions.get(partname)) ]
                   for partname, devname, partn, size in partmap] ))
    #print("\tNAME\tDEVICE\tSIZE(MiB)\tBACKUP?", file=stderr)
    #for partname, devname, partn, size in partmap:
    #    print("%d:\t%s\t%s\t%d\t\t%s" % (partn, partname, devname, size/2048, backup_partitions.get(partname, "(skip)")))

# backup partitions
backupdir = ("nandroid-backup-" if args.nandroid else "twrp-backup-") + datetime.datetime.now().strftime('%Y-%m-%d--%H-%M-%S')
os.mkdir(backupdir)
os.chdir(backupdir)
print("Saving backup images in %s/ ..." % backupdir, file=stderr)

for partname, devname, partn, size in partmap:
    if partname in backup_partitions:
        fn, mount, taropts = backup_partitions[partname]

        if mount:
            print("Saving tarball of %s (mounted at %s), %d MiB uncompressed..." % (devname, mount, size/2048))
            # FIXME: should do a more careful check to verify that the partition has been mounted
            sp.check_call(adbcmd+('shell','mount -r %s'%mount), stdout=sp.DEVNULL)
            cmdline = 'tar -cz -C %s %s . 2> /dev/null' % (mount, taropts or '')
        else:
            print("Saving partition %s (%s), %d MiB uncompressed..." % (partname, devname, size/2048))
            # FIXME: should do a more careful check to verify that the partition has been unmounted
            sp.check_call(adbcmd+('shell','umount /dev/block/%s'%devname), stdout=sp.DEVNULL)
            cmdline = 'dd if=/dev/block/%s 2> /dev/null | gzip -f' % devname

        if args.transport == adbxp.pipe_bin:
            # need stty -onlcr to make adb-shell an 8-bit-clean pipe: http://stackoverflow.com/a/20141481/20789
            child = sp.Popen(adbcmd+('shell','stty -onlcr && '+cmdline), stdout=sp.PIPE)
            block_iter = iter(lambda: child.stdout.read(65536), b'')
        elif args.transport == adbxp.pipe_b64:
            # pipe output through base64: excruciatingly slow
            child = sp.Popen(adbcmd+('shell',cmdline+'| base64'), stdout=sp.PIPE)
            block_iter = iter(lambda: b64dec(child.stdout.readline()), b'')
        else:
            # FIXME: try ports until one works
            port = 5600+partn
            sp.check_call(adbcmd+('forward','tcp:%d'%port, 'tcp:%d'%port))
            child = sp.Popen(adbcmd+('shell',cmdline + '| nc -l -p%d -w3'%port), stdout=sp.PIPE)

            # FIXME: need a better way to check that socket is ready to transmit
            time.sleep(1)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('localhost', port))
            block_iter = iter(lambda: s.recv(65536), b'')

        pbwidgets = ['  %s: ' % fn, Percentage(), ' ', ETA(), ' ', FileTransferSpeed()]
        pbar = ProgressBar(maxval=size*512, widgets=pbwidgets).start()

        with open(fn, 'wb') as out:
            for block in block_iter:
                out.write(block)
                pbar.update(out.tell())
            else:
                pbar.maxval = out.tell() or pbar.maxval # need to adjust for the smaller compressed size
                pbar.finish()

        if args.transport==adbxp.tcp:
            s.close()
            # try to remove port forwarding
            for retry in range(3):
                if sp.call(adbcmd+('forward','--remove','tcp:%d'%port))==0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('could not remove adb TCP forwarding (port %d)' % port)
        child.terminate()
