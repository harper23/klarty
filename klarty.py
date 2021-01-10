'''
Copyright (C) 2021 Kevin Grant <planet911@gmx.com>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, see <http://www.gnu.org/licenses/>.
'''

import zlib, struct, time, os, math
from datetime import datetime
from collections import namedtuple
try:
    import usb.core,usb.util
except ImportError as e:
    print("The pyusb module needs to be installed.\n"
          "At command prompt type:\npy -m pip install pyusb\n"
          "Also, the libusb library needs to be on the system path")

# PyUSB needs you to place libusb appropriately:
# https://github.com/libusb/libusb/releases
# For 32-bit python put 32bit libusb-1.0.dll in C:\Windows\SysWOW64
# For 64-bit python put 64bit libusb-1.0.dll in C:\Windows\System32
# Despite the names, System32 is full of 64-bit files and SysWOW64 is full of 32-bit files, nice!

# On Windows PyUSB uses libusb which in-turn uses WinUSB.dll/WinUSB.sys
# The Kingst Windows driver is just a branded wrap of WinUSB.dll, so PyUSB works fine with the Kingst driver.
# No need to use Zadig to switch drivers.

# It can sometimes be useful to use the Kingst OEM software to initialise the LA, then close it and
# experiment using this python code. However, when the Kingst software is closed by normal method, it
# sends a command to de-init the LA. This can be circumnavigated on Windows by first opening the
# 'About' dialog in the Kingst software then force the application to quit from Task Manager.

# This software is based on the work of Florian Schmidt with the changes required to run with available LA firmwares.
# Reference for sigrok-pulseview LA2016 code:
# https://sigrok.org/gitweb/?p=libsigrok.git;a=tree;f=src/hardware/kingst-la2016;hb=HEAD
# and the ezusb firmware upload code:
# https://sigrok.org/gitweb/?p=libsigrok.git;a=blob;f=src/ezusb.c;h=c2d270c4f85164298f626aa7de3826bc8e1ddd80;hb=HEAD

# Test setup:
# This python code was tested with the FX2 firmware extracted from KingstVIS_v3.4.2_linux.tar.gz and the 
# FPGA bitstream extracted from the USB communication packets of KingstVIS_v3.4.3_win.exe
# Software versions archived here:
# https://bitbucket.org/magellanic-clouds/kingst-logic-analyzer-software/src/master/
# The FX2 firmware can be extracted using the python utility linked on this page:
# https://sigrok.org/wiki/Kingst_LA2016
# Hardware version as printed on PCB: LA-2016 v1.3.0

# This python code can setup trigger conditions, run an acquistion which records to the LA SDRAM and then upload that data.
# Stream mode (slower sampling direct to PC) is not implemented.

# **** KNOWN ISSUES ****
# During upload of large captures (tens of megabytes) quite a lot of bytes go missing. Probably
# need to use pre-allocated receive buffer in capture_upload_nbytes()

LAx016_VID = 0x77a1
LAx016_PID = 0x01a2

VENDOR_CTRL_IN  = 0xC0  #USB control transfer types
VENDOR_CTRL_OUT = 0x40

