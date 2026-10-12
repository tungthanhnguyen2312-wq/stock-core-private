"""Historical heading/assurance text folding; never normalize financial values.

This preserves NFKD/punctuation behavior exactly. Literal row identity's stricter
NFD fold remains separately owned by the OCR row classifier and is not replaced.
"""
import re


def _normalize(value: str) -> str:
    import unicodedata
    # OCR commonly inserts apostrophes inside Vietnamese words (for example
    # ``LU'U``).  Normalize punctuation only for statement/scope headings;
    # values and their raw OCR text never pass through this helper.
    folded = "".join(ch for ch in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(ch))
    folded = re.sub(r"(?<=[a-z0-9])['’](?=[a-z0-9])", "", folded)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded.replace("đ", "d")).split())
