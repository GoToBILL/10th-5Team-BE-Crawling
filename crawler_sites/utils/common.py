from typing import Optional, Union

def normalize_platforms(value: Optional[Union[str, list]]) -> list[str]:
    if isinstance(value, str):
        return [value]
    elif isinstance(value, list):
        return value
    else:
        return []
