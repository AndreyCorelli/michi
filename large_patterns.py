"""
large-scale pattern routines (those patterns living in patterns.{spat,prob} files)
are you curious how these patterns look in practice? get
https://github.com/pasky/pachi/blob/master/tools/pattern_spatial_show.pl
and try e.g. ./pattern_spatial_show.pl 71
"""

import re


class LargePatternsStore:
    large_patterns_file = 'patterns.prob'

    def __init__(self):
        self.patterns = {}  # spatial id -> probability

    def load_large_patterns(self, f):
        """
        dictionary of numeric pattern ids, translating them to probabilities
        that a move matching such move will be played when it is available
        The pattern file contains other features like capture, selfatari too;
        we ignore them for now
        """
        for line in f:
            # line: 0.004 14 3842 (capture:17 border:0 s:784)
            p = float(line.split()[0])
            m = re.search('s:(\d+)', line)
            if m is not None:
                s = int(m.groups()[0])
                self.patterns[s] = p


large_patterns_store = LargePatternsStore()
