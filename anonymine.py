#!/usr/bin/python

# Copyright (c) Oskar Skog, 2016-2019
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1.  Redistributions of source code must retain the above copyright notice,
#     this list of conditions and the following disclaimer.
#
# 2.  Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#
# This software is provided by the copyright holders and contributors "as is"
# and any express or implied warranties, including, but not limited to, the
# implied warranties of merchantability and fitness for a particular purpose
# are disclaimed. In no event shall the copyright holder or contributors be
# liable for any direct, indirect, incidental, special, exemplary, or
# consequential damages (including, but not limited to, procurement of
# substitute goods or services; loss of use, data, or profits; or business
# interruption) however caused and on any theory of liability, whether in
# contract, strict liability, or tort (including negligence or otherwise)
# arising in any way out of the use of this software, even if advised of the
# possibility of such damage.

'''A minesweeper that can be solved without guessing

Copyright (c) Oskar Skog, 2016-2019
Released under the FreeBSD license.

A minesweeper that can be solved without guessing
=================================================

    This script contains a curses based interface class, a command line
    setup function, a line mode setup function and glue.

    The engine is in a separate module (anonymine_engine).
    
    The game support three different gametypes:
        Moore neighbourhoods: each cell has eight neighbours.
        Hexagonal cells: each cell has six neighbours.
        Von Neumann neighbourhoods: each cell has four neighbours.
'''

import curses
import os
import sys
import errno
import locale
import signal
import sys
import traceback        # Not required.

# Let piping to less(1) fail on Minix.
try:
    import subprocess
except:
    pass
# Losing the ability to take command line options is no biggy.
try:
    import argparse
except:
    pass

if 'SIGTSTP' in dir(signal):
    signal.signal(signal.SIGTSTP, signal.SIG_IGN)


import anonymine_engine as game_engine

# These two are still needed.
GAME_NAME = 'Anonymine'
GAME_FILENAME = 'anonymine'
GAME_CRAPTEXT = """Anonymine version MAKEFILE_GAME_VERSION
Copyright (c) Oskar Skog, 2016-2019
Released under the Simplified BSD license (2 clause).
\n"""


class curses_game():
    '''Class for interface object for `engine.play_game(interface)`.
    
    This is a large part of the curses mode interface for Anonymine.
    The "engine" is in the module `anonymine_engine` and could be used
    by a different interface.
    
    The engine is currently (as of version 0.0.13) responsible for
    creating the "field", initialization of the field (filling it with
    mines) and the main loop of a game.
    
    anonymine_engine.game_engine(**params).play_game(interface)
    
    `interface` is an object that needs to provide these methods:
        input(self, field)
        output(self, field)
        anykey_cont(self)
    
    It is recommended that you read the documentation for the engine
    as well.
    
    
    Coordinates
    ===========
    
        The "cursor" marks the selected cell on the field. It is a
        "field coordinate".
        
        A "virtual coordinate" is a coordinate on an imaginary screen.
        A virtual coordinate doesn't need to be in the "visible area".
        A virtual coordinate can easily be generated from a field
        coordinate.
        
        The visible area are those virtual coordinates that exist on
        the screen.  The visible area can be moved with
        `self.window_start`.
        
        A "real coordinate" is a coordinate on the screen and can be
        sent to the methods of `self.window`.
        
        real[0] = virtual[0] - window_start[0]
        real[1] = virtual[1] - window_start[1]
        
        The screen is `self.window`, not the real one.
    
    
    Externally used methods
    =======================
    
        interface = curses_game(cfgfile, gametype)
            `cfgfile` is the path to the cursescfg configuration file
                (the configuration file with the key bindings and
                textics.)
            `gametype` is either 'moore', 'hex' or 'neumann'.
            
            NOTICE: `curses_game.__init__` will enter curses mode.
            WARNING: `curses_game.__init__` MAY raise an exception
                while in curses mode if something is wrong with the
                configuration or if bad parameters are given.
        
        interface.leave()
            Leave curses mode.
        
        interface.input(engine)
            (This method is called by `engine.play_game`.)
            Take command from user and act on `engine.field`.
        
        interface.output(engine)
            (This method is called by `engine.play_game`.)
            Print the field (`engine.field`) to the screen.
            Prints the flags left text, invokes `self.print_square` or
            `self.print_hex`, and finally, `self.window.refresh`.
        
        interface.anykey_cont()
            (This method is called by `engine.play_game`.)
            Pause until input from user.
            "Press any key to continue..."
    
    
    Attributes
    ==========
    
        interface.window = curses.initscr()
            The screen.
        
        interface.cursor = (0, 0)
            The *field* coordinate.
        
        interface.window_start = [0, 0]
            Needed for translating virtual coordinates into real
            coordinates.
    
    
    Internally used methods
    =======================
    
        char, attributes = self.curses_output_cfg(key)
            "Parse" the configuration (cursescfg) and pick the most
            appropriate mode for the property `key`.  The color pair
            is properly attached to `attributes`.
        
        self.message(msg)
            Print `msg` at the bottom of the screen while in curses
            mode.  Invokes `self.window.refresh`.
            Used for printing the initialization message and by
            `self.anykey_cont`.
        
        self.travel(engine, direction)
            Modify `self.cursor` to select a new cell in the
            specified direction.
        
        self.print_char(x, y, cfg, char=None)
            Print a character at the virtual coordinate (x, y) using
            the textics property `cfg`.  `char` will override the
            character specified in the textics directive.
        
        self.move_visible_area(virtual_x,virtual_y,x_border,y_border)
            Modify `self.window_start` so (virtual_x, virtual_y) is
            visible on the screen, and not too close to any edge.
        
        self.print_square(field)
            Print Moore and Neumann fields and the "cursor" to the
            screen.  Does not invoke `self.window.refresh` and does
            not print the flags left text.
        
        self.print_hex(field)
            Print hexagonal fields and the "cursor" to the screen.
            Does not invoke `self.window.refresh` and does not print
            the flags left text.
    
    
    Constants
    =========
    
        self.travel_diffs
            A dictionary of dictionaries to translate a direction
            into DELTA-x and DELTA-y.  Used by `self.travel`.
        
        self.direction_keys
            A dictionary of lists representing the valid directions
            for a certain gametype.  This allows square and hex
            directions to share the same keys.
            Used by `self.input`.
        
        self.specials
            The method `get` of the field object may return one of
            these value or a normal number.  (Normal numbers will be
            printed using their digit as character and the textics
            directive 'number'.)
            This dictionary maps the special return values into
            textics properties.
    '''
    
