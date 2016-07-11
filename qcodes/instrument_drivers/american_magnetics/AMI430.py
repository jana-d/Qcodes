import time

import numpy as np

from qcodes import Instrument, VisaInstrument
from qcodes.utils.validators import Numbers, Ints, Enum, MultiType

class AMI430(VisaInstrument):
    """
    Driver for the American Magnetics Model 430 magnet power supply programmer
    """
    def __init__(self, name, address,
                 coil_constant, current_rating, current_ramp_limit, persistent_switch=True,
                 terminator='\n', reset=False, **kwargs):
        super().__init__(name, address, **kwargs)

        self._coil_constant = coil_constant
        self._current_rating = current_rating
        self._current_ramp_limit = current_ramp_limit
        self._persistent_switch = persistent_switch

        self._field_rating = coil_constant * current_rating

        self.add_parameter('field',
                           get_cmd='FIELD:MAG?',
                           get_parser=float,
                           set_cmd=self._set_field,
                           units='T',
                           vals=Numbers(-self._field_rating, self._field_rating))

        self.add_function('ramp_to',
                          call_cmd=self._ramp_to,
                          args=[Numbers(-self._field_rating, self._field_rating)])

        self.add_parameter('ramp_rate',
                           get_cmd=self._get_ramp_rate,
                           set_cmd=self._set_ramp_rate,
                           units='T/s',
                           vals=Numbers())

        self.add_parameter('setpoint',
                           get_cmd='FIELD:TARG?',
                           get_parser=float,
                           units='T')

        if persistent_switch:
            self.add_parameter('persistent_switch_heater_enabled',
                               get_cmd='PS?',
                               set_cmd=self._set_persistent_switch_heater,
                               val_mapping={False: '0', True: '1'})

            self.add_parameter('in_persistent_mode',
                               get_cmd='PERS?',
                               val_mapping={False: '0', True: '1'})

        self.add_parameter('is_quenched',
                           get_cmd='QU?',
                           val_mapping={False: '0', True: '1'})

        self.add_function('reset_quench', call_cmd='QU 0')
        self.add_function('set_quenched', call_cmd='QU 1')

        self.add_parameter('ramping_state',
                           get_cmd='STATE?',
                           val_mapping={
                               'ramping': 1,
                               'holding': 2,
                               'paused': 3,
                               'manual up': 4,
                               'manual down': 5,
                               'zeroing current': 6,
                               'quench detected': 7,
                               'at zero current': 8,
                               'heating switch': 9,
                               'cooling switch': 10,
                           })

        self.add_function('get_error', get_cmd='SYST:ERR?')

        self.add_function('ramp', call_cmd='RAMP')
        self.add_function('pause', call_cmd='PAUSE')
        self.add_function('zero', call_cmd='ZERO')

        self.add_function('reset', call_cmd='*RST')

        if reset:
            self.reset()

        self.connect_message()

    def _can_start_ramping(self):
        """
        Check the current state of the magnet to see if we
        can start ramping
        """
        if self.is_quenched():
            return False

        if self._persistent_switch and self.in_persistent_mode():
            return False

        state = self.ramping_state()

        if state == 'ramping':
            if not self._persistent_switch:
                return True
            elif self.persistent_switch_heater_enabled():
                return True
            else:
                return False
        elif state in ['holding', 'paused', 'at zero current']:
            return True
        else:
            return False

        return False

    def _set_field(self, value):
        """ BLocking method to ramp to a certain field """
        if self._can_start_ramping():
            self.pause()

            # Set the ramp target
            self.write('CONF:FIELD:TARG {}'.format(value))

            # If we have a persistent switch, make sure it is enabled
            if self._persistent_switch:
                if not self.persistent_switch_heater_enabled():
                    self.persistent_switch_heater_enabled(True)

            self.ramp()

            time.sleep(0.5)

            # Wait until no longer ramping
            while self.ramping_state() == 'ramping':
                time.sleep(0.3)

            time.sleep(2.0)

            # If we are now holding, it was succesful
            if self.ramping_state() == 'holding':
                self.pause()
            else:
                pass # ramp ended

    def _ramp_to(self, value):
        """ Non-blocking method to ramp to a certain field """
        if self._can_start_ramping():
            self.pause()

            # Set the ramp target
            self.write('CONF:FIELD:TARG {}'.format(value))

            # If we have a persistent switch, make sure it is enabled
            if self._persistent_switch:
                if not self.persistent_switch_heater_enabled():
                    self.persistent_switch_heater_enabled(True)

            self.ramp()

    def _get_ramp_rate(self):
        results = self.ask('RAMP:RATE:FIELD:1?').split(',')

        return float(results[0])

    def _set_ramp_rate(self, rate):
        cmd = 'CONF:RAMP:RATE:FIELD 1,{}{}'.format(rate, self._field_rating)

        self.write(cmd)

    def _set_persistent_switch_heater(self, value):
        """
        This function sets the persistent switch heater state and blocks until
        it has finished either heating or cooling

        value: False/True
        """
        if value:
            self.write('PS 1')

            time.sleep(0.5)

            # Wait until heating is finished
            while self.ramping_state() == 'heating switch':
                time.sleep(0.3)
        else:
            self.write('PS 0')

            time.sleep(0.5)

            # Wait until cooling is finished
            while self.ramping_state() == 'cooling switch':
                time.sleep(0.3)

class AMI430_2D(Instrument):
    """
    Virtual driver for a system of two AMI430 magnet power supplies.

    This driver provides methods that simplify setting fields as vectors.

    TODO:
    -   Offsets?
    """
    def __init__(self, name, magnet_x, magnet_y, **kwargs):
        super().__init__(name, **kwargs)

        self.magnet_x, self.magnet_y = magnet_x, magnet_y

    def _is_within_field_limit(self):
        pass

    def _get_alpha(self):
        pass

    def _set_alpha(self, alpha):
        field = self._get_field()

        alpha = np.radians(alpha)

    def _get_field(self):
        return np.hypot(self.magnet_x.field(), self.magnet_y.field())

    def _set_field(self, field):
        pass