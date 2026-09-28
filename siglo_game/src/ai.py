import random

class AI:
    """
    Artificial Intelligence for automated players in Siglo.
    """
    @staticmethod
    def decide_action(score: int) -> str:
        """
        Decides whether to draw a ball ("BOLA") or stay ("ME_QUEDO").
        """
        if score < 70:
            return "BOLA"
        elif 70 <= score <= 88:
            return "BOLA" if random.random() < 0.75 else "ME_QUEDO"
        elif 89 <= score <= 95:
            return "BOLA" if random.random() < 0.4 else "ME_QUEDO"
        elif 96 <= score <= 98:
            return "BOLA" if random.random() < 0.1 else "ME_QUEDO"
        else:
            return "ME_QUEDO"
