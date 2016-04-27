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

adbxp = Enum('AdbTransport', 'tcp pipe_xo pipe_b64 pipe_bin')

p = argparse.ArgumentParser(description='''Tool to create TWRP and nandroid-style backups of an Android device running TWRP recovery, using adb-over-USB, without touching the device's internal storage or SD card.''')
p.add_argument('-s', dest='specific', metavar='DEVICE_ID', default=None, help="Specific device ID (shown by adb devices). Default is sole USB-connected device.")
p.add_argument('-o', '--output-path', default=".", help="Set optional output path for backup files.")
p.add_argument('-N', '--nandroid', action='store_true', help="Make nandroid backup; raw images rather than tarballs for /system and /data partitions (default is TWRP backup)")
p.add_argument('-0', '--dry-run', action='store_true', help="Just show the partition map and backup plan, then exit.")
p.add_argument('-v', '--verbose', action='count', default=0)
g = p.add_argument_group('Data transfer methods',
                         description="The default is to use TCP forwarding. If you have problems, please try --base64 for a slow but reliable transfer method (and report issues at http://github.com/dlenski/tetherback/issues)")
x = g.add_mutually_exclusive_group()
x.add_argument('-t','--tcp', dest='transport', action='store_const', const=adbxp.tcp, default=adbxp.tcp,
               help="ADB TCP forwarding (fast, should work with any host OS, but prone to timing problems)")
x.add_argument('-x','--exec-out', dest='transport', action='store_const', const=adbxp.pipe_xo,
               help="ADB exec-out binary pipe (should work with any host OS, but only with newer versions of adb and TWRP)")
x.add_argument('-6','--base64', dest='transport', action='store_const', const=adbxp.pipe_b64,
               help="Base64 pipe (very slow, should work with any host OS)")
x.add_argument('-P','--pipe', dest='transport', action='store_const', const=adbxp.pipe_bin,
               help="ADB shell binary pipe (fast, but will PROBABLY CORRUPT DATA on non-Linux host)")
g = p.add_argument_group('Backup contents')
g.add_argument('-M', '--media', action='store_true', default=False, help="Include /data/media* in TWRP backup")
g.add_argument('-D', '--data-cache', action='store_true', default=False, help="Include /data/*-cache in TWRP backup")
g.add_argument('-R', '--recovery', action='store_true', default=False, help="Include recovery partition in backup")
g.add_argument('-C', '--no-cache', dest='cache', action='store_true', default=False, help="Include /cache partition in backup")
g.add_argument('-U', '--no-userdata', dest='userdata', action='store_false', default=True, help="Omit /data partition from backup")
g.add_argument('-S', '--no-system', dest='system', action='store_false', default=True, help="Omit /system partition from backup")
g.add_argument('-B', '--no-boot', dest='boot', action='store_false', default=True, help="Omit boot partition from backup")
g.add_argument('-X', '--extra', action='append', dest='extra', metavar='NAME', default=[], help="Include extra partition as raw image")
args = p.parse_args()

try:
    adbversions = sp.check_output(('adb','version')).strip().decode().split()[-1]
except Exception:
    p.error("could not determine ADB version -- is the adb binary in your PATH?\n\thttp://developer.android.com/tools/help/adb.html")
adbversion = tuple(int(x) for x in adbversions.split('.'))
if adbversion<(1,0,31):
    p.error("found ADB version %s, but version >= 1.0.31 is required" % adbversions)

if args.specific:
    adbcmd = ('adb','-s',args.specific)
else:
    adbcmd = ('adb','-d')

if args.nandroid:
    rp = args.extra + [x for x in ('boot','recovery','system','userdata','cache') if getattr(args, x)]
    backup_partitions = {p: ('%s.tar.gz'%p, None, None) for p in rp}
else:
    rp = args.extra + [x for x in ('boot','recovery') if getattr(args, x)]
    backup_partitions = {p: ('%s.emmc.win'%p, None, None) for p in rp}
    mp = [x for x in ('cache','system') if getattr(args, x)]
    backup_partitions.update(**{p: ('%s.ext4.win'%p, '/%s'%p, '-p') for p in mp})

    if args.userdata:
        data_omit = []
        if not args.media: data_omit.append("media*")
        if not args.data_cache: data_omit.append("*-cache")
        backup_partitions['userdata'] = ('data.ext4.win', '/data', '-p'+''.join(' --exclude="%s"'%x for x in data_omit))

########################################

def backup_how(devname, bp):
    if devname not in bp:
        return [None, None]
    else:
        fn, mount, taropts = bp[devname]
        if mount:
            return [fn, "tar -czC %s %s" % (mount, taropts)]
        else:
            return [fn, "gzipped raw image"]

def really_mount(dev, node, mode='ro'):
    for opts in (mode, 'remount,'+mode):
        if sp.check_output(adbcmd+('shell','mount -o %s %s %s 2>/dev/null && echo ok' % (opts, dev, node))).strip():
            break
    for l in sp.check_output(adbcmd+('shell','mount')).splitlines():
        f = l.decode().split()
        mdev, mnode, mtype = (f[0], f[2], f[4]) if (f[1], f[3])==('on','type') else (f[0], f[1], f[2])
        if mdev==dev or mnode==node:
            return mtype

def really_umount(dev, node):
    for opts in ('','-f','-l','-r'):
        if sp.check_output(adbcmd+('shell','umount %s 2>/dev/null && echo ok' % dev)).strip():
            break
        if sp.check_output(adbcmd+('shell','umount %s 2>/dev/null && echo ok' % node)).strip():
            break
    for l in sp.check_output(adbcmd+('shell','mount')).splitlines():
        f = l.decode().split()
        mdev, mnode = (f[0], f[2]) if (f[1], f[3])==('on','type') else (f[0], f[1])
        if mdev==dev or mnode==node:
            return False
    return True

