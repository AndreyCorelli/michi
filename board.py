from typing import List, Optional, Generator
import re

from const import pat_gridcular_seq
from large_patterns import large_patterns_store
from spat_patterns_store import spatial_pattern_store


class Board:
    N = 13
    W = N + 2
    W2 = W * W
    MAX_GAME_LEN = N * N * 3

    empty = "\n".join([(N + 1) * ' '] + N * [' ' + N * '.'] + [(N + 2) * ' '])
    # Regex that matches various kind of points adjacent to '#' (flood-filled) points
    contact_res = dict()
    _encoding = "utf-8"

    def __init__(self, board_data: Optional[str] = None):
        self.board = board_data or self.empty

    def floodfill(self, c) -> "Board":
        """ replace continuous-color area starting at c with special color # """
        # This is called so much that a bytearray is worthwhile...
        byteboard = bytearray(self.board, encoding=self._encoding)
        p = byteboard[c]
        byteboard[c] = ord('#')
        fringe = [c]
        while fringe:
            c = fringe.pop()
            for d in self.neighbors(c):
                if byteboard[d] == p:
                    byteboard[d] = ord('#')
                    fringe.append(d)
        return Board(byteboard.decode(self._encoding))

    def swapcase(self) -> "Board":
        return Board(self.board.swapcase())

    def is_eyeish(self, c: int) -> Optional[str]:
        """ test if c is inside a single-color diamond and return the diamond
        color or None; this could be an eye, but also a false one """
        eyecolor = None
        for d in self.neighbors(c):
            if self.board[d].isspace():
                continue
            if self.board[d] == '.':
                return None
            if eyecolor is None:
                eyecolor = self.board[d]
                othercolor = eyecolor.swapcase()
            elif self.board[d] == othercolor:
                return None
        return eyecolor

    def is_eye(self, c: int) -> Optional[str]:
        """ test if c is an eye and return its color or None """
        eyecolor = self.is_eyeish(c)
        if eyecolor is None:
            return None

        # Eye-like shape, but it could be a falsified eye
        falsecolor = eyecolor.swapcase()
        false_count = 0
        at_edge = False
        for d in self.diag_neighbors(c):
            if self.board[d].isspace():
                at_edge = True
            elif self.board[d] == falsecolor:
                false_count += 1
        if at_edge:
            false_count += 1
        if false_count >= 2:
            return None

        return eyecolor

    def contact(self, p):
        """ test if point of color p is adjecent to color # anywhere
        on the board; use in conjunction with floodfill for reachability """
        m = self.contact_res[p].search(self.board)
        if not m:
            return None
        return m.start() if m.group(0)[0] == p else m.end() - 1

    def board_put(self, c: int, p: str) -> Optional["Board"]:
        if c is None:
            return
        try:
            board = self.board[:c] + p + self.board[c + 1:]
            return Board(board)
        except Exception as e:
            print(e)
            raise

    def empty_area(self, c: int, dist=3) -> bool:
        """ Check whether there are any stones in Manhattan distance up
        to dist """
        for d in Board.neighbors(c):
            if self.board[d] in 'Xx':
                return False
            elif self.board[d] == '.' and dist > 1 and not self.empty_area(d, dist - 1):
                return False
        return True

    def large_pattern_probability(self, c: int) -> float:
        """ return probability of large-scale pattern at coordinate c.
        Multiple progressively wider patterns may match a single coordinate,
        we consider the largest one. """
        probability = None
        matched_len = 0
        non_matched_len = 0
        for n in self.neighborhood_gridcular(c):
            sp_i = spatial_pattern_store.spat_patterndict.get(hash(n))
            prob = large_patterns_store.patterns.get(sp_i) if sp_i is not None else None
            if prob is not None:
                probability = prob
                matched_len = len(n)
            elif matched_len < non_matched_len < len(n):
                # stop when we did not match any pattern with a certain
                # diameter - it ain't going to get any better!
                break
            else:
                non_matched_len = len(n)
        return probability

    def neighborhood_gridcular(self, c: int) -> Generator[str, None, None]:
        """
        Yield progressively wider-diameter gridcular board neighborhood
        stone configuration strings, in all possible rotations
        Each rotations element is (xyindex, xymultiplier)
        """
        rotations = [((0, 1), (1, 1)), ((0, 1), (-1, 1)), ((0, 1), (1, -1)), ((0, 1), (-1, -1)),
                     ((1, 0), (1, 1)), ((1, 0), (-1, 1)), ((1, 0), (1, -1)), ((1, 0), (-1, -1))]
        neighborhood = ['' for i in range(len(rotations))]
        wboard = self.board.replace('\n', ' ')
        for dseq in pat_gridcular_seq:
            for ri in range(len(rotations)):
                r = rotations[ri]
                for o in dseq:
                    y, x = divmod(c - (self.W + 1), self.W)
                    y += o[r[0][0]] * r[1][0]
                    x += o[r[0][1]] * r[1][1]
                    if 0 <= y < self.N and self.N > x >= 0:
                        neighborhood[ri] += wboard[(y + 1) * self.W + x + 1]
                    else:
                        neighborhood[ri] += ' '
                yield neighborhood[ri]

    def neighborhood_33(self, c: int) -> str:
        """ return a string containing the 9 points forming 3x3 square around
        a certain move candidate """
        return (self.board[c - self.W - 1: c - self.W + 2] +
                self.board[c - 1: c + 2] + self.board[c + self.W - 1: c + self.W + 2]).replace('\n', ' ')

    @classmethod
    def neighbors(cls, c: int):
        """ generator of coordinates for all neighbors of c """
        return [c - 1, c + 1, c - cls.W, c + cls.W]

    @classmethod
    def diag_neighbors(cls, c: int) -> List[int]:
        """ generator of coordinates for all diagonal neighbors of c """
        return [c - cls.W - 1, c - cls.W + 1, c + cls.W - 1, c + cls.W + 1]

    @classmethod
    def parse_coord(cls, s: str) -> Optional[int]:
        if s == 'pass':
            return None
        return cls.W + 1 + (cls.N - int(s[1:])) * cls.W + (ord(s[0].upper()) - ord("A"))

    @classmethod
    def str_coord(cls, c) -> str:
        if c is None:
            return 'pass'
        row, col = divmod(c - (cls.W + 1), cls.W)
        return f'{chr(col + ord("A"))}{cls.N - row}'

    @classmethod
    def line_height(cls, c: int) -> int:
        """ Return the line number above nearest board edge """
        row, col = divmod(c - (cls.W + 1), cls.W)
        return min(row, col, cls.N - 1 - row, cls.N - 1 - col)


def _initialize_board_statics():
    for p in ['.', 'x', 'X']:
        rp = '\\.' if p == '.' else p
        contact_res_src = ['#' + rp,  # p at right
                           rp + '#',  # p at left
                           '#' + '.'*(Board.W-1) + rp,  # p below
                           rp + '.'*(Board.W-1) + '#']  # p above
        # ['#\\.', '\\.#', '#..............\\.', '\\...............#']
        Board.contact_res[p] = re.compile('|'.join(contact_res_src), flags=re.DOTALL)


_initialize_board_statics()
