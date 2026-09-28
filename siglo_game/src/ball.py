class Ball:
    """
    Represents a single playing piece (ball/ficha) in the game 'Siglo'.
    Each ball has a unique value from 1 to 90.
    """
    def __init__(self, value: int):
        self.value = value

    def __str__(self):
        return f"[{self.value}]"

    def __repr__(self):
        return self.__str__()
