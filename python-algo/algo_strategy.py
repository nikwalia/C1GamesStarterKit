import gamelib
import random
import math
import warnings
from sys import maxsize
import json
from sys import stderr


"""
Most of the algo code you write will be in this file unless you create new
modules yourself. Start by modifying the 'on_turn' function.
Advanced strategy tips: 
  - You can analyze action frames by modifying on_action_frame function
  - The GameState.map object can be manually manipulated to create hypothetical 
  board states. Though, we recommended making a copy of the map to preserve 
  the actual current map state.
"""

class AlgoStrategy(gamelib.AlgoCore):

    def __init__(self):
        super().__init__()
        seed = random.randrange(maxsize)
        random.seed(seed)
        gamelib.debug_write('Random seed: {}'.format(seed))

    def on_game_start(self, config):
        """ 
        Read in config and perform any initial setup here 
        """
        gamelib.debug_write('Configuring your custom algo strategy...')
        self.config = config
        global FILTER, ENCRYPTOR, DESTRUCTOR, PING, EMP, SCRAMBLER
        FILTER = config["unitInformation"][0]["shorthand"]
        ENCRYPTOR = config["unitInformation"][1]["shorthand"]
        DESTRUCTOR = config["unitInformation"][2]["shorthand"]
        PING = config["unitInformation"][3]["shorthand"]
        EMP = config["unitInformation"][4]["shorthand"]
        SCRAMBLER = config["unitInformation"][5]["shorthand"]
        # This is a good place to do initial setup
        self.scored_on_locations = []

    def get_enemy_units(self, game_state, turn_state):
        turn_state_obj = json.loads(turn_state)
        p2units = turn_state_obj["p2Units"]
        
        enemy_defenses = []
        for item in p2units:
            for sub_item in item:
                x = sub_item[0]
                y = sub_item[1]
                for unit in game_state.game_map[x, y]:
                    enemy_defenses.append(unit)
        
        game_state.enemy_defenses = enemy_defenses
        
    def on_turn(self, turn_state):
        """
        This function is called every turn with the game state wrapper as
        an argument. The wrapper stores the state of the arena and has methods
        for querying its state, allocating your current resources as planned
        unit deployments, and transmitting your intended deployments to the
        game engine.
        """
        game_state = gamelib.GameState(self.config, turn_state)
        gamelib.debug_write('Performing turn {} of your custom algo strategy'.format(game_state.turn_number))
        game_state.suppress_warnings(True)  #Comment or remove this line to enable warnings.
        self.get_enemy_units(game_state, turn_state)
        self.strategy(game_state)
        
        game_state.submit_turn()

    def strategy(self, game_state):

        turn1_scrambler_locations = [[2,11], [25, 11], [11, 2], [16, 2]]

        if game_state.turn_number == 0:
            game_state.attempt_spawn(SCRAMBLER, turn1_scrambler_locations, 1)
        pathFinder = gamelib.navigation.ShortestPathFinder()
        pathFinder.initialize_map(game_state)

        enemy_left_side_locations = game_state.game_map.get_edge_locations(game_state.game_map.BOTTOM_LEFT)
        enemy_right_side_locations = game_state.game_map.get_edge_locations(game_state.game_map.BOTTOM_RIGHT)

        edge_paths = []
        for location in enemy_left_side_locations: 
            edge_paths.append(game_state.find_path_to_edge(location, game_state.game_map.TOP_LEFT))

        for location in enemy_right_side_locations: 
            edge_paths.append(game_state.find_path_to_edge(location, game_state.game_map.TOP_RIGHT))
        
        gamelib.debug_write(edge_paths)
        self.print_locations_on_map(self.get_block_locations(game_state, edge_paths))
    
    def get_block_locations(self, game_state, edge_paths):

        potential_block_locations = []

        for path in edge_paths:
            if path is not None:
                for location in path:
                    # if the path goes into our side
                    if location[1] > 14:
                        potential_block_locations.append(location)
        
        return potential_block_locations


    def build_defences(self, game_state):
        pass

    def build_reactive_defense(self, game_state):
        """
        This function builds reactive defenses based on where the enemy scored on us from.
        We can track where the opponent scored by looking at events in action frames 
        as shown in the on_action_frame function
        """
        for location in self.scored_on_locations:
            # Build destructor one space above so that it doesn't block our own edge spawn locations
            build_location = [location[0], location[1]+1]
            game_state.attempt_spawn(DESTRUCTOR, build_location)

    def emp_line_strategy(self, game_state):
        """
        Build a line of the cheapest stationary unit so our EMP's can attack from long range.
        """
        # First let's figure out the cheapest unit
        # We could just check the game rules, but this demonstrates how to use the GameUnit class
        stationary_units = [FILTER, DESTRUCTOR, ENCRYPTOR]
        cheapest_unit = FILTER
        for unit in stationary_units:
            unit_class = gamelib.GameUnit(unit, game_state.config)
            if unit_class.cost < gamelib.GameUnit(cheapest_unit, game_state.config).cost:
                cheapest_unit = unit

        # Now let's build out a line of stationary units. This will prevent our EMPs from running into the enemy base.
        # Instead they will stay at the perfect distance to attack the front two rows of the enemy base.
        for x in range(27, 5, -1):
            game_state.attempt_spawn(cheapest_unit, [x, 11])

        # Now spawn EMPs next to the line
        # By asking attempt_spawn to spawn 1000 units, it will essentially spawn as many as we have resources for
        game_state.attempt_spawn(EMP, [24, 10], 1000)

    def least_damage_spawn_location(self, game_state, location_options):
        """
        This function will help us guess which location is the safest to spawn moving units from.
        It gets the path the unit will take then checks locations on that path to 
        estimate the path's damage risk.
        """
        damages = []
        # Get the damage estimate each path will take
        for location in location_options:
            path = game_state.find_path_to_edge(location)
            damage = 0
            for path_location in path:
                # Get number of enemy destructors that can attack the final location and multiply by destructor damage
                damage += len(game_state.get_attackers(path_location, 0)) * gamelib.GameUnit(DESTRUCTOR, game_state.config).damage
            damages.append(damage)
        
        # Now just return the location that takes the least damage
        return location_options[damages.index(min(damages))]

    def detect_enemy_unit(self, game_state, unit_type=None, valid_x = None, valid_y = None):
        total_units = 0
        for location in game_state.game_map:
            if game_state.contains_stationary_unit(location):
                for unit in game_state.game_map[location]:
                    if unit.player_index == 1 and (unit_type is None or unit.unit_type == unit_type) and (valid_x is None or location[0] in valid_x) and (valid_y is None or location[1] in valid_y):
                        total_units += 1
        return total_units
        
    def filter_blocked_locations(self, locations, game_state):
        filtered = []
        for location in locations:
            if not game_state.contains_stationary_unit(location):
                filtered.append(location)
        return filtered

    def on_action_frame(self, turn_string):
        """
        This is the action frame of the game. This function could be called 
        hundreds of times per turn and could slow the algo down so avoid putting slow code here.
        Processing the action frames is complicated so we only suggest it if you have time and experience.
        Full doc on format of a game frame at: https://docs.c1games.com/json-docs.html
        """
        # Let's record at what position we get scored on
        state = json.loads(turn_string)
        events = state["events"]
        breaches = events["breach"]
        for breach in breaches:
            location = breach[0]
            unit_owner_self = True if breach[4] == 1 else False
            # When parsing the frame data directly, 
            # 1 is integer for yourself, 2 is opponent (StarterKit code uses 0, 1 as player_index instead)
            if not unit_owner_self:
                gamelib.debug_write("Got scored on at: {}".format(location))
                self.scored_on_locations.append(location)
                gamelib.debug_write("All locations: {}".format(self.scored_on_locations))


    def print_locations_on_map(self, locations):
        '''
        Pass in a list of locations and this will print out a map of the locations on the screen
        '''
        for y in range(28):
            for x in range(28):
                if ((27-y)-x > -14) and ((27-y)+x > 13) and ((27-y) - x < 14) and ((27-y) + x < 41):
                    if [x, y] in locations:
                        stderr.write("x")
                    else:
                        stderr.write(".")
                else:
                    stderr.write(" ")
            stderr.write("\n")
        stderr.flush()

if __name__ == "__main__":
    algo = AlgoStrategy()
    algo.start()

