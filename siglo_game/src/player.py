from typing import List
from src.ball import Ball

class Player:
    """
    Represents a player in the game.
    """
    def __init__(self, name: str, is_ai: bool = False):
        self.name = name
        self.is_ai = is_ai
        self.hand: List[Ball] = []
        self.score = 0
        self.status = "WAITING" # WAITING, PLAYING, ME_QUEDO, ME_FUI, SIGLO

    def add_ball(self, ball: Ball):
        """Adds a ball to the player's hand and updates the score."""
        self.hand.append(ball)
        self.score += ball.value

    def reset_round(self):
        """Resets the player's state for a new round."""
        self.hand = []
        self.score = 0
        self.status = "WAITING"
