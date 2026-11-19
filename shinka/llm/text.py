"""Pure text extraction; no provider SDK dependencies."""
import json
import re
from typing import Optional, Union


def extract_between(
    content: str,
    start: str = "<json>",
    end: str = "</json>",
    return_dict: bool = True,
    fallback: bool = False,
) -> Optional[Union[str, dict]]:
    """Extract text from between start and end tags.

    Args:
        content (str): The input string containing CUDA code

    Returns:
        str: The extracted text, or None if no text is found
    """
    # The tags are literal text, not patterns: a fence such as ```c++ must not
    # compile to a possessive quantifier that matches "c" and leaves "++" in
    # the extracted code.
    match = re.search(
        f"{re.escape(start)}\\s*(.*?)\\s*{re.escape(end)}", content, re.DOTALL
    )
    if match:
        matched_str = match.group(1).strip()
        if return_dict:
            return json.loads(matched_str)
        else:
            return matched_str

    # Extracts any block between ``` and ```
    if fallback:
        match = re.search("```\\s*(.*?)\\s*```", content, re.DOTALL)
        if match:
            matched_str = match.group(1).strip()
            if return_dict:
                return json.loads(matched_str)
            else:
                return matched_str
    return "none"
