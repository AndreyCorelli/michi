import multiprocessing
import random
import sys
from typing import List

from board import Board
from const import EXPAND_VISITS, REPORT_PERIOD, FASTPLAY5_THRES, FASTPLAY20_THRES
from heuristics import mcplayout
from tree_node import TreeNode
from ui import dump_subtree, print_tree_summary

PRIOR_EVEN = 10  # should be even number; 0.5 prior
PRIOR_SELFATARI = 10  # negative prior
PRIOR_CAPTURE_ONE = 15
PRIOR_CAPTURE_MANY = 30
PRIOR_PAT3 = 10
PRIOR_LARGEPATTERN = 100  # most moves have relatively small probability
PRIOR_CFG = [24, 22, 8]  # priors for moves in cfg dist. 1, 2, 3
PRIOR_EMPTYAREA = 10


worker_pool = None


def tree_descend(tree: TreeNode, amaf_map, disp=False):
    """ Descend through the tree to a leaf """
    tree.v += 1
    nodes = [tree]
    passes = 0
    while nodes[-1].children is not None and passes < 2:
        if disp:
            nodes[-1].pos.print_pos()

        # Pick the most urgent child
        children = list(nodes[-1].children)
        if disp:
            for c in children:
                dump_subtree(c, recurse=False)
        random.shuffle(children)  # randomize the max in case of equal urgency
        node = max(children, key=lambda node: node.rave_urgency())
        nodes.append(node)

        if disp:
            print('chosen %s' % (Board.str_coord(node.pos.last),), file=sys.stderr)
        if node.pos.last is None:
            passes += 1
        else:
            passes = 0
            if amaf_map[node.pos.last] == 0:  # Mark the coordinate with 1 for black
                amaf_map[node.pos.last] = 1 if nodes[-2].pos.n % 2 == 0 else -1

        # updating visits on the way *down* represents "virtual loss", relevant for parallelization
        node.v += 1
        if node.children is None and node.v >= EXPAND_VISITS:
            node.expand()

    return nodes


def tree_update(nodes: List[TreeNode], amaf_map, score, disp=False) -> None:
    """ Store simulation result in the tree (@nodes is the tree path) """
    for node in reversed(nodes):
        if disp:
            print('updating', Board.str_coord(node.pos.last), score < 0, file=sys.stderr)
        node.w += score < 0  # score is for to-play, node statistics for just-played
        # Update the node children AMAF stats with moves we made
        # with their color
        amaf_map_value = 1 if node.pos.n % 2 == 0 else -1
        if node.children is not None:
            for child in node.children:
                if child.pos.last is None:
                    continue
                if amaf_map[child.pos.last] == amaf_map_value:
                    if disp:  print('  AMAF updating', Board.str_coord(child.pos.last), score > 0, file=sys.stderr)
                    child.aw += score > 0  # reversed perspective
                    child.av += 1
        score = -score


def tree_search(tree: TreeNode, n, owner_map, disp=False):
    """ Perform MCTS search from a given position for a given #iterations """
    # Initialize root node
    if tree.children is None:
        tree.expand()

    # We could simply run tree_descend(), mcplayout(), tree_update()
    # sequentially in a loop.  This is essentially what the code below
    # does, if it seems confusing!

    # However, we also have an easy (though not optimal) way to parallelize
    # by distributing the mcplayout() calls to other processes using the
    # multiprocessing Python module.  mcplayout() consumes maybe more than
    # 90% CPU, especially on larger boards.  (Except that with large patterns,
    # expand() in the tree descent phase may be quite expensive - we can tune
    # that tradeoff by adjusting the EXPAND_VISITS constant.)

    n_workers = multiprocessing.cpu_count() if not disp else 1  # set to 1 when debugging
    global worker_pool
    if worker_pool is None:
        worker_pool = multiprocessing.Pool(processes=n_workers)
    outgoing = []  # positions waiting for a playout
    incoming = []  # positions that finished evaluation
    ongoing = []  # currently ongoing playout jobs
    i = 0
    while i < n:
        if not outgoing and not (disp and ongoing):
            # Descend the tree so that we have something ready when a worker
            # stops being busy
            amaf_map = Board.W * Board.W * [0]
            nodes = tree_descend(tree, amaf_map, disp=disp)
            outgoing.append((nodes, amaf_map))

        if len(ongoing) >= n_workers:
            # Too many playouts running? Wait a bit...
            ongoing[0][0].wait(0.01 / n_workers)
        else:
            i += 1
            if i > 0 and i % REPORT_PERIOD == 0:
                print_tree_summary(tree, i, f=sys.stderr)

            # Issue an mcplayout job to the worker pool
            nodes, amaf_map = outgoing.pop()
            ongoing.append((worker_pool.apply_async(mcplayout, (nodes[-1].pos, amaf_map, disp)), nodes))

        # Anything to store in the tree?  (We do this step out-of-order
        # picking up data from the previous round so that we don't stall
        # ready workers while we update the tree.)
        while incoming:
            score, amaf_map, owner_map_one, nodes = incoming.pop()
            tree_update(nodes, amaf_map, score, disp=disp)
            for c in range(Board.W * Board.W):
                owner_map[c] += owner_map_one[c]

        # Any playouts are finished yet?
        for job, nodes in ongoing:
            if not job.ready():
                continue
            # Yes! Queue them up for storing in the tree.
            score, amaf_map, owner_map_one = job.get()
            incoming.append((score, amaf_map, owner_map_one, nodes))
            ongoing.remove((job, nodes))

        # Early stop test
        best_wr = tree.best_move().winrate()
        if i > n*0.05 and best_wr > FASTPLAY5_THRES or i > n*0.2 and best_wr > FASTPLAY20_THRES:
            break

    for c in range(Board.W * Board.W):
        owner_map[c] = float(owner_map[c]) / i
    dump_subtree(tree)
    print_tree_summary(tree, i, f=sys.stderr)
    return tree.best_move()
