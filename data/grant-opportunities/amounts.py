"""Read dollar amounts out of the free-text funding columns of the grants tracker."""
import re

MULT = {'k': 1e3, 'm': 1e6, 'million': 1e6, 'b': 1e9, 'billion': 1e9}
NUM = r'(\d[\d,]*(?:\.\d+)?)'
SUF = r'(?:\s*(k|million|billion|m|b)\b)?'
AMOUNT = re.compile(r'\$\s?' + NUM + SUF + r'(?:\s*(?:-|–|to)\s*\$?\s?' + NUM + SUF + r')?', re.I)

def _num(s):
    s = s.rstrip(',')  # '$150,000, with ...'
    # reject malformed digit grouping such as "2,00,000" rather than guess
    if ',' in s and not re.fullmatch(r'\d{1,3}(,\d{3})+(\.\d+)?', s):
        return None
    return float(s.replace(',', ''))

def amounts(text):
    """Every dollar amount in text; a range like '$5-20M' yields both ends."""
    out = []
    for m in AMOUNT.finditer(text or ''):
        a, sa, b, sb = m.groups()
        a = _num(a)
        if a is None:
            continue
        if b:
            b = _num(b)
            # '$100-$500K', '$5-20M': the suffix on the upper end applies to both
            if not sa and sb and a < 1000:
                sa = sb
            if b is not None:
                out.append(b * MULT.get((sb or sa or '').lower(), 1))
        out.append(a * MULT.get((sa or '').lower(), 1))
    return sorted({round(x) for x in out})

UNKNOWN = re.compile(r'^\s*(unclear|unknown|tbd|not specified|varies)', re.I)

def total_funds(text):
    """Total funding in dollars when the text states exactly one amount, else None."""
    text = text or ''
    a = amounts(text)
    if len(a) != 1 or UNKNOWN.match(text):
        return None
    return a[0]

def award_range(text):
    """(grant_award_min, grant_award_max) from the award text; None where not given."""
    text = text or ''
    a = amounts(text)
    if not a or re.search(r'no (set )?(min(imum)? or max|funding range)', text, re.I):
        return None, None
    no_min = bool(re.match(r'\s*no minimum', text, re.I))
    no_max = bool(re.match(r'\s*no maximum', text, re.I))
    if len(a) == 1:
        if re.search(r'minimum|\bmin\b', text, re.I) and not no_min:
            lo, hi = a[0], None
        elif re.search(r'up to|max|ceiling|<|largest', text, re.I):
            lo, hi = None, a[0]
        else:
            lo, hi = a[0], a[0]
    elif len(re.findall(r'\bmax', text, re.I)) >= 2:
        # 'Planning $250K max; Implementation $4M max': every amount is a cap
        lo, hi = None, a[-1]
    else:
        lo, hi = a[0], a[-1]
    return (None if no_min else lo), (None if no_max else hi)