# BUG: This is referenced from various lines in the class.
#    More or less platform specific.
#    Detected on:
#       OS: Debian 8 (Linux 3.16) (x86-64)
#       curses.version: 2.2
#       Library: ncurses5.9
#    Description:
#        After forking, it appears, when the field is being initialized, the
#        curses mode stops working.
#    Solution:
#        Define a program mode and temporarily reset to shell mode while
#        initializing the field.
#            The cursor can still not be hidden, so it will be moved to an
#        unimportant place.
#            The screen requires one complete redrawal of the screen, so that
#        will also be done.
#    NOTICE:
#        FOR THE LOVE OF KEN, DO NOT REMOVE WORKAROUND!!
#    NOTICE:
#        DO NOT REMOVE.
#        This is referenced from the source.
#    Update 2016-07-17:
#        The windows only needs to be redrawn on initialization, not on every
#        click.
#        Trying to leave and re-enter curses mode was no good.
#    Update 2016-12-10 (pre 0.4.2):
#        No need to temporarily reset to shell mode every time a cell is
#        revealed.  The issue was that game_status changed. Fixed in 0.3.11
    
    def __init__(self, cfgfile, gametype):
        '''Create interface object and enter curses mode.
        
        `cfgfile` is the path to the cursescfg file.
        `gametype` must be 'moore', 'hex' or 'neumann'.
        
        WARNING: This does not leave curses mode on exceptions!
        '''
        
        self.curses_voodoo = not sys.platform.startswith('win')
        
        # Constants
        self.travel_diffs = {
            'square': {
                'up':           (0, -1),
                'right':        (1,  0),
                'down':         (0,  1),
                'left':        (-1,  0),
                'NE':           (1, -1),
                'SE':           (1,  1),
                'SW':          (-1,  1),
                'NW':          (-1, -1),
            },
            'hex-even': {
                'hex0':         (0, -1),         # 5 0
                'hex1':         (1,  0),        # 4   1
                'hex2':         (0,  1),         # 3 2
                'hex3':        (-1,  1),
                'hex4':        (-1,  0),        # x - 1 and x on even
                'hex5':        (-1, -1),        # rows.
            },
            'hex-odd': {
                'hex0':         (1, -1),
                'hex1':         (1,  0),        # x and x + 1 on odd
                'hex2':         (1,  1),        # rows.
                'hex3':         (0,  1),
                'hex4':        (-1,  0),
                'hex5':         (0, -1),
            }
        }
        self.direction_keys = {
            'hex': ['hex0', 'hex1', 'hex2', 'hex3', 'hex4', 'hex5'],
            'square': ['up', 'NE', 'right', 'SE', 'down', 'SW', 'left', 'NW'],
        }
        self.specials = {
            0:          'zero',
            None:       'free',
            'F':        'flag',
            'X':        'mine',
        }
        # Initialize...
        self.gametype = gametype
        self.window_start = [0, 0]      # Item assignment
        self.cursor = (0, 0)
        self.attention_mode = False
        # Initialize curses.
        self.window = curses.initscr()
        curses.cbreak()
        curses.noecho()
        curses.meta(1)
        self.window.keypad(True)
        try:
            self.old_cursor = curses.curs_set(0)
        except:
            pass
        curses.def_prog_mode()  # BUG: see comments above __init__
        # Check that we have a reasonable size on the window.
        height, width = self.window.getmaxyx()
        
        def toosmall():
            self.leave()
            sys.stdout.flush()
            output(sys.stderr,'\nSCREEN TOO SMALL\n')
            sys.stderr.flush()
            sys.exit(1)
        
        if self.gametype == 'hex' and (width < 10 or height < 8):
            toosmall()
        if self.gametype != 'hex' and (width < 7 or height < 4):
            toosmall()
        
        # Read the configuration.
        self.cfg = eval(open(cfgfile).read())
        # Apply ord() automatically to the keys in 'curses-input'.
        for key in self.cfg['curses-input']:
            for index in range(len(self.cfg['curses-input'][key])):
                value = self.cfg['curses-input'][key][index]
                if isinstance(value, str):
                    self.cfg['curses-input'][key][index] = ord(value)
        # Initialize the color pairs.
        self.color_pairs = []
        if curses.has_colors():
            self.use_color = True
            # TODO: Check that enough pairs are available.
            curses.start_color()
            for key in self.cfg['curses-output']:
                value = self.cfg['curses-output'][key]
                ch, foreground, background, attr = value
                # Only add new pairs.
                if (foreground, background) not in self.color_pairs:
                    self.color_pairs.append((foreground, background))
                    curses.init_pair(
                        len(self.color_pairs),
                        eval('curses.COLOR_' + foreground),
                        eval('curses.COLOR_' + background)
                    )
        else:
            self.use_color = False
        # Initialize mouse
        mask = curses.REPORT_MOUSE_POSITION|curses.ALL_MOUSE_EVENTS
        self.old_mousemask = curses.mousemask(mask)
        curses.mouseinterval(self.cfg['curses-mouse-input']['interval'])
    
    def leave(self):
        '''Leave curses mode.'''
        curses.nocbreak()
        curses.echo()
        self.window.keypad(False)
        try:
            curses.curs_set(self.old_cursor)
        except:
            pass
        curses.endwin()
    
    def curses_output_cfg(self, key):
        '''Retrieve textics directive from cursescfg.
        
        char, attributes = self.curses_output_cfg(key)
        
        `key` is the property in cursescfg ('curses-output').
        `char` is a character and needs to be converted before passed
            to a curses function.
        `attributes` is an integer to be passed directly to a curses
            function.  Color is or'ed in.
        
        Retrieve a textics directive from the configuration file
        (cursescfg).  This function is responsible to choose the
        key with the correct property and best available mode.
        
        Raises KeyError if the entry can't be found.
        
        gametype        Best available mode     2nd best        worst
        'moore':        ':moore'                ':square'       ''
        'hex':          ':hex'                  ''
        'neumann'       ':neumann'              ':square'       ''
        
        This function will automatically convert the directive line
        into two directly useful parts:
            `char`:             The character to be printed or `None`.
            `attributes`:       The attributes to be used (curses).
                                The color pair is also or'ed in.
        
        See also: the configuration file.
        '''
        cfg = self.cfg['curses-output']
        # Choose gametype specific entries if available
        if self.gametype == 'neumann':
            if key + ':neumann' in cfg:
                key += ':neumann'
            elif key + ':square' in cfg:
                key += ':square'
        elif self.gametype == 'hex':
            if key + ':hex' in cfg:
                key += ':hex'
        elif self.gametype == 'moore':
            if key + ':moore' in cfg:
                key += ':moore'
            elif key + ':square' in cfg:
                key += ':square'
        # Translate the key into (char, attributes)
        char, foreground, background, attributes = cfg[key]
        if self.use_color:
            attributes |= curses.color_pair(
                self.color_pairs.index((foreground, background)) + 1
            )
        return char, attributes
    
    def message(self, msg):
        '''Print `msg` at the bottom of the screen while in curses mode.
        
        Invokes `self.window.refresh`.
        Used for printing the initialization message and by
        `self.anykey_cont`.
        '''
        height, width = self.window.getmaxyx()
        ign, attributes = self.curses_output_cfg('text')
        text_width = width - 4  # Pretty margin on the left.
        lines = len(msg)//text_width + 1
        if lines <= height:
            for line in range(lines):
                self.window.addstr(
                    height - lines + line, 3,
                    msg[line*text_width:(line+1)*text_width],
                    attributes
                )
        else:
            pass        # A screen this small? Seriously?
        self.window.refresh()
    
    def anykey_cont(self):
        '''Press any key to continue...
        
        Wait for input from the user, discard the input.
        
        (This method is called by `engine.play_game`.)
        '''
        self.message('Press the "any" key to continue...')
        self.window.getch()

    def output(self, engine):
        '''This method is called by `engine.play_game`.
        
        It erases the window, prints the flags left message if it would
        fit on the screen, invokes the appropriate field printer and
        refreshes the screen. (In that order.)
        '''
        
        # TODO: The background gets set ridiculously often.
        # Set the appropriate background.
        char, attributes = self.curses_output_cfg('background')
        self.window.bkgdset(32, attributes)     # 32 instead of `char`.
        # BUG: window.bkgdset causes a nasty issue when the background
        # character is not ' ' and color is unavailable.
        
        # Print the screen.
        self.window.erase()
        # Screen could resized at any time.
        self.height, self.width = self.window.getmaxyx()
        
        chunks = []
        if engine.game_status == 'pre-game':
            chunks.append('Choose your starting point.')
        
        if engine.game_status == 'play-game':
            chunks.append("Flags left: {0}".format(engine.field.flags_left))
        
        msg = '  '.join(chunks)
        if len(msg) + 4 <= self.width:
            ign, attributes = self.curses_output_cfg('text')
            self.window.addstr(self.height - 1, 3, msg, attributes)
        # (Keeping the following outside the loop magically solves a resizing
        # bug that traces back to an `addch` in `self.print_char`.)
        # Lie to the field printer functions to preserve the text.
        self.height -= 1
        
        # Print the field.
        if self.gametype == 'hex':
            self.print_hex(engine.field)
        else:
            self.print_square(engine.field)
        # Remember that self.height has already been decremented by one.
        self.window.move(self.height, 0)  # BUG: see comments above __init__
        self.window.refresh()

    def input(self, engine):
        '''This method is called by `engine.play_game`.
        
        It receives a character from the user and interprets it.
        Invokes `self.travel` for the steering of the cursor.
        
        It doesn't do any output except for printing the field
        initialization message, and forcing the entire screen to be
        redrawn on unrecognised input (to de-fuck-up the screen).
        '''
        if self.gametype == 'hex':
            direction_keys = self.direction_keys['hex']
        else:
            direction_keys = self.direction_keys['square']
        look_for = ['reveal','flag','toggle-attention','quit']+direction_keys
        # Receive input from player.
        ch = self.window.getch()
        # Interpret.
        command = None
        if ch == curses.KEY_MOUSE:
            _, x, y, _, buttons = curses.getmouse()
            valid = True
            if self.gametype == 'hex':
                valid = self.mouse_travel_hex(x, y, engine.field)
            else:
                valid = self.mouse_travel_square(x, y, engine.field)
            if valid:
                for tmp_command in ('flag', 'reveal'):
                    for mask in self.cfg['curses-mouse-input'][tmp_command]:
                        if buttons & mask:
                            command = tmp_command
                    else:
                        continue
                    break
        else:
            # Keyboard input:
            for key in look_for:
                if ch in self.cfg['curses-input'][key]:
                    command = key
        # Act.
        if command == 'flag':
            engine.flag(self.cursor)
        elif command == 'reveal':
            pre_game = engine.game_status == 'pre-game'
            if pre_game:
                self.message('Initializing field...   This may take a while.')
                if self.curses_voodoo:
                    curses.reset_shell_mode() #BUG: see comments above __init__
            engine.reveal(self.cursor)
            if pre_game:
                if self.curses_voodoo:
                    curses.reset_prog_mode()  #BUG: see comments above __init__
                # Clear junk that gets on the screen from impatient players.
                self.window.redrawwin()
        elif command in direction_keys:
            self.travel(engine.field, command)
        elif command == 'toggle-attention':
            self.attention_mode = not self.attention_mode
        elif command == 'quit':     # Needed on Windows
            raise KeyboardInterrupt
        elif ch != curses.KEY_MOUSE:
            # Don't do this all the time, that'd be a little wasteful.
            self.window.redrawwin()
    
    def travel(self, field, direction):
        '''Move the cursor in the specified direction.
        
        It will not move past an edge (or in an otherwise impossible
        direction).  This is why the `field` argument is required.
        
        Valid directions when self.gametype == 'moore':
            'up', 'NE', 'right', 'SE', 'down', 'SW', 'left', 'NW'
        Valid directions when self.gametype == 'hex':
            'hex0', 'hex1', 'hex2', 'hex3', 'hex4', 'hex5'
        Valid directions when self.gametype == 'neumann':
            'up', 'right', 'down', 'left'
        
        The hexagonal directions are:
             5 0
            4   1
             3 2
        '''
        x, y = self.cursor
        # Find the appropriate dictionary of direction to DELTA-x and DELTA-y.
        if self.gametype != 'hex':
            key = 'square'
        elif y % 2:
            key = 'hex-odd'
        else:
            key = 'hex-even'
        
        # Move in the specified direction.
        x_diff, y_diff = self.travel_diffs[key][direction]
        new = x + x_diff, y + y_diff
        # Do nothing if it is impossible to move in the specified direction.
        x, y = new
        if x >= 0 and x < field.dimensions[0]:
            if y >= 0 and y < field.dimensions[1]:
                self.cursor = new
    
    def move_visible_area(self, virtual_x, virtual_y, x_border, y_border):
        '''Move the area that will be printed by `self.print_char`.
        
        Move the visible area (as printed by `self.print_char`) by
        modifying `self.window_start`, which is used for translating
        virtual coordinates (a step between field coordinates and
        screen coordinates.)
        
        `virtual_x` and `virtual_y` is the virtual coordinate.
        `x_border` is the minimal allowed border between the virtual
        coordinate and the left or the right side of the screen.
        `y_border` is the minimal allowed border between the virtual
        coordinate and the top or the bottom of the screen.
        '''
        real_x = virtual_x - self.window_start[0]
        real_y = virtual_y - self.window_start[1]
        if real_x + x_border > self.width - 1:
            self.window_start[0] = virtual_x - self.width + x_border + 1
        if real_x - x_border < 0:
            self.window_start[0] = virtual_x - x_border
        if real_y + y_border > self.height - 1:
            self.window_start[1] = virtual_y - self.height + y_border + 1
        if real_y - y_border < 0:
            self.window_start[1] = virtual_y - y_border
    
    def print_char(self, x, y, cfg, char=None):
        '''Print a character at a virtual coordinate with the right attributes.
        
        Print a character at the virtual coordinate (`x`, `y`)
        using the textics directive `cfg`.
        
        `char` is used to override the default character of the
        textics directive.
        '''
        real_x = x - self.window_start[0]
        real_y = y - self.window_start[1]
        # Verify that the coordinate is printable.
        if 0 <= real_x < self.width:
            if 0 <= real_y < self.height:
                cfg_char, attributes = self.curses_output_cfg(cfg)
                # curses_output_cfg may raise KeyError
                if char is None:
                    char = cfg_char
                self.window.addstr(real_y, real_x, char, attributes)
    
    def print_digit(self, x, y, digit):
        '''Print a digit at a virtual coordinate.
        
        Introduced in 0.4.9 to allow digits to have different colors.
        '''
        try:
            self.print_char(x, y, str(digit))
        except KeyError:
            self.print_char(x, y, 'number', str(digit))
    
    def print_cell(self, x, y, field, cell):
        '''
        `x` and `y` is the virtual coordinate for the single character
        to be printed.
        
        `cell` is the cell from the field.
        
        Introduced in 0.4.15 to reduce code duplication and apply the
        attention mode to numbers with too many mines around them.
        '''
        value = field.get(cell)
        if value not in self.specials:
            if self.attention_mode:
                flags = 0
                for neighour in field.get_neighbours(cell):
                    if field.get(neighour) == 'F':
                        flags += 1
                if flags > value:
                    self.print_char(x, y, 'attention', str(value))
                    return
            self.print_digit(x, y, value)
        else:
            if value is None and self.attention_mode:
                self.print_char(x, y, 'attention')
            else:
                self.print_char(x, y, self.specials[value])
    
    def print_square(self, field):
        '''Helper function for `self.output` for non-hexagonal gametypes.
        
        Print a non-hexagonal field in the area
        0 to self.width-1 by 0 to self.height-2.
        
        Also prints the "cursor".
        It does not print the flags left text.
        
        It will invoke `self.move_visible_area` to keep the "cursor" on
        the screen.  It will use `self.print_char` to print characters
        on the screen.
           _______
          | X X X |
          | X(*)X |
          | X X X |
           -------
        '''
        # Move the visible area.
        # Compute the virtual locations on the screen and real locations.
        # Adjust the virtual coordinate of the visible area.
        #
        # Border = 1 cell.
        x, y = self.cursor
        self.move_visible_area(2*x+1, y, 3, 1)
        
        # Print all cells in a field.
        for cell in field.all_cells():
            x, y = cell
            # Print blank grid .
            self.print_char(2*x, y, 'grid', ' ')
            self.print_char(2*x+2, y, 'grid', ' ')
            # Print the actual cell.
            self.print_cell(2*x+1, y, field, cell)
        # Print the "cursor".
        x, y = self.cursor
        self.print_char(2*x, y, 'cursor-l')
        self.print_char(2*x+2, y, 'cursor-r')
    
    def mouse_travel_square(self, x, y, field):
        '''
        '''
        x += self.window_start[0]
        y += self.window_start[1]
        # Inverse transformation of x and y.
        if not x % 2:
            return False
        x = (x-1) // 2
        # Travel
        if 0 <= x < field.dimensions[0] and 0 <= y < field.dimensions[1]:
            self.cursor = (x, y)
            return True
        else:
            return False

    def print_hex(self, field):
        r'''Helper function for `self.output` for the hexagonal gametype.
        
        Print a hexagonal field in the area
        0 to self.width-1 by 0 to self.height-2.
        
        Also prints the "cursor".
        It does not print the flags left text.
        
        It will invoke `self.move_visible_area` to keep the "cursor" on
        the screen.  It will use `self.print_char` to print characters
        on the screen.
        
            0000000000111111111122222222223
            0123456789012345678901234567890
        00   / \ / \ / \ / \ / \ / \ / \
        01  | X | X | X | X | X | X | X |
        02   \ / \ / \ / \ / \ / \ / \ / \
        03    | X | X | X | X | X | X | X |
        04   / \ / \ / \ / \ / \ / \ / \ /
        05  | X | X | X |(X)| X | X | X |
        06   \ / \ / \ / \ / \ / \ / \ / \
        07    | X | X | X | X | X | X | X |
        08     \ / \ / \ / \ / \ / \ / \ /
        '''
        # Define functions that translates field coordinates into
        # virtual screen coordinates.
        def fx(x, y): return 2 * (2*x + 1 + (y % 2))
        
        def fy(x, y): return 2*y + 1
        
        # Move the visible area.
        #
        # Compute the virtual locations on the screen and real locations.
        # Adjust the virtual coordinate of the visible area.
        # Border = 1 cell.
        x, y = self.cursor
        self.move_visible_area(fx(x, y), fy(x, y), 6, 3)
        
        # Print all cells in a field.
        for cell in field.all_cells():
            x = 2 * (2*cell[0] + 1 + (cell[1] % 2))
            y = 2*cell[1] + 1
            
            # Print blank grid.
            # Roof:
            self.print_char(x - 1, y - 1, 'grid', '/')
            self.print_char(x, y - 1, 'grid', ' ')
            self.print_char(x + 1, y - 1, 'grid', '\\')
            # Left wall:
            self.print_char(x - 2, y, 'grid', '|')
            self.print_char(x - 1, y, 'grid', ' ')
            # Right wall:
            self.print_char(x + 2, y, 'grid', '|')
            self.print_char(x + 1, y, 'grid', ' ')
            # Floor:
            self.print_char(x - 1, y + 1, 'grid', '\\')
            self.print_char(x, y + 1, 'grid', ' ')
            self.print_char(x + 1, y + 1, 'grid', '/')
            # Print the actual cell.
            self.print_cell(x, y, field, cell)
        
        # Print the "cursor".
        x, y = self.cursor
        self.print_char(fx(x, y) - 1, fy(x, y), 'cursor-l')
        self.print_char(fx(x, y) + 1, fy(x, y), 'cursor-r')
    
    def mouse_travel_hex(self, x, y, field):
        '''
        '''
        x += self.window_start[0]
        y += self.window_start[1]
        # Inverse transformation of x and y.
        if x % 4 == 2 and y % 4 == 0 or x % 4 == 0 and y % 4 == 2:
            y += 1              # Right above the target
        if x % 4 == 2 and y % 4 == 2 or x % 4 == 0 and y % 4 == 0:
            y -= 1              # Right below the target
        if not y % 2:
            return False        # Misc place on horizontal border
        if y % 4 == 3:          # Unpush the pushed rows.
            x -= 2
        if not x % 4:           # Vertical border
            return False
        y = y // 2
        x = x // 4
        # Travel
        if 0 <= x < field.dimensions[0] and 0 <= y < field.dimensions[1]:
            self.cursor = (x, y)
            return True
        else:
            return False


