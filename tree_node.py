import math

from board import Board
from const import RAVE_EQUIV
from heuristics import fix_atari, cfg_distances, gen_playout_moves
from position import Position

PRIOR_EVEN = 10  # should be even number; 0.5 prior
PRIOR_SELFATARI = 10  # negative prior
PRIOR_CAPTURE_ONE = 15
PRIOR_CAPTURE_MANY = 30
PRIOR_PAT3 = 10
PRIOR_LARGEPATTERN = 100  # most moves have relatively small probability
PRIOR_CFG = [24, 22, 8]  # priors for moves in cfg dist. 1, 2, 3
PRIOR_EMPTYAREA = 10

N = Board.N
W = Board.W
########################
# montecarlo tree search


class TreeNode:
    """ Monte-Carlo tree node;
    v is #visits, w is #wins for to-play (expected reward is w/v)
    pv, pw are prior values (node value = w/v + pw/pv)
    av, aw are amaf values ("all moves as first", used for the RAVE tree policy)
    children is None for leaf nodes """
    def __init__(self, pos: Position):
        self.pos = pos
        self.v = 0
        self.w = 0
        self.pv = PRIOR_EVEN
        self.pw = PRIOR_EVEN/2
        self.av = 0
        self.aw = 0
        self.children = None

    def expand(self):
        """ add and initialize children to a leaf node """
        cfg_map = cfg_distances(self.pos.board, self.pos.last) if self.pos.last is not None else None
        self.children = []
        childset = dict()
        # Use playout generator to generate children and initialize them
        # with some priors to bias search towards more sensible moves.
        # Note that there can be many ways to incorporate the priors in
        # next node selection (progressive bias, progressive widening, ...).
        for c, kind in gen_playout_moves(self.pos, range(N, (N+1)*W), expensive_ok=True):
            pos2 = self.pos.move(c)
            if pos2 is None:
                continue
            # gen_playout_moves() will generate duplicate suggestions
            # if a move is yielded by multiple heuristics
            try:
                node = childset[pos2.last]
            except KeyError:
                node = TreeNode(pos2)
                self.children.append(node)
                childset[pos2.last] = node

            if kind.startswith('capture'):
                # Check how big group we are capturing; coord of the group is
                # second word in the ``kind`` string
                if self.pos.board.floodfill(int(kind.split()[1])).board.count('#') > 1:
                    node.pv += PRIOR_CAPTURE_MANY
                    node.pw += PRIOR_CAPTURE_MANY
                else:
                    node.pv += PRIOR_CAPTURE_ONE
                    node.pw += PRIOR_CAPTURE_ONE
            elif kind == 'pat3':
                node.pv += PRIOR_PAT3
                node.pw += PRIOR_PAT3

        # Second pass setting priors, considering each move just once now
        for node in self.children:
            c = node.pos.last

            if cfg_map is not None and cfg_map[c]-1 < len(PRIOR_CFG):
                node.pv += PRIOR_CFG[cfg_map[c]-1]
                node.pw += PRIOR_CFG[cfg_map[c]-1]

            height = Board.line_height(c)  # 0-indexed
            if height <= 2 and self.pos.board.empty_area(c):
                # No stones around; negative prior for 1st + 2nd line, positive
                # for 3rd line; sanitizes opening and invasions
                if height <= 1:
                    node.pv += PRIOR_EMPTYAREA
                    node.pw += 0
                if height == 2:
                    node.pv += PRIOR_EMPTYAREA
                    node.pw += PRIOR_EMPTYAREA

            in_atari, ds = fix_atari(node.pos, c, singlept_ok=True)
            if ds:
                node.pv += PRIOR_SELFATARI
                node.pw += 0  # negative prior

            patternprob = self.pos.board.large_pattern_probability(c)
            if patternprob is not None and patternprob > 0.001:
                pattern_prior = math.sqrt(patternprob)  # tone up
                node.pv += pattern_prior * PRIOR_LARGEPATTERN
                node.pw += pattern_prior * PRIOR_LARGEPATTERN

        if not self.children:
            # No possible moves, add a pass move
            self.children.append(TreeNode(self.pos.pass_move()))

    def rave_urgency(self):
        v = self.v + self.pv
        expectation = float(self.w+self.pw) / v
        if self.av == 0:
            return expectation
        rave_expectation = float(self.aw) / self.av
        beta = self.av / (self.av + v + float(v) * self.av / RAVE_EQUIV)
        return beta * rave_expectation + (1-beta) * expectation

    def winrate(self):
        return float(self.w) / self.v if self.v > 0 else float('nan')

    def best_move(self):
        """ best move is the most simulated one """
        return max(self.children, key=lambda node: node.v) if self.children is not None else None