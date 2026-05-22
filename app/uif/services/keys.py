from typing import Tuple


def patrimonial_key(kardex: str, act_code: str) -> Tuple[str, str]:
    return (kardex, str(act_code).zfill(3))
