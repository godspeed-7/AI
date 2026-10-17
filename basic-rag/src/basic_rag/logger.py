"""Coloured console output shared by the scripts.

Each helper prints one line with a coloured tag:

    [INFO]   cyan     extra detail
    [....]   yellow   a step is starting
    [DONE]   green    a step finished
    [ERROR]  red      something went wrong
    [TIME]   blue     how long a step took
    heading  magenta  a banner between sections of output
"""

from colorama import Fore, Style, just_fix_windows_console


# Makes the colour codes work in the Windows console; does nothing on
# macOS/Linux.
just_fix_windows_console()


def info(message: str):
    print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} {message}")


def progress(message: str):
    print(f"{Fore.YELLOW}[....]{Style.RESET_ALL} {message}")


def success(message: str):
    print(f"{Fore.GREEN}[DONE]{Style.RESET_ALL} {message}")


def error(message: str):
    print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {message}")


def heading(message: str):
    print(f"\n{Fore.MAGENTA}{'=' * 55}")
    print(f"  {message}")
    print(f"{'=' * 55}{Style.RESET_ALL}")


def timing(message: str, seconds: float):
    print(
        f"{Fore.BLUE}[TIME]{Style.RESET_ALL} "
        f"{message}: {seconds:.2f}s"
    )