def output(stream, content):
    '''
    Due to a bug syscalls may fail with EINTR after leaving curses mode.
    
    Write `content` to `stream` and flush() without crashing.
    
    Example:
    output(sys.stdout, 'Hello world!\n')
    
    
    The bug
    =======
    
        sys.stdin.readline() in `ask` dies with IOError and
        errno=EINTR when the terminal gets resized after curses has
        been de-initialized.
        1: SIGWINCH is sent by the terminal when the screen has been
            resized.
        2: curses forgot to restore the signal handling of SIGWINCH
            to the default of ignoring the signal.
            NOTE: signal.getsignal(signal.SIGWINCH) incorrectly
                returns signal.SIG_DFL. (Default is to be ignored.)
        3: Python fails to handle EINTR when reading from stdin.
    REFERENCES:
        Issue 3949: https://bugs.python.org/issue3949
        PEP 0457: https://www.python.org/dev/peps/pep-0475/
    SIMULATION:
        Function `bug1` in 'test.py'.
    FIX #1 (caused new bug: Can't resize on later games/SIGWICH not reset):
        Set signal handling of SIGWINCH to ignore.
        SIGWINCH:       Fixed by the solution.
        SIGINT:         Properly handled by Python. (Well tested.)
        SIGTSTP:        Default is STOP, seems to be at default.
        Any other signal will probably not be caught and
        IOError with errno=EINTR will therefore never be returned.
    FIX #2 (0.2.17)
        Accept that `IOError`s and `InterrputedError`s may be raised
        by IO functions.
    '''
    def write():
        stream.write(content)
    def flush():
        stream.flush()
    for function in (write, flush):
        i = 0
        while True:
            i += 1
            try:
                function()
            except InterruptedError:
                if i > 10**7:
                    raise
                continue
            except IOError as e:
                if 'EINTR' in dir(errno):
                    if i > 10**7:
                        raise
                    if e.errno == errno.EINTR:
                        continue
                raise
            break