def really_forward(port1, port2):
    for port in range(port1, port2):
        if sp.call(adbcmd+('forward','tcp:%d'%port,'tcp:%d'%port))==0:
            return port
        time.sleep(1)

def really_unforward(port, tries=3):
    for retry in range(tries):
        if sp.call(adbcmd+('forward','--remove','tcp:%d'%port))==0:
            return retry+1
        time.sleep(1)

def uevent_dict(path):
    lines = sp.check_output(adbcmd+('shell','cat "%s"'%path)).decode().splitlines()
    d = {}
    for l in lines:
        if '=' not in l:
            print( "WARNING: don't understand this line from %s: %s" % (repr(path), repr(l)), file=stderr )
        else:
            k, v = l.split('=',1)
            d[k] = v
    return d

# check that device is booted into TWRP
kver = sp.check_output(adbcmd+('shell','uname -r')).strip().lower().decode()
if '-twrp-' not in kver:
    p.error("device reports non-TWRP kernel (%s)\n\tplease boot into TWRP recovery and retry." % kver)
else:
    print("Device reports TWRP kernel (%s)." % kver, file=stderr)

# build partition map
partmap = []
d = uevent_dict('/sys/block/mmcblk0/uevent')
nparts = int(d['NPARTS'])
print("Reading partition map for mmcblk0 (%d partitions)..." % nparts, file=stderr)
pbar = ProgressBar(maxval=nparts, widgets=['  partition map: ', Percentage(), ' ', ETA()]).start()
for ii in range(1, nparts+1):
    d = uevent_dict('/sys/block/mmcblk0/mmcblk0p%d/uevent'%ii)
    size = int(sp.check_output(adbcmd+('shell','cat /sys/block/mmcblk0/mmcblk0p%d/size'%ii)))
    partmap.append((d['PARTNAME'], d['DEVNAME'], int(d['PARTN']), size))
    pbar.update(ii)
else:
    pbar.finish()

if args.dry_run or args.verbose > 0:
    print()
    print(tabulate( [[ devname, partname, size//2] + backup_how(partname, backup_partitions)
                     for partname, devname, partn, size in partmap],
                    [ 'BLOCK DEVICE','NAME','SIZE (KiB)','FILENAME','FORMAT' ] ))
    print()

if args.dry_run:
    p.exit()

# check for optional backup path
if not os.path.exists(args.output_path):
   print("Creating backup directory %s" % args.output_path, file=stderr)
   os.mkdir(args.output_path)

# backup partitions
backupdir = os.path.join(args.output_path, ("nandroid-backup-" if args.nandroid else "twrp-backup-") + datetime.datetime.now().strftime('%Y-%m-%d--%H-%M-%S'))
os.mkdir(backupdir)
os.chdir(backupdir)
print("Saving backup images in %s/ ..." % backupdir, file=stderr)

for partname, devname, partn, size in partmap:
    if partname in backup_partitions:
        fn, mount, taropts = backup_partitions[partname]

        if mount:
            print("Saving tarball of %s (mounted at %s), %d MiB uncompressed..." % (devname, mount, size/2048))
            fstype = really_mount('/dev/block/'+devname, mount)
            if not fstype:
                raise RuntimeError('%s: could not mount %s' % (partname, mount))
            elif fstype != 'ext4':
                raise RuntimeError('%s: expected ext4 filesystem, but found %s' % (partname, fstype))
            cmdline = 'tar -czC %s %s . 2> /dev/null' % (mount, taropts or '')
        else:
            print("Saving partition %s (%s), %d MiB uncompressed..." % (partname, devname, size/2048))
            if not really_umount('/dev/block/'+devname, mount):
                raise RuntimeError('%s: could not unmount %s' % (partname, mount))
            cmdline = 'dd if=/dev/block/%s 2> /dev/null | gzip -f' % devname

        if args.transport == adbxp.pipe_bin:
            # need stty -onlcr to make adb-shell an 8-bit-clean pipe: http://stackoverflow.com/a/20141481/20789
            child = sp.Popen(adbcmd+('shell','stty -onlcr && '+cmdline), stdout=sp.PIPE)
            block_iter = iter(lambda: child.stdout.read(65536), b'')
        elif args.transport == adbxp.pipe_b64:
            # pipe output through base64: excruciatingly slow
            child = sp.Popen(adbcmd+('shell',cmdline+'| base64'), stdout=sp.PIPE)
            block_iter = iter(lambda: b64dec(b''.join(child.stdout.readlines(65536))), b'')
        elif args.transport == adbxp.pipe_xo:
            # use adb exec-out, which is
            # (a) only available with newer versions of adb on the host, and
            # (b) only works with newer versions of TWRP (works with 2.8.0 for @kerlerm)
            # https://plus.google.com/110558071969009568835/posts/Ar3FdhknHo3
            # https://android.googlesource.com/platform/system/core/+/5d9d434efadf1c535c7fea634d5306e18c68ef1f/adb/commandline.c#1244
            child = sp.Popen(adbcmd+('exec-out',cmdline), stdout=sp.PIPE)
            block_iter = iter(lambda: child.stdout.read(65536), b'')
        else:
            port = really_forward(5600+partn, 5700+partn)
            if not port:
                raise RuntimeError('%s: could not ADB-forward a TCP port')
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
            if not really_unforward(port):
                raise RuntimeError('could not remove ADB-forward for TCP port %d' % port)
        child.terminate()
