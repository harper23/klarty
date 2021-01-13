from klarty import klarty

'''
These are the values OEM software writes to FPGA
register 0x68 (onwards) for stated thresholds.
VBIAS is the resulting DAC output voltage applied
to the input networks. VBIAS measured at
R23 (end nearest PCB edge)

The PWM outputs can be seen on R79 and R56.
Frequency is fixed at 100kHz and duty is varied.
The R79 PWM uses just three settings.
The R56 PWM varies with required threshold and behaviour
also changes depending on the setting of R79 PWM.

Threshold Setting   VBIAS      HEX (reg 0x69 0x68 0x6B 0x6A)
5V TTL   (1.58V)    -0.3939    0258 00F2
5V CMOS  (2.50V)    -1.3225    036E 00F2
3V3 CMOS (1.65V)    -0.4640    026D 00F2
3V0 CMOS (1.50V)    -0.3103    023F 00F2
2V5 CMOS (1.25V)    -0.0597    01F4 00F2
1V8 CMOS (0.90V)     0.2976    0189 00F2
1V5 CMOS (0.75V)     0.4479    015C 00F2
1V2 CMOS (0.60V)     0.5982    012F 00F2
0V9 CMOS (0.45V)     0.7521    0101 00F2

Custom     4V0      -2.822     0350 0000   R79 PWM signal = 0x0000 = OFF
Custom     3V3      -2.126     027C 0000
Custom     3V0      -1.822     0221 0000
Custom     2V91     -1.732     0206 0000
Custom     2V9      -1.722     0302 0000

Custom     2V8      -1.626     03C9 00F2   R79 PWM signal = 0x00F2 = 25% duty
Custom     2V0      -0.818     02D7 00F2
Custom     1V0       0.194     01A8 00F2        
Custom     0V0       1.200     0079 00F2
Custom    -0V39      1.600     0003 00F2

Custom    -0V4       1.604     03C9 02D7   R79 PWM signal = 0x02D7 = 72% duty
Custom    -0V5       1.705     03AB 02D7
Custom    -1V0       2.212     0313 02D7
Custom    -2V0       3.225     01E4 02D7
Custom    -3V0       4.236     00B5 02D7
Custom    -3V5       4.740     001E 02D7
Custom    -4V0       1.825     FF87 02D7   Unintended rollover in Kingst software, threshold gone awry (fixed in Python code here)

So, the above data is fitted with three seperate straight line fits
'''

dev = klarty()
dev.connect()
dev.threshold(1.65)

'''
volts = 0
while volts <= 4.0:
    dev.threshold(volts)
    print(f'\nThreshold= {volts}V')
    input("Press Enter to continue...")
    volts += .05
'''
