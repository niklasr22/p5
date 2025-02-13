#
# Part of p5: A Python package based on Processing
# Copyright (C) 2017-2019 Abhik Pal
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import builtins
from collections import namedtuple
from enum import IntEnum

Position = namedtuple('Position', ['x', 'y'])

handler_names = ['key_pressed', 'key_released', 'key_typed',
                 'mouse_clicked', 'mouse_double_clicked',
                 'mouse_dragged', 'mouse_moved',
                 'mouse_pressed', 'mouse_released', 'mouse_wheel', ]


class VispyButton(IntEnum):
    LEFT = 1
    RIGHT = 2
    MIDDLE = 3


class MouseButton:
    """An abstraction over a set of mouse buttons.

    :param buttons: list of mouse buttons pressed at the same time.
    :type buttons: str list

    """

    def __init__(self, buttons):
        button_names = {
            VispyButton.LEFT: 'LEFT',
            VispyButton.RIGHT: 'RIGHT',
            VispyButton.MIDDLE: 'MIDDLE',
        }

        self._buttons = buttons
        self._button_names = [button_names[bt] for bt in self._buttons]

    @property
    def buttons(self):
        self._button_names

    def __eq__(self, other):
        button_map = {
            'CENTER': VispyButton.MIDDLE,
            'MIDDLE': VispyButton.MIDDLE,
            'LEFT': VispyButton.LEFT,
            'RIGHT': VispyButton.RIGHT,
        }
        if isinstance(other, str):
            return button_map.get(other.upper(), -1) in self._buttons
        return self._buttons == other._buttons

    def __neq__(self, other):
        return not (self == other)

    def __repr__(self):
        fstr = ', '.join(self.buttons)
        return "MouseButton({})".format(fstr)

    __str__ = __repr__


class Key:
    """A higher level abstraction over a single key.

    :param name: The name of the key; ENTER, BACKSPACE, etc.
    :type name: str

    :param text: The text associated with the given key. This
        corresponds to the symbol that will be "typed" by the given
        key.
    :type name: str

    """

    def __init__(self, name, text=''):
        self.name = name.upper()
        self.text = text

    def __eq__(self, other):
        if isinstance(other, str):
            return other == self.name or other == self.text
        return self.name == other.name and self.text == other.text

    def __neq__(self, other):
        return not (self == other)

    def __str__(self):
        if self.text.isalnum():
            return self.text
        else:
            return self.name

    def __repr__(self):
        return "Key({})".format(self.name)


class Event:
    """A generic sketch event.

    :param modifers: The set of modifiers held down at the time of the
        event.
    :type modifiers: str list

    :param pressed: If the key/button is held down when the event
        occurs.
    :type pressed: bool

    """

    def __init__(self, raw_event, active=False):
        self._modifiers = list(map(lambda k: k.name, raw_event.modifiers))
        self._active = active
        self._raw = raw_event

    @property
    def modifiers(self):
        return self._modifiers

    @property
    def pressed(self):
        return self._active

    def is_shift_down(self):
        """Was shift held down during the event?

        :returns: True if the shift-key was held down.
        :rtype: bool

        """
        return 'Shift' in self._modifiers

    def is_ctrl_down(self):
        """Was ctrl (command on Mac) held down during the event?

        :returns: True if the ctrl-key was held down.
        :rtype: bool

        """
        return 'Control' in self._modifiers

    def is_alt_down(self):
        """Was alt held down during the event?

        :returns: True if the alt-key was held down.
        :rtype: bool

        """
        return 'Alt' in self._modifiers

    def is_meta_down(self):
        """Was the meta key (windows/option key) held down?

        :returns: True if the meta-key was held down.
        :rtype: bool

        """
        return 'Meta' in self._modifiers

    def _update_builtins(self):
        pass


class KeyEvent(Event):
    """Encapsulates information about a key event.

    :param key: The key associated with this event.
    :type key: str

    :param pressed: Specifies whether the key is held down or not.
    :type pressed: bool

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self._raw.key is not None:
            self.key = Key(self._raw.key.name, self._raw.text)
        else:
            self.key = Key('UNKNOWN')

    def _update_builtins(self):
        builtins.key_is_pressed = self.pressed
        builtins.key = self.key if self.pressed else None


class MouseEvent(Event):
    """A class that encapsulates information about a mouse event.

    :param x: The x-position of the mouse in the window at the time of
        the event.
    :type x: int

    :param y: The y-position of the mouse in the window at the time of
        the event.
    :type y: int

    :param position: Position of the mouse in the window at the time
        of the event.
    :type position: (int, int)

    :param change: the change in the x and y directions (defaults to
        (0, 0))
    :type change: (int, int)

    :param scroll: the scroll amount in the x and y directions
         (defaults to (0, 0)).
    :type scroll: (int, int)

    :param count: amount by which the mouse whell was dragged.
    :type count: int

    :param button: Button information at the time of the event.
    :type button: MouseButton

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        x, y = self._raw.pos
        x = max(min(builtins.width, x), 0)
        y = max(min(builtins.height, builtins.height - y), 0)
        dx, dy = self._raw.delta
        
        self.x = max(min(builtins.width, x), 0)
        self.y = max(min(builtins.height, builtins.height - y), 0)

        self.position = Position(x, y)
        self.scroll = Position(int(dx), int(dy))

        self.count = self.scroll.y
        self.button = MouseButton(self._raw.buttons)

    def _update_builtins(self):
        builtins.pmouse_x = builtins.mouse_x
        builtins.pmouse_y = builtins.mouse_y
        builtins.mouse_x = self.x
        builtins.mouse_y = self.y
        builtins.mouse_is_pressed = self._active
        builtins.mouse_button = self.button if self.pressed else None

    def __repr__(self):
        press = 'pressed' if self.pressed else 'not-pressed'
        return "MouseEvent({} at {})".format(press, self.position)

    __str__ = __repr__