def convert_param(paramtype, s):
    '''Convert user input (potentially incorrect text) to the proper type.
    
    Convert the string `s` to the proper type.
    Raises ValueError if `s` cannot be converted.
    
    `paramtype` MUST be one of the recognised values:
    
        'str':          `s` is returned.
        
        'yesno':        "Yes" is True and "no" is False.
        
        'dimension':    An integer >= 4
        
        'minecount':    Two modes (automatic selection):
                            An integer >= 1 returned as an integer.
                            Or a percentage `str(float)+'%'` in
                            ]0%, 100%[ returned as a float:
        
        'gametype':     Mapping with case-insensitive keys and
                        lower-case values:
                            'a', 'neumann' and '4' to 'neumann'
                            'b', 'hex', 'hexagonal' and '6' to 'hex'
                            'c', 'moore' and '8' to 'moore'
        
        'reverse-minecount':    `s` is an integer or a float and the
                                returned value is a string that can be
                                converted back to `s` with 'minecount'.
    '''
    if paramtype == 'str':
        return s
    elif paramtype == 'yesno':
        if s.upper() in ('Y', 'YES'):
            return True
        elif s.upper() in ('N', 'NO'):
            return False
        else:
            output(sys.stderr,'"Yes" or "no" please. (WITHOUT quotes.)\n')
            raise ValueError
    elif paramtype == 'dimension':
        try:
            value = int(s)
        except ValueError:
            # Easter egg.
            #
            # ~85.6% of English words contain 'a', 'c', 'm' or 'p'.
            # All numbers under one thousand belongs to the ~14.4%.
            #
            # 194 of the numbers between 0 and 200 contain one or more of
            # the letters 'n', 'f' and 'h'.
            #
            # But zero, two, six and twelve aren't included.
            # So check for X and startswith('TW').
            #
            # Some special words may appear too, so let's remove them.
            s = s.lower()
            for word in ['and', 'percent', 'point', 'comma', 'decimal']:
                s = s.replace(word, '')
            S = s.upper()
            if (
                'A' not in S and 'C' not in S and 'M' not in S and
                'P' not in S and ('N' in S or 'F' in S or 'H' in S
                or 'X' in S or S.startswith('TW'))
            ):
                output(sys.stderr, "Use digits.\n")
            else:
                output(sys.stderr,
                    'Invalid width or height;'
                    ' "{0}" is not an integer.\n'.format(s)
                )
            raise ValueError
        if value < 4:
            output(sys.stderr, 'Lowest allowed width or height is 4.\n')
            raise ValueError
        return value
    elif paramtype == 'minecount':
        if len(s) == 0:
            output(sys.stderr, 'No (empty) amount of mines specified.\n')
            raise ValueError
        if s[-1] == '%':
            try:
                value = float(s[:-1])/100
            except ValueError:
                output(sys.stderr,
                    "You can't have {0} percent of the cells to be mines;"
                    " {0} is not a number.\n".format(s)
                )
                raise ValueError
            if value >= 1.0 or value <= 0.0:
                output(sys.stderr,
                    'Percentage of the cells that will be mines'
                    ' must be in ]0%, 100%[.\n'
                )
                raise ValueError
        else:
            try:
                value = int(s)
            except ValueError:
                output(sys.stderr,
                    "You can't have {0} mines;"
                    " {0} is not an integer\n".format(s)
                )
                raise ValueError
            if value <= 0:
                output(sys.stderr,'You must have at least ONE mine.\n')
                raise ValueError
        return value
    elif paramtype == 'gametype':
        if s.upper() in ('A', 'NEUMANN', '4'):
            return 'neumann'
        elif s.upper() in ('B', 'HEX', 'HEXAGONAL', '6'):
            return 'hex'
        elif s.upper() in ('C', 'MOORE', '8'):
            return 'moore'
        else:
            output(sys.stderr,'Invalid gametype. TODO: explain\n')
            raise ValueError
    elif paramtype == 'reverse-minecount':
        if isinstance(s, float):
            return '{0}%'.format(100 * s)
        else:
            return str(s)
    else:
        while True:
            invalid_paramtype = True


