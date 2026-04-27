import re
import unicodedata


def normalize_search_text(value):
    if value is None:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    cleaned = re.sub(r'[^A-Za-z0-9]+', ' ', ascii_text)
    collapsed = re.sub(r'\s+', ' ', cleaned).strip().lower()
    return collapsed


def normalize_name_shape(value):
    normalized = normalize_search_text(value)
    if not normalized:
        return ''
    collapsed_vowels = re.sub(r'[aeiou]+', 'a', normalized)
    collapsed_letters = re.sub(r'([a-z])\1+', r'\1', collapsed_vowels)
    return collapsed_letters


def simple_soundex(value):
    cleaned = normalize_search_text(value)
    if not cleaned:
        return ''
    letters = re.sub(r'[^a-z]', '', cleaned)
    if not letters:
        return ''
    first = letters[0].upper()
    mapping = {
        **{char: '1' for char in 'bfpv'},
        **{char: '2' for char in 'cgjkqsxz'},
        **{char: '3' for char in 'dt'},
        'l': '4',
        **{char: '5' for char in 'mn'},
        'r': '6',
    }
    digits = []
    previous = mapping.get(letters[0], '')
    for char in letters[1:]:
        digit = mapping.get(char, '')
        if digit and digit != previous:
            digits.append(digit)
        previous = digit
    return (first + ''.join(digits) + '000')[:4]


def build_initials(*parts):
    tokens = []
    for part in parts:
        normalized = re.sub(r'[^A-Za-z0-9 ]', ' ', str(part or '')).split()
        tokens.extend(token for token in normalized if token)
    if not tokens:
        return '?'
    if len(tokens) == 1:
        return tokens[0][0].upper()
    return (tokens[0][0] + tokens[1][0]).upper()
