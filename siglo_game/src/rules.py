from typing import List
from src.player import Player

class Rules:
    """
    Implements the rules of the Siglo game.
    """
    
    @staticmethod
    def evaluate_player_status(player: Player):
        """
        Updates the player's status based on their score.
        """
        if player.score == 99 or player.score == 100:
            player.status = "SIGLO"
        elif player.score > 100:
            player.status = "ME_FUI"
            
    @staticmethod
    def determine_round_winners(players: List[Player]) -> List[Player]:
        """
        Determines the winner(s) of a round.
        Returns a list of winning players (handling ties).
        """
        valid_players = [p for p in players if p.status != "ME_FUI" and p.score <= 100]
        
        if not valid_players:
            return [] # Everyone exceeded 100
            
        max_score = max(p.score for p in valid_players)
        winners = [p for p in valid_players if p.score == max_score]
        
        return winners