def ask(question, paramtype, default):
    '''Ask the user a question in line mode. (Not curses mode.)
    
    Ask the user a question (line mode; not curses mode) and return the
    answer after it has been converted.
    
    It will invoke `convert_param` to convert the string into the
    proper type and check that the user didn't say something stupid.
    
    `default` is what will be sent to `convert_param` if the user
    hits enter.
    
    `paramtype` will be sent to `convert_param`.  See the doc-string
    for `convert_param` to know what values of `paramtype` are permitted.
    
    NOTICE: This function will cause the program to exit if a
    KeyboardInterrupt is raised.
    '''
    while True:
        output(sys.stdout, '{0} [{1}]: '.format(question, default))
        try:
            # Due to a bug, syscalls may fail with EINTR after leaving
            # curses mode. See the docstring of `output` for info about
            # the bug.
            i = 0
            while True:
                i += 1
                try:
                    answer = sys.stdin.readline().strip()
                except InterruptedError:
                    if i > 10*7:
                        raise
                    continue
                except IOError as e:
                    if 'EINTR' in dir(errno):
                        if i > 10*7:
                            raise
                        if e.errno == errno.EINTR:
                            continue
                    raise
                break
            if not answer:
                answer = default
            value = convert_param(paramtype, answer)
        except ValueError:
            continue
        except KeyboardInterrupt:
            output(sys.stdout,'\n')
            sys.exit(0)
        return value


