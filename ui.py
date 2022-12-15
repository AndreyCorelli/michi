import sys

from board import Board
from const import N_SIMS
from tree_node import TreeNode


def dump_subtree(node: TreeNode, thres=N_SIMS/50, indent=0, f=sys.stderr, recurse=True):
    """ print this node and all its children with v >= thres. """
    print("%s+- %s %.3f (%d/%d, prior %d/%d, rave %d/%d=%.3f, urgency %.3f)" %
          (indent*' ', Board.str_coord(node.pos.last), node.winrate(),
           node.w, node.v, node.pw, node.pv, node.aw, node.av,
           float(node.aw)/node.av if node.av > 0 else float('nan'),
           node.rave_urgency()), file=f)
    if not recurse:
        return
    for child in sorted(node.children, key=lambda n: n.v, reverse=True):
        if child.v >= thres:
            dump_subtree(child, thres=thres, indent=indent+3, f=f)


def print_tree_summary(tree: TreeNode, sims, f=sys.stderr):
    best_nodes = sorted(tree.children, key=lambda n: n.v, reverse=True)[:5]
    best_seq = []
    node = tree
    while node is not None:
        best_seq.append(node.pos.last)
        node = node.best_move()
    print('[%4d] winrate %.3f | seq %s | can %s' %
          (sims, best_nodes[0].winrate(), ' '.join([Board.str_coord(c) for c in best_seq[1:6]]),
           ' '.join(['%s(%.3f)' % (Board.str_coord(n.pos.last), n.winrate()) for n in best_nodes])), file=f)