# USB Control Transfers are used for sending commands to the FX2 firmware
# bRequest will be one of these FX2CMD_ bytes:
FX2CMD_KAUTH_x60_d96 = 96               # Used to communicate with the authentication IC 'KAuth' (SOIC8 adjacent to LED)
FX2CMD_FPGA_PROG_x50_d80 = 80           # Begin\end the FPGA bitstream programming mode
FX2CMD_FPGA_ENABLE_x10_d16 = 16         # Control the FPGA RESET pin
FX2CMD_RESET_BULK_TRANSFER_x38_d56 = 56 # Stop any ongoing capture upload from FPGA and flush the FX2 USB bulk endpoints
FX2CMD_START_BULK_TRANSFER_x30_d48 = 48 # Sets FPGA Reg1=1 to begin bulk transfer of the capture data to the FX2
FX2CMD_EEPROM_xA2_d162 = 162            # Access I2C EEPROM AT24C02 (256 bytes). IN transfer to read, OUT to write.
FX2CMD_EE2KAUTH_x68_d104 = 104          # Reads 16 bytes from EEPROM address 0x10 and sends them to the 'KAuth' chip
FX2CMD_FPGA_SPI_x20_d32 = 32            # Access the register bank in the FPGA via SPI bus
# The FPGA has a bank of 8-bit registers for control of FPGA functions. They are accessed
# from the Cypress FX2 using it's SPI master port. Each SPI transfer is two bytes, the first
# being register address and the second a data byte to be written (or 0xFF when reading).
# The address MSbit is 0 for write and 1 for read, so maximum of 128 byte-wide registers possible
# but only 63 (if I can add up correctly) addresses are used.
# 16 and 32 bit registers are byte accessed, with low byte at the low address.
# Read-back is not implemented for most registers (write only).
#
# PC software sends FX2CMD_FPGA_SPI_x20_d32 control OUT transfers to write, IN transfer to read.
# For accessing multiple registers sequentially, just specify the base register address e.g.
# fpga_read(first_register_addr:int, num_byte_regs:int)->bytes
# fpga_write(first_register_addr:int, data_bytes:bytes)
#
# Known FPGA base register addresses to be used with FX2CMD_FPGA_SPI_x20_d32:
FPGA_REG_RUN        = 0x00 # Write / read three regs to control capture start and read capture status. see start/stop_acquistion() and stop_sampling() 
FPGA_REG_UPLOAD     = 0x08 # Write regs 0x08..0x0B 32bit Upload start address, 0x0C..0x0F 32bit byte count
FPGA_REG_SAMPLING   = 0x10 # Write sampling setup, read sampling results. Different usage/registers accessed depending upon read/write.
FPGA_REG_THRESHOLD  = 0x68 # Write regs 0x68..0x69 16bit duty register (see resistor R56), 0x6A..0x6B 16bit duty register (see resistor R79)
FPGA_REG_TRIGGER    = 0x20 # Write regs 0x20..2F ...see set_trigger_config()
FPGA_REG_PWM_EN     = 0x02 # Write reg, one byte, lower two bits enable/disable USER PWM1/PWM2
FPGA_REG_PWM1       = 0x70 # Write regs USER PWM1 0x70..0x73 32bit period register, 0x74..0x77 32bit duty register. 200MHz PWM clock.
FPGA_REG_PWM2       = 0x78 # Write regs USER PWM2 0x78..0x7B 32bit period register, 0x7C..0x7F 32bit duty register. 200MHz PWM clock.


class Chunker:
    """ A naive iterable chunker, probably slow and inefficient
    
    If n_chunks is zero, iteration will stop at the end of data,
    Otherwise, iteration will stop after n_chunks, padding with zeros
    at the end if required.
    """
    def __init__(self, data:bytearray, chunk_sz:int, n_chunks:int=0):
        self._data = data
        self._chunk_sz = chunk_sz
        self._n_chunks = n_chunks
        self.n = 0
    
    def get_chunk(self):
        ch = self._data[(self.n*self._chunk_sz):((self.n+1)*self._chunk_sz)]
        self.n += 1
        if self._n_chunks == 0:
            return ch # don't pad if n_chunks==0
        if ch == None:
            return bytearray(self._chunk_sz) # zero pad
        if len(ch) < self._chunk_sz:
            b = bytearray(self._chunk_sz)
            b[0:len(ch)] = ch # zero pad
            return b
        return ch

    def __iter__(self):
        self.n = 0
        return self

    def __next__(self):
        if self._n_chunks == 0:
            c = self.get_chunk()
            if len(c) == 0:
                raise StopIteration # End of data, not padding
            else:
                return c
        else:
            if self.n < self._n_chunks:
                return self.get_chunk()
            else:
                raise StopIteration # Requested n_chunks completed



