

from colorama import Fore, Style, just_fix_windows_console


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
