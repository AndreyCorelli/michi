import random
import sys
from typing import Optional, Tuple, List, Any, Dict, Generator, Iterable

from board import Board
from board_patterns import pat3set
from const import PROB_HEURISTIC, PROB_RSAREJECT, PROB_SSAREJECT
from position import Position


def fix_atari(pos: Position,
              c: int,
              singlept_ok=False,
              twolib_test=True,
              twolib_edgeonly=False) -> Optional[Tuple[bool, List[Any]]]:
    """ An atari/capture analysis routine that checks the group at c,
    determining whether (i) it is in atari (ii) if it can escape it,
    either by playing on its liberty or counter-capturing another group.

    N.B. this is maybe the most complicated part of the whole program (sadly);
    feel free to just TREAT IT AS A BLACK-BOX, it's not really that
    interesting!

    The return value is a tuple of (boolean, [coord..]), indicating whether
    the group is in atari and how to escape/capture (or [] if impossible).
    (Note that (False, [...]) is possible in case the group can be captured
    in a ladder - it is not in atari but some capture attack/defense moves
    are available.)

    singlept_ok means that we will not try to save one-point groups;
    twolib_test means that we will check for 2-liberty groups which are
    threatened by a ladder
    twolib_edgeonly means that we will check the 2-liberty groups only
    at the board edge, allowing check of the most common short ladders
    even in the playouts """

    def read_ladder_attack(pos: Position, c: int, l1: int, l2: int) -> Optional[int]:
        """ check if a capturable ladder is being pulled out at c and return
        a move that continues it in that case; expects its two liberties as
        l1, l2  (in fact, this is a general 2-lib capture exhaustive solver) """
        for l in [l1, l2]:
            pos_l = pos.move(l)
            if pos_l is None:
                continue
            # fix_atari() will recursively call read_ladder_attack() back;
            # however, ignore 2lib groups as we don't have time to chase them
            is_atari, atari_escape = fix_atari(pos_l, c, twolib_test=False)
            if is_atari and not atari_escape:
                return l
        return None

    fboard = pos.board.floodfill(c)
    group_size = fboard.board.count('#')
    if singlept_ok and group_size == 1:
        return False, []
    # Find a liberty
    l = fboard.contact('.')
    # Ok, any other liberty?
    fboard = fboard.board_put(l, 'L')
    l2 = fboard.contact('.')
    if l2 is not None:
        # At least two liberty group...
        if twolib_test and group_size > 1 \
                and (not twolib_edgeonly or Board.line_height(l) == 0 and Board.line_height(l2) == 0):
            l_board = fboard.board_put(l2, 'L')
            if l_board.contact('.') is None:
                # Exactly two liberty group with more than one stone.  Check
                # that it cannot be caught in a working ladder; if it can,
                # that's as good as in atari, a capture threat.
                # (Almost - N/A for countercaptures.)
                ladder_attack = read_ladder_attack(pos, c, l, l2)
                if ladder_attack:
                    return False, [ladder_attack]
        return False, []

    # In atari! If it's the opponent's group, that's enough...
    if pos.board.board[c] == 'x':
        return True, [l]

    solutions = []

    # Before thinking about defense, what about counter-capturing
    # a neighboring group?
    ccboard = Board(fboard.board)
    while True:
        othergroup = ccboard.contact('x')
        if othergroup is None:
            break
        a, ccls = fix_atari(pos, othergroup, twolib_test=False)
        if a and ccls:
            solutions += ccls
        # XXX: floodfill is better for big groups
        ccboard = ccboard.board_put(othergroup, '%')

    # We are escaping.  Will playing our last liberty gain
    # at least two liberties?  Re-floodfill to account for connecting
    escpos = pos.move(l)
    if escpos is None:
        return True, solutions  # oops, suicidal move

    fboard = escpos.board.floodfill(l)
    l_new = fboard.contact('.')
    fboard = fboard.board_put(l_new, 'L')
    l_new_2 = fboard.contact('.')
    if l_new_2 is not None:
        # Good, there is still some liberty remaining - but if it's
        # just the two, check that we are not caught in a ladder...
        # (Except that we don't care if we already have some alternative
        # escape routes!)
        if solutions or not (fboard.board_put(l_new_2, 'L').contact('.') is None
                             and read_ladder_attack(escpos, l, l_new, l_new_2) is not None):
            solutions.append(l)

    return True, solutions