class klarty:
    """Kingst Logic Analyser Research Tool for You
    
    A simple set of methods for experimenting with Kingst LA1016 and LA2016 Logic Analysers,
    with the aim of assisting the effort to support these LA's in Sigrok.
    These analysers use the same hardware but a software authentication scheme limits the
    LA1016 to 100MHz. I expect the LA1016 will work at 200MHz in Sigrok PV.
    Minimal error checking, expect exceptions :-)
    """


    def __init__(self):
        self.dev = None
    

    def __del__(self):
        self.disconnect()


    def print_ascii_hex(self, data:bytes, prefix_msg='', postfix_msg=''):
        print(prefix_msg + ''.join('{:02X} '.format(b) for b in data) + postfix_msg)


    def connect(self):
        self.dev = usb.core.find(idVendor=LAx016_VID, idProduct=LAx016_PID)
        if self.dev is None:
            raise ValueError('Device not found')
        self.dev.set_configuration()


    def disconnect(self):
        if self.dev != None:
            usb.util.dispose_resources(self.dev)


    def load_fx2_fw(self, filename:str, apply_fw_patch:bool=False):
        """Load 8051 binary firmware file into the FX2"""

        if os.path.isfile(filename):
            # Looks like an absolute path and filename
            fw_filename = filename
        else:
            # Not an absolute path so assume relative to this Python file
            fw_filename = os.path.join(os.path.dirname(__file__), filename)
            if os.path.isfile(fw_filename) == False:
                raise ValueError('Firmware file not found')

        fw_file_sz = os.stat(fw_filename).st_size
        print(f"Loading FX2 firmware file '{fw_filename}' ({fw_file_sz} bytes)")
        if fw_file_sz < 1000 or fw_file_sz > 20000:
            raise ValueError("Firmware file size doesn't seem correct")

        with open(fw_filename, "rb") as fw:
            fw_bin = bytearray(fw.read()) # Read in whole file

        fw_crc = zlib.crc32(fw_bin) & 0xffffffff
        print(f'Firmware CRC: 0x{fw_crc:08X}')

        if fw_crc == 0x720551a9:
            print('This is recognised as the FX2 firmware extracted from KingstVIS-Linux v3.4.2 (and perhaps other versions too)')
            print('This version can be optionally patched to disable the FPGA bitstream\nlength check (which uses obfuscated length for some interlock scheme)')
            print("If you know the bitstream 'obfuscated length' value for use with FX2CMD_FPGA_PROG_x50_d80, you don't need to patch:")
            if apply_fw_patch:
                print('\tPatch APPLIED')
                fw_bin[0xe30]= 0x02  # Jump over some code
                fw_bin[0xe31]= 0x0e
                fw_bin[0xe32]= 0x81
            else:
                print('\tPatch NOT applied')
        else:
            print('This FX2 firmware is not recognised, it may work but has not been tested on LA1016\\LA2016')
            print('Be aware this firmware probably uses an obfuscated length check on the FPGA bitstream to spoil your fun')

        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, 0xA0, 0xE600, 0, bytes([1]), 100) # FX2 RESET
        fw_chunks = Chunker(fw_bin,1024) # Read firmware in chunks of 1024 bytes, no padding at the end
        offset=0
        for chunk in fw_chunks:
            self.dev.ctrl_transfer(VENDOR_CTRL_OUT, 0xA0, offset, 0, chunk, 100)
            offset += len(chunk)
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, 0xA0, 0xE600, 0, bytes([0]), 100) # FX2 RUN
        print("Loading FX2 complete")


    def load_fpga_fw(self, filename:str):
        """Load bitstream into the Cyclone IV FPGA

        All the bytes from the bitstream file are sent to the FX2 (EP2) which then
        sends them to the FPGA using the SPI connection (well, sync serial really, SCLK, MOSI, no CS),
        Intel/Altera Cyclone Passive Serial configuration method.
        """

        if os.path.isfile(filename):
            # Looks like an absolute path and filename
            fw_filename = filename
        else:
            # Not an absolute path so assume relative to this Python file
            fw_filename = os.path.join(os.path.dirname(__file__), filename)
            if os.path.isfile(fw_filename) == False:
                raise ValueError('Firmware file not found')

        fw_file_sz = os.stat(fw_filename).st_size
        print(f"Loading FPGA bitstream file '{fw_filename}' ({fw_file_sz} bytes)")
        if fw_file_sz < 160e3 or fw_file_sz > 200e3:
            raise ValueError("Bitstream file size doesn't seem correct")

        with open(fw_filename, "rb") as fw:
            fw_bin = bytearray(fw.read()) # Read in whole file

        fw_crc = zlib.crc32(fw_bin) & 0xffffffff
        print(f'Firmware CRC: 0x{fw_crc:08X}')

        # The Kingst FX2 firmware requires notification of FPGA bitstream length prior to loading (FX2CMD_FPGA_PROG_x50_d80 command).
        # However, it is obfuscated for some interlock scheme, a number close to, but not exactly the true file length.
        # The obfuscated length is known for some bitstreams (as seen in USB control packets)
        # The LA seems to work if a not-too-different number is used for obfuscated length.
        # Any number seems to work if the FX2 firmwae has patch applied.
        bitstream_length_obfuscated = fw_file_sz # Just a default number which will be wrong (true file size)

        if fw_crc == 0x31a1cffe:
            if fw_file_sz != 0x2d000:
                raise ValueError(f'Bitstream file length is 0x{fw_file_sz:x} which is not 0x2d000 as expected for this file')
            print('This file is recognised as the padded bitstream seen in USB packets between KingstVIS-Win v3.4.2 and the FX2')
            # 0x2b8ba is the known obfuscated length for this bitstream
            bitstream_length_obfuscated = 0x2b8ba
        else:
            print('This FPGA bitstream is not recognised, it may work but has not been tested on LA1016\\LA2016')
            print('Be aware the FX2 firmware might have an obfuscated length check on the FPGA bitstream to spoil your fun')
            print('fbitstream_length_obfuscated has been set to the default, true bitstream length ({bitstream_length_obfuscated} bytes)')
        
        self.fpga_hold_in_reset()

        # Inform the FX2 of FPGA bitstream length in bytes, as little endian 32-bit number
        # If the FX2 firmware has been patched (see load_fx2_fw()) this length can be anything.
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_FPGA_PROG_x50_d80, 0, 0, struct.pack('<L', bitstream_length_obfuscated), 100)

        OUT_EP_FOR_BITSTREAM = 2 # FX2 OUT endpoint for FPGA bitstream
        PADDED_LENGTH = 0x2d000 # Or perhaps the rule is to always end with 4096 zeros, rather than fixed length. To be tested.
        CHUNK_SIZE = 4096
        CHUNK_TIMEOUT_MS = 1000

        n_chunks = math.ceil(PADDED_LENGTH / CHUNK_SIZE)
        fw_chunks = Chunker(fw_bin,CHUNK_SIZE,n_chunks) # Pad with zeros to PADDED_LENGTH
        for chunk in fw_chunks:
            self.dev.write(OUT_EP_FOR_BITSTREAM, chunk, CHUNK_TIMEOUT_MS)

        # Check FX2 is happy
        resp = self.dev.ctrl_transfer(VENDOR_CTRL_IN, FX2CMD_FPGA_PROG_x50_d80, 0, 0, 1, 100) # Expected reponse 1 byte == 0x00
        if resp[0] == 0:
            time.sleep(.1)
            self.fpga_release_reset_and_run()
            time.sleep(.1)
            print("Loading FPGA complete")
        else:
            print(f'Response to FX2CMD_FPGA_PROG_x50_d80 IN request should have been 0x00 but it was 0x{resp[0]:02X}')
            print("Loading FPGA **FAILED**")
    

    def fpga_hold_in_reset(self):
        """ Set FPGA RESET line high """
        fpga_enable = False
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_FPGA_ENABLE_x10_d16, int(fpga_enable), 0, None, 100)


    def fpga_release_reset_and_run(self):
        """ Set FPGA RESET line low """
        fpga_enable = True
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_FPGA_ENABLE_x10_d16, int(fpga_enable), 0, None, 100)


    def eeprom_read(self, address, n) -> bytes:
        """Read 'n' bytes of the 24C02 EEPROM starting at 'address'

        256 bytes of EEPROM available
        Kingst software reads
        4 bytes starting at 0x20:  lax.eeprom_read(0x20, 4)
        8 bytes starting at 0x08:  lax.eeprom_read(0x08, 8)        
        """

        return self.dev.ctrl_transfer(VENDOR_CTRL_IN, FX2CMD_EEPROM_xA2_d162, address, 0, n, 100)


    def eeprom_write(self, address, data:bytes):
        """Write bytes to the 24C02 EEPROM starting at 'address'

        256 bytes of EEPROM available
        Example:
        lax.eeprom_write(0x30, bytes([0x01, 0x02, 0x03]))
        """

        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_EEPROM_xA2_d162, address, 0, data, 100)


    def kauth_read_serial(self):
        """Read board serial number from the 'Kingst Authentication' chip

        There is an authentication IC in SOIC8 package adjacent to the LED. Let's call it the 'KAuth' chip.
        It communicates via pin 3, bi-directional open-drain, UART protocol 8E1 (even parity) at 12900 baud
        Data bytes sent/received using command FX2CMD_KAUTH_x60_d96 will be seen on KAUTH chip pin 3.

        Data format for send and receive is
        START_BYTE_0xA3    NUM_BYTES_IN_PACKET    PACKET_BYTES...

        This method reads the board serial number, as shown in KingstVIS 'about' dialog
        """

        # Afer the 0xA3 start byte and 0x01 byte count, the remaining packet byte 0xCA is probably the ID command
        CMD_READ_KAUTH_ID = bytes([0xa3, 0x01, 0xca])
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_KAUTH_x60_d96, 0, 0, CMD_READ_KAUTH_ID, 100)
        time.sleep(0.5)
        resp = self.dev.ctrl_transfer( VENDOR_CTRL_IN , FX2CMD_KAUTH_x60_d96, 0, 0, 20, 100)
        self.print_ascii_hex(resp)
    

    def kauth_authenticate(self):
        """Kingst Authentication with the 'KAuth' chip

        There is an authentication IC in SOIC8 package adjacent to the LED. Let's call it the 'KAuth' chip.
        It communicates via pin 3, bi-directional open-drain, UART protocol 8E1 (even parity) at 12900 baud
        Data bytes sent/received using command FX2CMD_KAUTH_x60_d96 will be seen on KAUTH chip pin 3.

        Data format for send and receive is
        START_BYTE_0xA3    NUM_BYTES_IN_PACKET    PACKET_BYTES...

        This method provides a challenge and reads secure authentication code response.
        Note the response changes every time, even if challenge is the same. LFSR type rolling code perhaps.
        Not a useful function but noted here for documentation purposes.
        """

        # After the 0xA3 start byte and 0x09 byte count, the remaining packet bytes are likely a random or coded challenge.
        CMD_READ_KAUTH_SECURE_CODE = bytes([0xa3, 0x09, 0xc9, 0xf4, 0x32, 0x4c, 0x4d, 0xee, 0xab, 0xa0, 0xdd]) 
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_KAUTH_x60_d96, 0, 0, CMD_READ_KAUTH_SECURE_CODE, 100)
        time.sleep(0.5)
        resp = self.dev.ctrl_transfer( VENDOR_CTRL_IN , FX2CMD_KAUTH_x60_d96, 0, 0, 20, 100)
        self.print_ascii_hex(resp)


    def eeprom_to_kauth(self):
        """Copy EEPROM bytes to Kingst Authentication 'KAuth' chip

        This command causes the FX2 to read 16 bytes I2C EEPROM from address 0x10 and
        send those bytes to the KAuth chip with uart sequence: A3 11 CB <EEPROM Bytes>
        I expected the second byte of that sequence to be 0x10. Hmmm.
        This might be a factory command for one time initialisation of the KAuth chip.
        Not a useful function but noted here for documentation purposes.
        """
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_EE2KAUTH_x68_d104, 0, 0, None, 100)
        time.sleep(0.5)


    def fpga_read(self, address:int, n:int) -> bytes:
        """Read 'n' byte registers of the FPGA registers starting at 'address'

        FX2 accesses FPGA control registers over the SPI bus.
        The registers are accessed as individual byte registers.
        Address is in range 0..127, although only some addresses of that range will
        have a register implemented.        
        """

        if address < 0 or address > 127:
            raise ValueError("FPGA register address out of range")
        address |= 0x80 #Set the MSbit for read access
        return self.dev.ctrl_transfer(VENDOR_CTRL_IN, FX2CMD_FPGA_SPI_x20_d32, address, 0, n, 100)


    def fpga_write(self, address:int, data:bytes):
        """Write bytes to the FPGA starting at 'address'

        FX2 accesses FPGA control registers over the SPI bus.
        The registers are accessed as individual byte registers.
        Address is in range 0..127, although only some addresses of that range will
        have a register implemented.
        """

        if address < 0 or address > 127:
            raise ValueError("FPGA register address out of range")
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_FPGA_SPI_x20_d32, address, 0, data, 100)


    def user_pwm_enable(self, channel1:bool, channel2:bool):
        """Enable/disable PWM channels

        The FPGA has two programmable PWM outputs.
        """

        en=0
        if channel1:
            en+=1
        if channel2:
            en+=2
        self.fpga_write(FPGA_REG_PWM_EN, bytes([en])) # 0x00=PWMs OFF, 0x03=PWMs on


    def user_pwm_settings(self, channel:int, freq:float, duty:float):
        """Setup PWM channel 1 or 2

        The FPGA has two programmable PWM outputs which use 32bit
        period and duty comparator registers. The PWM counters
        are clocked at 200MHz.
        """

        PWM_CLOCK = 200e6
        period = int((PWM_CLOCK / freq) + 0.5)
        duty = int((period * duty / 100.0) + 0.5)
        p=struct.pack('<LL', period, duty)
        #self.print_ascii_hex(p)
        if channel == 1:
            self.fpga_write(FPGA_REG_PWM1, p)
        elif channel == 2:
            self.fpga_write(FPGA_REG_PWM2, p)
        else:
            raise ValueError("Invalid user PWM channel (must be 1 or 2)")
        print(f'PWM channel {channel}:')
        print(f'Requested output frequency={freq:#.8g}, duty={duty:#.8g}%')
        print(f'PWM clock is {PWM_CLOCK/1e6}MHz, 32bit period reg=0x{period:08X}, 32bit duty reg=0x{duty:08X}')
        print(f'Therefore, actual output frequency={PWM_CLOCK/period:#.8g}Hz, duty={100*duty/period:#.8g}%')


    def threshold(self, volts:float):
        """Set threshold for all 16 logic inputs

        The FPGA has two programmable PWM outputs which feed a DAC that
        is used to adjust input offset. The DAC changes the input
        swing around the fixed FPGA input threshold.
        The two PWM outputs can be seen on R79 and R56 respectvely.
        Frequency is fixed at 100kHz and duty is varied.
        The R79 PWM uses just three settings.
        The R56 PWM varies with required threshold and its behaviour
        also changes depending on the setting of R79 PWM.
        """

        if volts > 4.0 or volts < -4.0:
            raise ValueError("Invalid threshold voltage")
        duty_R79 = 0
        if volts >= 2.9:
            duty_R79 = 0 #OFF, 0V
            duty_R56 = 302 * volts - 363
        elif volts <= -0.4:
            duty_R79 = 0x02D7 #72% duty
            duty_R56 = 302 * volts + 1090
        else:
            duty_R79 = 0x00F2 #25% duty
            duty_R56 = 302 * volts + 121
        if duty_R56 < 10:
            duty_R56 = 10 # Catch overflow (Kingst Sw dude, please add this fix to KingstViz)
        if duty_R56 > 1100:
            duty_R56 = 1100 # Sensible limit
        p=struct.pack('<HH', int(duty_R56+0.5), int(duty_R79))
        self.print_ascii_hex(p,'Threshold PWMs register values: ')
        self.fpga_write(FPGA_REG_THRESHOLD, p)


    def get_run_state(self) -> int:
        """Read FPGA run state register 16bits

        The 16bit run state is FPGA registers 1[hi-byte] and 0[lo-byte]
        The run_state values in order are:
        0x85E2: Pre-sampling (for samples before trigger position, e.g. half of samples when set at 50% capture ratio)
        0x85EA: Waiting for trigger
        0x85EE: Running
        0x85ED: Done

        reg0=
        written with 0x03 to begin capture
        bit0  1=Done
        bit1  1=Writing to SDRAM
        bit2  1=Triggered (running)
        bit3  0=pre-trigger sampling  1=post-trigger sampling
        TODO  what are other bits? Not required anyway it seems.       

        reg1=
        bit0  write 1 to start bulk capture data transfer from SDRAM to FX2
        TODO  what are other bits?  Not required anyway it seems.        
        """

        state = self.fpga_read(FPGA_REG_RUN, 2)
        return int(state[0] + state[1]*256)


    def reset_bulk(self):
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_RESET_BULK_TRANSFER_x38_d56, 0, 0, None, 100)


    def start_acquisition(self):
        self.fpga_write(FPGA_REG_RUN, bytes([0x03]))


    def stop_acquisition(self):
        #These bytes are written seperately by OEM software, so doing the same here.
        self.fpga_write(FPGA_REG_RUN + 1, bytes([1]))  #Write Reg1=1 (which is also done automatically by the FX2CMD_START_BULK_TRANSFER_x30_d48)
        self.fpga_write(FPGA_REG_RUN, bytes([0x00]))   #Write Reg0=0


    def stop_sampling(self):
        self.fpga_write(FPGA_REG_RUN + 3, bytes([0])) #within sigrok la2016_setup_acquisition()


    def has_triggered(self) -> bool:
        if self.get_run_state() & 0x04:
            return True
        return False
    

    def set_sample_config(self, sample_rate, n_samples, capture_ratio_percent):
        """Setup sampling parameters for next capture

        capture_ratio_percent controls what proportion of n_samples is captured
        before the trigger event.
        """

        # clock_divisor
        MAX_SAMPLE_RATE = 200e6
        sample_clock_divisor = int ((MAX_SAMPLE_RATE / sample_rate) + 0.5)
        if sample_clock_divisor > 0xffff:
            sample_clock_divisor = 0xffff
        self.curr_samplerate = MAX_SAMPLE_RATE / sample_clock_divisor
        # capture_ratio_percent determines number of samples stored prior to trigger event
        SAMPLE_MEM_SZ_BYTES = 128 * 1024 * 1024
        pre_trigger_samples = int((capture_ratio_percent * n_samples) / 100)
        pre_trigger_mem_bytes = int((capture_ratio_percent * SAMPLE_MEM_SZ_BYTES) / 100)
        pre_trigger_mem_bytes = pre_trigger_mem_bytes & 0x00FFFFFF00 #Clear low byte
        p=struct.pack('<LBLLHB', int(n_samples), 0, pre_trigger_samples, pre_trigger_mem_bytes, sample_clock_divisor,0)
        print(f'\nSample config: {int(n_samples)} samples at {200e3/sample_clock_divisor}kHz rate with {capture_ratio_percent}% pre-trigger samples.')
        self.print_ascii_hex(p,'Sampling Config FPGA Register Values:')
        self.fpga_write(FPGA_REG_SAMPLING, p)


    def set_trigger_config(self, verbose=True):
        """Setup channels and triggers for next capture

        From FPGA reg 0x20 onwards we have:
        uint32  channel_enable
        uint32  channel_trigger_enable
        uint32  trigger_type 0=edge 1=level
        uint32  trigger_sense 0=LOW/RISING  1=HIGH/FALLING
        For these 16 bit Logic Analysers the upper 16bits of above are always zero.
        """

        channel_enable = 0x0000FFFF  # Record all 16 channels
        trigger_enable = 0x00000000  # LA trigger = logical AND of all enabled channel triggers
        trigger_type   = 0x00000000  # 0=edge 1=level
        trigger_sense  = 0x00000000  # 0=LOW/RISING  1=HIGH/FALLING

        p=struct.pack('<LLLL', channel_enable, trigger_enable, trigger_type, trigger_sense)
        self.fpga_write(FPGA_REG_TRIGGER, p)

        if verbose == False:
            return

        print('\nCH15   TRIGGER    CH0')
        print(f'   {channel_enable:016b} Enabled Channels')
        print(f'   {trigger_enable:016b} Trigger Enable')
        print(f'   {trigger_type:016b} Trigger Type 0=EDGE 1=LEVEL')
        print(f'   {trigger_sense:016b} Trigger Sense 0=LOW/RISING  1=HIGH/FALLING')
        self.print_ascii_hex(p,'Trigger Config FPGA Register Values:')


    def capture_info(self, verbose=True):
        """Retrieve capture information

        Retrieve information on the last completed capture from the FPGA registers.
        Each data sample ("Repetition Packet") is a 16-bit input state plus 8 bit repetition count
        Read 12 bytes from the FPGA registers starting at address FPGA_REG_SAMPLING to get:
        32bit n_rep_packets
        32bit n_rep_packets_before_trigger
        32bit write_pos
        """

        resp = self.fpga_read(FPGA_REG_SAMPLING, 12)        
        CaptureInfo = namedtuple("CaptureInformation", ["n_rep_packets", "n_rep_packets_before_trigger", "write_pos"])
        ci = CaptureInfo(*struct.unpack('<LLL', resp))
        if verbose:
            print('\nCapture info:')
            self.print_ascii_hex(resp, 'FPGA read bytes:')
            print(f'n_rep_packets: {ci.n_rep_packets}\nn_rep_packets_before_trigger: {ci.n_rep_packets_before_trigger}\nwrite_pos: {ci.write_pos}')
            if ci.n_rep_packets % 5:
                print(f'WARNING: number of packets is not multiples of 5 as expected: {ci.n_rep_packets}')
        return ci

    
    def capture_upload(self, n_rep_packets, write_pos):
        """Retrieve captured data

        Retrieve data from SDRAM via FX2 FIFO port to FPGA connection.
        USB bulk HS is 512 bytes per packet. IN endpoint number is 0x86.
        Each data sample ("Repetition Packet") is a 16-bit input state plus 8 bit repetition count
        Each transfer packet is 5 Repetition Packets plus an 8 bit sequence number
        """

        SIZEOF_TRANSFER_PKT = ((2+1)*5)+1
        n_transfer_packets_to_read = int(n_rep_packets / 5)
        n_bytes_to_read = n_transfer_packets_to_read * SIZEOF_TRANSFER_PKT
        self.capture_upload_nbytes(n_bytes_to_read, write_pos)


    def capture_upload_nbytes(self, n_bytes:int, write_pos:int):
        """Retrieve n_bytes of data from SDRAM, starting at (write_pos - n_bytes)
        
        n_bytes is approximate to nearest 4 bytes. Seems to be chunk size of 4 bytes.

        Note that if no triggers are enabled, then upload of data will always
        start from address 0 up until address == write_pos.
        If a trigger is enabled and the LA has to enter the 'waiting for trigger' state
        then the upload will start from a higher address (unless it happens to have
        wrapped through memory, but you get the idea).
        """

        MAX_MEM_ADDR_128MB = (128*1024*1024)-1
        n_bytes = int(n_bytes)
        write_pos = int(write_pos)
        if write_pos < 0 or write_pos > MAX_MEM_ADDR_128MB:
            raise ValueError('Memory address pointer not in expected range')
        if n_bytes == 0:
            print('Upload of 0 bytes requested, ignoring.')
            return
        if n_bytes < 0 or n_bytes > MAX_MEM_ADDR_128MB:
            raise ValueError('Number of bytes to retrieve not in expected range')
        if n_bytes <= write_pos:
            start_pos = int(write_pos - n_bytes)
        else:
            # Handle memory address wrap, eg write_pos = 1 and uploading 1MB
            # Assuming memory is treated as circular buffer, which it
            # must be to handle pre-trigger capture (I think)
            start_pos = int(write_pos + MAX_MEM_ADDR_128MB + 1 - n_bytes)
        
        print(f'\nReading {n_bytes} bytes starting from SDRAM address 0x{start_pos:X}')
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_RESET_BULK_TRANSFER_x38_d56, 0, 0, None, 100)
        p= struct.pack('<LL', start_pos, n_bytes)
        self.print_ascii_hex(p, 'Upload FPGA Register Values: ')
        self.fpga_write(FPGA_REG_UPLOAD, p) #Tell FPGA the start position and n_bytes for this bulk read
        #time.sleep(0.02) # Just in case FPGA needs a few ms to prepare??..unlikely.
        self.dev.ctrl_transfer(VENDOR_CTRL_OUT, FX2CMD_START_BULK_TRANSFER_x30_d48, 0, 0, None, 100)
        ENDPOINT_BULK_IN = 0x86
        data = self.dev.read(ENDPOINT_BULK_IN, n_bytes)  #TODO this is losing bytes in large transfers >20MB, try pre-allocating storage buffer
        self.capture_data_to_file(data)
        
        
    def capture_data_to_file(self, data:bytes):
        fname = datetime.now().isoformat()
        fname = fname[:19].replace(':','-') + '.bin'
        fpathname = os.path.join('captures',fname)
        print(f'Saving {len(data)} bytes of data to .\\{fpathname}')
        fpathname = os.path.join(os.path.dirname(__file__), fpathname)
        os.makedirs(os.path.dirname(fpathname), exist_ok=True)
        with open(fpathname, "wb") as f:
            f.write(data)

#--------------------------
if __name__ == "__main__":
    print('See other files which use this code, this file doesn\'t run alone')
