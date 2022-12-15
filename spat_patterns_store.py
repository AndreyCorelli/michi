class SpatialPatternsStore:
    spat_patterndict_file = 'patterns.spat'

    def __init__(self):
        self.spat_patterndict = dict()  # hash(neighborhood_gridcular()) -> spatial id

    def load_spat_patterndict(self, f):
        """ load dictionary of positions, translating them to numeric ids """
        for line in f:
            # line: 71 6 ..X.X..OO.O..........#X...... 33408f5e 188e9d3e 2166befe aa8ac9e 127e583e 1282462e 5e3d7fe 51fc9ee
            if line.startswith('#'):
                continue
            neighborhood = line.split()[2].replace('#', ' ').replace('O', 'x')
            self.spat_patterndict[hash(neighborhood)] = int(line.split()[0])


spatial_pattern_store = SpatialPatternsStore()