def cfg_distances(board: Board, c: int) -> List[int]:
    """ return a board map listing common fate graph distances from
    a given point - this corresponds to the concept of locality while
    contracting groups to single points """
    cfg_map = board.W * board.W * [-1]
    cfg_map[c] = 0

    # flood-fill like mechanics
    fringe = [c]
    while fringe:
        c = fringe.pop()
        for d in Board.neighbors(c):
            if board.board[d].isspace() or 0 <= cfg_map[d] <= cfg_map[c]:
                continue
            cfg_before = cfg_map[d]
            if board.board[d] != '.' and board.board[d] == board.board[c]:
                cfg_map[d] = cfg_map[c]
            else:
                cfg_map[d] = cfg_map[c] + 1
            if cfg_before < 0 or cfg_before > cfg_map[d]:
                fringe.append(d)
    return cfg_map


###########################
# montecarlo playout policy

def gen_playout_moves(
        pos: Position,
        heuristic_set: Iterable[int],
        probs: Optional[Dict[str, float]] = None,
        expensive_ok=False) -> Generator[Tuple[int, str], None, None]:
    """ Yield candidate next moves in the order of preference; this is one
    of the main places where heuristics dwell, try adding more!

    heuristic_set is the set of coordinates considered for applying heuristics;
    this is the immediate neighborhood of last two moves in the playout, but
    the whole board while prioring the tree. """

    # Check whether any local group is in atari and fill that liberty
    # print('local moves', [str_coord(c) for c in heuristic_set], file=sys.stderr)
    if probs is None:
        probs = {'capture': 1, 'pat3': 1}

    if random.random() <= probs['capture']:
        already_suggested = set()
        for c in heuristic_set:
            if pos.board.board[c] in 'Xx':
                in_atari, ds = fix_atari(pos, c, twolib_edgeonly=not expensive_ok)
                random.shuffle(ds)
                for d in ds:
                    if d not in already_suggested:
                        yield d, 'capture ' + str(c)
                        already_suggested.add(d)

    # Try to apply a 3x3 pattern on the local neighborhood
    if random.random() <= probs['pat3']:
        already_suggested = set()
        for c in heuristic_set:
            if pos.board.board[c] == '.' and c not in already_suggested and pos.board.neighborhood_33(c) in pat3set:
                yield c, 'pat3'
                already_suggested.add(c)

    # Try *all* available moves, but starting from a random point
    # (in other words, suggest a random move)
    x, y = random.randint(1, Board.N), random.randint(1, Board.N)
    for c in pos.moves(y * Board.W + x):
        yield c, 'random'


def mcplayout(pos: Position, amaf_map, disp=False):
    """
    Start a Monte Carlo playout from a given position,
    return score for to-play player at the starting position;
    amaf_map is board-sized scratchpad recording who played at a given
    position first """
    if disp:
        print('** SIMULATION **', file=sys.stderr)

    start_n = pos.n
    passes = 0
    while passes < 2 and pos.n < Board.MAX_GAME_LEN:
        if disp:
            pos.print_pos()

        pos2 = None
        # We simply try the moves our heuristics generate, in a particular
        # order, but not with 100% probability; this is on the border between
        # "rule-based playouts" and "probability distribution playouts".
        for c, kind in gen_playout_moves(pos, pos.last_moves_neighbors(), PROB_HEURISTIC):
            if disp and kind != 'random':
                print('move suggestion', Board.str_coord(c), kind, file=sys.stderr)
            pos2 = pos.move(c)
            if pos2 is None:
                continue
            # check if the suggested move did not turn out to be a self-atari
            if random.random() <= (PROB_RSAREJECT if kind == 'random' else PROB_SSAREJECT):
                in_atari, ds = fix_atari(pos2, c, singlept_ok=True, twolib_edgeonly=True)
                if ds:
                    if disp:
                        print('rejecting self-atari move', Board.str_coord(c), file=sys.stderr)
                    pos2 = None
                    continue
            if amaf_map[c] == 0:  # Mark the coordinate with 1 for black
                amaf_map[c] = 1 if pos.n % 2 == 0 else -1
            break
        if pos2 is None:  # no valid moves, pass
            pos = pos.pass_move()
            passes += 1
            continue
        passes = 0
        pos = pos2

    owner_map = Board.W * Board.W * [0]
    score = pos.score(owner_map)
    if disp:
        print('** SCORE B%+.1f **' % (score if pos.n % 2 == 0 else -score), file=sys.stderr)
    if start_n % 2 != pos.n % 2:
        score = -score
    return score, amaf_map, owner_map
