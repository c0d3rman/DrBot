def get_dupes(L: list) -> set:
    """
    Given a list, get a set of all elements which appear more than once.
    """
    seen, seen2 = set(), set()
    for item in L:
        seen2.add(item) if item in seen else seen.add(item)
    return seen2
