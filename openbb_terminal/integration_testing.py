#!/usr/bin/env python
"""Main Testing Module"""
__docformat__ = "numpy"

import contextlib
from datetime import datetime
from pathlib import Path
import re
import time
from typing import List, Dict, Optional, Tuple
import traceback
import argparse
import logging
import sys
import os

from openbb_terminal.rich_config import console
from openbb_terminal.core.config.paths import (
    MISCELLANEOUS_DIRECTORY,
    REPOSITORY_DIRECTORY,
)
from openbb_terminal.terminal_controller import (
    insert_start_slash,
    terminal,
    replace_dynamic,
)
from openbb_terminal.terminal_helper import is_reset, suppress_stdout

logger = logging.getLogger(__name__)
special_arguments_values = [
    "ticker",
    "currency",
    "crypto",
    "country",
    "repo",
    "crypto_vs",
    "crypto_full",
    "currency_vs",
]

LENGTH = 90
GRAY = "rgb(128,128,128)"
YELLOW = "yellow"
STYLES = [
    "[bold]",
    "[/bold]",
    "[red]",
    "[/red]",
    "[green]",
    "[/green]",
    "[bold red]",
    "[/bold red]",
]


def to_title(title: str, char: str = "=") -> str:
    """Format title for test mode.

    Parameters
    ----------
    title: str
        The title to format

    Returns
    -------
    str
        The formatted title
    """
    title = " " + title + " "

    len_styles = 0
    for style in STYLES:
        if style in title:
            len_styles += len(style)

    n = int((LENGTH - len(title) + len_styles) / 2)
    formatted_title = char * n + title + char * n
    formatted_title = formatted_title + char * (
        LENGTH - len(formatted_title) + len_styles
    )

    return formatted_title


def build_test_path_list(path_list: List[str]) -> List[Path]:
    """Build the paths to use in test mode."""
    if path_list == "":
        console.print("Please send a path when using test mode")
        return []

    test_files = []

    for path in path_list:
        script_path = MISCELLANEOUS_DIRECTORY / "scripts" / path

        if script_path.exists():
            chosen_path = script_path
        else:
            console.print(f"\n[red]Can't find the file: {script_path}[/red]\n")
            continue

        if chosen_path.is_file() and str(chosen_path).endswith(".openbb"):
            test_files.append(str(chosen_path))
        elif chosen_path.is_dir():
            all_files = os.walk(script_path)
            for root, _, files in all_files:
                for name in files:
                    if name.endswith(".openbb"):
                        path_obj = f"{root}/{name}"
                        test_files.append(path_obj)

    test_files_unique = set(test_files)
    final_path_list = [Path(x) for x in test_files_unique]
    return sorted(final_path_list)


def collect_test_files(path_list: List[str]) -> List[Path]:
    """Collects the test files from the scripts directory

    Parameters
    ----------
    path_list: List[str]
        The list of paths to test
    """

    if not path_list:
        path_list = [""]
    test_files = build_test_path_list(path_list)
    scripts_location = MISCELLANEOUS_DIRECTORY / "scripts"
    console.print(f"Collecting scripts from: {scripts_location}\n")
    console.print(f"collected {len(test_files)} scripts\n", style="bold")

    return test_files


