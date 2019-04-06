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


'''This module provides the engine of Anonymine

Copyright (c) Oskar Skog, 2016-2019
Released under the FreeBSD license.

The engine of Anonymine
=======================

    The class `game_engine` contains the field, initializes it and
    manipulates it during a game.
    The documentation for `game_engine` will describe the coordinate
    system for the different field types, methods used to manipulate
    it, and the actual gluing of engine and interface.

'''


import os
import time
import signal
import errno
import sys
import getpass
import locale

try:
    import math
except:
    class mathclass(): # Just don't blow up on stupid platforms.
        def __init__(self): return None
        def ceil(self, x): return int(x)
    math = mathclass()


# Allow module names to be changed later.
import anonymine_solver as solver
import anonymine_fields as fields


class security_alert(Exception):
    pass


class hiscores():
    '''
    Manage highscores.
    
    The `play_game` method of `game_engine` will return a
    pre-configured `hiscores` object to the interface (its caller).
    
    The `add_entry` method will need to be called to add the recently
    played game to the list.  There is no need to check if the game
    was actually won, as `add_entry` is made a no-op on the returned
    `hiscores` object if the game was lost.
    
    
    File format
    -----------
    
        Each line represents an item in a list, the list items also
        specify in which list they are.
        
        The file does not support comments.
    
        line = <paramstring> ":" <delta_time> ":" <time> ":" <user> ":" <nick>
        
        `paramstring` identifies in which list the item is.
        
        `delta_time` is the time in seconds of how long it took to
        play.
        
        `time` is the Unix time when the `hiscores` instance was
        created.  (The time when the game was won.)
        Or if the `paramstring` is for a lost game: `time` is
        "{mines_left},{time}".
        
        `user` is the user name (login name) of the player.
        
        `nick` is a player chosen nickname.  `nick` is the only field
        that MAY contain a colon.  Other fields MUST NOT contain
        colons.
        
        Even if either `user` or `nick` is disabled in the
        configuration, their fields must still appear in the
        highscores file.  Disabling them only disables them from
        being reported by the `display` method and makes the
        `add_entry` method set their fields to an empty string.
    
    
    paramstring
    -----------
    
        The syntax that will be used for paramstrings should be
        documented somewhere and somehow.
        
        "{mines}@{width}x{height}-{gametype}" + ng*"+losable"
        
        <mines>"@"<width>"x"<height>"-"<gametype>["+losable"]
        
        And for a lost game, "lost/" is prepended to the paramstring, ie:
        
        "lost/"<mines>"@"<width>"x"<height>"-"<gametype>["+losable"]
    
    
    Unicode
    -------
    
        The highscores file is UTF-8 encoded.  The stings returned by
        the methods in this class are a combination of ASCII only `str`
        types on both Python versions, and Unicode strings (`unicode`
        or `str`).   Notice that the callback for `add_entry` MUST
        return an `str` instance on both Python versions.
        
    '''
    def __init__(self, cfg, paramstring, delta_time, mines_left=0):
        '''
        Create a `hiscores` object for the played game.
        This object is created by `game_engine.play_game` after
        the game has been won.
        
        If `delta_time` is None, the `add_entry` method is neutralized
        for both won and lost games.
        
        `paramstring` selects the sublist (game settings/parameters).
        
        `cfg` is a dictionary that MUST contain the following keys:
            - 'file'        string; Path to the highscores file
            - 'maxsize'     int; Maximum allowed filesize (bytes)
            - 'nick-maxlen' int; Maximum allowed length of nickname
                            (unicode code points)
            - 'entries'     int; Entries per sublist (paramstring)
            - 'use-user'    bool; List and display user/login names
            - 'use-nick'    bool; List and display nicknames
        
        `mines_left` (integer) is only used if the game was lost.
        
        If the game was lost, either set `delta_time` to None
        (to prevent someone from entering the winners' highscores),
        or prepend "lost/" to `paramstring`.  The latter option
        will add a record the losers' highscores.
        '''
        self.paramstring = paramstring
        if delta_time is None:
            self.delta_time = None
        else:
            self.delta_time = str(delta_time)
        self.win_time = str(time.time())
        self.mines_left = mines_left
        
        self.hiscorefile = cfg['file']
        self.maxsize = cfg['maxsize']
        self.n_entries = cfg['entries']
        self.use_user = cfg['use-user']
        self.use_nick = cfg['use-nick']
        self.nick_maxlen = cfg['nick-maxlen']
        
        # The caption that will be displayed by the callback sent to
        # `display`.  This caption can be changed by any method before
        # ending up on the screen.
        self.display_caption = 'Higscores for these settings'
        self.hiscores = None
    
    def _load(self):
        '''Load `self.hiscores` from `self.hiscorefile`.'''
        def line_to_entry(line):
            parts = line.split(':', 4)
            parts[0] = parts[0].replace('+nocount', '')
            return tuple(parts)
        try:
            f = open(self.hiscorefile, 'rb')
        except IOError as err:
            self.display_caption = 'IO error on read: ' + err.strerror
            self.hiscores = []
            return
        filecontent = f.read().decode('utf-8')
        lines = list(filter(None, filecontent.split('\n')))
        self.hiscores = list(map(line_to_entry, lines))
    
    def _store(self):
        '''Store `self.hiscores` to `self.hiscorefile`.'''
        content = ''
        for entry in self.hiscores:
            content += ':'.join(entry) + '\n'
        content = content.encode('utf-8')
        if len(content) <= self.maxsize:
            try:
                f = open(self.hiscorefile, 'wb')
            except IOError as err:
                self.display_caption = 'IO error on write: ' + err.strerror
                return
            f.write(content)
            f.close()
        else:
            self.display_caption = "New highscore's filesize too large"
    
    def _sort(self, sublist, game_lost):
        '''
        Sort a sublist.
        
        Function needed due to loser's highscores [0.3.1]
        '''
        if not game_lost:
            sublist.sort(key=lambda entry: float(entry[1]))
        else:
            times = {}
            for record in sublist:
                mines_left = int(record[1].split(',')[0])
                t = float(record[1].split(',')[1])
                if mines_left not in times:
                    times[mines_left] = t
                if times[mines_left] > t:
                    times[mines_left] = t
            def rank(record):
                mines_left = int(record[1].split(',')[0])
                t = float(record[1].split(',')[1])
                return t/times[mines_left] * mines_left
            sublist.sort(key=rank)
    
    def add_entry(self, inputfunction):
        '''Call this method to add yourself to the hiscores list.
        
        `inputfunction` is a callback to the interface.
        string = inputfunction(titlebar, prompt)
        
        string MUST be of the `str` type on both Python versions.
        '''
        def load_split_add(self_reference, new_entry):
            '''
            Load self_reference.hiscores and separates the sublist
            from it.  `new_entry` will be appended to the sublist.
            
            Returns the sorted and tail truncated sublist.
            self_reference.hiscores does not contain the sublist.
            '''
            self_reference._load()
            sublist = list(filter(
                lambda entry: entry[0] == self_reference.paramstring,
                self_reference.hiscores
            ))
            self.hiscores = list(filter(
                lambda entry: entry[0] != self_reference.paramstring,
                self_reference.hiscores
            ))
            # Add entry.
            sublist.append(new_entry)
            self._sort(sublist, self.paramstring.startswith('lost/'))
            sublist = sublist[:self_reference.n_entries]
            return sublist
        # Display only mode:
        if self.delta_time is None:
            return
        # Get login name
        if self.use_user:
            try:
                user = getpass.getuser()
            except:
                user = '(unknown)'
        else:
            user = ''
        user = user.replace('\\', '\\\\').replace(':', '\\x3a')
        # Prepare the new entry
        if self.paramstring.startswith('lost/'):
            delta_time = "{0},{1}".format(self.mines_left, self.delta_time)
        else:
            delta_time = self.delta_time
        new_entry = [
            self.paramstring,
            delta_time,
            self.win_time,
            user,
            '',
        ]
        assert '\n' not in ''.join(new_entry)
        # Get the nickname only if the player actually made it to the list.
        # The entry will actually be added twice, but only the latter will
        # be stored.
        try:
            position = load_split_add(self, new_entry).index(new_entry)
        except ValueError:
            position = None
            self.display_caption = "You didn't make it to the top {0}".format(
                self.n_entries
            )
        if position is not None:
            if self.use_nick:
                title = 'You made it to #{0}'.format(position + 1)
                while True:
                    nick = inputfunction(title, 'Nickname')
                    if sys.version_info[0] == 2:
                        # Don't try decoding using other charsets,
                        # it'll just blow up on output instead.
                        if sys.version_info[1] == 7:
                            nick = nick.decode(
                                locale.getpreferredencoding(), errors='ignore'
                            )
                        else:
                            nick = nick.decode(locale.getpreferredencoding())
                    if len(nick) > self.nick_maxlen:
                        title = 'No more than {0} characters allowed'.format(
                            self.nick_maxlen
                        )
                    else:
                        break
                new_entry[4] = nick
                # Load the list again (inputfunction may take a very long time)
                # and add the nickname to the entry.
                sublist = load_split_add(self, new_entry)
                # Write back
                self.hiscores.extend(sublist)
                self._store()
            # Position message.
            if new_entry in sublist:
                position = sublist.index(new_entry)
                self.display_caption = 'You made it to #{0}'.format(
                    position + 1
                )
            else:
                # Race condition
                self.display_caption = "Nearly made it!"
        if self.paramstring.startswith('lost/'):
            self.display_caption = "Losers' highscores"
    
    def display(self):
        '''
        self.display -> caption, headers, rows
        
        `caption` is a string.
        `headers` is a tuple of strings.
        `rows` is a list of tuples of strings.
        
        Explaining with pseudoHTML:
        <h1>caption</h1>
        <table>
            <tr><th>headers[0]</th>...<th>headers[c]</tr>
            <tr><td>rows[0][0]</td>...<td>rows[0][c]</tr>
            ...
            <tr><td>rows[r][0]</td>...<td>rows[r][c]</tr>
        </table>
        <!-- There are r-1 rows and c-1 columns -->
        '''
        
        def format_deltatime(t):
            def tfmt(format, t):
                return time.strftime(format, time.gmtime(t))
            if t <= 3559.999:
                t = math.ceil(t * 1000.0) / 1000.0
                subsec = int(math.ceil(t * 1000.0) % 1000)
                ds = str(int(subsec/100))
                cs = str(int(subsec/10%10))
                ms = str(int(subsec%10))
                return tfmt('%M:%S.', t) + ds + cs + ms
            elif t <= 86399:
                t = math.ceil(t)
                return tfmt('%H:%M:%S', t)
            elif t <= 863940:
                t = 60 * math.ceil(t / 60.0)
                return "{0}d {1}".format(int(t//86400), tfmt('%H:%M', t))
            else:
                return "A long time"
        
        def format_wontime(t):
            # Does not need to be precise, anything less than a week is good.
            if time.time() - t < 518400:
                s = time.strftime('%a %H:%M', time.localtime(t))
                if sys.version_info[0] == 3:
                    return s
                else:
                    encodings = [
                        locale.getpreferredencoding(),
                        'UTF-8',
                        'ISO-8859-1',   # Fallback
                    ]
                    for encoding in encodings:
                        try:
                            return s.decode(encoding)
                        except UnicodeDecodeError:
                            continue
            elif time.time() - t < 0:
                return '(Future)'
            else:
                return time.strftime('%Y-%m-%d', time.localtime(t))
        
        game_lost = self.paramstring.startswith('lost/')
        
        self._load()
        # Use only the relevant sublist.
        sublist = list(filter(
            lambda entry: entry[0] == self.paramstring,
            self.hiscores
        ))
        
        self._sort(sublist, game_lost)
        
        if game_lost:
            headers = ['Rank', 'Mines left', '/\\T time', 'Played']
        else:
            headers = ['Rank', '/\\T time', 'Won at']
        if self.use_user:
            headers.append('Login name')
        if self.use_nick:
            headers.append('Nickname')
        
        rows = []
        for index, entry in enumerate(sublist):
            if game_lost:
                row = [
                    '#' + str(index + 1),
                    str(int(entry[1].split(',')[0])),
                    format_deltatime(float(entry[1].split(',')[1])),
                    format_wontime(float(entry[2])),
            ]
            else:
                row = [
                    '#' + str(index + 1),
                    format_deltatime(float(entry[1])),
                    format_wontime(float(entry[2])),
                ]
            if self.use_user:
                row.append(entry[3])
            if self.use_nick:
                row.append(entry[4])
            rows.append(tuple(row))
        
        return self.display_caption, headers, rows


class game_engine():
    r'''
    This class creates game engine objects.
    
    This doc-string describes how the engine and the interface
    interacts.
    
    The engine:
        * Creates and initializes a field with the specified game
            parameters.
        * Has a play loop that will use the interface to do all IO.
        * Contains and manipulates the field object.
    
    The interface:
        * Makes a representation of the field for the player.
        * Contains IO methods that are used by the play loop.
        * Uses various important methods of the engine.
    
    
    (field-) Coordinates (non-hexagonal fields)
    ===========================================
    
        Each coordinate is a tuple of (x, y).
        Where x and y are integers and
            0 <= x < width
            0 <= y < height
        
        (0, 0)  (1, 0)  (2, 0)  (3, 0)  (4, 0)
        (0, 1)  (1, 1)  (2, 1)  (3, 1)  (4, 1)
        (0, 2)  (1, 2)  (2, 2)  (3, 2)  (4, 2)
        (0, 3)  (1, 3)  (2, 3)  (3, 3)  (4, 3)
        (0, 4)  (1, 4)  (2, 4)  (3, 4)  (4, 4)
        
        The Moore neighbours are
            (x-1, y-1)  (x, y-1)  (x+1, y-1)
            (x-1, y)              (x+1, y)
            (x-1, y+1)  (x, y+1)  (x+1, y+1)
        And the Neumann neighbours are:
                        (x, y-1)
            (x-1, y)              (x+1, y)
                        (x, y+1)
    
    
    (field-) Coordinates (hexagonal fields)
    =======================================
    
        Each coordinate is a tuple of (x, y).
        Where x and y are integers and
            0 <= x < width
            0 <= y < height
        
        What makes this different from square fields is that odd lines
        are indented (a half step) on the screen so that it looks like.
        
         / \ / \ / \ / \ / \ / \ / \
        |0,0|1,0|2,0|3,0|4,0|5,0|6,0|
         \ / \ / \ / \ / \ / \ / \ / \
          |0,1|1,1|2,1|3,1|4,1|5,1|6,1|
         / \ / \ / \ / \ / \ / \ / \ /
        |0,2|1,2|2,2|3,2|4,2|5,2|6,2|
         \ / \ / \ / \ / \ / \ / \ / \
          |0,3|1,3|2,3|3,3|4,3|5,3|6,3|
           \ / \ / \ / \ / \ / \ / \ /
        
        The neighbourhoods are similar to Moore neighbourhoods, but
        these have no "corners" on the right for even rows, and no
        "corners" on the left on odd rows
        
        The hexagonal neighbours are:
            (x - 1 + y%2,  y - 1)       (x + y%2,  y - 1)
            (x - 1,  y)                 (x + 1,  y)
            (x - 1 + y%2,  y + 1)       (x + y%2,  y + 1)
    
    
    Important parts of the engine object
    ====================================
    
        `engine.game_status` is a string that has the value:
            'pre-game'  when the field hasn't been initialized
                        (every cell is free).
            'play-game' while the game has been initialized but not
                        won or lost.
            (INTERNAL): 'game-won'
            (INTERNAL): 'game-lost'
        
        `engine.field` is the actual field object.  The interface will
            need to use the `get` method of the field.  A modifying
            method (of the field object) can safely be used AFTER
            initialization.
        
        `engine.flag(coordinate)` is a simple wrapper that flags free
            cells and unflags flagged cells.
        
        `engine.reveal(coordinate)` is a simple wrapper that reveals
            cells after initialization, OR initializes the field.
            (Let the player choose the starting point by playing.)
        
        `engine.init_field(startpoint)` is the method that will place
            the mines and reveals the starting point, from which the
            game CAN be won.
    
    
    Required methods of the interface object
    ========================================
    
        `interface.input(engine)`
            Receive input from the user and manipulate the field.
        
        `interface.output(engine)`
            "Show" the user a representation of the field.
            To do this, you are probably going to need to know how
            the coordinate system used by the field works.
        
        `interface.anykey_cont()`
            "Press any key to continue..."
            Let the user see the last screen before returning from
            `engine.play_game`.
            This method is actually not required.
    '''
    def __init__(self, cfgfile, **parameters):
        '''
        `cfgfile` is the path to the "enginecfg" configuration file.
        
        Recognised keyword arguments are:
            width=              # int >= 4
            height=             # int >= 4
            mines=              # int; Only integers are allowed here.
            gametype=           # str; 'moore', 'hex' or 'neumann'
            guessless=          # bool; Must be possible to solve without
                                #       guessing?
        
        As of version 0.0.20, no parameters are mandatory; they all
        have default values.  This may change in the future.
        '''
        # Define some constants.
        self.gametypes = ('moore', 'hex', 'neumann')
        
        # Handle parameters.
        default = {
            'width':     10,
            'height':    10,
            'mines':     10,
            'gametype':  'moore',
            'guessless': True,
        }
        for key in default:
            if key not in parameters:
                parameters[key] = default[key]
        assert parameters['gametype'] in ('neumann', 'hex', 'moore')
        
        self.cfg = eval(open(cfgfile).read())
        # Prevent DoS:
        area = parameters['width'] * parameters['height']
        if area > self.cfg['init-field']['sec-maxarea']:
            raise security_alert('Area too large, aborting')
        
        # Begin initialization.
        self.dimensions = (parameters['width'], parameters['height'])
        self.gametype = parameters['gametype']
        self.n_mines = parameters['mines']
        self.guessless = parameters['guessless']
        if self.gametype == 'hex':
            self.field = fields.hexagonal_field(
                parameters['width'],
                parameters['height'],
                True    # Flagcount
            )
        else:
            self.field = fields.generic_field(
                [parameters['width'], parameters['height']],
                self.gametype == 'moore',
                True    # Flagcount
            )
        
        self.game_status = 'pre-game' # play-game game-won game-lost
        
        self.solver = solver.solver()
        self.solver.field = self.field
    
    def init_field2(self, startpoint):
        '''(Internal use.)  Uses enginecfg.
        
        Uses multiple processes to test random fields to find a
        solvable one.  When a process finds a solvable field, it will
        store the coordinates of the mines in a tempfile which will
        then be read by the master process.
        
        enginecfg['init-field']
            'procs'     int: Number of slaves.
            'maxtime'   float: Start over after having tried one field
                        for this long.
            'filename'  string: tempfile, filename.format(x)
        '''
        def child():
            # The startpoint and its neighbours MUST NOT be mines.
            safe = self.field.get_neighbours(startpoint) + [startpoint]
            cells = list(filter(
                lambda x: x not in safe,
                self.field.all_cells()
            ))
            # Set up handler for kill signal.
            # Update 2016-07-15:  Processes will only be killed if their
            #   tempfiles can't be deleted (most likely because they don't
            #   exist yet);
            # Update 2018-11-07: Use SIGTERM instead of SIGCONT, the likelihood
            #   that new processes will spawn with the PID of a recently
            #   terminated is teeny-tiny.  Not crashing after having been
            #   stopped is far more valuable.
            def die(ignore1, ignore2):
                os._exit(0)
            signal.signal(signal.SIGTERM, die)
            # Solve
            solved = False
            while not solved:
                # Choose self.n_mines randomly selected mines.
                cells.sort(key=lambda x: os.urandom(1))
                mines = cells[:self.n_mines]
                self.field.clear()
                self.field.fill(mines)
                self.field.reveal(startpoint)
                solved = self.solver.solve()[0]
            # Store the mine coordinates in the tempfile.
            try:
                try:
                    f = open(filename.format(os.getpid()), 'wx')
                except ValueError:
                    try:
                        f = open(filename.format(os.getpid()), 'x')
                    except ValueError:
                        # WARNING WARNING
                        f = open(filename.format(os.getpid()), 'w')
            except:
                raise security_alert('Exploit attempt (tempfile)!')
            for x, y in mines:
                f.write('{0} {1}\n'.format(x, y))
            f.close()
        
        # FUNCTION STARTS HERE.
        # Clean up after whatever may have called us.
        self.field.clear()
        unix = 'fork' in dir(os)
        
        # Need to know tempfile name before creating children because
        # we're going to add 64 bits of entropy just in case exclusive
        # opening somehow would fail to stop a tempfile exploit.
        filename = self.cfg['init-field']['filename']
        for i in range(8):
            filename += '-'+str(ord(os.urandom(1)))
        
        # 1. Create slaves (unix)
        # 2. Set up alarm
        # 3. Fork error (not unix)
        # 4. Wait for slaves to finish (unix)
        # 5. Enter mine coordinates
        
        # 1: Create slaves.
        if unix:
            children = []
            for i in range(self.cfg['init-field']['procs']):
                try:
                    pid = os.fork()
                except:
                    # Do without fork if there are no children at all.
                    if not children:
                        unix = False
                    break
                if pid:
                    children.append(pid)
                else:
                    try:
                        child()
                        os._exit(0)
                    except KeyboardInterrupt:
                        # Kill the python interpreter on ^C.
                        os._exit(1)
        
        # 2: Security timeout raises Exception
        if 'alarm' in dir(signal):      # (unix only)
            def die(ignore1, ignore2):
                raise security_alert
            def stop_alarm():
                signal.signal(signal.SIGALRM, signal.SIG_IGN)
            signal.signal(signal.SIGALRM, die)
            signal.alarm(self.cfg['init-field']['sec-maxtime'])
        else:
            def stop_alarm():
                pass
        security_timeout = False
        
        # 3: Compatibility for non-unix systems, or on fork failure.
        if not unix:
            try:
                child()
                success_pid = os.getpid()
            except security_alert:
                security_timeout = True
            stop_alarm()
        
        # 4: Wait for the first child to finish.
        if unix:
            success_pid = 0
            try:
                while success_pid not in children:
                    while True:
                        try:
                            pid, status = os.wait()
                        except OSError as e:
                            if 'EINTR' in dir(errno):
                                if e.errno == errno.EINTR:
                                    continue
                            raise
                        except InterruptedError:
                            continue
                        break
                    if os.WIFEXITED(status):
                        success_pid = pid
            except security_alert:
                security_timeout = True
            stop_alarm()
            # Kill all remaining children.
            # Delete potential left-over tempfiles.
            for child in children:
                if child != success_pid:
                    try:
                        os.remove(filename.format(child))
                    except OSError:
                        # File does not exist, process has not finished.
                        try:
                            os.kill(child, signal.SIGTERM)
                            os.waitpid(child, 0)    # Destroy the zombie.
                            os.remove(filename.format(child))
                        except OSError:
                            pass
        
        # 5: Done soplving the field, enter the mine locations:
        if security_timeout:
            raise security_alert('Initialization took too long, aborted')
        # Parse the tempfile.
        self.field.clear()
        f = open(filename.format(success_pid))
        lines = f.read().split('\n')[:-1]
        f.close()
        os.remove(filename.format(success_pid))
        mines = []
        for line in lines:
            mine = list(map(int, line.split(' ')))
            mines.append(mine)
        # Fill the field with the mines.
        self.field.fill(mines)
        self.field.reveal(startpoint)
    
    def init_field(self, startpoint):
        '''Place the mines and reveal the starting point.
        
        Internal details:
            It will wrap in `init_field2` in guessless mode.
            It will place the mines by itself when not in guessless
            mode.
        '''
        if self.guessless:
            # Wrap in the best version.
            self.init_field2(startpoint)
        else:
            safe = self.field.get_neighbours(startpoint) + [startpoint]
            cells = list(filter(
                lambda x: x not in safe,
                self.field.all_cells()
            ))
            # Choose self.n_mines randomly selected mines.
            cells.sort(key=lambda x: os.urandom(1))
            mines = cells[:self.n_mines]
            self.field.clear()
            self.field.fill(mines)
            self.field.reveal(startpoint)
            
        def win(field, engine):
            engine.game_status = 'game-won'
            field.set_callback('win', None, None)
            field.set_callback('lose', None, None)
        def lose(field, engine):
            engine.game_status = 'game-lost'
            field.set_callback('win', None, None)
            field.set_callback('lose', None, None)
        self.field.set_callback('win', win, self)
        self.field.set_callback('lose', lose, self)
    
    def flag(self, coordinate):
        '''Automatic flag/unflag at `coordinate`.
        '''
        if self.field.get(coordinate) == 'F':
            self.field.unflag(coordinate)
        else:
            self.field.flag(coordinate)
    
    def reveal(self, coordinate):
        '''Automatic initialization/reveal at `coordinate`.
        '''
        if self.game_status == 'pre-game':
            # # Let the player choose the starting point.
            self.init_field(coordinate)
            self.start = time.time()
            self.game_status = 'play-game'
        elif self.game_status == 'play-game':
            self.field.reveal(coordinate)
        else:
            assert False, "game_status not in ('play-game', 'in-game')"
    
    def play_game(self, interface):
        '''bool_won, float_time_spent = play_game(interface)
        
        Attach the interface to the engine and play the game.
        
        See the doc-string for the class as a whole for (more)
        information.
        '''
        
        self.field.clear()
        # Enter the main loop.
        self.start = time.time()
        while self.game_status in ('pre-game', 'play-game'):
            interface.output(self)
            interface.input(self)
        # Won? Time?
        game_won = self.game_status == 'game-won'
        delta_time = time.time() - self.start
        # Show everything.
        if self.game_status == 'game-lost':
            # This takes a long time in some really weird configurations.
            # anonymine -m 1 -s 100x100
            for cell in self.field.all_cells():
                self.field.reveal(cell)
        interface.output(self)
        
        # Create a proper paramstring for the hiscores object.
        paramstring = '{0}{1}@{2}x{3}-{4}'.format(
            {True: "", False: "lost/"}[game_won],
            self.n_mines,
            self.dimensions[0],
            self.dimensions[1],
            self.gametype
        )
        if not self.guessless:
            paramstring += '+losable'
        mines_left = 0
        if not game_won:
            # Count the remaining mines. Flags != mines.
            for cell in self.field.all_cells():
                if self.field.get(cell) == 'X':
                    mines_left += 1
            # Somehow missed more than 20% of all mines??
            fail = float(mines_left - self.field.flags_left)/self.n_mines
            if fail > .20:
                mines_left = self.n_mines * 42
        hs = hiscores(self.cfg['hiscores'], paramstring, delta_time, mines_left)
        # NOTICE: This used to return game_won, delta_time
        
        # Do this last, so the player won't unfairly get a terrible time.
        try:
            interface.anykey_cont()         # ANY key
        except NameError:
            pass
        
        return game_won, hs


try:
    assert os.geteuid() or sys.platform.startswith('haiku'), "Gaming as root!"
except AttributeError:
    pass

assert __name__ != '__main__', "I'm not a script."

# Force InterruptedError to be defined.
try:
    InterruptedError
except NameError:
    InterruptedError = SystemExit
