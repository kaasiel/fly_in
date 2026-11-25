"""Content of the main programm."""
import sys
import logging
from srcs import ParseError
from srcs import Parser
from srcs import Solver, SimulationError
from srcs import App, Graph, App3D
from srcs import choose_map
logging.getLogger("raylib").setLevel(logging.ERROR)


def main() -> None:
    """Run the program."""
    graph: Graph | None = None
    lines: list[str] = []
    try:
        while True:
            choice = choose_map()
            if choice is None:
                return
            path, view = choice
            if path is None:
                break
            graph = Parser().parse(path)
            lines = Solver().solve(graph)
            for output_line in lines:
                print(output_line)
            if view == "iso":
                App3D(graph, lines).run()
            else:
                App(graph, lines).run()
        print(f"Total turns: {len(lines)}", file=sys.stderr)
    except (OSError, ParseError, SimulationError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
