import sys
from srcs.model import ParseError
from srcs import Parser
from srcs import Solver, SimulationError


def main() -> None:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <map-file>", file=sys.stderr)
        sys.exit(1)

    try:
        graph = Parser().parse(sys.argv[1])
        lines = Solver().solve(graph)
    except (OSError, ParseError, SimulationError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    for line in lines:
        print(line)
    moves = sum(len(line.split()) for line in lines)
    print(f"Total turns: {len(lines)}", file=sys.stderr)
    print(f"Total moves: {moves}", file=sys.stderr)


if __name__ == "__main__":
    main()