def arg_input(default):
    '''Get configuration filepaths and game parameters from `sys.argv`.
    
    user_input_required, params = arg_input(default)
    
    This function will retrieve the game parameters, and paths to the
    configuration files, from `sys.argv`.  If `sys.argv` contains no
    game parameters, `user_input` will be True.
    
    `default` is a dictionary that MUST contain these keys:
    'width', 'height', 'mines', 'gametype', 'guessless' and 'insult'.
    Their types are specified in the doc-string for `play_game`.
    
    `params` is a dictionary that contains either all of the keys that
    are required for `default`, or none of them.  It may also contain
    'enginecfg' and/or 'cursescfg' for specifying configuration files
    that are not in the ordinary search path.
    
    The program will exit if bogus parameters are given.
    
    NOTICE: If argparse couldn't be imported, this function will exit
    the program if there are any command line arguments.  If there
    aren't, it will return `True, {}`.
    '''
    # argparse is new in Python 2.7. Allow this to be run by the obsolete 2.6.
    try:
        dir(argparse)
    except NameError:
        if len(sys.argv) == 1:
            return True, {}
        else:
            output(sys.stderr,'Cannot parse the arguments without argparse!\n')
            sys.exit(1)
    # argparse exists:
    default_s = {
        True: ' (Default)',
        False: ' (Not default)'
    }
    # Get the arguments sent on the command line.
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='''
{0} is a curses mode minesweeper that checks if the field can be solved
without guessing and supports three different game types:
    Traditional; Moore neighbourhoods; 8 neighbours {1}
    Hexagonal; 6 neighbours {2}
    von Neumann neighbourhoods; 4 neighbours {3}
{4}
        '''.format(
          GAME_NAME,
          default_s[default['gametype'] == 'moore'],
          default_s[default['gametype'] == 'hex'],
          default_s[default['gametype'] == 'neumann'],
          {
            True:   'By default, it will insult you for both winning and\n'
                    'losing a game that has been proven to be 100% winnable.',
            False:  'By default, it will not insult you for either winning '
                    'or losing.',
          }[default['insult']],
        )
    )
    # Configuration files.
    parser.add_argument(
        '-c', '--cursescfg', dest='cursescfg',
        help=(
            'The path to the configuration file for the key bindings '
            'and textics directives.\n'
            'Default is "~/.{0}/cursescfg" or "/etc/{0}/cursescfg".'.format(
                GAME_FILENAME
            )
        )
    )
    parser.add_argument(
        '-e', '--enginecfg', dest='enginecfg',
        help=(
            'The path to the configuration file for field '
            'initialization and misc. game engine functions.\n'
            'Default is "~/.{0}/enginecfg" or "/etc/{0}/enginecfg".'.format(
                GAME_FILENAME
            )
        )
    )
    # Dimensions and minecount.
    parser.add_argument(
        '-s', '--size', dest='size',
        help=(
            "The size of the field width+'x'+height.  Ex. 30x16\n"
            "Default is {0}x{1}.".format(
                default['width'], default['height']
            )
        )
    )
    parser.add_argument(
        '-m', '--mines', dest='mines',
        help=(
            "The number of mines. OR the percentage. Default is {0}.\n"
            "Creating solvable fields becomes exponentially slower\n"
            "somewhere around 20 to 25 percent.".format(
                convert_param(
                    'reverse-minecount',
                    default['mines']
                ).replace('%', '%%')
            )
        )
    )
    # Gametype
    gametype = parser.add_mutually_exclusive_group()
    gametype.add_argument(
        '-4', '--neumann',
        action='store_const', dest='gametype', const='neumann',
        help=(
            "Use von Neumann neighbourhoods. (4 neighbours.)" +
            default_s[
                default['gametype'] == 'neumann'
            ]
        )
    )
    gametype.add_argument(
        '-6', '--hex', '--hexagonal',
        action='store_const', dest='gametype', const='hex',
        help=(
            "Use a hexagonal field. (6 neighbours.)" +
            default_s[
                default['gametype'] == 'hex'
            ]
        )
    )
    gametype.add_argument(
        '-8', '--moore', '--traditional',
        action='store_const', dest='gametype', const='moore',
        help=(
            "Traditional minesweeper; Moore neighbourhoods. (8)" +
            default_s[
                default['gametype'] == 'moore'
            ]
        )
    )
    # Bools.
    guessless = parser.add_mutually_exclusive_group()
    guessless.add_argument(
        '-g', '--guessless', dest='guessless', action='store_true',
        help=(
            "Play a minesweeper that can be solved without guessing." +
            default_s[
                default['guessless']
            ]
        )
    )
    guessless.add_argument(
        '-G', '--no-guessless', dest='noguessless', action='store_true',
        help=(
            "Play with the risk of having to guess. " +
            "Large fields will be initialized much faster." + default_s[
                not default['guessless']
            ]
        )
    )
    insult = parser.add_mutually_exclusive_group()
    insult.add_argument(
        '-r', '--rude', dest='insult', action='store_true',
        help=(
            "<std>" + default_s[
                default['insult']
            ]
        )
    )
    insult.add_argument(
        '-n', '--nice', dest='noinsult', action='store_true',
        help=(
            "(more polite setting)" + default_s[
                not default['insult']
            ]
        )
    )
    #
    # Parse the args and store the params.
    args = parser.parse_args()
    params = {}
    user_input_required = True
    error = False
    # Size, mines and gametype.
    if args.size:
        user_input_required = False
        try:
            params['width'], params['height'] = map(
                lambda x: convert_param('dimension', x),
                args.size.split('x')
            )
        except ValueError:
            error = True
            output(sys.stderr,
                'Error with "--size": Explanation above.\n'
            )
        except:
            error = True
            output(sys.stderr,'Error with "--size": UNKNOWN\n')
            raise
    if args.mines:
        user_input_required = False
        try:
            params['mines'] = convert_param('minecount', args.mines)
        except ValueError:
            error = True
            output(sys.stderr,
                'Error with "--mines": Explanation above.\n'
            )
        except:
            error = True
            output(sys.stderr,'Error with "--mines": UNKNOWN\n')
            raise
    if args.gametype:
        user_input_required = False
        assert args.gametype in ('moore', 'hex', 'neumann')
        params['gametype'] = args.gametype
    # guessless, insult
    if args.guessless:
        user_input_required = False
        params['guessless'] = True
    if args.noguessless:
        user_input_required = False
        params['guessless'] = False
    if args.insult:
        user_input_required = False
        params['insult'] = True
    if args.noinsult:
        user_input_required = False
        params['insult'] = False
    # Configuration
    if args.cursescfg:
        params['cursescfg'] = args.cursescfg
    if args.enginecfg:
        params['enginecfg'] = args.enginecfg
    # Deal with error and user_input_required.
    if error:
        sys.exit(1)
    if not user_input_required:
        for key in default:
            if key not in params:
                params[key] = default[key]
    return user_input_required, params