def run_scripts(
    path: Path,
    test_mode: bool = False,
    verbose: bool = False,
    routines_args: List[str] = None,
    special_arguments: Optional[Dict[str, str]] = None,
    output: bool = True,
):
    """Run given .openbb scripts.

    Parameters
    ----------
    path : str
        The location of the .openbb file
    test_mode : bool
        Whether the terminal is in test mode
    verbose : bool
        Whether to run tests in verbose mode
    routines_args : List[str]
        One or multiple inputs to be replaced in the routine and separated by commas.
        E.g. GME,AMC,BTC-USD
    special_arguments: Optional[Dict[str, str]]
        Replace `${key=default}` with `value` for every key in the dictionary
    output: bool
        Whether to log tests to txt files
    """
    if not path.exists():
        console.print(f"File '{path}' doesn't exist. Launching base terminal.\n")
        if not test_mode:
            terminal()

    with path.open() as fp:
        raw_lines = [x for x in fp if (not is_reset(x)) and ("#" not in x) and x]
        raw_lines = [
            raw_line.strip("\n") for raw_line in raw_lines if raw_line.strip("\n")
        ]

        if routines_args:
            lines = []
            for rawline in raw_lines:
                templine = rawline
                for i, arg in enumerate(routines_args):
                    templine = templine.replace(f"$ARGV[{i}]", arg)
                lines.append(templine)
        # Handle new testing arguments:
        elif special_arguments:
            lines = []
            for line in raw_lines:
                new_line = re.sub(
                    r"\${[^{]+=[^{]+}",
                    lambda x: replace_dynamic(x, special_arguments),  # type: ignore
                    line,
                )
                lines.append(new_line)

        else:
            lines = raw_lines

        if test_mode and "exit" not in lines[-1]:
            lines.append("exit")

        export_folder = ""
        if "export" in lines[0]:
            export_folder = lines[0].split("export ")[1].rstrip()
            lines = lines[1:]

        simulate_argv = f"/{'/'.join([line.rstrip() for line in lines])}"
        file_cmds = simulate_argv.replace("//", "/home/").split()
        file_cmds = insert_start_slash(file_cmds) if file_cmds else file_cmds
        if export_folder:
            file_cmds = [f"export {export_folder}{' '.join(file_cmds)}"]
        else:
            file_cmds = [" ".join(file_cmds)]

        if not test_mode or verbose:
            terminal(file_cmds, test_mode=True)
        else:
            with suppress_stdout():
                print(f"To ensure: {output}")
                if output:
                    timestamp = datetime.now().timestamp()
                    stamp_str = str(timestamp).replace(".", "")
                    whole_path = Path(REPOSITORY_DIRECTORY / "integration_test_output")
                    whole_path.mkdir(parents=True, exist_ok=True)
                    first_cmd = file_cmds[0].split("/")[1]
                    with open(
                        whole_path / f"{stamp_str}_{first_cmd}_output.txt", "w"
                    ) as output_file:
                        with contextlib.redirect_stdout(output_file):
                            terminal(file_cmds, test_mode=True)
                else:
                    terminal(file_cmds, test_mode=True)


def run_test_files(
    test_files: list, verbose: bool, special_arguments: dict
) -> Tuple[int, int, Dict[str, Dict[str, object]], float]:
    """Runs the test scripts and returns the fails dictionary

    Parameters
    -----------
    test_files: list
        The list of paths to test
    verbose: bool
        Whether or not to print the output of the scripts
    special_arguments: dict
        The special arguments to use in the scripts

    Returns
    -------
    fails: dict
        The dictionary with failure information
    """

    start = time.time()

    os.environ["DEBUG_MODE"] = "true"
    SUCCESSES = 0
    FAILURES = 0
    fails = {}
    for i, file in enumerate(test_files):

        file_short_name = str(file).replace(str(MISCELLANEOUS_DIRECTORY), "")
        file_short_name = file_short_name[1:]

        try:
            run_scripts(
                file,
                test_mode=True,
                verbose=verbose,
                special_arguments=special_arguments,
                output=True,
            )
            SUCCESSES += 1
        except Exception as e:
            _, _, exc_traceback = sys.exc_info()
            fails[file_short_name] = {
                "exception": e,
                "traceback": traceback.extract_tb(exc_traceback),
            }
            FAILURES += 1

        # Test performance
        percentage = f"{(i + 1)/len(test_files):.0%}"
        percentage_with_spaces = "[" + (4 - len(percentage)) * " " + percentage + "]"
        spacing = LENGTH - len(file_short_name) - len(percentage_with_spaces)
        console.print(
            f"{file_short_name}" + spacing * " " + f"{percentage_with_spaces}",
            style="green" if not FAILURES else "red",
        )

    end = time.time()
    seconds = end - start

    return SUCCESSES, FAILURES, fails, seconds


