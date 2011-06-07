#!/usr/bin/env python2

import sys
import threading
import subprocess
import random

# Just copy this from a Python 2.7 installation if you use an older version
import argparse

PLOWDOWN = 'plowdown'


class NetworkHelper():
    '''Helper functions that return network interfaces'''

    @classmethod
    def get_interfaces(cls):
        '''Return list of interfacs'''

        # This code has been mostly stolen from
        # http://code.activestate.com/recipes/439093-get-names-of-all-up-network-interfaces-linux-only/

        import platform
        import fcntl
        import socket
        import array
        import struct

        SIOCGIFCONF = 0x8912
        MAX_POSSIBLE = 128

        bytes = MAX_POSSIBLE * 32
        arch = platform.architecture()[0]

        if arch == '32bit':
            (o1, o2) = (32, 32)
        elif arch == '64bit':
            (o1, o2) = (16, 40)
        else:
            raise OSError("Unknown architecture: %s" % arch)

        names = array.array('B', '\0' * bytes)

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        outbytes = struct.unpack('iL', fcntl.ioctl(
                s.fileno(),
                SIOCGIFCONF,
                struct.pack('iL', bytes, names.buffer_info()[0])
        ))[0]

        namestr = names.tostring()
        return [namestr[i:i + o1].split('\0', 1)[0] for i in range(0, outbytes, o2)]

    @classmethod
    def get_filtered_interfaces(cls, regexp):
        '''Filter interfaces based on regexp'''

        import re

        return [interface for interface in cls.get_interfaces() if regexp is None or re.match(regexp, interface)]


class URLProducer:
    def __init__(self, url_list):
        self.lock = threading.Lock()
        self.url_list = url_list

    def get_url(self):
        with self.lock:
            if len(self.url_list) > 0:
                return self.url_list.pop(0)
            else:
                return None


class PlowdownRunner(threading.Thread):
    def __init__(self, producer, interface):
        threading.Thread.__init__(self)
        self.producer = producer
        self.interface = interface

    def run(self):
        while True:
            url = self.producer.get_url()

            if url is None:
                break

            sys.stdout.write('Interface %s downloading %s\n' % (self.interface, url))

            try:
                subprocess_check_output([PLOWDOWN, '-i', self.interface, url], stderr=subprocess.STDOUT)
                sys.stdout.write('COMPLETE: Interface %s downloading %s\n' % (self.interface, url))
            except subprocess.CalledProcessError as e:
                sys.stdout.write('FAILURE: Interface %s downloading %s (%s)\n' % (self.interface, url, e.output.split('\n')[-2]))
            finally:
                sys.stdout.flush()


def subprocess_check_output(*popenargs, **kwargs):
    '''subprocess.check_output from Python 2.7 for compatibility with older
    Python versions'''

    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise subprocess.CalledProcessError(retcode, cmd, output=output)
    return output


def downloader(regexp, urls):
    '''Download from specified URLs'''

    interfaces = NetworkHelper.get_filtered_interfaces(regexp)

    try:
        interfaces.remove('lo')
    except:
        pass

    random.shuffle(interfaces)
    runners = []

    for (module, urlset) in identify_modules(urls).iteritems():
        producer = URLProducer(urlset)

        for interface in interfaces:
            runner = PlowdownRunner(producer, interface)
            runners.append(runner)
            runner.start()

    for runner in runners:
        runner.join()


def identify_module(url):
    '''Identify module responsible for a given URL'''

    try:
        return subprocess_check_output([PLOWDOWN, '--get-module', url], stderr=open('/dev/null', 'w')).rstrip()
    except subprocess.CalledProcessError:
        return None


def identify_modules(urls):
    '''Identify modules responsible for multiple URLs'''

    result = {}

    for url in urls:
        module = identify_module(url)
        result[module] = result.get(module, []) + [url]

    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Multi-interface Plowdown starter')
    parser.add_argument('regexp', help='Regexp matching allowed network interfaces')
    parser.add_argument('urls', nargs='+', help='List of URLs to download')
    args = parser.parse_args()

    downloader(args.regexp, args.urls)