def user_input(default, cursescfg_path):
    '''Retrieve game parameters from the user.
    
    `cursescfg_path` is the path to the configuration file that happens
    to contain the key bindings and their documentation, which might be
    displayed by this function.
    
    `default` is a dictionary that MUST contain these keys:
    'width', 'height', 'mines', 'gametype', 'guessless' and 'insult'.
    Their types are specified in the doc-string for `play_game`.
    
    `user_input` will return dictionary containing the same keys.
    '''
    parameters = {}
    booldefault = {True: 'Yes', False: 'No'}
    parameters['width'] = ask(
        'Width of the playing field',
        'dimension',
        default['width']
    )
    parameters['height'] = ask(
        'Height of the playing field',
        'dimension',
        default['height']
    )
    # MUST ask for dimensions before for the # of mines.
    parameters['mines'] = ask(
        'Mines: number or percent% (It gets very slow after 25-ish-%)',
        'minecount',
        convert_param('reverse-minecount', default['mines'])
    )
    parameters['gametype'] = ask(
        'A: Neumann, B: Hexagonal or C: Moore',
        'gametype',
        default['gametype']
    )
    parameters['guessless'] = ask(
        '100% solvable field (no guessing required)',
        'yesno',
        booldefault[default['guessless']]
    )
    # MUST ask for guessless mode before polite mode.
    if parameters['guessless']:
        parameters['insult'] = not ask(
            'Polite mode?',
            'yesno',
            booldefault[not default['guessless']]
        )
    # Ask if the user wants to know the key bindings.
    if ask('Show key bindings?', 'yesno', 'No'):
        cursescfg = eval(open(cursescfg_path).read())
        output(sys.stdout,cursescfg['pre-doc'])
        if parameters['gametype'] == 'hex':
            output(sys.stdout, cursescfg['doc-hex'])
        else:
            output(sys.stdout, cursescfg['doc-square'])
        output(sys.stdout,
            "\nPressing an unrecognised key will refresh the screen.\n"
            "^C (Ctrl-c) to quit a game or the game.\n\n"
        )
        ask('Press enter to continue...', 'str', '')
    return parameters

def highscores_add_entry(title, prompt):
    '''
    Input callback for `game_engine.hiscores.add_entry`.
    '''
    output(sys.stdout,title + '\n')
    while True:
        try:
            return ask(prompt, 'str', '')
        except UnicodeDecodeError:
            output(sys.stderr, 'Decoding error.\n')

