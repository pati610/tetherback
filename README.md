# tetherback

Tools to create TWRP and nandroid-style backups of an Android device via a USB connection,
without using the device's internal storage or SD card.

**WARNING:** This is a work in progress. I've only tested it on a
  [LG/Google Nexus 5](http://wikipedia.org/wiki/Nexus_5) with
  [TWRP recovery v3.0.0-0](https://twrp.me/site/update/2016/02/05/twrp-3.0.0-0-released.html),
  with `adb` v1.0.31 under Ubuntu. You have been warned ☺

## Requirements

* Python 3.3+ under Linux
  * `progressbar` package is needed (`pip install progressbar` should do it)
* You must have [TWRP recovery](https://twrp.me/) installed on your rooted Android device
* [`adb`](https://en.wikipedia.org/wiki/Android_software_development#ADB) (Android Debug Bridge) command-line tools

## Usage

Boot your device into TWRP recovery and connect it via USB. Ensure that it's visible to `adb`:

```bash
$ adb devices
List of devices attached
0123deadbeaf5f5f	recovery
```

* Make a TWRP-style backup over ADB. This saves a gzipped image of the
  `boot` partition as `boot.emmc.win`, and saves the *contents* of the
  `/system` and `/data` partitions as tarballs named `system.ext4.win`
  and `data.ext4.win`:

    ```bash
    $ ./twrp_backup.py
    Device reports TWRP kernel (3.4.0-bricked-hammerhead-twrp-g7b77eb4).
    Reading partition map for mmcblk0 (29 partitions)...
      partition map: 100% Time: 0:00:03
    Saving TWRP backup images in twrp-backup-2016-03-17--17-44-04/ ...
    Saving partition boot (mmcblk0p19), 22 MiB uncompressed...
      boot.emmc.win: 100% Time: 0:00:05   3.04 MB/s
    Saving tarball of mmcblk0p25 (mounted at /system), 1024 MiB uncompressed...
      system.ext4.win: 100% Time: 0:02:16   2.29 MB/s
    Saving tarball of mmcblk0p28 (mounted at /data), 13089 MiB uncompressed...
      data.ext4.win: 100% Time: 0:05:38   2.60 MB/s
    ```

* Make a "nandroid"-style backup over ADB. This saves gzipped images
  of the partitions labeled `boot`, `system`, and `userdata` (named
  `<label>.img.gz`):

    ```bash
    $ ./nandroid_backup.py
    Device reports TWRP kernel (3.4.0-bricked-hammerhead-twrp-g7b77eb4).
    Reading partition map for mmcblk0 (29 partitions)...
      partition map: 100% Time: 0:00:03
    Saving nandroid partition images in nandroid-backup-2016-03-17--18-15-03/ ...
    Saving partition boot (mmcblk0p19), 22 MiB uncompressed...
      mmcblk0p19: 100% Time: 0:00:05   3.07 MB/s
    Saving partition system (mmcblk0p25), 1024 MiB uncompressed...
      mmcblk0p25: 100% Time: 0:03:05   1.76 MB/s
    Saving partition userdata (mmcblk0p28), 13089 MiB uncompressed...
      mmcblk0p28: 100% Time: 0:40:04   1.80 MB/s
    ```

## Motivation

I've been frustrated by the fact that all the Android recovery backup
tools save their backups _on a filesystem on the device itself_.

* [TWRP recovery](https://twrp.me/)
  ([code](https://github.com/omnirom/android_bootable_recovery))
  creates a mixture of raw partition images and tarballs, and **stores
  the backups on the device itself.**
* Same with [CWM recovery](http://clockworkmod.com/rommanager) , which
  creates nandroid-style backup images (just raw partition images) and
  again **stores them on the device itself.**

This is problematic for several reasons:

1. Most modern Android smartphones don't have a microSD card slot.
2. There may not be enough space on the device's own filesystem to back up its own contents.
3. Getting the large backup files off of the device requires an extra, slow transfer step.

Clearly I'm not the only one with this problem:

* http://android.stackexchange.com/questions/64354/how-to-do-a-full-nandroid-backup-via-pc
* http://android.stackexchange.com/questions/47975/is-there-a-way-to-do-nandroid-backup-directly-to-pc-and-then-restore-it-directly

I found that [**@inhies**](https://github.com/inhies) had already
created a shell script to do a TWRP-style backup over USB
([Gist](https://gist.github.com/inhies/5069663)) and decided to try to
put together a more polished version of this.

## License

GPL v3 or newer
