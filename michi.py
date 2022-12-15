#!/usr/bin/env pypy
# -*- coding: utf-8 -*-
#
# (c) Petr Baudis <pasky@ucw.cz>  2015
# MIT licence (i.e. almost public domain)
#
# A minimalistic Go-playing engine attempting to strike a balance between
# brevity, educational value and strength.  It can beat GNUGo on 13x13 board
# on a modest 4-thread laptop.
#
# When benchmarking, note that at the beginning of the first move the program
# runs much slower because pypy is JIT compiling on the background!
#
# To start reading the code, begin either:
# * Bottom up, by looking at the goban implementation - starting with
#   the 'empty' definition below and Position.move() method.
# * In the middle, by looking at the Monte Carlo playout implementation,
#   starting with the mcplayout() function.
# * Top down, by looking at the MCTS implementation, starting with the
#   tree_search() function.  It can look a little confusing due to the
#   parallelization, but really is just a loop of tree_descend(),
#   mcplayout() and tree_update() round and round.
# It may be better to jump around a bit instead of just reading straight
# from start to end.

# Given a board of size NxN (N=9, 19, ...), we represent the position
# as an (N+1)*(N+2) string, with '.' (empty), 'X' (to-play player),
# 'x' (other player), and whitespace (off-board border to make rules
# implementation easier).  Coordinates are just indices in this string.
# You can simply print(board) when debugging.


from __future__ import print_function
import multiprocessing
import re
import sys
import time
from past.builtins import raw_input

from board import Board
from const import N_SIMS, RESIGN_THRES
from heuristics import mcplayout
from large_patterns import large_patterns_store
from position import Position, empty_position
from spat_patterns_store import spatial_pattern_store
from tree import tree_search
from tree_node import TreeNode


# various main programs


def mcbenchmark(n):
    # run n Monte-Carlo playouts from empty position, return avg. score
    sumscore = 0
    for i in range(0, n):
        sumscore += mcplayout(empty_position(), Board.W * Board.W * [0])[0]
    return float(sumscore) / n


def game_io(computer_black=False):
    """ A simple minimalistic text mode UI. """
    tree = TreeNode(pos=empty_position())
    tree.expand()
    owner_map = Board.W * Board.W * [0]
    while True:
        if not (tree.pos.n == 0 and computer_black):
            tree.pos.print_pos(sys.stdout, owner_map)

            sc = raw_input("Your move: ")
            try:
                c = Board.parse_coord(sc)
            except Exception as e:
                print('An incorrect move')
                continue
            if c is not None:
                # Not a pass
                if tree.pos.board.board[c] != '.':
                    print('Bad move (not empty point)')
                    continue

                # Find the next node in the game tree and proceed there
                nodes = [ch for ch in tree.children if ch.pos.last == c]
                # filter(lambda n: n.pos.last == c, tree.children)
                if not nodes:
                    print('Bad move (rule violation)')
                    continue
                tree = nodes[0]

            else:
                # Pass move
                if tree.children[0].pos.last is None:
                    tree = tree.children[0]
                else:
                    tree = TreeNode(pos=tree.pos.pass_move())

            tree.pos.print_pos()

        owner_map = Board.W * Board.W * [0]
        tree = tree_search(tree, N_SIMS, owner_map)
        if tree.pos.last is None and tree.pos.last2 is None:
            score = tree.pos.score()
            if tree.pos.n % 2:
                score = -score
            print('Game over, score: B%+.1f' % (score,))
            break
        if float(tree.w)/tree.v < RESIGN_THRES:
            print('I resign.')
            break
    print('Thank you for the game!')


