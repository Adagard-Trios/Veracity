import sys
try:
    import src.nodes.win_loss_node
except Exception as e:
    print("Exact error:", repr(e))
    sys.exit(1)
