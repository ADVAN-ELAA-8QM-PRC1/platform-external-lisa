# SPDX-License-Identifier: Apache-2.0
#
# Copyright (C) 2015, ARM Limited and contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import os
import re

from gfxinfo import GfxInfo
from surfaceflinger import SurfaceFlinger

from . import System

class Workload(object):
    """
    Base class for Android related workloads
    """

    _packages = None
    _availables = {}

    def __init__(self, test_env):
        """
        Initialized workloads available on the specified test environment

        test_env: target test environment
        """
        self._te = test_env
        self._target = test_env.target
        self._log = logging.getLogger('Workload')

        # Set of data reported in output of each run
        self.trace_file = None
        self.nrg_report = None

    def _adb(self, cmd):
        return 'adb -s {} {}'.format(self._target.adb_name, cmd)

    @classmethod
    def _check_availables(cls, test_env):
        """
        List the supported android workloads which are available on the target
        """

        _log = logging.getLogger('Workload')

        # Getting the list of installed packages
        cls._packages = test_env.target.list_packages()
        _log.debug('Packages:\n%s', cls._packages)

        _log.debug('Building list of available workloads...')
        for sc in Workload.__subclasses__():
            _log.debug('Checking workload [%s]...', sc.__name__)
            if sc.package in cls._packages:
                cls._availables[sc.__name__.lower()] = sc

        _log.info('Supported workloads available on target:')
        _log.info('  %s', ', '.join(cls._availables.keys()))

    @classmethod
    def getInstance(cls, test_env, name):
        """
        Get a reference to the specified Android workload
        """

        # Initialize list of available workloads
        if cls._packages is None:
            cls._check_availables(test_env)

        if name.lower() not in cls._availables:
            msg = 'Workload [{}] not available on target'.format(name)
            raise ValueError(msg)

        return cls._availables[name.lower()](test_env)

    def run(self, out_dir, collect='',
            **kwargs):
        raise RuntimeError('Not implemented')

    def tracingStart(self):
        # Reset the dumpsys data for the package
        if 'gfxinfo' in self.collect:
            System.gfxinfo_reset(self._target, self.package)
        if 'surfaceflinger' in self.collect:
            System.surfaceflinger_reset(self._target, self.package)
        # Make sure ftrace and systrace are not both specified to be collected
        if 'ftrace' in self.collect and 'systrace' in self.collect:
            msg = 'ftrace and systrace cannot be used at the same time'
            raise ValueError(msg)
        # Start FTrace
        if 'ftrace' in self.collect:
            self.trace_file = os.path.join(self.out_dir, 'trace.dat')
            self._log.info('FTrace START')
            self._te.ftrace.start()
        # Start Systrace (mutually exclusive with ftrace)
        elif 'systrace' in self.collect:
            self.trace_file = os.path.join(self.out_dir, 'trace.html')
            # Get the systrace time
            match = re.search(r'systrace_([0-9]+)', self.collect)
            self._trace_time = match.group(1) if match else None
            self._log.info('Systrace START')
            self._systrace_output = System.systrace_start(
                self._te, self.trace_file, self._trace_time)
        # Initialize energy meter results
        if 'energy' in self.collect and self._te.emeter:
            self._te.emeter.reset()
            self._log.info('Energy meter STARTED')

    def tracingStop(self):
        # Collect energy meter results
        if 'energy' in self.collect and self._te.emeter:
            self.nrg_report = self._te.emeter.report(self.out_dir)
            self._log.info('Energy meter STOPPED')
        # Stop FTrace
        if 'ftrace' in self.collect:
            self._te.ftrace.stop()
            self._log.info('FTrace STOP')
            self._te.ftrace.get_trace(self.trace_file)
        # Stop Systrace (mutually exclusive with ftrace)
        elif 'systrace' in self.collect:
            if not self._systrace_output:
                self._log.warning('Systrace is not running!')
            else:
                self._log.info('Waiting systrace report [%s]...',
                                 self.trace_file)
                if self._trace_time is None:
                    # Systrace expects <enter>
                    self._systrace_output.sendline('')
                self._systrace_output.wait()
        # Parse the data gathered from dumpsys gfxinfo
        if 'gfxinfo' in self.collect:
            dump_file = os.path.join(self.out_dir, 'dumpsys_gfxinfo.txt')
            System.gfxinfo_get(self._target, self.package, dump_file)
            self.gfxinfo = GfxInfo(dump_file)
        # Parse the data gathered from dumpsys SurfaceFlinger
        if 'surfaceflinger' in self.collect:
            dump_file = os.path.join(self.out_dir, 'dumpsys_surfaceflinger.txt')
            System.surfaceflinger_get(self._target, self.package, dump_file)
            self.surfaceflinger = SurfaceFlinger(dump_file)
        # Dump a platform description
        self._te.platform_dump(self.out_dir)

# vim :set tabstop=4 shiftwidth=4 expandtab