def gtp_io():
    """ GTP interface for our program.  We can play only on the board size
    which is configured (N), and we ignore color information and assume
    alternating play! """
    known_commands = ['boardsize', 'clear_board', 'komi', 'play', 'genmove',
                      'final_score', 'quit', 'name', 'version', 'known_command',
                      'list_commands', 'protocol_version', 'tsdebug']

    tree = TreeNode(pos=empty_position())
    tree.expand()

    while True:
        try:
            line = raw_input().strip()
        except EOFError:
            break
        if line == '':
            continue
        command = [s.lower() for s in line.split()]
        if re.match('\d+', command[0]):
            cmdid = command[0]
            command = command[1:]
        else:
            cmdid = ''
        owner_map = Board.W2 * [0]
        ret = ''
        if command[0] == "boardsize":
            if int(command[1]) != Board.N:
                print("Warning: Trying to set incompatible boardsize %s (!= %d)"
                      % (command[1], Board.N), file=sys.stderr)
                ret = None
        elif command[0] == "clear_board":
            tree = TreeNode(pos=empty_position())
            tree.expand()
        elif command[0] == "komi":
            # XXX: can we do this nicer?!
            tree.pos = Position(board=tree.pos.board, captures=(tree.pos.captures[0], tree.pos.captures[1]),
                                n=tree.pos.n, ko=tree.pos.ko, last=tree.pos.last, last2=tree.pos.last2,
                                komi=float(command[1]))
        elif command[0] == "play":
            c = Board.parse_coord(command[2])
            if c is not None:
                # Find the next node in the game tree and proceed there
                if tree.children is not None and filter(lambda n: n.pos.last == c, tree.children):
                    tree = filter(lambda n: n.pos.last == c, tree.children)[0]
                else:
                    # Several play commands in row, eye-filling move, etc.
                    tree = TreeNode(pos=tree.pos.move(c))

            else:
                # Pass move
                if tree.children[0].pos.last is None:
                    tree = tree.children[0]
                else:
                    tree = TreeNode(pos=tree.pos.pass_move())
        elif command[0] == "genmove":
            tree = tree_search(tree, N_SIMS, owner_map)
            if tree.pos.last is None:
                ret = 'pass'
            elif float(tree.w)/tree.v < RESIGN_THRES:
                ret = 'resign'
            else:
                ret = Board.str_coord(tree.pos.last)
        elif command[0] == "final_score":
            score = tree.pos.score()
            if tree.pos.n % 2:
                score = -score
            if score == 0:
                ret = '0'
            elif score > 0:
                ret = 'B+%.1f' % (score,)
            elif score < 0:
                ret = 'W+%.1f' % (-score,)
        elif command[0] == "name":
            ret = 'michi'
        elif command[0] == "version":
            ret = 'simple go program demo'
        elif command[0] == "tsdebug":
            pos = tree_search(tree, N_SIMS, Board.W2 * [0], disp=True)
            if not pos:
                print("Position's unreachable")
            else:
                pos.print_pos()
        elif command[0] == "list_commands":
            ret = '\n'.join(known_commands)
        elif command[0] == "known_command":
            ret = 'true' if command[1] in known_commands else 'false'
        elif command[0] == "protocol_version":
            ret = '2'
        elif command[0] == "quit":
            print('=%s \n\n' % (cmdid,), end='')
            break
        else:
            print('Warning: Ignoring unknown command - %s' % (line,), file=sys.stderr)
            ret = None

        tree.pos.print_pos(sys.stderr, owner_map)
        if ret is not None:
            print('=%s %s\n\n' % (cmdid, ret,), end='')
        else:
            print('?%s ???\n\n' % (cmdid,), end='')
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        with open(spatial_pattern_store.spat_patterndict_file) as f:
            print('Loading pattern spatial dictionary...', file=sys.stderr)
            spatial_pattern_store.load_spat_patterndict(f)
        with open(large_patterns_store.large_patterns_file) as f:
            print('Loading large patterns...', file=sys.stderr)
            large_patterns_store.load_large_patterns(f)
        print('Done.', file=sys.stderr)
    except IOError as e:
        print(f'Warning: Cannot load pattern files: {e}; will be much weaker, '
              'consider lowering EXPAND_VISITS 5->2',
              file=sys.stderr)
    if len(sys.argv) < 2:
        # Default action
        game_io()
    elif sys.argv[1] == "white":
        game_io(computer_black=True)
    elif sys.argv[1] == "gtp":
        gtp_io()
    elif sys.argv[1] == "mcdebug":
        print(mcplayout(empty_position(), Board.W2*[0], disp=True)[0])
    elif sys.argv[1] == "mcbenchmark":
        print(mcbenchmark(20))
    elif sys.argv[1] == "tsbenchmark":
        t_start = time.time()
        pos = tree_search(TreeNode(pos=empty_position()), N_SIMS, Board.W2 * [0], disp=False).pos
        pos.print_pos()
        print('Tree search with %d playouts took %.3fs with %d threads; speed is %.3f playouts/thread/s' %
              (N_SIMS, time.time() - t_start, multiprocessing.cpu_count(),
               N_SIMS / ((time.time() - t_start) * multiprocessing.cpu_count())))
    elif sys.argv[1] == "tsdebug":
        pos = tree_search(TreeNode(pos=empty_position()), N_SIMS, Board.W2[0], disp=True).pos
        pos.print_pos()
    else:
        print('Unknown action', file=sys.stderr)
