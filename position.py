from __future__ import print_function
import random
import sys
from itertools import count
from typing import Optional, Tuple, Generator, List, Any

from board import Board
from const import colstr


class Position:
    def __init__(
            self,
            board: Optional[Board],
            captures: Tuple[int, int],
            n: int,
            ko: Optional[int],
            last: Optional[int],
            last2: Optional[int],
            komi: float
    ):
        self.board = board or Board()
        self.captures = captures
        # n is how many moves were played so far
        self.n = n
        self.ko = ko
        self.last = last
        self.last2 = last2
        self.komi = komi

    def move(self, c: int) -> Optional["Position"]:
        """ play as player X at the given coord c, return the new position """
        # Test for ko
        if c == self.komi:
            return None
        # Are we trying to play in enemy's eye?
        in_enemy_eye = self.board.is_eyeish(c) == 'x'
        board = self.board.board_put(c, 'X')

        # Test for captures, and track ko
        capt_X = self.captures[0]
        singlecaps = []
        for d in Board.neighbors(c):
            if board.board[d] != 'x':
                continue
            # XXX: The following is an extremely naive and SLOW approach
            # at things - to do it properly, we should maintain some per-group
            # data structures tracking liberties.
            fboard = board.floodfill(d)  # get a board with the adjecent group replaced by '#'
            if fboard.contact('.') is not None:
                continue  # some liberties left
            # no liberties left for this group, remove the stones!
            capcount = fboard.board.count('#')
            if capcount == 1:
                singlecaps.append(d)
            capt_X += capcount
            board.board = fboard.board.replace('#', '.')  # capture the group
        # Set ko
        ko = singlecaps[0] if in_enemy_eye and len(singlecaps) == 1 else None
        # Test for suicide
        sfboard = board.floodfill(c)
        if sfboard.contact('.') is None:
            return None

        # Update the position and return
        return Position(board=board.swapcase(), captures=(self.captures[1], capt_X),
                        n=self.n + 1, ko=ko, last=c, last2=self.last, komi=self.komi)

    def pass_move(self):
        """ pass - i.e. return simply a flipped position """
        return Position(board=self.board.swapcase(), captures=(self.captures[1], self.captures[0]),
                        n=self.n + 1, ko=None, last=None, last2=self.last, komi=self.komi)

    def moves(self, i0: int) -> Generator[int, None, None]:
        """ Generate a list of moves (includes false positives - suicide moves;
        does not include true-eye-filling moves), starting from a given board
        index (that can be used for randomization) """
        i = i0-1
        passes = 0
        while True:
            i = self.board.board.find('.', i+1)
            if passes > 0 and (i == -1 or i >= i0):
                break  # we have looked through the whole board
            elif i == -1:
                i = 0
                passes += 1
                continue  # go back and start from the beginning
            # Test for to-play player's one-point eye
            if self.board.is_eye(i) == 'X':
                continue
            yield i

    def last_moves_neighbors(self) -> List[Any]:
        """
        generate a randomly shuffled list of points including and
        surrounding the last two moves (but with the last move having
        priority)
        """
        coord_list = []
        for c in self.last, self.last2:
            if c is None:
                continue
            diag_list = [c] + list(Board.neighbors(c) + Board.diag_neighbors(c))
            random.shuffle(diag_list)
            coord_list += [d for d in diag_list if d not in coord_list]
        return coord_list

    def score(self, owner_map: Optional[List[int]] = None):
        """ compute score for to-play player; this assumes a final position
        with all dead stones captured; if owner_map is passed, it is assumed
        to be an array of statistics with average owner at the end of the game
        (+1 black, -1 white) """
        board = self.board
        i = 0
        while True:
            i = self.board.board.find('.', i+1)
            if i == -1:
                break
            fboard = self.board.floodfill(i)
            # fboard is board with some continuous area of empty space replaced by #
            touches_X = fboard.contact('X') is not None
            touches_x = fboard.contact('x') is not None
            if touches_X and not touches_x:
                board = fboard.board.replace('#', 'X')
            elif touches_x and not touches_X:
                board = fboard.board.replace('#', 'x')
            else:
                board = fboard.board.replace('#', ':')  # seki, rare
            # now that area is replaced either by X, x or :
        komi = self.komi if self.n % 2 == 1 else -self.komi
        if owner_map is not None:
            for c in range(self.board.W * self.board.W):
                n = 1 if board[c] == 'X' else -1 if board[c] == 'x' else 0
                owner_map[c] += n * (1 if self.n % 2 == 0 else -1)
        return board.count('X') - board.count('x') + komi

    def print_pos(self, f=sys.stderr, owner_map=None) -> None:
        """ print visualization of the given board position, optionally also
        including an owner map statistic (probability of that area of board
        eventually becoming black/white) """
        if self.n % 2 == 0:  # to-play is black
            board = self.board.board.replace('x', 'O')
            Xcap, Ocap = self.captures
        else:  # to-play is white
            board = self.board.board.replace('X', 'O').replace('x', 'X')
            Ocap, Xcap = self.captures
        print('Move: %-3d   Black: %d caps   White: %d caps  Komi: %.1f' % (self.n, Xcap, Ocap, self.komi), file=f)
        pretty_board = ' '.join(board.rstrip()) + ' '
        if self.last is not None:
            pretty_board = pretty_board[:self.last * 2 - 1] + '(' + board[self.last] + ')' + \
                           pretty_board[self.last * 2 + 2:]
        rowcounter = count()
        pretty_board = [' %-02d%s' % (Board.N - i, row[2:]) for row, i
                        in zip(pretty_board.split("\n")[1:], rowcounter)]
        if owner_map is not None:
            pretty_ownermap = ''
            for c in range(Board.W2):
                if board[c].isspace():
                    pretty_ownermap += board[c]
                elif owner_map[c] > 0.6:
                    pretty_ownermap += 'X'
                elif owner_map[c] > 0.3:
                    pretty_ownermap += 'x'
                elif owner_map[c] < -0.6:
                    pretty_ownermap += 'O'
                elif owner_map[c] < -0.3:
                    pretty_ownermap += 'o'
                else:
                    pretty_ownermap += '.'
            pretty_ownermap = ' '.join(pretty_ownermap.rstrip())
            pretty_board = ['%s   %s' % (brow, orow[2:]) for brow, orow in
                            zip(pretty_board, pretty_ownermap.split("\n")[1:])]
        print("\n".join(pretty_board), file=f)
        print('    ' + ' '.join(colstr[:Board.N]), file=f)
        print('', file=f)


def empty_position() -> Position:
    # Return an initial board position
    return Position(board=Board(), captures=(0, 0), n=0, ko=None, last=None, last2=None, komi=7.5)