def highscores_display(title, headers, rows, cfgfile):
    '''
    Output formatter function for `game_engine.hiscores.display`.
    '''
    # Settings:
    cfg = eval(open(cfgfile).read())
    hs_conf = cfg['highscores']
    # Create all rows to be displayed.
    header_underline = ['='*len(col) for col in headers]
    header_blankline = ['' for col in headers]
    all_rows = [headers] + [header_underline] + [header_blankline] + rows
    # Calculate column widths.
    column_width = []
    for column in zip(*all_rows):
        #column_width.append(max(list(map(len, column))) + 1)
        column_width.append(max(list(map(len, column))))
    # Print
    text = 'Arrow keys to scroll, "q" when done viewing highscores.\n'
    text += '\n' + '_'*len(title) + '\n'
    text += title + '\n\n'
    for row in all_rows:
        for index, width in enumerate(column_width):
            spacing = -(width) % hs_conf['tabsize']
            if spacing < hs_conf['min_tabspace']:
                spacing += hs_conf['tabsize']
            text += row[index]
            text += ' ' * (width - len(row[index]))
            text += ' ' * spacing
        text += '\n'
    encodings = [
        locale.getpreferredencoding(),
        'UTF-8',
    ]
    utext = text        # Needed for Python 3 if |less fails.
    for encoding in encodings:
        try:
            text = text.encode(encoding)
            break
        except UnicodeEncodeError:
            continue
    # Pipe to (less || more)
    try:
        os.environ['LESSSECURE'] = '1'          # LOL
        less = subprocess.Popen(
            ['less', '-S', '-#', str(hs_conf['less_step'])],
            stdin=subprocess.PIPE
        )
        less.communicate(text)
        less.wait()
    except:
        try:
            # more is only a shell builtin on Windows.
            more = subprocess.Popen('more', stdin=subprocess.PIPE, shell=True)
            more.communicate(text)
            more.wait()
        except:
            output(sys.stderr,
                'Failed to pipe to `less -S -"#" {}` and `more`!\n'.format(
                    hs_conf['less_step']
                )
            )
            if sys.version_info[0] == 3:
                output(sys.stdout, utext)
            else:
                output(sys.stdout, text)
    

def play_game(parameters):
    '''Play a custom game of minesweeper.
    
    When called with all required parameters,
    one game of minesweeper will be played.
    
    NOTICE: This function does not expect incorrect parameters!
    
    WARNING: If anything, except a KeyboardInterrupt, happens during an
        actual game, this function will raise an exception without
        leaving curses mode.
    
    `parameters` is a dictionary which MUST contain all these keys:
        'width'         Integer >= 4
        'height'        Integer >= 4
        'mines'         Integer >= 1 or float in ]0.0, 1.0[
        'gametype'      'moore', 'hex' or 'neumann'
        'guessless'     A boolean (no guessing required)
        'insult'        A boolean (!polite mode)
        'enginecfg'     The path to the configuration file for the
                        game engine.
        'cursescfg'     The path to the configuration file for key
                        bindings and textics customisation.
    '''
    if isinstance(parameters['mines'], float):
        area = parameters['width'] * parameters['height']
        mines = int(parameters['mines'] * area + 0.5)
        parameters['mines'] = mines
    # WORKAROUND for a special bug.
    if parameters['mines'] == 0:      # Test: 42
        parameters['mines'] == 1      # Test: 0
    # Don't blame the player when it's not the players fault.
    if not parameters['guessless']:
        parameters['insult'] = False
    
    engine = game_engine.game_engine(parameters['enginecfg'], **parameters)
    interface = curses_game(
        parameters['cursescfg'],
        parameters['gametype'],
    )
    try:
        win, highscores = engine.play_game(interface)
    except KeyboardInterrupt:
        interface.leave()
        return
    interface.leave()
    
    if parameters['insult']:
        if win:
            output(sys.stdout,
                '\n\n"Congratulations", you won the unlosable game.\n')
        else:
            output(sys.stdout,'\n\nYou moron, you lost the unlosable game!\n')
    ask('Press enter to continue...', 'str', '')
    highscores.add_entry(highscores_add_entry)
    title, headers, rows = highscores.display()
    highscores_display(title, headers, rows, parameters['cursescfg'])


def main():
    '''42
    
    Invoke `arg_input` to find configuration files with non-standard
    paths.
    
    Find the remaining configuration files.
    NOTICE: As of version 0.0.13, it does not check if the
    configuration file is valid, only if it exists.
    
    Invoke `user_input` if `arg_input` didn't return game parameters.
    
    Invoke `play_game`.
    
    Invoke `ask` in a while loop to ask the player if [s]he wants to
    continue play again. And while True, invoke `play_game`.
    
    
    WARNING: MAY raise an exception while in curses mode.
    '''
    default = {
        'width': 20,
        'height': 20,
        'mines': .2,
        'gametype': 'moore',
        'guessless': True,
        'insult': True,
    }
    
    interactive, parameters = arg_input(default)
    
    # Handle the configuration filepaths.
    cfgfiles = {
        'enginecfg': None,
        'cursescfg': None,
    }
    error = False
    for cfgfile in cfgfiles:
        if cfgfile in parameters:
            cfgfiles[cfgfile] = parameters[cfgfile]
        else:
            locations = (
                os.path.expanduser('~/.' + GAME_FILENAME + '/' + cfgfile),
                "MAKEFILE_CFGDIR" + '/' + cfgfile,
                '/etc/' + GAME_FILENAME + '/' + cfgfile,
                'windows-beta/' + cfgfile,
            )
            for location in locations:
                try:
                    open(location)
                    cfgfiles[cfgfile] = location
                    break
                except IOError:
                    pass
            else:
                output(sys.stderr,'{0} not found.\n'.format(cfgfile))
                error = True
    if error:
        sys.exit(1)
    
    if interactive:
        output(sys.stdout,GAME_CRAPTEXT)
        output(sys.stdout,
            'You can quit the game with the interrupt signal. (Ctrl + c)\n\n'
        )
        output(sys.stdout,
            'How do you want your game to be set up? Write in the values'
            ' and press Enter.\nLeave blank to use the default.\n\n'
        )
        parameters = user_input(default, cfgfiles['cursescfg'])
    
    parameters.update(cfgfiles)
    play_game(parameters)
    
    while ask('Play again?', 'yesno', 'Yes'):
        parameters = user_input(default, cfgfiles['cursescfg'])
        parameters.update(cfgfiles)
        play_game(parameters)

try:
    assert os.geteuid() or sys.platform.startswith('haiku'), "Gaming as root!"
except AttributeError:
    pass

if __name__ == '__main__':
    # Force InterruptedError to be defined
    try:
        InterruptedError
    except NameError:
        # Both are not going to be expected at the same time.
        InterruptedError = SystemExit
    try:
        main()
    except SystemExit as e:
        # Cause the interpreter to exit with the expected status.
        os._exit(e.code)
    except game_engine.security_alert as e:
        try:
            curses.endwin()
        except:
            pass
        output(sys.stderr,'Security alert: ' + str(e) + '\n')
        os._exit(1)
    except:
        # Get the traceback without fucking up the terminal.
        exception = sys.exc_info()
        try:
            curses.endwin()
        except:
            pass
        traceback.print_exception(*exception)
        os._exit(1)
    os._exit(0)
