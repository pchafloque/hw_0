import random
import sys

filename = sys.argv[1] "Comment"

with open(filename) as f:
    for line in f:
        if random.random() < 0.01:
            print(line, end = "")
