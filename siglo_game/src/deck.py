import random
from src.ball import Ball

class Deck:
    """
    Represents the collection of balls (1 to 90).
    Handles drawing and shuffling of balls.
    """
    def __init__(self):
        self.balls = []
        self._initialize_deck()

    def _initialize_deck(self):
        """Creates 90 unique balls and shuffles them."""
        self.balls = [Ball(i) for i in range(1, 91)]
        self.shuffle()

    def shuffle(self):
        """Shuffles the current balls randomly."""
        random.shuffle(self.balls)

    def draw(self) -> Ball:
        """
        Extracts and returns one ball from the deck.
        Returns None if the deck is empty.
        """
        if not self.balls:
            return None
        return self.balls.pop()

    def count(self) -> int:
        """Returns the number of remaining balls."""
        return len(self.balls)