def display_failures(fails: dict) -> None:
    """Generates the message and csv from the fails dictionary

    Parameters
    -----------
    fails: dict
        The dictionary with failure information
    output: bool
        Whether or not to save output into a CSV file
    """
    if fails:
        console.print("\n" + to_title("FAILURES"))
        for file, exception in fails.items():
            title = f"[bold red]{file}[/bold red]"
            console.print(to_title(title=title, char="-"), style="red")

            console.print("[bold red]\nTraceback:[/bold red]")
            formatted_tb = traceback.format_list(exception["traceback"])
            style = ""
            for i, line in enumerate(formatted_tb):
                if "openbb_terminal" not in line:
                    style = GRAY
                elif i == len(formatted_tb) - 1:
                    style = YELLOW
                elif "openbb_terminal" not in formatted_tb[i + 1]:
                    style = YELLOW

                console.print(line, end="", style=style)

            console.print(
                f"[bold red]Exception type:[/bold red] {exception['exception'].__class__.__name__}"
            )
            console.print(f"[bold red]Detail:[/bold red] {exception['exception']}")
            console.print("- " * int(LENGTH / 2))


def display_summary(
    fails: dict,
    n_successes: int,
    n_failures: int,
    seconds: float,
) -> None:
    """Generates the summary message

    Parameters
    ----------
    fails: dict
        The dictionary with failure information
    n_successes: int
        The number of successes
    n_failures: int
        The number of failures
    seconds: float
        The number of seconds it took to run the tests
    """

    if fails:
        console.print("\n" + to_title("integration test summary"))

        for file, exception in fails.items():

            broken_cmd = "unknown"
            for _, frame in reversed(list(enumerate(exception["traceback"]))):
                if "_controller.py" in frame.filename and "call_" in frame.name:
                    broken_cmd = frame.name.split("_")[1]
                    break

            console.print(f"FAILED {file} -> command: {broken_cmd}")

    failures = (
        f"[bold][red]{n_failures} failed, [/red][/bold]" if n_failures > 0 else ""
    )
    successes = f"[green]{n_successes} passed[/green]" if n_successes > 0 else ""
    console.print(
        to_title(failures + successes + " in " + f"{(seconds):.2f} s"),
        style="green" if not n_failures else "red",
    )


def run_test_list(
    path_list: List[str], verbose: bool, special_arguments: Dict[str, str]
) -> None:
    """Run commands in test mode.

    Workflow:
    1. Collect scripts
    2. Run tests
    3. Display failures
    4. Display summary

    Parameters
    ----------
    path_list: list
        The list of paths to test
    verbose: bool
        Whether or not to print the output of the scripts
    special_arguments: dict
        The special arguments to use in the scripts
    """

    console.print(to_title("integration test session starts"), style="bold")

    test_files = collect_test_files(path_list)
    SUCCESSES, FAILURES, fails, seconds = run_test_files(
        test_files, verbose, special_arguments
    )
    display_failures(fails)
    display_summary(fails, SUCCESSES, FAILURES, seconds)


def parse_args_and_run():
    """Parse input arguments and run integration tests."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        prog="testing",
        description="Integration tests for the OpenBB Terminal.",
    )
    parser.add_argument(
        "-p",
        "--path",
        help=(
            "The path or .openbb file to run. Starts at "
            "OpenBBTerminal/openbb_terminal/miscellaneous/scripts"
        ),
        dest="path",
        nargs="+",
        default="",
        type=str,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Enable verbose output for debugging",
        dest="verbose",
        action="store_true",
        default=False,
    )
    # This is the list of special arguments a user can send
    for arg in special_arguments_values:
        parser.add_argument(
            f"--{arg}",
            help=f"Change the default values for {arg}",
            dest=arg,
            type=str,
            default="",
        )

    ns_parser, _ = parser.parse_known_args()
    special_args_dict = {x: getattr(ns_parser, x) for x in special_arguments_values}
    run_test_list(
        path_list=ns_parser.path,
        verbose=ns_parser.verbose,
        special_arguments=special_args_dict,
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if "-" not in sys.argv[1][0]:
            sys.argv.insert(1, "-p")
    parse_args_and_run()
